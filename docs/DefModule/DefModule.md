# DefModule — 统一定义框架

DefModule 是 QSExt 的统一计算图定义框架，支持返回任意 Node 子类的列表，供 QSWeb 展开为可编辑计算图；保留原因子/策略运行与注册接口。

## 通用计算图定义

推荐 `defNode(di: DefInput) -> list[Node]`。返回列表是公开输出，完整依赖图通过节点的 Dependencies 展开。使用 `__GRAPH_META__` 声明公共元信息，通用定义无需 TargetTable。

```python
__GRAPH_META__ = {
    "MaxLookBack": 365,
    "NodeDeps": [{"Module": ".signal", "Output": "signal", "Alias": "signal",
                  "ModelArgs": {"window": "$window"}}],
}

def defNode(di):
    return [make_report(di.Nodes["signal"])]
```

`Output` 匹配依赖模块的公开输出名，Alias 在当前模块内唯一。`$name` 引用父模块参数，`$$name` 转义为字面值。FactorDeps/StrategyDeps 保持兼容，并填充 di.Factors/di.Strategies；所有显式依赖同时出现在 di.Nodes。新的 GRAPH_META 优先；两种旧元信息字段冲突时需用 GRAPH_META 消歧。

Python 使用 `build_graph_def([(module, model_args, meta_override)], di)`，得到 GraphBuildResult：requested 是按请求顺序排列的 GraphDef，definitions 是本次共享缓存，max_lookback 是依赖闭包最大回溯需求。GraphDef 的 NodeList/OutputNames 对应公开输出，FactorList/StrategyList/OtherNodeList 是派生视图。相同模块、参数和有效元信息在一次构图内只执行一次，不同实例不会按名称或 QSID 合并。

`prepare_input(plan, di)` 回调在依赖分析后、执行入口前运行，可根据 plan.max_lookback 准备日期。RequireDates=True 的模块缺少 DTs 时在调用入口前失败。新协议严格返回列表；同一对象重复返回只保留首次，同名不同对象自动生成不同输出名。

QSWeb 的脚本导入已接入该协议，并自动持久化可还原的上传 Node 类。示例 `examples/graph_example.py` 无需数据库，同时公开普通汇总节点和常量因子。未知外部类需先注册组件；上传类必须是模块级类，且不能带未建模的额外实例状态。

只需导出已注册组件构成的图时：

```bash
python -m QSExt.DefModule.scripts.export_graph --source-dir ./definitions --entry main.py --components-dir ./components --output ./graph.json
```

旧 build_dep_fd/build_dep_sd/build_dep 返回结构不变，使用同一解析核心，遇到普通 Node 输出时明确拒绝进入旧写库/注册流程。FactorScriptWriter 继续只支持 Factor。

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

`stock_cn_strategy_example.py` 返回 `strategy_from_signal`、`strategy_from_custom_class`
和 `strategy_from_timing_account` 三个账户。第三个使用 `MakeTimingAccount`：短期均线
不低于长期均线时看多，否则看空并清仓；仅价格大于零且两条均线齐备的标的入池。
`ModelArgs["timing_init_cash"]` 设置每个标的的固定入池本金，缺省时沿用 `init_cash`。
盈亏留在各自子账户复投，出池清仓后提走剩余现金，再入池重新注入本金。

配置 `BT_STORE` 后，执行脚本自动为该账户选择 `TimingAccountStats`，保存资金流水、
资金流调整净值、择时交易及胜率和赔率。单独生成报告时，使用
`TimingAccountReport(TimingAccountStats(account))`。

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

框架支持 Python `.ipynb` notebook 作为定义载体，与 `.py` 共用 `defNode(di: DefInput) -> list[Node]` 入口，兼容 `defFactor`、`defStrategy`。返回值可以包含因子、账户、统计、报告及普通自定义 Node，完整依赖由统一构图器展开，不再从全局变量自动收集策略对象。

为定义区域的最后一个代码单元添加 `node-def` 标签（兼容 `strategy-def`）。加载器按文件顺序提取该单元及之前的所有代码单元，之后的调试单元不执行；没有定义标签时明确报错。定义区域仅支持标准 Python，IPython 魔法命令和绘图、计算等交互代码应放在后面的调试区域。加载失败直接报告 notebook 路径、单元序号和行号，不回退执行全部单元。

`QSExt.DefModule.Source.extract_notebook_source(content, path)` 只返回提取源码和单元映射，不执行代码。`normalize_definition_sources(files)` 将 `.py`、`.ipynb` 混合文件统一为 Python 模块源码，拒绝同名格式冲突；`QSExt.Graph.import_definition` 复用此转换和原有构图流程。模块级自定义 Node 和算子的快照保存提取后的源码，因此修改历史输出、执行次数或调试区域不会改变组件身份。原 notebook 由 QSWeb 保存到 `users/<用户ID>/notebooks/<所选目录>/`，同批依赖保留相对路径，计算图库按当前账号发现这些定义，Jupyter 可以直接打开原文件。

示例 `stock_cn_strategy_example.ipynb` 的 `defNode` 使用 `di.FDB["BSDB"]` 和 `di.ModelArgs`，同时返回均线、策略账户、账户统计与报告；BaoStock 连接及本地执行仅放在调试单元。旧运行/注册流程仍只接受因子或策略，包含普通节点或报告的 notebook 应使用 `build_graph_def` 或 QSWeb 计算图导入。

仅返回因子/策略的 notebook 仍可在原运行配置中直接引用 `.ipynb` 文件路径：

```python
DEF_PROFILES = [{
    "strategy_modules": [
        "path/to/strategy_definition.ipynb",
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
3. `QS_*` 环境变量
4. 命令行 `--xxx` 参数

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
