# DefModule — 统一定义框架

DefModule 是 QSExt 的统一因子/策略定义框架，支持在同一个脚本中定义和运行因子与策略。

## 目录结构

```
QSExt/DefModule/
├── DefContent.py                          # 核心：DefInput / DefMeta / Def / DefProfile / DefSettings / DefInputBuilder
├── FactorScriptWriter.py                  # 因子脚本生成器
├── PortfolioStrategyOperator.py           # 组合策略算子库
├── utils.py                               # 工具：expand_glob(), load_notebook_as_module()
├── examples/
│   ├── mixed_example.py                   # 混合定义示例（同时产出因子和策略）
│   ├── stock_cn_factor_example1.py        # 因子示例
│   ├── stock_cn_factor_example2.py        # 因子示例（含 FactorDeps 依赖）
│   ├── stock_cn_strategy_example.py       # 策略示例
│   └── stock_cn_strategy_example.ipynb    # 策略示例（notebook 模式）
├── scripts/
│   ├── run_def.py                         # 统一执行脚本
│   ├── register_to_graphdb.py             # 统一图数据库注册
│   └── register_to_graphdb.ps1            # PowerShell 启动器
└── skills/
    ├── generate-def-code/                 # 统一 Skill（因子+策略+混合）
    ├── generate-factor-def-code/          # 因子专用 Skill
    └── generate-strategy-def-code/        # 策略专用 Skill
```

配置文件统一放在 `QSExt/RuntimeConfig/conf/`，示例见 `settings_example.py`。

定义脚本（业务模块）通过 `from QSExt.DefModule.DefContent import DefInput` 引用框架。

---

## 核心类

### DefInput — 统一运行时上下文

传递给 `defNode(di)` / `defFactor(fdi)` / `defStrategy(sdi)` 的入参，是因子定义和策略定义输入的统一超集：

| 字段 | 类型 | 说明 |
|------|------|------|
| `FDB` | `Dict[str, FactorDB]` | 可用因子库字典 |
| `DTs` | `List[datetime]` | 计算时点 |
| `DTRuler` | `List[datetime]` | 时点标尺（覆盖全部回溯范围） |
| `IDs` | `List[str]` | 证券 ID 列表 |
| `SectionIDs` | `List[str]` | 截面 ID |
| `ModelArgs` | `Dict` | 模型参数 |
| `Factors` | `Dict[str, Factor]` | 已解析的依赖因子（由框架根据 `FactorDeps` 注入） |
| `Strategies` | `Dict[str, Factor]` | 已解析的依赖策略（由框架根据 `StrategyDeps` 注入，策略场景专用） |
| `Debug` | `bool` | 调试模式 |
| `TDB` | `WritableFactorDB` | 写入目标库 |

### DefMeta — 统一静态元信息

合并 `FactorMeta` + `StrategyMeta` 超集字段。策略特有字段默认空值，因子模块可忽略。

| 字段 | 默认值 | 说明 | 来源 |
|------|--------|------|------|
| `TargetTable` | `""` | 输出因子表/策略信号表名 | 共有 |
| `IDType` | `""` | ID 类型 | 共有 |
| `Author` | `"Anonymous"` | 作者 | 共有 |
| `Description` | `""` | 描述信息 | 共有 |
| `MaxLookBack` | `365` | 最大回溯天数 | 共有 |
| `DefaultStartDT` | `2002-01-01` | 默认起始日 | 因子 |
| `DTType` | `"自定义"` | 时点类型 | 因子 |
| `Freq` | `"1d"` | 时点频率 | 因子 |
| `DefScriptPath` | `""` | 定义脚本路径 | 共有 |
| `OperatorConfig` | `{}` | 策略算子配置 | 策略 |
| `Tags` | `[]` | 检索标签 | 共有 |
| `FactorDeps` | `{}` | 依赖因子声明 | 共有 |
| `StrategyDeps` | `{}` | 依赖策略声明 | 策略 |
| `DBDeps` | `{}` | 因子库依赖 | 共有 |
| `ModelArgs` | `{}` | 期望的模型参数 | 共有 |
| `ResultKey` | `None` | 回测结果键名模板 | 策略 |

### Def — 统一定义容器

同时持有因子和策略实例，由框架自动归类：

```python
class Def:
    FactorList: List[Factor]      # 因子列表
    StrategyList: List[Factor]    # 策略实例列表
    Meta: DefMeta                 # 静态元信息
```

**自动归类逻辑**：模块返回的 `List[Factor]` 中，算子为 `MakeAccount` 实例的归入 `StrategyList`，其余归入 `FactorList`。

---

## 入口函数

DefModule 支持三种等价入口函数，框架按优先级 `defNode > defFactor > defStrategy` 查找：

```python
from QSExt.DefModule.DefContent import DefInput

# 推荐：统一入口，可同时返回因子和策略
def defNode(di: DefInput) -> list:
    ...

# 兼容旧因子模块
def defFactor(fdi: DefInput) -> list:
    ...

# 兼容旧策略模块
def defStrategy(sdi: DefInput) -> list:
    ...
```

---

## `__FACTOR_META__` / `__STRATEGY_META__` 约定

因子模块声明 `__FACTOR_META__`，策略模块声明 `__STRATEGY_META__`。框架读取对应字典构造 `DefMeta`。

### 因子模块示例

```python
__FACTOR_META__ = {
    "TargetTable": "stock_cn_factor_value",
    "IDType": "A股",
    "Description": "A股价值因子",
    "Author": "示例作者",
    "MaxLookBack": 365 * 4,
    "Tags": ["估值", "基本面", "value"],
    "FactorDeps": {
        "stock_cn_status": ["if_listed"],
        "stock_cn_day_bar_nafilled": ["total_cap"],
    },
    "DBDeps": {"JYDB": "聚源数据库"},
    "DefScriptPath": __file__,
}

def defFactor(fdi: DefInput) -> list:
    IsListed = fdi.Factors["if_listed"]
    MarketCap = fdi.Factors["total_cap"] * 10000
    # ... 因子计算 ...
    return [factor]
```

### 策略模块示例

```python
__STRATEGY_META__ = {
    "TargetTable": "stock_cn_strategy_example",
    "IDType": "A股",
    "Description": "均线交叉策略",
    "OperatorConfig": {
        "SignalType": "目标权重",
        "InitCash": 1e6,
        "ShortAllowed": False,
    },
    "DBDeps": {"BSDB": "BaoStock"},
    "ModelArgs": {"short_window": "短期均线窗口", "long_window": "长期均线窗口"},
    "MaxLookBack": 120,
    "DefScriptPath": __file__,
}

def defStrategy(sdi: DefInput) -> list:
    BSDB = sdi.FDB["BSDB"]
    close = BSDB.getTable("A股K线数据").getFactor("close")
    # ... 策略构建 ...
    return [strategy_instance]
```

### 混合模块示例

```python
__FACTOR_META__ = {
    "TargetTable": "stock_cn_mixed_example",
    "IDType": "A股",
    "Description": "混合定义示例：同时产出因子和策略",
    "DBDeps": {"BSDB": "BaoStock"},
    "DefScriptPath": __file__,
}

def defNode(di: DefInput) -> list:
    items = []
    BSDB = di.FDB["BSDB"]
    FT = BSDB.getTable("A股K线数据", args={"LookBack": 0})
    close = FT.getFactor("close")
    items.append(FT.getFactor("open"))  # 因子

    # 策略
    Signal = fo.Where()(1, fo.RollingMean(5)(close) >= fo.RollingMean(20)(close), 0)
    Signal = Signal / fo.Aggregate(aggr_func=np.nansum)(Signal)
    strategy = MakeAccount(signal_type="目标权重", init_cash=1e6)(last_price=close, signal=Signal)
    items.append(strategy)  # 策略（MakeAccount 算子，自动归类）

    return items
```

---

## FactorDeps 格式

```python
"FactorDeps": {
    "依赖表名": [
        "因子名",                                          # 直接取因子
        "*",                                               # 该表全部因子
        "$model_args_key",                                 # $ 前缀：从 ModelArgs 动态取因子名
        {"Name": "orig_name", "Alias": "alias"},           # 取因子并重命名
        {"Name": "*", "ModelArgs": {"key": "$parent_key"}},# 传递 ModelArgs 给依赖模块
    ],
}
```

## StrategyDeps 格式

```python
"StrategyDeps": {
    "依赖策略的模块路径": [
        {"Name": "信号名", "Alias": "别名"},                  # 引用依赖策略的信号
        {"Name": "信号名", "ModelArgs": {"k": "$parent_key"}},# 透传参数
    ],
}
```

---

## Notebook 定义

框架支持 `.ipynb` notebook 作为定义载体。通过 cell tag（`node-def` 或 `strategy-def`）标记核心 cell，框架只执行带 tag 的 cell。从执行结果中收集 `MakeAccount` 实例作为策略输出。

在配置中直接引用 `.ipynb` 文件路径：

```python
DEF_PROFILES = [{
    "strategy_modules": [
        "QSExt/DefModule/examples/stock_cn_strategy_example.ipynb",
    ],
}]
```

---

## 运行时配置

配置文件是 Python 模块，支持 `__INHERIT_FROM__` 链式继承。

### 三种 Profile 格式

| 格式 | 配置项 | collect_mode | 说明 |
|------|--------|-------------|------|
| 仅因子 | `FACTOR_PROFILES` | `"factor"` | 只收集 `FactorList` |
| 仅策略 | `STRATEGY_PROFILES` | `"strategy"` | 只收集 `StrategyList` |
| 混合 | `DEF_PROFILES` | `"both"` | 同时收集，优先级最高 |

```python
# 混合配置示例
DEF_PROFILES = [
    {
        "id_selection": "全部A股",
        "section_id_list": "全部A股",
        "factor_modules": ["my_project.factor_defs.stock_cn_factor_value"],
        "strategy_modules": ["my_project.strategies.ma_cross"],
        "target_db": "TDB",
    },
]
```

### 配置覆盖优先级（由低到高）

1. `__INHERIT_FROM__` 父模块
2. 当前模块变量
3. `settings_local.py`（不入库）
4. `QS_*` 环境变量
5. 命令行 `--xxx` 参数

---

## 执行脚本

### run_def.py — 统一执行入口

```bash
python -m QSExt.DefModule.scripts.run_def
python -m QSExt.DefModule.scripts.run_def --settings settings_prod
python -m QSExt.DefModule.scripts.run_def --use-proxy --register-graph
python -m QSExt.DefModule.scripts.run_def --debug --end-dt 2026-06-30
python -m QSExt.DefModule.scripts.run_def --dry-run
```

| 参数 | 说明 |
|------|------|
| `--settings`, `-s` | 配置模块路径 |
| `--debug`, `-d` | 调试模式 |
| `--dry-run`, `-n` | 仅分析，不执行 |
| `--end-dt` | 截止日期 |
| `--lookback` | 回溯天数 |
| `--workers`, `-w` | 并发 worker 数 |
| `--use-proxy` | 使用代理因子库 |
| `--register-graph` | 同时注册到图数据库 |

### register_to_graphdb.py — 图数据库注册

```bash
python -m QSExt.DefModule.scripts.register_to_graphdb
python -m QSExt.DefModule.scripts.register_to_graphdb --tags 动量 实验
python -m QSExt.DefModule.scripts.register_to_graphdb --skip-embedding
```

包含策略特有注册逻辑：`storeStrategies()`、`storeBTResultDB()`、`storeBTResultSet()`、表-FDB关系注册。

---

## 回测结果存储

配置 `BT_STORE` 后，策略流水线自动构建 `AccountStats → BTStorer` 节点链，将回测结果持久化到 `HDF5BTResultDB`。

```python
BT_STORE = {
    "name": "BTResultDB",
    "class": "HDF5BTResultDB",
    "args": {"MainDir": r"D:\Data\BTResult"},
}
```

---

## 相关文档

- [FactorScriptWriter](FactorScriptWriter.md) — 因子脚本生成器
