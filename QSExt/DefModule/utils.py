# -*- coding: utf-8 -*-
"""DefModule 工具函数 —— 合并自原策略定义工具模块（超集）"""

import fnmatch
import importlib
import json
import os
import pkgutil
import types


def expand_glob(pattern: str) -> list:
    """展开 glob 模式为完整模块路径列表。

    使用 pkgutil.iter_modules 遍历包下模块（不扫文件系统）。

    模式格式: 'package.subpkg.glob_pattern'
    例如: 'QSExt.DefModule.examples.stock_cn_factor_*'
      → ['QSExt.DefModule.examples.stock_cn_factor_example1', ...]

    不含通配符时原样返回。
    """
    parts = pattern.split(".")
    for i, p in enumerate(parts):
        if "*" in p or "?" in p:
            pkg_name = ".".join(parts[:i])
            glob_pat = p
            break
    else:
        return [pattern]  # 不含通配符

    pkg = importlib.import_module(pkg_name)
    result = []
    for info in pkgutil.iter_modules(pkg.__path__, prefix=pkg_name + "."):
        stem = info.name.rsplit(".", 1)[-1]
        if fnmatch.fnmatch(stem, glob_pat):
            result.append(info.name)
    return sorted(result)


def load_notebook_as_module(path: str) -> types.ModuleType:
    """加载 .ipynb 文件作为定义模块。

    定义协议：在 notebook 中对核心 cell 打 ``node-def`` 或 ``strategy-def`` tag。
    框架找到最后一个带此 tag 的 cell，执行该 cell 及其之前的所有 code cell。
    若执行失败则回退为执行所有 code cell。

    从最终命名空间中收集所有产出对象，自动通过算子类型区分因子和策略。

    Args:
        path: .ipynb 文件路径（绝对或相对）

    Returns:
        types.ModuleType 对象，包含:
        - __file__: notebook 路径
        - __FACTOR_META__ / __STRATEGY_META__: 元信息字典（若 notebook 中定义了）
        - defNode / defFactor / defStrategy: 若 notebook 中定义了入口函数则保留

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: notebook 中无 code cell 或执行失败
    """
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Notebook 文件不存在: {path}")

    with open(path, encoding="utf-8") as f:
        nb = json.load(f)

    code_cells = [c for c in nb.get("cells", []) if c.get("cell_type") == "code"]
    if not code_cells:
        raise ValueError(f"Notebook 中没有 code cell: {path}")

    # 找最后一个带 node-def 或 strategy-def tag 的 cell
    last_tagged_idx = -1
    for i, cell in enumerate(code_cells):
        tags = cell.get("metadata", {}).get("tags", [])
        if "node-def" in tags or "strategy-def" in tags:
            last_tagged_idx = i

    def _exec_cells(cells):
        ns = {"__name__": "__def_module__", "__file__": path}
        for cell in cells:
            source = "".join(cell["source"])
            if source.strip():
                exec(compile(source, path, "exec"), ns)
        return ns

    # 优先：执行到最后一个 tagged cell 为止
    if last_tagged_idx >= 0:
        cells_to_run = code_cells[: last_tagged_idx + 1]
        try:
            namespace = _exec_cells(cells_to_run)
        except Exception:
            namespace = _exec_cells(code_cells)  # 回退：执行全部
    else:
        namespace = _exec_cells(code_cells)

    # 构造 module 对象
    mod = types.ModuleType(f"_notebook_def:{os.path.basename(path)}")
    mod.__file__ = path

    # 将命名空间中的对象复制到 module（跳过内部名称）
    for k, v in namespace.items():
        if k.startswith("__") and k not in ("__FACTOR_META__", "__STRATEGY_META__"):
            continue
        setattr(mod, k, v)

    # 收集由 MakeAccount / MakeStrategy 算子产出的策略因子
    from QuantStudio.BackTest.Strategy.Strategy import MakeAccount
    strategy_objects = []
    for val in namespace.values():
        if hasattr(val, '_Operator') and isinstance(val._Operator, MakeAccount):
            strategy_objects.append(val)
        elif hasattr(val, '_QSArgs') and hasattr(val._QSArgs, 'Operator') and isinstance(val._QSArgs.Operator, MakeAccount):
            strategy_objects.append(val)
    mod.StrategyObjects = strategy_objects

    return mod
