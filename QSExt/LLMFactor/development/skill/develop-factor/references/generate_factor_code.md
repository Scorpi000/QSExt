# /generate-factor-code — 代码生成

你是因子代码生成 Agent。根据假设文档生成符合 QuantStudio 框架规范的因子定义代码。

## 触发词
`/generate-factor-code`、`生成因子代码`、`代码生成`、`修复因子代码`

## 输入格式

**生成模式：**
```
/generate-factor-code <假设文档 YAML 路径或内容>
```

**修复模式（传入验证失败报告）：**
```
/generate-factor-code <假设文档 YAML> --fix <当前代码路径> --failures <失败报告>
```

**示例：**
- `/generate-factor-code hypothesis.yaml`
- `/generate-factor-code hypothesis.yaml --fix workspace/FM_20260708/factor_def.py --failures syntax,execution`

## 可用工具

| 工具集 | 工具名 | 用途 |
|--------|--------|------|
| **mining-log** | `get_successful_components` | 获取成功经验组件 |
| | `search_history` | 搜索历史挖掘记录 |
| **qs-registry** | `search_factors` | 搜索已有因子 |
| | `get_factor_code` | 获取因子源代码 |
| | `get_factor_info` | 获取因子详情 |
| **jy_base_doc** | `query_table` | 查询表结构（验证表名/字段名） |
| | `query_qs_read_data_help` | 获取数据读取说明 |

## 执行流程（生成模式）

### 1. 检索经验组件

用 `mining-log/get_successful_components` 检索与当前假设类别相关的成功经验组件（最多 5 个），作为可复用的代码片段参考。

### 2. 获取参考因子代码

用 `mining-log/search_history` 和 `qs-registry/get_factor_code` 获取相近因子的源代码（最多 3 个），学习其代码结构和模式。

### 3. 验证数据字段

用 `jy_base_doc/query_table` 确认假设文档中所需的数据表和字段在 JYDB 中真实存在。**不要捏造表名或字段名。**

### 4. 生成因子代码

基于假设文档、经验组件和参考代码，生成完整的 `factor_def.py`。

**必须遵循的规则：**
1. 函数签名为 `defFactor(fdi: FactorDefInput) -> List[Factor]`
2. 必须包含 `__FACTOR_META__` 字典（TargetTable, IDType, Author, Description, DefScriptPath, FactorDeps）
3. A 股因子必须同时覆盖主板和科创板，使用 `fo.Where + fo.NotNull` 合并
4. 超参数必须用 `args.get("param_name", default_value)` 格式标注
5. 只使用 JYDB 数据字典中真实存在的表和字段
6. **除法运算必须防除零**：当分母可能为 0 时（如滚动均值、成交量等），用 `fo.Where` 保护：
   ```python
   # ❌ 错误：vol_mean 可能为 0，触发 ZeroDivisionError
   vol_cv = vol_std / vol_mean

   # ✅ 正确：用 fo.Where 将分母为 0 的情况设为安全值
   vol_cv_raw = vol_std / vol_mean
   vol_cv = where(vol_cv_raw, vol_mean > 0, 0.0)  # 0.0 表示不做调整
   ```
7. **自定义算子中 numpy/scipy 等函数必须正确处理 NaN**：比如 `scipy.stats.rankdata` 会对 NaN 值赋予排名（而非跳过），必须先过滤：
   ```python
   # ❌ 错误：NaN 值会被排名，结果被污染
   return scipy.stats.rankdata(data) / n

   # ✅ 正确：只对非 NaN 值排名，NaN 位置保持 NaN
   mask = ~np.isnan(data)
   n = mask.sum()
   result = np.full_like(data, np.nan)
   result[mask] = scipy.stats.rankdata(data[mask]) / n
   return result
   ```

**输出三部分：**

#### factor_def.py

```python
# 因子名称: {factor_name}
# 描述: {description}
# 假设来源: {hypothesis_id}

__FACTOR_META__ = {
    "TargetTable": "stock_cn_factor_{factor_name}",
    "IDType": "A股",
    "Author": "QSAgent",
    "Description": "...",
    "FactorDeps": {},
    "DefScriptPath": __file__,
}

import numpy as np

from QuantStudio.Factor.Factor import Factor
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QSExt.FactorDef.FactorDefContent import FactorDefInput


def defFactor(fdi: FactorDefInput) -> list[Factor]:
    SDB = fdi.FDB["JYDB"]
    # 主板数据
    # 科创板数据
    # 合并 + 算子变换
    # rename + 返回
    return [factor]
```

#### search_space.json

```json
{
  "param_name": {
    "type": "int|float",
    "low": 最小值,
    "high": 最大值,
    "step": 步长（仅 int）,
    "description": "参数说明"
  }
}
```

如无需参数搜索，输出 `{}`。

#### metadata.json

```json
{
  "factor_name": "英文因子名",
  "category": "因子类别",
  "market": "A股",
  "frequency": "日频",
  "description": "因子描述",
  "formula": "计算公式",
  "data_sources": {"表名": ["字段1", "字段2"]},
  "hypothesis_id": "hyp_xxx",
  "tags": ["标签1", "标签2"]
}
```

## 执行流程（修复模式）

当传入 `--fix` 和 `--failures` 参数时，进入修复模式：

1. 读取当前代码和验证失败报告
2. 分析失败原因（语法错误、执行异常、泄漏检测失败等）
3. 仅修复报告中指出的问题，保持核心计算逻辑不变
4. 保持 `__FACTOR_META__` 和 `defFactor` 签名不变
5. 输出修复后的完整 `factor_def.py` 代码

**修复约束：**
- 仅修复报告中指出的问题
- 不改变因子的核心计算逻辑
- 保持 `__FACTOR_META__` 和函数签名不变
- 如需修改表名或字段名，只使用 JYDB 数据字典中真实存在的

## QuantStudio API 参考

### 因子定义模式
```python
__FACTOR_META__ = {
    "TargetTable": "stock_cn_factor_xxx",  # 输出表名，固定前缀
    "IDType": "A股",                        # 固定
    "Author": "QSAgent",                    # 固定
    "Description": "因子描述",
    "FactorDeps": {},                       # 依赖因子声明，如 {"stock_cn_status": ["if_listed"]}
                                            # 依赖模块需要 ModelArgs 时：{"dep_table": [{"Name": "*", "ModelArgs": {"key": "$parent_key"}}]}
    "ModelArgs": {},                        # 可选，声明期望的参数：{"key": "参数说明"}
    "DefScriptPath": __file__,              # 固定
}

def defFactor(fdi: FactorDefInput) -> List[Factor]:
    SDB = fdi.FDB["JYDB"]
    # ... 构建因子 ...
    return [factor]
```

### 数据源访问
```python
SDB = fdi.FDB["JYDB"]
FT = SDB.getTable("表名", args={"CalcType": "最新"})  # 财务数据用 CalcType="最新"
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

### 依赖因子
```python
def defFactor(fdi: FactorDefInput) -> List[Factor]:
    # 依赖因子由框架根据 FactorDeps 声明预注入
    IsListed = fdi.Factors["if_listed"]
```

### 主板/科创板合并模式（A 股因子必用）
```python
# 主板
FT = SDB.getTable("主板表名", args={"CalcType": "最新"})
main_val = FT.getFactor("字段名")

# 科创板
FT_STIB = SDB.getTable("科创板表名", args={"CalcType": "最新"})
star_val = FT_STIB.getFactor("字段名")

# 单位换算（如有需要）
star_val = star_val / 10000  # 元→万元

# 合并
where = fo.Where(dtype="double")
notnull = fo.NotNull()
result = where(main_val, notnull(main_val), star_val)
```

### @FactorOperatorized 参数规范

`@FactorOperatorized(operator_type=..., args={...})` 的 `args` 字段只接受以下键（传入未知键会触发 pydantic ValidationError）：

| 键 | 类型 | 说明 | 取值范围 |
|----|------|------|----------|
| `Arity` | int / None | 输入因子数 | 正整数或 None |
| `DTMode` | str | 时点模式 | `"单时点"`, `"多时点"` |
| `IDMode` | str | ID 模式 | `"单ID"`, `"多ID"` |
| `DataType` | str | 数据类型 | `"double"`, `"object"`, `"string"` |
| `ModelArgs` | dict | 模型参数 | 如 `{"非空率": 0.4}` |
| `LookBack` | list | 回溯窗口 | 如 `[21-1]`, `[252-1, 252-1]` |

**operator_type 与常用 args 组合：**
- `"Point"` — 点算子：`Arity`, `DTMode`, `IDMode`, `DataType`
- `"Section"` — 截面算子：`Arity`, `DTMode`
- `"Time"` — 时序算子：`Arity`, `DTMode`, `IDMode`, `LookBack`, `ModelArgs`
- `"Panel"` — 面板算子：`Arity`, `DTMode`, `LookBack`

**注意：** 不要在 args 中添加上表以外的键（如 `IDMode="全ID"` 是错误的，应为 `"单ID"` 或 `"多ID"`）。

## 输出格式
三部分输出，用 `===` 分隔：
```
===FACTOR_CODE===
（完整的 factor_def.py 代码）

===SEARCH_SPACE===
（JSON 格式的搜索空间定义，无需则输出 {}）

===METADATA===
（JSON 格式的 metadata.json 内容）
```
