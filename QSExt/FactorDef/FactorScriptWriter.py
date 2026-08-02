# -*- coding: utf-8 -*-
"""因子定义脚本生成器

将 ``Factor`` 对象列表生成为可执行的 FactorDef 脚本。
生成的脚本采用"重建算子 → 重建描述子 → 调用算子"方式重建因子对象，
不内联展开表达式，支持所有算子类型（标准算子、自定义 calculate 算子）。

典型用法::

    from QSExt.FactorDef.FactorScriptWriter import generate_script

    meta = {
        "TargetTable": "stock_cn_factor_mining",
        "IDType": "A股",
        "Author": "MiningStudio",
    }
    generate_script(factors=[factor1, factor2], meta=meta,
                     output_path="~/FactorDef/Scripts/my_factors.py")
"""

import json
import os
from typing import Dict, List, Optional, Set

from QuantStudio.Factor.FactorOperation import DerivativeFactor
from QuantStudio.Factor.Factor import DataFactor, Factor


# ============================================================================
#  因子树展平
# ============================================================================

def _flatten(factor: Factor) -> list:
    """将因子树展平为 PN (Polish Notation) 序列

    算子节点在前，终端节点在后。
    """
    if not factor.Descriptors:
        return [factor]
    return [factor] + sum((_flatten(d) for d in factor.Descriptors), start=[])


# ============================================================================
#  PN → 代码生成
# ============================================================================

def _pn_to_code(pn: list) -> tuple:
    """将 PN 序列转换为 FactorDef 脚本代码行

    每个节点:
    - DerivativeFactor: 其 Operator 用 ``FactorOperator.deserialize()`` 重建
    - DataFactor(Value): 生成 DataFactor(data=..., args={...})
    - DataFactor(terminal): 生成 ``fdi.FDB[...].getTable(...).getFactor(...)``

    Returns:
        (code_lines, extra_imports)
    """
    if not pn:
        return ["# 空表达式"], {}

    extra_imports: Dict[str, set] = {}
    var_counter = [0]

    def _add_import(op_data: dict):
        class_path = op_data["__class__"]
        module, class_name = class_path.rsplit(".", 1)
        extra_imports.setdefault(module, set()).add(class_name)

    def _new_var(prefix: str) -> str:
        var_counter[0] += 1
        return f"_{prefix}_{var_counter[0]}"

    stack = []
    lines = []

    for node in reversed(pn):
        if isinstance(node, DerivativeFactor):
            op_data = node.Operator.serialize()
            _add_import(op_data)
            arity = len(node.Descriptors)

            operands = []
            while stack and len(operands) < arity:
                operands.append(stack.pop())
            operands.reverse()

            op_var = _new_var("op")
            result_var = _new_var("factor")

            lines.append(
                f"    {op_var} = _deserialize_op({json.dumps(op_data, ensure_ascii=False)})"
            )
            args_str = ", ".join(v[0] for v in operands)
            lines.append(f"    {result_var} = {op_var}({args_str})")

            stack.append((result_var, "var"))
        elif isinstance(node, DataFactor):
            if node._DataContent == "Value":
                value = node._Data
                if not isinstance(value, (int, float, str)):
                    value = str(value)
                var = _new_var("c")
                lines.append(
                    f'    {var} = DataFactor(data={repr(value)}, args={{"Name": {repr(str(value))}}})'
                )
                stack.append((var, "constant"))
            else:
                # 终端因子：尝试从属性获取来源信息
                ft = getattr(node, "_FactorTable", None)
                fdb = ft.FactorDB if ft else None
                table_name = ft.Name if ft else ""
                conn_id = fdb.Name if fdb else getattr(fdb, "_QSArgs", {}).get("Name", "")
                name = node.Name

                var = _new_var("t")
                if conn_id and table_name:
                    lines.append(
                        f'    {var} = fdi.FDB["{conn_id}"].getTable("{table_name}").getFactor("{name}")'
                    )
                else:
                    lines.append(f'    {var} = fdi.Factors["{name}"]')
                stack.append((var, "terminal"))

    return lines, extra_imports


# ============================================================================
#  公开 API
# ============================================================================

def generate_script(
    factors: List[Factor],
    meta: dict,
    output_path: str,
    factor_names: Optional[List[str]] = None,
) -> str:
    """将因子对象列表生成 FactorDef 脚本并写入文件

    Args:
        factors: Factor 对象列表
        meta: ``__FACTOR_META__`` 字典（不要包含 ``DefScriptPath``, 会自动添加）
        output_path: 输出 .py 文件路径
        factor_names: 因子名称列表，长度需与 factors 一致。None 则使用因子自带的 Name

    Returns:
        输出文件的绝对路径
    """
    if factor_names is None:
        factor_names = [f.Name for f in factors]
    elif len(factor_names) != len(factors):
        raise ValueError(f"factor_names 长度 ({len(factor_names)}) 与 factors ({len(factors)}) 不匹配")

    # 收集所有 import
    all_imports: Dict[str, Set[str]] = {}
    all_pns = []
    for factor in factors:
        pn = _flatten(factor)
        all_pns.append(pn)
        _, imports = _pn_to_code(pn)
        for mod, classes in imports.items():
            all_imports.setdefault(mod, set()).update(classes)

    # 元信息
    meta_out = dict(meta)
    meta_out["DefScriptPath"] = "__file__"

    # 构建脚本
    lines = [
        '# -*- coding: utf-8 -*-',
        '"""自动生成的因子定义脚本',
        '',
        f'  因子数: {len(factors)}',
        '"""',
        '',
        'from typing import List',
        '',
        'from QuantStudio.Factor.Factor import Factor, DataFactor',
        'from QuantStudio.Factor.BasicOperator import rename',
        'from QuantStudio.Factor.FactorOperation import FactorOperator',
        'from QSExt.FactorDef.FactorDefContent import FactorDefInput',
        '',
        '_deserialize_op = FactorOperator.deserialize',
        '',
    ]

    for mod in sorted(all_imports):
        for cls in sorted(all_imports[mod]):
            lines.append(f"from {mod} import {cls}")
    if all_imports:
        lines.append('')

    lines.append('')
    lines.append('__FACTOR_META__ = ' + json.dumps(meta_out, ensure_ascii=False, indent=4))
    lines.append('')
    lines.append('')
    lines.append('def defFactor(fdi: FactorDefInput) -> List[Factor]:')
    lines.append('    """自动生成的因子定义"""')
    lines.append('    Factors = []')
    lines.append('')

    for i, (factor, pn) in enumerate(zip(factors, all_pns)):
        name = factor_names[i]
        lines.append(f'    # 因子 {i+1}: {name}')
        code_lines, _ = _pn_to_code(pn)
        lines.extend(code_lines)
        # 最后一个 result_var 是根因子
        last_line = code_lines[-1]
        root_var = last_line.split(" = ")[0].strip()
        lines.append(
            f'    Factors.append(rename({root_var}, factor_name="{name}", '
            f'factor_args={{"Meta": {{"Description": "自动生成的因子, 名称={name}"}}}}))'
        )
        lines.append('')

    lines.append('    return Factors')
    lines.append('')

    script = "\n".join(lines)

    output_path = os.path.expanduser(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(script)

    return os.path.abspath(output_path)
