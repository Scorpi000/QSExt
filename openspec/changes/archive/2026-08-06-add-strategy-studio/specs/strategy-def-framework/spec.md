# strategy-def-framework

## Purpose

StrategyDef 策略定义框架，提供策略脚本的元信息约定、标准入口函数、依赖解析引擎和注册/执行管线。作为 QSWeb 策略工作台和策略持久化的基础层，与 FactorDef 框架对齐。

## ADDED Requirements

### Requirement: `__STRATEGY_META__` 元信息声明

每个策略脚本模块 SHALL 在顶层声明 `__STRATEGY_META__` 字典，描述策略的静态属性。框架通过此字典发现、筛选和注册策略，无需实际执行策略代码。

字典字段如下：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `TargetTable` | `str` | 是 | 策略信号输出的因子表名 |
| `IDType` | `str` | 是 | 证券类型，如 `"A股"` |
| `OperatorConfig` | `dict` | 否 | 策略算子默认配置，含 `SignalType`（默认 `"目标权重"`）、`InitCash`（默认 `1e6`）、`ShortAllowed`（默认 `False`） |
| `FactorDeps` | `dict[str, list]` | 否 | 依赖的因子声明，格式同 FactorDef（含价格因子，不单独区分） |
| `StrategyDeps` | `dict[str, dict]` | 否 | 依赖的策略声明，key 为目标策略的 `TargetTable`，value 为 `{因子名: 别名}` 映射 |
| `DBDeps` | `dict[str, str]` | 否 | 依赖的因子库，键为 `sdi.FDB` 中的逻辑名称，值为用途说明 |
| `ModelArgs` | `dict[str, str]` | 否 | 期望的模型参数，键为参数名，值为参数说明 |
| `Author` | `str` | 否 | 作者，默认 `"Anonymous"` |
| `Description` | `str` | 否 | 模块描述 |
| `MaxLookBack` | `int` | 否 | 最大回溯天数，默认 365 |
| `Tags` | `list[str]` | 否 | 检索标签 |
| `DefScriptPath` | `str` | 否 | 脚本路径，通常为 `__file__` |

#### Scenario: 声明完整的策略元信息

- **WHEN** 策略脚本在顶部声明 `__STRATEGY_META__` 包含 TargetTable、IDType、OperatorConfig、FactorDeps、StrategyDeps 和 Tags
- **THEN** 注册脚本可读取该字典，无需执行策略代码即可完成 Neo4j 注册

#### Scenario: 声明最小元信息

- **WHEN** 策略脚本只声明必填字段 `TargetTable` 和 `IDType`
- **THEN** 框架使用各可选字段的默认值（OperatorConfig 默认目标权重/1e6/不允许卖空）

### Requirement: `defStrategy` 标准入口

策略脚本模块 SHALL 暴露 `defStrategy(sdi: StrategyDefInput) -> list` 函数，作为策略实例化的唯一入口。一个模块可返回多个策略实例。框架在调用前完成依赖解析和注入。

#### Scenario: 依赖注入后调用 defStrategy

- **WHEN** 框架调用 `defStrategy(sdi)`
- **THEN** `sdi.Factors` 已包含 `FactorDeps` 声明的所有因子实例，`sdi.Strategies` 已包含 `StrategyDeps` 声明的所有策略实例，`sdi.FDB` 包含 `DBDeps` 声明的所有因子库连接

#### Scenario: defStrategy 返回策略实例列表

- **WHEN** 用户实现 `defStrategy` 从 `sdi.Factors` 取依赖因子、从 `sdi.Strategies` 取依赖策略、从 `sdi.ModelArgs` 读取参数覆盖值，构造 MakeStrategy 算子并调用之
- **THEN** 返回值为 `List[Factor]`，每个元素是一个策略实例（继承自 `PanelOperation` 的因子对象），框架统一包装为 `StrategyDef(StrategyList=[...])`

### Requirement: StrategyDefInput 输入上下文

`StrategyDefInput` SHALL 作为 `defStrategy` 的唯一入参，承载运行时上下文。其字段与 FactorDefInput 对齐，新增 `Strategies` 用于策略依赖。

#### Scenario: StrategyDefInput 包含完整上下文

- **WHEN** 框架构建 `StrategyDefInput` 实例
- **THEN** 实例包含 `FDB`（因子库字典）、`Factors`（依赖因子）、`Strategies`（依赖策略）、`ModelArgs`（模型参数）、`DTs`（计算时点）、`DTRuler`（时点标尺）、`IDs`（证券 ID）、`SectionIDs`（截面 ID）

### Requirement: StrategyMeta 类型定义

`StrategyMeta` SHALL 继承 `__QS_Args__`，为 `__STRATEGY_META__` 字典提供 Pydantic 类型校验。其字段与 `FactorMeta` 对齐，新增 `OperatorConfig`、`StrategyDeps`。

#### Scenario: 从字典构造 StrategyMeta

- **WHEN** 调用 `StrategyMeta(**__STRATEGY_META__)`
- **THEN** 返回经过校验的 StrategyMeta 实例，默认值自动填充（Author="Anonymous", MaxLookBack=365, SignalType="目标权重" 等）

### Requirement: StrategyDef 包装类

`StrategyDef` SHALL 继承 `__QS_Args__`，组合策略实例列表和元信息。一个定义文件可产出多个策略实例，统一包装在一个 `StrategyDef` 中。提供 `StrategyNames` 属性和 `getStrategy(name)` 方法按名称查找策略实例。

#### Scenario: 包装多个策略实例

- **WHEN** 调用 `StrategyDef(StrategyList=[s1, s2], Meta=StrategyMeta(**__STRATEGY_META__))`
- **THEN** 返回包含策略列表和元信息的包装对象，`StrategyList` 为已实例化的策略因子列表

#### Scenario: 按名称查找策略实例

- **WHEN** 调用 `sd.getStrategy("signal_name")`
- **THEN** 在 `StrategyList` 中查找 `Name` 匹配的策略实例，未找到抛出 `__QS_Error__`

### Requirement: build_dep_sd 依赖解析

`build_dep_sd()` SHALL 递归解析策略模块的 `StrategyDeps` 和 `FactorDeps` 依赖链，按拓扑序先解析因子依赖（复用 `build_dep_fd`），再解析策略依赖，最后调用 `defStrategy`。

#### Scenario: 策略依赖另一个策略

- **WHEN** 策略 A 的 `StrategyDeps` 声明依赖策略 B（其 `TargetTable`），策略 B 的 `FactorDeps` 声明依赖某些因子
- **THEN** 框架先解析因子 → 执行策略 B 的 `defStrategy` → 将结果注入策略 A 的 `sdi.Strategies` → 执行策略 A 的 `defStrategy`

#### Scenario: 检测循环依赖

- **WHEN** 策略 A 依赖策略 B，策略 B 又依赖策略 A
- **THEN** `build_dep_sd()` 抛出 `RuntimeError`，包含循环路径信息

### Requirement: Settings 配置系统

`StrategyDefSettings` SHALL 继承 `__QS_Args__`，提供与 `FactorDefSettings` 一致的配置加载链：settings 模块 → settings_local 覆盖 → 环境变量 `STRATEGYDEF_` 前缀 → 命令行参数。

#### Scenario: 从 settings.py 加载配置

- **WHEN** 调用 `StrategyDefSettings.from_module("settings")`
- **THEN** 加载 `QSExt.StrategyDef.conf.settings` 模块，提取大写变量构造 Settings 实例

### Requirement: 策略信号持久化

`run_strategy_def.py` SHALL 作为策略执行管线入口：加载 settings → 构建输入上下文 → 递归解析依赖 → 调用 `defStrategy` → 将策略信号因子写入目标 HDF5 表。

#### Scenario: 执行策略并写入 HDF5

- **WHEN** 运行 `python run_strategy_def.py --settings settings`
- **THEN** 策略信号因子数据写入 `TargetTable` 指定的 HDF5 表中，可通过 FactorDB 读取

### Requirement: 策略图数据库注册

`register_strategies_to_graphdb.py` SHALL 作为策略 Neo4j 注册入口：加载 settings → 读取策略模块 → 执行 `defStrategy` → 调用 `QSGraphDB.storeStrategies()` 批量注册。

#### Scenario: 注册策略到图数据库

- **WHEN** 运行 `python register_strategies_to_graphdb.py --modules my_strategies.ma_cross`
- **THEN** 策略节点和依赖关系写入 Neo4j，`(:策略)` 节点包含 Name、OperatorConfig、TargetTable、DefScriptPath 等属性
