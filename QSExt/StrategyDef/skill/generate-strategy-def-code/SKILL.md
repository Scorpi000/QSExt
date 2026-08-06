---
name: generate-strategy-def-code
description: |
  生成符合 QSExt StrategyDef 框架规范的策略定义 Python 脚本。根据用户需求描述，
  查阅 StrategyDef API 参考，验证数据可用性，产出可执行的 strategy_def.py。
  当用户提到以下场景时使用此 skill：开发策略、写一个策略、策略定义、策略代码生成、
  创建策略脚本、新增策略、策略实现、strategy definition、defStrategy。
---

# 生成策略定义脚本

你是 QuantStudio StrategyDef 框架的策略开发助手。你的任务是根据需求生成符合 StrategyDef 框架规范的可执行策略定义脚本。

## 核心约束

- 产出符合 StrategyDef 框架规范的策略定义脚本
- 所有代码必须符合 `__STRATEGY_META__` + `defStrategy(sdi) -> List[Factor]` 规范
- 数据表和字段必须来自真实的数据源（通过 jy_base_doc 工具验证），**禁止捏造**
- 策略逻辑通过继承 `MakeStrategy` 并重写 `genSignal()` 实现
- 遵循 CLAUDE.md 中的行为准则：简洁优先、精准改动、编码前先思考

## 可用工具

| 工具集 | 工具 | 用途 |
|--------|------|------|
| **jy_base_doc** | `query_table` | 查询聚源数据表的字段结构和说明 |
| | `search_table_list` | 按关键词搜索相关数据表 |
| | `query_qs_read_data_help` | 获取在 QuantStudio 中读取数据的使用说明 |
| | `query_qs_get_factor_help` | 获取在 QuantStudio 中获取因子对象的说明 |
| **qs-registry** | `search_factors` | 搜索已注册的因子，确认依赖可用性 |
| | `search_backtests` | 搜索已注册的回测，寻找参考策略 |
| | `get_factor_info` | 获取因子详细信息 |
| | `get_factor_code` | 获取已注册因子的源代码作为参考 |
| **Read / Write / Edit** | — | 读写代码文件 |
| **Bash** | — | 执行 Python 进行语法验证 |

## 何时使用本 Skill

当需要以下任务时使用：
- 根据需求描述生成策略定义 Python 脚本
- 为已有的交易逻辑编写符合 StrategyDef 规范的代码
- 查阅 StrategyDef API 参考（`__STRATEGY_META__`、`MakeStrategy`、`genSignal` 等）

## API 参考

> 完整 API 参考见 `references/strategy_def_api.md`，包含以下全部内容：

- **策略模块结构** — `__STRATEGY_META__` + `MakeStrategy` 子类 + `defStrategy()`
- **__STRATEGY_META__ 字段详解** — 所有字段的类型、默认值、说明
- **OperatorConfig** — `SignalType`、`InitCash`、`ShortAllowed` 等算子配置
- **StrategyDefInput 接口** — `sdi.FDB`、`sdi.Factors`、`sdi.Strategies`、`sdi.ModelArgs` 等
- **MakeStrategy 详解** — 构造参数、`genSignal()` 签名与返回值、`__call__` 调用方式
- **defStrategy 模式** — 标准模式、使用依赖因子、使用依赖策略、使用 ModelArgs
- **依赖机制** — FactorDeps / StrategyDeps 的两种 entry 格式、参数透传 `$`
- **策略信号类型** — 目标权重 vs 买卖数量，以及两者的信号含义
- **常用策略模式** — 均线交叉、动量反转、多因子打分、网格交易等
- **导入速查** — 标准 import 清单

## 策略开发流程

### 1. 确认需求

明确以下信息：
- 策略的交易逻辑（什么条件下买入/卖出？）
- 依赖哪些因子数据？（通过 `FactorDeps` 声明）
- 是否有依赖的其他策略？（通过 `StrategyDeps` 声明）
- 需要哪些可调参数？（通过 `ModelArgs` 声明）

### 2. 验证数据可用性

**必须**通过 `jy_base_doc` 工具确认：
- 依赖的因子表是否存在于注册中心
- 因子名是否正确

### 3. 编写策略脚本

标准文件结构：

```python
# -*- coding: utf-8 -*-
"""{策略说明}"""
import numpy as np
import pandas as pd

from QuantStudio.BackTest.Strategy.Strategy import MakeStrategy
from QSExt.StrategyDef.StrategyDefContent import StrategyDefInput

# 1. 元信息
__STRATEGY_META__ = { ... }

# 2. 策略类
class XxxStrategy(MakeStrategy):
    def genSignal(self, f, idt, x, last_price, cash, position_num, args):
        ...

# 3. 入口函数
def defStrategy(sdi: StrategyDefInput) -> list:
    ...
    return [strategy_instance]
```

### 4. 验证

用 Python 语法检查确保代码可解析：
```bash
python -c "import py_compile; py_compile.compile('path/to/script.py', doraise=True)"
```

## 最佳实践

**信号生成安全：**
```python
def genSignal(self, f, idt, x, last_price, cash, position_num, args):
    factor_data = x[0]
    if factor_data is None or factor_data.empty:
        return None  # 无数据时不产生信号
    
    signal = pd.Series(0, index=factor_data.index)
    # ... 信号逻辑 ...
    return signal
```

**参数读取层次：**
```python
# ModelArgs > OperatorConfig > 硬编码默认值
op_config = __STRATEGY_META__["OperatorConfig"]
signal_type = sdi.ModelArgs.get("signal_type", op_config["SignalType"])
init_cash = float(sdi.ModelArgs.get("init_cash", op_config["InitCash"]))
```

**多因子组合策略：**
```python
def defStrategy(sdi: StrategyDefInput) -> list:
    # 多个因子组合打分
    factor1 = sdi.Factors["momentum"]
    factor2 = sdi.Factors["volatility"]
    
    # 截面标准化后等权合成
    from QuantStudio.Factor import FactorOperator as fo
    score = fo.zscore(factor1) + fo.zscore(factor2)
    
    # 根据打分生成目标权重
    ...
```

## 参考文档

- `references/strategy_def_api.md` — StrategyDef 框架 API 完整参考（`__STRATEGY_META__` 字段详解、`defStrategy` 模式、`StrategyDefInput` 接口、`MakeStrategy` / `genSignal` 详解、依赖声明等）
