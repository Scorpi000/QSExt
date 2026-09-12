# DefModule 因子定义 API 参考

本文档是 QSExt DefModule 因子定义框架的完整 API 参考，供生成因子定义脚本时查阅。

## 目录

1. [因子模块结构](#因子模块结构)
2. [__FACTOR_META__ 字段详解](#__factor_meta__-字段详解)
3. [DefInput 接口](#factordefinput-接口)
4. [defFactor 模式](#deffactor-模式)
5. [数据源访问](#数据源访问)
6. [依赖机制](#依赖机制)
7. [常用算子](#常用算子)
8. [自定义算子 (@FactorOperatorized)](#自定义算子-factoroperatorized)
9. [主板/科创板合并模式](#主板科创板合并模式)
10. [导入速查](#导入速查)

---

## 因子模块结构

每个因子定义脚本是一个独立的 Python 模块，必须包含两个要素：

```python
# -*- coding: utf-8 -*-
"""{模块说明}"""
from typing import List

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor import FactorOperator as fo
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.DefModule.DefContent import DefInput

# 1. 元信息声明（必须）
__FACTOR_META__ = { ... }

# 2. 自定义算子（可选）
@FactorOperatorized(...)
def calcXxx(...):
    ...

# 3. 因子定义入口（必须）
def defNode(fdi: DefInput) -> List[Factor]:
    ...
    return [factor1, factor2, ...]
```

---

## __FACTOR_META__ 字段详解

`__FACTOR_META__` 是模块级字典，描述因子定义模块的静态元信息。框架在运行前解析此字典来发现和调度模块。

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `TargetTable` | `str` | ✅ 是 | — | 输出的因子表名。命名规范：`stock_cn_factor_{name}`（A 股） |
| `IDType` | `str` | ✅ 是 | — | 证券类型。可选：`"A股"`、`"ETF"`、`"公募基金"`、`"期货"`、`"期权"`、`"指数"`、`"申万一级行业"`、`"申万一级行业指数"` |
| `Description` | `str` | 推荐 | `""` | 因子模块的描述信息，说明输出哪些因子及其含义 |
| `Author` | `str` | 否 | `"Anonymous"` | 作者名称 |
| `MaxLookBack` | `int` | 否 | `365` | 最大回溯天数。若依赖更长回溯的因子，框架自动向上调整 |
| `DefaultStartDT` | `datetime` | 否 | `2002-01-01` | 默认起始日期 |
| `FactorDeps` | `dict` | 否 | `{}` | 依赖因子声明。键为依赖模块的 TargetTable，值为所需因子名列表 |
| `DBDeps` | `dict` | 否 | `{}` | 直接访问的因子库声明。键为 `fdi.FDB` 中的逻辑名称，值为用途说明 |
| `ModelArgs` | `dict` | 否 | `{}` | 期望的模型参数。键为参数名，值为参数说明字符串 |
| `Tags` | `list[str]` | 否 | `[]` | 检索标签，用于因子分类和发现 |
| `DefScriptPath` | `str` | 推荐 | `""` | 脚本路径，通常设为 `__file__` |

### FactorDeps 详解

`FactorDeps` 声明本模块依赖哪些因子，框架自动完成依赖解析和注入：

```python
"FactorDeps": {
    # 键 = 依赖模块的 TargetTable
    # 值 = 该模块中需要的因子名列表
    "stock_cn_status": ["if_listed"],              # 依赖上市状态因子
    "stock_cn_day_bar_nafilled": ["close"],        # 依赖收盘价因子
}
```

每个 entry 支持两种格式：

**字符串格式**（简单场景）：
```python
"stock_cn_status": ["if_listed", "is_st"]
```
直接写因子名，注入到 `fdi.Factors` 时键名即为因子名。

**字典格式**（需别名或传参数）：
```python
"stock_cn_day_bar_nafilled": [
    {"Name": "close", "Alias": "price"},             # 以 "price" 别名注入
    {"Name": "*"},                                     # 全部因子
    {"Name": "factor_x", "ModelArgs": {"key": "$parent_key"}},  # 透传参数
]
```

- `Name`：因子名（必填）。`"*"` = 该表全部因子
- `Alias`：注入 `fdi.Factors` 时的别名（可选，默认用 Name）
- `ModelArgs`：传递给依赖模块 `defFactor` 的参数（可选）。值以 `"$"` 开头时从父模块的 `fdi.ModelArgs` 中查找，实现参数透传

使用时通过 `fdi.Factors` 访问：
```python
def defNode(fdi: DefInput) -> List[Factor]:
    IsListed = fdi.Factors["if_listed"]
    Close = fdi.Factors["close"]  # 或 "price"（如果用了 Alias）
```

### DBDeps 详解

`DBDeps` 声明本模块直接访问的因子库，框架校验存在性：

```python
"DBDeps": {
    "JYDB": "聚源数据库，提供行情和财务数据",
}
```

如果 `DBDeps` 中声明的库在运行时 `fdi.FDB` 中不存在，框架抛出 `KeyError`。

### ModelArgs 详解

`ModelArgs` 声明本模块期望的运行时参数，用于参数化因子计算：

```python
"ModelArgs": {
    "lookback": "回溯窗口天数",
    "threshold": "信号阈值",
}
```

运行时由 `DefInput.ModelArgs` 传入：
```python
def defNode(fdi: DefInput) -> List[Factor]:
    lookback = fdi.ModelArgs.get("lookback", 20)
    threshold = fdi.ModelArgs.get("threshold", 0.5)
```

---

## DefInput 接口

`DefInput` 是 `defFactor` 的唯一入参，包含运行时上下文：

| 属性 | 类型 | 说明 |
|------|------|------|
| `FDB` | `dict[str, FactorDB]` | 可用因子库字典。键为逻辑名称（如 `"JYDB"`），值为已连接的 FactorDB 实例 |
| `Factors` | `dict[str, Factor]` | 已解析的依赖因子字典。由框架根据 `FactorDeps` 声明预注入 |
| `ModelArgs` | `dict` | 运行时模型参数。由 `DefSettings` 或调用方传入 |
| `DTs` | `list[datetime]` | 本次运行的计算时点列表 |
| `DTRuler` | `list[datetime]` | 时点标尺（含回溯窗口的扩展时点范围） |
| `IDs` | `list[str]` | 当前截面证券 ID 列表 |
| `SectionIDs` | `list[str]` | 截面计算用的证券列表 |
| `Debug` | `bool` | 是否调试模式 |
| `TDB` | `WritableFactorDB` (可选) | 写入目标库 |

---

## defFactor 模式

### 标准模式

```python
def defNode(fdi: DefInput) -> List[Factor]:
    """标准签名：接收 DefInput，返回 List[Factor]"""
    JYDB = fdi.FDB["JYDB"]
    Factors = []

    # 读取数据、构建因子...

    Factors.append(factor)
    return Factors
```

### 使用依赖因子

```python
def defNode(fdi: DefInput) -> List[Factor]:
    # 框架已根据 FactorDeps 声明预注入
    Close = fdi.Factors["close"]
    IsListed = fdi.Factors["if_listed"]

    # 使用依赖因子作为输入进行进一步计算...
    returns = Close / Close.shift(1) - 1
    returns = rename(returns, factor_name="daily_return", ...)
    return [returns]
```

### 使用 ModelArgs

```python
def defNode(fdi: DefInput) -> List[Factor]:
    window = fdi.ModelArgs.get("window", 20)
    # 使用 window 参数控制计算逻辑
    ...
```

---

## 数据源访问

### 获取数据库连接

```python
def defNode(fdi: DefInput) -> List[Factor]:
    JYDB = fdi.FDB["JYDB"]      # 通过 DBDeps 声明过的库
```

`fdi.FDB` 中的实例是已连接状态，可以直接使用。

### 读取因子数据

```python
# 行情类数据
FT = JYDB.getTable("日行情表", args={"LookBack": 0})
value = FT.getFactor("字段名")

# 财务类数据（通常需要 CalcType="最新"）
FT = JYDB.getTable("财务表", args={"CalcType": "最新"})
value = FT.getFactor("字段名")
```

关键参数：
- `LookBack`：回溯窗口天数。`0` 表示只要当天数据
- `CalcType`：财务数据计算类型，`"最新"` 表示使用最新披露数据
- `FactorTable` 的 `args` 取决于具体数据库实现

---

## 依赖机制

### 依赖解析流程

```
模块 A FactorDeps = {"stock_cn_status": ["if_listed"]}
    ↓
框架解析 "stock_cn_status" → 找到对应模块 → 递归执行其 defFactor
    ↓
注入 fdi.Factors = {"if_listed": <Factor 对象>}
    ↓
执行模块 A 的 defFactor(fdi)
```

### 参数透传

当依赖模块需要参数时，通过 `$` 前缀从父模块透传：

**父模块** (`__FACTOR_META__`)：
```python
"ModelArgs": {"lookback": "回溯窗口天数"},
"FactorDeps": {
    "stock_cn_factor_momentum": [
        {"Name": "momentum", "ModelArgs": {"lookback": "$lookback"}},
    ],
},
```

运行时，框架将 `"$lookback"` 解析为 `fdi.ModelArgs["lookback"]` 的值，传递给依赖模块。

### 校验与错误处理

框架在依赖解析时自动执行以下校验：
1. `DBDeps` 中声明的库是否在 `fdi.FDB` 中存在（不存在则 `KeyError`）
2. `FactorDeps` 中的 `$` 引用是否在 `ModelArgs` 中声明（仅警告，不阻断）
3. 循环依赖检测（抛 `RuntimeError`）

---

## 常用算子

### 内置算子

```python
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename

# ---- 数学运算 ----
fo.Abs()                              # 绝对值
fo.Log()                              # 自然对数
fo.Sign()                             # 符号函数
fo.Power(power=2)                     # 幂运算

# ---- 条件选择 ----
where = fo.Where(dtype="double")      # 条件选择：where(val, condition, default)
notnull = fo.NotNull()                # 非空条件

# ---- 时序运算 ----
fo.Diff(d=1)                          # 差分
fo.PctChange()                        # 百分比变化
fo.Shift(d=1)                         # 平移
fo.RollingMean(window=20, min_periods=10)      # 滚动均值
fo.RollingStd(window=20, min_periods=10)       # 滚动标准差
fo.RollingSum(window=20, min_periods=10)       # 滚动求和
fo.RollingMax(window=20, min_periods=10)       # 滚动最大值
fo.RollingMin(window=20, min_periods=10)       # 滚动最小值
fo.RollingApply(func=np.nanmean, window=20, min_periods=10)  # 滚动自定义函数
fo.RollingRank(window=20)                         # 滚动排名

# ---- 截面运算 ----
fo.Quantile(q=0.5)                    # 截面分位数
fo.ZScore()                           # 截面 Z-Score 标准化
fo.Rank()                             # 截面排名
fo.Demean()                           # 截面去均值
fo.SectionApply(func=np.nanmean)      # 截面自定义函数

# ---- 重命名 ----
factor = rename(factor,
    factor_name="factor_name",
    factor_args={
        "Meta": {
            "Description": "因子描述",
            "Tags": ["标签1"],
        },
    },
)
```

### Where 算子详解

`fo.Where(dtype="double")` 是最常用的条件选择算子，也是双板合并的核心：

```python
where = fo.Where(dtype="double")
notnull = fo.NotNull()

# Where(候选值, 条件, 默认值)
# 当条件为 True 时取候选值，否则取默认值
result = where(candidate, condition, default)

# 实际用法：优先取主板数据，主板缺失时取科创板数据
result = where(main_board_val, notnull(main_board_val), star_board_val)
```

---

## 自定义算子 (@FactorOperatorized)

当内置算子无法满足需求时，使用 `@FactorOperatorized` 装饰器定义自定义算子。

### 导入

```python
from QuantStudio.Factor.FactorOperation import FactorOperatorized
```

### 算子类型

#### Point 算子 — 单点运算

对单个时点上单个 ID 的单个值进行变换：

```python
@FactorOperatorized(
    operator_type="Point",
    args={
        "Arity": 2,               # 输入因子数（可为 None 表示不限）
        "DTMode": "多时点",        # "单时点" | "多时点"
        "IDMode": "多ID",          # "单ID" | "多ID"
        "DataType": "double",      # "double" | "object" | "string"
    },
)
def calcRatio(f, idt, iid, x, args):
    """计算比值，防除零"""
    a, b = x[0], x[1]
    if b == 0 or np.isnan(b):
        return np.nan
    return a / b
```

#### Section 算子 — 截面运算

在单个时点上跨所有 ID 操作：

```python
@FactorOperatorized(
    operator_type="Section",
    args={
        "Arity": 1,
        "DTMode": "单时点",
        "DataType": "double",
    },
)
def calcCrossSectionalRank(f, idt, iid, x, args):
    """截面排名（百分位数），NaN 安全"""
    import scipy.stats
    data = np.array(x[0], dtype=float)
    mask = ~np.isnan(data)
    if mask.sum() <= 1:
        return np.full_like(data, np.nan)
    result = np.full_like(data, np.nan)
    result[mask] = scipy.stats.rankdata(data[mask]) / mask.sum()
    return result
```

#### Time 算子 — 时序运算

对单个 ID 跨时间操作：

```python
@FactorOperatorized(
    operator_type="Time",
    args={
        "Arity": 1,
        "DTMode": "多时点",         # 必须为多时点
        "IDMode": "单ID",           # 一般为单ID
        "DataType": "double",
        "LookBack": [252],          # 回溯窗口长度（长度与 Arity 一致）
        "ModelArgs": {"min_valid_ratio": 0.8},  # 可选参数
    },
)
def calcMomentum(f, idt, iid, x, args):
    """过去 N 日动量"""
    Prices = x[0]  # 2D array shape=(LookBack+1, 1)
    Returns = (Prices[-1] - Prices[0]) / Prices[0]
    return Returns
```

### @FactorOperatorized args 参数规范

`args` 字典只接受以下合法键：

| 键 | 类型 | 说明 | 取值范围 |
|----|------|------|----------|
| `Arity` | `int` / `None` | 输入因子数量 | 正整数或 `None`（不限） |
| `DTMode` | `str` | 时点模式 | `"单时点"` | `"多时点"` |
| `IDMode` | `str` | ID 模式 | `"单ID"` | `"多ID"` |
| `DataType` | `str` | 数据类型 | `"double"` | `"object"` | `"string"` |
| `ModelArgs` | `dict` | 模型参数 | 如 `{"非空率": 0.4}` |
| `LookBack` | `list[int]` | 回溯窗口 | 如 `[21]`, `[252, 252]` |

**operator_type 与常用 args 组合：**

| operator_type | 必含 args | 说明 |
|---------------|-----------|------|
| `"Point"` | `Arity`, `DTMode`, `IDMode`, `DataType` | 单点运算 |
| `"Section"` | `Arity`, `DTMode` | 截面运算 |
| `"Time"` | `Arity`, `DTMode`, `IDMode`, `LookBack` | 时序运算 |
| `"Panel"` | `Arity`, `DTMode`, `LookBack` | 面板运算 |

**注意**：
- 不要添加上表以外的键，否则触发 pydantic `ValidationError`
- `IDMode` 只能是 `"单ID"` 或 `"多ID"`，不能是 `"全ID"` 等
- Time 算子的 `LookBack` 格式为 `[N-1]`，框架给 `x` 填充 `N` 个时点的数据（当前 + N-1 历史）

### 自定义算子使用

定义后像内置算子一样调用：

```python
# 不带额外参数
result = calcMomentum(Close)

# 带 factor_args（设置输出因子名称和元信息）
result = calcMomentum(
    Close,
    factor_args={
        "Name": "momentum_252d",
        "Meta": {"Description": "252日动量因子"},
    },
)

# 带算子参数（覆盖 ModelArgs 默认值）
result = calcMomentum(
    Close,
    args={"min_valid_ratio": 0.6},
    factor_args={"Name": "momentum_252d"},
)
```

---

## 主板/科创板合并模式

A 股因子必须同时覆盖主板和科创板（及创业板），标准模式如下：

```python
def defNode(fdi: DefInput) -> List[Factor]:
    JYDB = fdi.FDB["JYDB"]
    where = fo.Where(dtype="double")
    notnull = fo.NotNull()

    # 1. 读取主板数据
    FT = JYDB.getTable("日行情表", args={"LookBack": 0})
    main_val = FT.getFactor("目标字段")

    # 2. 读取科创板数据
    FT_STAR = JYDB.getTable("科创板日行情", args={"LookBack": 0})
    star_val = FT_STAR.getFactor("目标字段")

    # 3. 单位换算（如有差异）
    # 例如：主板为万元，科创板为元 → star_val = star_val / 10000

    # 4. 合并：主板数据优先，缺失时用科创板补充
    merged = where(main_val, notnull(main_val), star_val)

    # 5. 重命名
    result = rename(merged, factor_name="xxx", ...)
    return [result]
```

关键点：
- **必须检查单位差异**！主板和科创板的单位可能不同（如元 vs 万元），必须做单位换算
- 合并逻辑：`where(主板值, notnull(主板值), 科创板值)` —— 主板有值用主板，否则用科创板
- 若有三板（北交所）也需要覆盖，同理叠加

---

## 导入速查

因子定义脚本的标准导入集合：

```python
# 基础
from typing import List
import numpy as np

# DefModule 框架
from QSExt.DefModule.DefContent import DefInput

# QuantStudio 因子
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor import FactorOperator as fo
from QuantStudio.Factor.FactorOperation import FactorOperatorized

# 可选：科学计算
import scipy.stats
```

**不要导入的：**
- `Def`、`DefMeta` — 因子定义脚本不需要构造这些对象，框架自动包装
- `DBPool`、`DefSettings` — 运行时由执行脚本管理，因子定义脚本不需要
- `DefInputBuilder` — 同上
