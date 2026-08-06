# StrategyDef 框架 API 参考

本文档是 QSExt StrategyDef 策略定义框架的完整 API 参考，供生成策略定义脚本时查阅。

## 目录

1. [策略模块结构](#策略模块结构)
2. [__STRATEGY_META__ 字段详解](#__strategy_meta__-字段详解)
3. [StrategyDefInput 接口](#strategydefinput-接口)
4. [MakeStrategy 详解](#makestrategy-详解)
5. [defStrategy 模式](#defstrategy-模式)
6. [依赖机制](#依赖机制)
7. [策略信号类型](#策略信号类型)
8. [常用策略模式](#常用策略模式)
9. [导入速查](#导入速查)

---

## 策略模块结构

每个策略定义脚本是一个独立的 Python 模块，必须包含三个要素：

```python
# -*- coding: utf-8 -*-
"""{模块说明}"""
import numpy as np
import pandas as pd

from QuantStudio.BackTest.Strategy.Strategy import MakeStrategy
from QSExt.StrategyDef.StrategyDefContent import StrategyDefInput

# 1. 元信息声明（必须）
__STRATEGY_META__ = { ... }

# 2. MakeStrategy 子类（必须）
class XxxStrategy(MakeStrategy):
    def genSignal(self, f, idt, x, last_price, cash, position_num, args):
        ...
        return signal

# 3. 策略定义入口（必须）
def defStrategy(sdi: StrategyDefInput) -> list:
    ...
    return [strategy_instance]
```

与 FactorDef 的关键区别：
- 返回 `List[Factor]`，其中每个 Factor 是通过 `MakeStrategy.__call__` 产生的策略因子
- 策略因子是**复合因子**，包含 Cash、Position、Amount、Signal、TradeNum、TradePrice、Fee 等子字段
- 通过继承 `MakeStrategy` 并重写 `genSignal()` 定义交易逻辑，而非使用算子组合

---

## __STRATEGY_META__ 字段详解

`__STRATEGY_META__` 是模块级字典，描述策略定义模块的静态元信息。框架在运行前解析此字典来发现和调度模块。

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `TargetTable` | `str` | ✅ 是 | — | 策略信号输出的因子表名 |
| `IDType` | `str` | ✅ 是 | — | 证券类型。可选：`"A股"`、`"ETF"`、`"公募基金"`、`"期货"`、`"期权"`、`"指数"` |
| `Description` | `str` | 推荐 | `""` | 策略模块的描述信息，说明策略逻辑和输出信号含义 |
| `Author` | `str` | 否 | `"Anonymous"` | 作者名称 |
| `MaxLookBack` | `int` | 否 | `365` | 最大回溯天数。若依赖更长回溯的因子/策略，框架自动向上调整 |
| `DefScriptPath` | `str` | 推荐 | `""` | 脚本路径，通常设为 `__file__` |

### OperatorConfig — 算子默认配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `SignalType` | `str` | `"目标权重"` | 信号类型：`"目标权重"` 或 `"买卖数量"` |
| `InitCash` | `float` | `1e6` | 初始资金 |
| `ShortAllowed` | `bool` | `False` | 是否允许卖空 |

```python
"OperatorConfig": {
    "SignalType": "目标权重",
    "InitCash": 1e6,
    "ShortAllowed": False,
},
```

### FactorDeps — 依赖因子声明

与 FactorDef 的 `FactorDeps` 完全一致，声明本策略依赖哪些因子：

```python
"FactorDeps": {
    "stock_cn_day_bar_nafilled": ["close"],
    "stock_cn_status": ["if_listed"],
}
```

### StrategyDeps — 依赖策略声明

声明本策略依赖其他策略输出的信号：

```python
"StrategyDeps": {
    # key = 依赖策略的模块路径
    # value = [{Name: 信号因子名, Alias: 本地别名, ModelArgs: {...}}]
    "grid_trading": [{"Name": "grid_signal", "Alias": "gs"}],
}
```

- `Name`：策略模块输出的信号因子名（必填）
- `Alias`：注入 `sdi.Strategies` 时的别名（可选，默认用 Name）
- `ModelArgs`：传递给依赖策略 `defStrategy` 的参数（可选，`$` 前缀从父模块透传）

### DBDeps — 因子库依赖

```python
"DBDeps": {"JYDB": "聚源数据库，提供行情和财务数据"},
```

### ModelArgs — 可调参数

```python
"ModelArgs": {
    "short_window": "短期均线窗口",
    "long_window": "长期均线窗口",
    "threshold": "信号阈值",
},
```

### Tags — 检索标签

```python
"Tags": ["趋势跟踪", "均线", "CTA"],
```

---

## StrategyDefInput 接口

`StrategyDefInput` 是 `defStrategy` 的唯一入参，包含运行时上下文。与 `FactorDefInput` 对齐，新增 `Strategies` 字段：

| 属性 | 类型 | 说明 |
|------|------|------|
| `FDB` | `dict[str, FactorDB]` | 可用因子库字典。键为逻辑名称（如 `"JYDB"`），值为已连接的 FactorDB 实例 |
| `Factors` | `dict[str, Factor]` | 已解析的依赖因子字典。由框架根据 `FactorDeps` 声明预注入 |
| `Strategies` | `dict[str, Factor]` | 已解析的依赖策略信号字典。由框架根据 `StrategyDeps` 声明预注入 |
| `ModelArgs` | `dict` | 运行时模型参数。由配置或调用方传入 |
| `DTs` | `list[datetime]` | 本次运行的计算时点列表 |
| `DTRuler` | `list[datetime]` | 时点标尺（含回溯窗口的扩展时点范围） |
| `IDs` | `list[str]` | 当前截面证券 ID 列表 |
| `SectionIDs` | `list[str]` | 截面计算用的证券列表 |
| `Debug` | `bool` | 是否调试模式 |
| `TDB` | `WritableFactorDB` (可选) | 写入目标库 |

---

## MakeStrategy 详解

### 构造参数

```python
MakeStrategy(
    signal_type="目标权重",   # "目标权重" | "买卖数量"
    init_cash=1e6,            # 初始资金
    short_allowed=False,      # 是否允许卖空
    start_dt=None,            # 净值开始日，None 从第一个时点开始
    x_lookback=[],            # 策略所依赖因子的回溯期数
    x_section_ids=[],         # 策略所依赖因子的截面ID序列
    signal_dts=None,          # 指定生成信号的时点，None 表示所有时点
    args={},                  # 额外参数
)
```

关键参数说明：
- `signal_type="目标权重"`：信号值为目标持仓权重（0~1），框架自动计算交易数量
- `signal_type="买卖数量"`：信号值直接为交易数量（正=买入，负=卖出）
- `start_dt`：净值从该日期开始累计，之前无持仓
- `x_lookback`：长度与传入的 x 因子数量一致，每个元素表示对应因子的回溯期数

### genSignal() 签名

```python
def genSignal(
    self,
    f: PanelOperation,                    # 策略因子对象
    idt: dt.datetime,                     # 当前时点
    x: List[pd.DataFrame],                # 策略依赖的因子数据，每个元素为 DataFrame(index=[datetime], columns=[证券ID])
    last_price: pd.Series,                # 当前证券最新价，Series(index=[证券ID])
    cash: float,                          # 当前账户剩余现金
    position_num: pd.Series,              # 当前账户持仓数量，Series(index=[证券ID])
    args: dict,                           # 策略参数
) -> Optional[pd.Series]:
    """返回信号 Series(index=[证券ID])，None 表示无信号"""
```

返回值：
- `pd.Series`：索引为证券 ID，值为信号
- **目标权重模式**：值应在 [0, 1] 范围，表示每个证券的目标持仓权重
- **买卖数量模式**：正值买入、负值卖出
- `None`：表示当前时点不产生信号
- 不需要输出全部证券，框架会自动处理未覆盖的证券（信号=0）

### __call__ 调用方式

`MakeStrategy` 实例是算子，调用时传入依赖因子产生策略因子：

```python
# 基本调用
strategy = MACrossStrategy(...)
signal = strategy(ma_short, ma_long, last_price=close)

# 带额外参数
signal = strategy(
    factor1, factor2,
    last_price=close,
    buy_price=open_price,         # 买入成交价因子（默认用 last_price）
    buy_limit=restricted_list,     # 禁止买入条件（=1 的 ID 禁止买入）
    buy_fee=0.001,                 # 买入费率
    sell_price=open_price,         # 卖出成交价因子
    sell_limit=restricted_list,    # 禁止卖出条件
    sell_fee=0.001,                # 卖出费率
)

# 返回 List[Factor]
return [strategy(ma_short, ma_long, last_price=close)]
```

调用时传入的因子顺序对应 `genSignal()` 中 `x` 列表的顺序。

### genSignal 中 x 参数的格式

`x` 是 `List[pd.DataFrame]`，每个元素对应调用时传入的一个依赖因子在当前时点的数据切片：
- `x[0]`：第一个传入因子的历史数据，DataFrame(index=[datetime], columns=[证券ID])
- `x[1]`：第二个传入因子的历史数据，格式同上

数据的时间范围由 `x_lookback` 控制：若 `x_lookback=[5]`，则 `x[0]` 包含当前时点及往前 5 个时点的数据。

---

## defStrategy 模式

### 标准模式

```python
def defStrategy(sdi: StrategyDefInput) -> list:
    """标准签名：接收 StrategyDefInput，返回策略实例列表"""
    close = sdi.Factors["close"]

    op_config = __STRATEGY_META__["OperatorConfig"]
    strategy_op = MACrossStrategy(
        signal_type=op_config["SignalType"],
        init_cash=op_config["InitCash"],
        short_allowed=op_config["ShortAllowed"],
    )

    from QuantStudio.Factor import FactorOperator as fo
    ma_short = fo.rolling_mean(close, window=5, min_periods=1)
    ma_long = fo.rolling_mean(close, window=20, min_periods=1)

    return [strategy_op(ma_short, ma_long, last_price=close)]
```

### 使用依赖因子

```python
def defStrategy(sdi: StrategyDefInput) -> list:
    # 框架已根据 FactorDeps 声明预注入
    close = sdi.Factors["close"]
    volume = sdi.Factors["volume"]

    # 用因子构造策略信号
    ...
    return [strategy_op(factor1, factor2, last_price=close)]
```

### 使用依赖策略

```python
def defStrategy(sdi: StrategyDefInput) -> list:
    # 框架已根据 StrategyDeps 声明预注入其他策略的信号
    parent_signal = sdi.Strategies["grid_signal"]  # 或别名

    # 基于父策略信号做二次决策
    ...
    return [strategy_op(parent_signal, last_price=close)]
```

### 使用 ModelArgs

```python
def defStrategy(sdi: StrategyDefInput) -> list:
    lookback = int(sdi.ModelArgs.get("lookback", 60))
    threshold = float(sdi.ModelArgs.get("threshold", 0.5))

    op_config = __STRATEGY_META__["OperatorConfig"]
    signal_type = sdi.ModelArgs.get("signal_type", op_config["SignalType"])
    ...
```

### 一个模块多个策略

```python
def defStrategy(sdi: StrategyDefInput) -> list:
    close = sdi.Factors["close"]

    # 策略1：5-20 均线交叉
    strategy1 = MACrossStrategy(...)
    ma5 = fo.rolling_mean(close, window=5)
    ma20 = fo.rolling_mean(close, window=20)

    # 策略2：10-60 均线交叉
    strategy2 = MACrossStrategy(...)
    ma10 = fo.rolling_mean(close, window=10)
    ma60 = fo.rolling_mean(close, window=60)

    return [
        strategy1(ma5, ma20, last_price=close),
        strategy2(ma10, ma60, last_price=close),
    ]
```

---

## 依赖机制

### 依赖解析流程

```
模块 A StrategyDeps = {"grid_trading": [{"Name": "grid_signal"}]}
    ↓
框架解析 "grid_trading" → 找到对应模块 → 递归执行其 defStrategy
    ↓
提取信号因子: dep_sd_entry.getStrategy("grid_signal")
    ↓
注入 sdi.Strategies = {"grid_signal": <Factor 对象>}
    ↓
同时解析 FactorDeps → 递归执行依赖因子的 defFactor
    ↓
注入 sdi.Factors = {"close": <Factor 对象>, ...}
    ↓
执行模块 A 的 defStrategy(sdi)
```

### FactorDeps entry 格式（同 FactorDef）

**字符串格式**（简单场景）：
```python
"stock_cn_status": ["if_listed", "is_st"]
```

**字典格式**（需别名或传参数）：
```python
"stock_cn_day_bar_nafilled": [
    {"Name": "close", "Alias": "price"},
    {"Name": "*"},                                        # 全部因子
    {"Name": "factor_x", "ModelArgs": {"key": "$parent_key"}},
]
```

### StrategyDeps entry 格式

```python
"StrategyDeps": {
    "grid_trading": [
        {"Name": "grid_signal", "Alias": "gs"},
        {"Name": "grid_signal", "ModelArgs": {"lookback": "$lookback"}},
    ],
}
```

### 参数透传

当依赖模块需要参数时，通过 `$` 前缀从父模块透传：

```python
"ModelArgs": {"lookback": "回溯窗口天数"},
"StrategyDeps": {
    "momentum_strategy": [
        {"Name": "momentum_signal", "ModelArgs": {"lookback": "$lookback"}},
    ],
},
```

### 校验与错误处理

框架在依赖解析时自动执行以下校验：
1. `DBDeps` 中声明的库是否在 `sdi.FDB` 中存在（不存在则 `KeyError`）
2. 循环依赖检测（抛 `RuntimeError`）
3. `StrategyDeps` 依赖的目标信号是否存在（不存在则 `KeyError`）

---

## 策略信号类型

### 目标权重（默认）

```python
MakeStrategy(signal_type="目标权重", init_cash=1e6, short_allowed=False)
```

- 信号值表示每个证券的目标持仓权重
- 权重范围通常 [0, 1]（不允许卖空）或可含负值（允许卖空）
- 框架自动将权重转换为买卖数量，考虑交易费用
- 权重之和应 ≤ 1（剩余为现金）

```python
# 等权分配示例
signal = pd.Series(0.0, index=selected_stocks)
signal[selected_stocks] = 1.0 / len(selected_stocks)  # 等权
```

### 买卖数量

```python
MakeStrategy(signal_type="买卖数量", init_cash=1e6, short_allowed=True)
```

- 信号值直接表示买卖数量（股数）
- 正值 = 买入，负值 = 卖出
- 框架直接按信号数量执行交易

```python
# 固定数量调仓
signal = pd.Series(0.0, index=all_stocks)
signal[buy_list] = 100     # 各买入 100 股
signal[sell_list] = -100   # 各卖出 100 股
```

---

## 常用策略模式

### 1. 均线交叉策略

```python
class MACrossStrategy(MakeStrategy):
    def genSignal(self, f, idt, x, last_price, cash, position_num, args):
        short_ma, long_ma = x[0], x[1]
        if short_ma is None or long_ma is None:
            return None

        signal = pd.Series(0.0, index=last_price.index)
        # 短均线上穿长均线 → 买入
        buy = (short_ma.iloc[-1] > long_ma.iloc[-1]) & (short_ma.iloc[-2] <= long_ma.iloc[-2])
        # 短均线下穿长均线 → 卖出
        sell = (short_ma.iloc[-1] < long_ma.iloc[-1]) & (short_ma.iloc[-2] >= long_ma.iloc[-2])

        n_buy = buy.sum()
        if n_buy > 0:
            signal[buy[buy].index] = 1.0 / n_buy  # 等权分配
        if sell.any():
            signal[sell[sell].index] = -1.0  # 清仓

        return signal
```

### 2. 动量反转策略

```python
class MomentumStrategy(MakeStrategy):
    def genSignal(self, f, idt, x, last_price, cash, position_num, args):
        returns = x[0]  # 过去 N 日收益率
        if returns is None or returns.empty:
            return None

        # 取最新一期的截面数据
        latest_return = returns.iloc[-1]

        top_n = args.get("top_n", 20)
        # 买入收益最高的 top_n 只
        ranked = latest_return.rank(ascending=False)
        selected = ranked[ranked <= top_n].index

        signal = pd.Series(0.0, index=latest_return.index)
        signal[selected] = 1.0 / top_n
        return signal
```

### 3. 多因子打分策略

```python
def defStrategy(sdi: StrategyDefInput) -> list:
    from QuantStudio.Factor import FactorOperator as fo

    # 多个因子截面标准化后合成
    scores = []
    for name in ["momentum", "volatility", "value"]:
        factor = sdi.Factors[name]
        scores.append(fo.zscore(factor))

    composite = sum(scores) / len(scores)

    class ScoringStrategy(MakeStrategy):
        def genSignal(self, f, idt, x, last_price, cash, position_num, args):
            score = x[0].iloc[-1]
            if score is None:
                return None
            top_n = args.get("top_n", 30)
            selected = score.rank(ascending=False) <= top_n
            signal = pd.Series(0.0, index=score.index)
            signal[selected[selected].index] = 1.0 / top_n
            return signal

    op = ScoringStrategy(
        signal_type=sdi.ModelArgs.get("signal_type", "目标权重"),
    )
    return [op(composite, last_price=sdi.Factors["close"])]
```

### 4. 网格交易策略

```python
class GridStrategy(MakeStrategy):
    def genSignal(self, f, idt, x, last_price, cash, position_num, args):
        close = x[0]
        if close is None or close.empty:
            return None

        latest = close.iloc[-1]
        grid_num = args.get("grid_num", 10)

        # 计算价格分位作为网格层级
        price_rank = close.rank(pct=True).iloc[-1]

        signal = pd.Series(0.0, index=latest.index)
        # 低价区 → 买入（高权重）
        signal[price_rank < 0.3] = 1.0 / grid_num
        # 高价区 → 卖出
        signal[price_rank > 0.7] = -1.0 / grid_num

        return signal
```

### 5. 条件过滤

```python
def genSignal(self, f, idt, x, last_price, cash, position_num, args):
    factor = x[0].iloc[-1]

    # 使用 sdi 中注入的状态因子过滤
    # （需要在 __STRATEGY_META__ FactorDeps 中声明 is_st, if_listed）
    ...
```

---

## 导入速查

策略定义脚本的标准导入集合：

```python
# 基础
import numpy as np
import pandas as pd

# StrategyDef 框架
from QSExt.StrategyDef.StrategyDefContent import StrategyDefInput

# QuantStudio 策略
from QuantStudio.BackTest.Strategy.Strategy import MakeStrategy

# 可选：因子算子（在 defStrategy 中构造策略输入时使用）
from QuantStudio.Factor import FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
```

**不要导入的：**
- `StrategyDef`、`StrategyMeta` — 策略定义脚本不需要构造这些对象，框架自动包装
- `StrategyDefSettings`、`StrategyDefInputBuilder` — 运行时由执行脚本管理
- `build_dep_sd` — 框架内部使用
