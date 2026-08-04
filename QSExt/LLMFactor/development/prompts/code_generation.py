# -*- coding: utf-8 -*-
"""代码生成 Prompt 模板。

包含 Step 1 代码生成阶段所需的 prompt 模板：
  - SYSTEM_PROMPT: 系统角色设定
  - build_generation_prompt(): 构建完整的代码生成 prompt
  - QuantStudio API 参考文本

prompt 结构：
    系统角色 + 假设文档 + API 参考 + 经验组件 + 参考代码 + 约束
"""
from __future__ import annotations

import json
from typing import Optional


# ============================================================
# 系统 Prompt
# ============================================================

SYSTEM_PROMPT = """你是一个 QuantStudio 量化因子开发专家。你的任务是根据假设文档生成符合 FactorDef 框架规范的因子定义代码。

你必须严格遵循以下规则：
1. 生成的代码必须能直接运行，无语法错误
2. 严格遵循 FactorDef 规范（defFactor 单参数签名、__FACTOR_META__ 元数据）
3. A 股因子必须同时覆盖主板和科创板，使用 fo.Where + fo.NotNull 合并
4. 超参数必须用 args.get("param_name", default_value) 格式标注
5. 不要捏造表名或字段名，只使用 JYDB 数据字典中真实存在的表和字段
6. 输出必须包含三部分：===FACTOR_CODE===、===SEARCH_SPACE===、===METADATA==="""


# ============================================================
# QuantStudio API 参考
# ============================================================

QUANTSTUDIO_API_REFERENCE = """## FactorDef 框架 API 参考

### 必需的 import（严格使用以下路径，不要猜测其他路径）
```python
from typing import List
import numpy as np

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput
```

### 因子定义模式（FactorDef 规范）
```python
__FACTOR_META__ = {
    "TargetTable": "stock_cn_factor_xxx",    # 输出表名，固定前缀
    "IDType": "A股",                          # 证券类型
    "Author": "QSAgent",                      # 作者
    "Description": "因子描述",
    "FactorDeps": {                           # 依赖因子声明（可选）
        "stock_cn_status": ["if_listed"],
    },
    "DBDeps": {"JYDB": "聚源数据库"},         # 依赖的因子库（可选）
    "ModelArgs": {},                          # 期望的模型参数（可选）
    "DefScriptPath": __file__,                # 固定
}

def defFactor(fdi: FactorDefInput) -> List[Factor]:
    \"\"\"
    标准签名：接收 FactorDefInput，返回 List[Factor]。
    框架在调用前已完成：
    1. 递归解析 FactorDeps 依赖链
    2. 将依赖因子注入到 fdi.Factors
    3. 校验 DBDeps 中声明的库是否在 fdi.FDB 中存在
    \"\"\"
    Factors = []
    JYDB = fdi.FDB["JYDB"]
    # ... 构建因子 ...
    return Factors
```

### 依赖因子获取（框架自动注入）
```python
# FactorDeps 中声明的依赖因子由框架预注入到 fdi.Factors
IsListed = fdi.Factors["if_listed"]
Close = fdi.Factors["close"]

# FactorDeps 支持高级格式：别名和参数透传
# 在 __FACTOR_META__["FactorDeps"] 中：
#   "dep_table": [{"Name": "factor_name", "Alias": "my_alias"}]
#   "dep_table": [{"Name": "*"}]  # 该表全部因子
#   "dep_table": [{"Name": "*", "ModelArgs": {"key": "$parent_key"}}]  # 参数透传
```

### 数据源访问
```python
JYDB = fdi.FDB["JYDB"]
FT = JYDB.getTable("表名", args={"CalcType": "最新"})  # 财务数据用 CalcType="最新"
value = FT.getFactor("字段名")
```

### 常用算子
```python
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename

# 条件选择（双板合并核心）
where = fo.Where(dtype="double")
notnull = fo.NotNull()
result = where(main_board, notnull(main_board), star_board)

# 数学运算
fo.Log()                    # 自然对数
fo.Sum(all_nan=np.nan)      # 求和

# 时序运算
fo.RollingMean(window=5, min_periods=3)  # 滚动均值
fo.RollingApply(func=np.nansum, window=240, min_periods=1)  # 滚动应用

# 截面运算
fo.Quantile(q=0.5)          # 截面分位数

# 重命名
factor = rename(factor, factor_name="xxx", factor_args={"Meta": {"Description": "描述"}})
```

### 自定义算子（@FactorOperatorized）
```python
from QuantStudio.Factor.FactorOperation import FactorOperatorized

# Point 算子 — 单点运算
@FactorOperatorized(operator_type="Point", args={"Arity": 2, "DTMode": "多时点", "IDMode": "多ID", "DataType": "double"})
def calcXxx(f, idt, iid, x, args):
    return x[0] + x[1]

# Time 算子 — 时序运算
@FactorOperatorized(operator_type="Time", args={
    "Arity": 1, "LookBack": [20-1], "IDMode": "多ID", "DTMode": "单时点",
    "ModelArgs": {"非空率": 0.8},
})
def calcMomentum(f, idt, iid, x, args):
    # x[0] 是 2D array (time x IDs)
    return x[0][-1] / x[0][0] - 1

# Section 算子 — 截面运算
@FactorOperatorized(operator_type="Section", args={"Arity": 1, "DTMode": "单时点", "DataType": "double"})
def calcRank(f, idt, iid, x, args):
    return scipy.stats.rankdata(x[0]) / len(x[0])
```

### 主板/科创板合并模式（A 股因子必用）
```python
# 主板
FT = JYDB.getTable("主板表名", args={"CalcType": "最新"})
main_val = FT.getFactor("字段名")

# 科创板
FT_STIB = JYDB.getTable("科创板表名", args={"CalcType": "最新"})
star_val = FT_STIB.getFactor("字段名")

# 单位换算（如有需要）
star_val = star_val / 10000  # 元→万元

# 合并
where = fo.Where(dtype="double")
notnull = fo.NotNull()
result = where(main_val, notnull(main_val), star_val)
```"""


# ============================================================
# 代码生成 Prompt 构建
# ============================================================

def build_generation_prompt(
    hypothesis: dict,
    components: Optional[list[dict]] = None,
    ref_codes: Optional[list[dict]] = None,
) -> str:
    """构建完整的代码生成 prompt。

    Args:
        hypothesis: 假设文档（HypothesisDoc.to_development_input() 的输出）
        components: 经验库中的可复用组件列表
        ref_codes: 参考因子代码列表

    Returns:
        完整的用户 prompt
    """
    parts = []

    # 1. 假设文档
    parts.append("## 假设文档")
    parts.append(f"```yaml\n{json.dumps(hypothesis, ensure_ascii=False, indent=2)}\n```")

    # 2. API 参考
    parts.append("")
    parts.append(QUANTSTUDIO_API_REFERENCE)

    # 3. 可复用组件
    if components:
        parts.append("\n## 可复用组件（来自经验库）")
        for i, comp in enumerate(components[:5], 1):
            name = comp.get("name", f"组件{i}")
            code = comp.get("code", comp.get("content", ""))
            desc = comp.get("description", "")
            parts.append(f"\n### 组件 {i}: {name}")
            if desc:
                parts.append(f"描述: {desc}")
            if code:
                parts.append(f"```python\n{code}\n```")

    # 4. 参考因子代码
    if ref_codes:
        parts.append("\n## 参考因子代码")
        for i, ref in enumerate(ref_codes[:3], 1):
            name = ref.get("name", f"参考{i}")
            code = ref.get("code", "")
            desc = ref.get("description", "")
            parts.append(f"\n### 参考 {i}: {name}")
            if desc:
                parts.append(f"描述: {desc}")
            if code:
                parts.append(f"```python\n{code}\n```")

    # 5. forbidden_patterns
    forbidden = hypothesis.get("forbidden_patterns", [])
    if forbidden:
        parts.append("\n## 需规避的模式")
        for p in forbidden:
            parts.append(f"- {p}")

    # 6. 输出要求
    parts.append(OUTPUT_INSTRUCTIONS)

    return "\n".join(parts)


OUTPUT_INSTRUCTIONS = """
## 输出要求

请严格按以下格式输出，用 === 分隔三部分：

===FACTOR_CODE===
（完整的 factor_def.py 代码，包含 __FACTOR_META__、imports、defFactor 函数）

===SEARCH_SPACE===
（JSON 格式的搜索空间定义，如无需搜索则输出 {}）

===METADATA===
（JSON 格式的 metadata.json 内容）

注意事项：
- factor_def.py 必须包含完整的 import 语句
- 必须包含 __FACTOR_META__ 字典（TargetTable, IDType, Author, Description, DefScriptPath 为必填字段，FactorDeps, DBDeps, ModelArgs, Tags 为可选字段）
- defFactor 函数签名为 defFactor(fdi: FactorDefInput) -> List[Factor]（单参数）
- 依赖因子通过 fdi.Factors["因子名"] 获取（框架已根据 FactorDeps 预注入）
- 超参数用 args.get("param_name", default) 格式，同时在 SEARCH_SPACE 中定义搜索范围
- metadata.json 必须包含 factor_name, category, market, frequency, description, formula, data_sources, tags 字段
"""


# ============================================================
# 自动修复 Prompt 构建
# ============================================================

def build_fix_prompt(
    code: str,
    hypothesis: dict,
    failed_validators: list[dict],
) -> str:
    """构建自动修复 prompt。

    Args:
        code: 当前因子代码
        hypothesis: 原始假设文档
        failed_validators: 失败的验证器信息列表
            [{"name": "syntax", "issues": [...]}, ...]

    Returns:
        修复 prompt
    """
    parts = [
        "## 任务",
        "以下因子代码在验证过程中发现问题，请修复这些问题。",
        "保持假设文档的核心逻辑不变，仅修复技术问题。",
        "",
        "## 原始假设文档",
        f"```yaml\n{json.dumps(hypothesis, ensure_ascii=False, indent=2)}\n```",
        "",
        "## 当前代码",
        f"```python\n{code}\n```",
        "",
        "## 验证失败报告",
    ]

    for v in failed_validators:
        name = v.get("name", "unknown")
        issues = v.get("issues", [])
        parts.append(f"\n### {name} 验证失败")
        for issue in issues:
            parts.append(f"- {issue}")

    parts.append("""
## 修复要求
1. 仅修复上述报告中指出的问题
2. 不要改变因子的核心计算逻辑
3. 保持 __FACTOR_META__ 和函数签名不变
4. 如果需要修改表名或字段名，只使用 JYDB 数据字典中真实存在的

## 输出格式
请输出修复后的完整 factor_def.py 代码，用 ===FACTOR_CODE=== 包裹：

===FACTOR_CODE===
（修复后的完整代码）
===""")

    return "\n".join(parts)


# ============================================================
# 语义审查 Prompt 构建
# ============================================================

def build_semantic_review_prompt(
    code: str,
    hypothesis: dict,
) -> str:
    """构建语义审查 prompt。

    Args:
        code: 因子代码
        hypothesis: 假设文档

    Returns:
        语义审查 prompt
    """
    return f"""请审查以下因子代码是否与假设文档一致。

## 假设文档
- 因子名称: {hypothesis.get('factor_name', '')}
- 类别: {hypothesis.get('category', '')}
- 经济逻辑: {hypothesis.get('factor_description', '')}
- 计算公式: {hypothesis.get('formula', '')}
- 预期特征: {json.dumps(hypothesis.get('expected_characteristics', {}), ensure_ascii=False)}

## 因子代码
```python
{code}
```

## 审查要点
1. 代码逻辑是否与假设文档的公式一致？
2. 参数搜索空间是否合理？
3. 是否有明显的计算效率问题？
4. 是否遗漏了假设文档中的关键计算步骤？
5. 双板合并逻辑是否正确？

请按以下格式输出：

===REVIEW===
审查结论: PASSED / FAILED / WARNING

审查意见:
（详细说明代码与假设的一致性、发现的问题等）

改进建议:
（如有，列出具体建议）
==="""
