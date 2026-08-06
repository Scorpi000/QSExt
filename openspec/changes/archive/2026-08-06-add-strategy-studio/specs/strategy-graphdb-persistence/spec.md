# strategy-graphdb-persistence

## Purpose

在 QSGraphDB（Neo4j）中新增策略节点的完整 CRUD 能力，支持策略元数据、因子依赖关系、策略间依赖关系的存储和检索。

## ADDED Requirements

### Requirement: 策略节点存储

`QSGraphDB` SHALL 提供 `storeStrategies()` 方法，将策略列表及其依赖 DAG 批量写入 Neo4j。由于一个 StrategyDef 可包含多个策略实例（`StrategyList`），按实例逐个创建 `(:策略)` 节点。标签为 `(:策略)`，属性与 `__STRATEGY_META__` 对齐。

策略节点属性：

| 属性 | 来源 | 说明 |
|------|------|------|
| `Name` | `strategy_instance._QSArgs.Name` | 策略名称 |
| `QSID` | `strategy_instance.QSID` | 唯一标识 |
| `TargetTable` | `Meta.TargetTable` | 输出因子表名 |
| `IDType` | `Meta.IDType` | 证券类型 |
| `OperatorConfigJSON` | `Meta.OperatorConfig` 序列化 | 算子默认配置 JSON |
| `ClassName` | `type(strategy_instance).__name__` | MakeStrategy 子类名 |
| `ModulePath` | `type(strategy_instance).__module__` | 模块路径 |
| `MetaJSON` | `Meta` 完整序列化 | 全量元信息 JSON |
| `DefScriptPath` | `Meta.DefScriptPath` | 定义脚本文件路径 |
| `CreatedAt` | MERGE 时自动设置 | ISO-format UTC |
| `UpdatedAt` | `datetime.now()` | ISO-format UTC |
| `Embedding` | Ollama 嵌入向量 | 语义搜索用 |

#### Scenario: 按策略实例批量注册

- **WHEN** 调用 `gdb.storeStrategies(strategies, tags=tags_map)`，其中每个 StrategyDef 的 `StrategyList` 可能包含多个策略实例
- **THEN** 遍历每个 StrategyDef 的 `StrategyList`，为每个策略实例独立创建 `(:策略)` 节点，返回值为策略实例总数（而非 StrategyDef 个数）

#### Scenario: 重复注册幂等

- **WHEN** 对已存在于图库中的策略再次调用 `storeStrategies()`
- **THEN** 使用 MERGE 语义，更新 UpdatedAt 和 MetaJSON，不产生重复节点

#### Scenario: _serializeStrategy 接受两参数

- **WHEN** `_serializeStrategy(strategy_def, strategy_instance)` 被调用
- **THEN** 从 `strategy_def.Meta` 取元信息，从 `strategy_instance` 取实例属性（Name、QSID），从 `type(strategy_instance)` 取类信息（ClassName、ModulePath）

### Requirement: 策略依赖关系存储

`storeStrategies()` SHALL 同时创建策略的依赖关系：
- `(策略)-[:依赖因子]->(:因子)` — FactorDeps 中声明的因子依赖
- `(策略)-[:依赖策略]->(:策略)` — StrategyDeps 中声明的策略间依赖
- `(策略)-[:输出到]->(:因子表)` — 策略信号输出目标表
- `(策略)-[:打标签]->(:标签)` — 分类标签

#### Scenario: 存储策略依赖因子关系

- **WHEN** 策略的 `FactorDeps` 声明了 factor_a 和 factor_b
- **THEN** Neo4j 中创建 `(:策略)-[:依赖因子]->(:因子)` 两条关系，`order` 属性记录依赖顺序

#### Scenario: 存储策略间依赖关系

- **WHEN** 策略 A 的 `StrategyDeps` 声明了策略 B
- **THEN** Neo4j 中创建 `(策略A)-[:依赖策略]->(策略B)` 关系

### Requirement: 策略检索

`QSGraphDB` SHALL 提供策略检索方法，支持按名称、标签、依赖因子和语义搜索。

#### Scenario: 按名称搜索策略

- **WHEN** 调用 `gdb.searchStrategies(name="均线")`
- **THEN** 返回所有名称包含 "均线" 的策略节点，含 Name、QSID、Description、Tags 等属性

#### Scenario: 按依赖因子搜索

- **WHEN** 调用 `gdb.searchStrategies(factor_qsid="f_abc123")`
- **THEN** 返回所有依赖该因子的策略列表

#### Scenario: 语义搜索策略

- **WHEN** 调用 `gdb.searchStrategiesByDescription("趋势跟踪的均线策略")`
- **THEN** 通过向量索引返回语义最相似的策略，按相似度排序

### Requirement: 策略依赖图查询

`QSGraphDB` SHALL 提供策略依赖图的查询方法，包括上游依赖（策略用了哪些因子/策略）和下游影响（哪些策略/回测依赖此策略）。

#### Scenario: 查询策略依赖图

- **WHEN** 调用 `gdb.getStrategyDependencyGraph(strategy_qsid)`
- **THEN** 返回包含该策略及所有直接/间接上下游节点的子图，支持 Mermaid 可视化

#### Scenario: 查询策略的下游影响

- **WHEN** 调用 `gdb.getStrategyDependents(strategy_qsid)`
- **THEN** 返回所有依赖此策略的其他策略和回测列表

### Requirement: 策略重建

`QSGraphDB` SHALL 提供 `reconstructStrategy(qsid)` 方法，从图元数据重建策略的 MakeStrategy 子类定义（代码路径）和算子配置。实际策略实例化需要调用方提供因子依赖。

#### Scenario: 从图库获取策略代码路径

- **WHEN** 调用 `gdb.reconstructStrategy(qsid)` 或 `gdb.getStrategyCode(qsid)`
- **THEN** 返回策略的 `DefScriptPath` 路径，调用方可读取 `.py` 文件获取 `genSignal()` 实现

### Requirement: 策略更新和删除

`QSGraphDB` SHALL 提供策略元信息更新和节点删除方法。

#### Scenario: 更新策略元信息

- **WHEN** 调用 `gdb.updateStrategyMeta(qsid, meta_updates)`
- **THEN** 将新的键值合并到策略节点的 `MetaJSON` 和对应属性字段

#### Scenario: 删除策略

- **WHEN** 调用 `gdb.deleteStrategy(qsid)`
- **THEN** DETACH DELETE 该策略节点及其所有关系，但不删除其依赖的因子或子策略

### Requirement: 回测-策略关联

`QSGraphDB` SHALL 支持 `(回测)-[:运行策略]->(:策略)` 关系的创建和查询，记录回测使用了哪个策略。

#### Scenario: 回测完成后关联策略

- **WHEN** 一次策略回测完成
- **THEN** 在 Neo4j 中创建或更新 `(回测节点)-[:运行策略]->(策略节点)` 关系，`result_id` 属性指向回测结果
