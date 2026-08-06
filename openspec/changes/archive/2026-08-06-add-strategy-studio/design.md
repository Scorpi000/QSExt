# Design: add-strategy-studio

## Context

当前 QSWeb 的回测工作台（BacktestStudio）仅支持模块化因子分析（IC、分位数组合、Fama-MacBeth 等），通过声明式 `_BT_NODE_BUILDERS` 字典驱动。用户无法在 Web 端编写和调试自定义交易策略。同时，QuantStudio 核心框架已提供完整的策略基类（`MakeStrategy` / `MakeAccount` / `AccountReport`），但缺少策略的持久化和 Web 化管理能力。

本次变更参照 FactorDef 架构，新增 StrategyDef 框架、Neo4j 策略持久化和 QSWeb 策略工作台。

### 约束

- 必须与 FactorDef 保持架构一致（相同的模式、命名约定、文件结构）
- 必须复用 QSWeb 现有的 TaskManager（异步任务）、FactorPool（全局因子池）、QSBridge（桥接层）
- 必须兼容现有 `ResultNode` 树结构（策略回测结果与模块化回测结果格式统一）
- Neo4j 图模型扩展必须与现有 `QSGraphDB` 的节点/关系命名一致

## Goals / Non-Goals

**Goals:**
- StrategyDef 框架：`__STRATEGY_META__` 约定、`defStrategy()` 标准入口、`build_dep_sd()` 依赖解析、`run_strategy_def.py` 执行管线
- Neo4j `(:策略)` 节点 CRUD + 依赖关系存储
- QSWeb `/strategy` 页面：策略列表/搜索、Monaco 编辑器、参数配置、回测执行、结果可视化
- 策略信号作为因子持久化到 HDF5（与 FactorDef 的 `TargetTable` 对齐）

**Non-Goals:**
- 策略版本管理（多版本并存）——第一版直接覆盖
- 策略参数自动优化/扫描——属于后续功能
- 可视化策略构建器（低代码拖拽）——代码编辑器优先
- 策略 marketplace 或分享功能

## Decisions

### 1. StrategyDef 与 FactorDef 的架构对齐策略

**决定**：StrategyDef 在整体结构上镜像 FactorDef，但简化无意义的对称。

- `StrategyDefContent.py`：定义 `StrategyDefInput`、`StrategyMeta`、`StrategyDef`、`build_dep_sd()`
- `StrategyDefSettings` + `StrategyDefInputBuilder`：与 FactorDef 同模式
- `run_strategy_def.py`：settings → build → defStrategy → HDF5
- `register_strategies_to_graphdb.py`：同模式注册到 Neo4j

**理由**：策略信号未来作为因子存储（TargetTable → HDF5），需要完整的执行管线。与 FactorDef 保持一致降低学习成本和维护负担。

**备选方案**：
- 极简方案（只注册 Neo4j，不写 HDF5）→ 放弃，因为策略信号需要被下游因子/策略引用
- 全新架构（不用 FactorDef 模式）→ 放弃，增加认知负担且与现有生态割裂

### 2. `OperatorConfig` 复合字段设计

**决定**：将 `SignalType`、`InitCash`、`ShortAllowed` 聚合为 `OperatorConfig` 嵌套字段，而非平铺在 `__STRATEGY_META__` 顶层。

```python
"OperatorConfig": {
    "SignalType": "目标权重",   # 默认 "目标权重"
    "InitCash": 1e6,           # 默认 1e6
    "ShortAllowed": False,     # 默认 False
}
```

**理由**：这三个字段是 MakeStrategy 算子的构造参数，语义上属于一组。聚合后元信息顶层更简洁，扩展新算子参数时只需在此嵌套中添加。

### 3. `StrategyDeps` 与 `FactorDeps` 分离

**决定**：策略依赖放在独立的 `StrategyDeps` 字段，不从 `FactorDeps` 中混合解析。

```python
"FactorDeps": {                         # 依赖的因子
    "market_data": ["close"],
    "technical_indicators": ["ma_20"],
},
"StrategyDeps": {                       # 依赖的策略
    "grid_trading": {"Signal": "grid_signal"},
},
```

在 `StrategyDefInput` 中对应两个独立字段：`sdi.Factors` 和 `sdi.Strategies`。

**理由**：
- 语义清晰：因子来自因子表，策略来自策略模块，解析路径不同
- Neo4j 关系不同：`[:依赖因子]` vs `[:依赖策略]`
- 解析时机不同：因子依赖先解析（复用 `build_dep_fd`），策略依赖后解析（递归执行 `defStrategy`）

### 4. 价格因子不单独区分

**决定**：价格因子作为普通因子声明在 `FactorDeps` 中，不再设 `PriceFactor` 专用字段。

**理由**：`MakeStrategy.__call__` 中 `last_price` 是必填参数，但它是从 `sdi.Factors` 中取出的普通 Factor 对象。用 `FactorDeps` 声明 + 用户在 `defStrategy` 中手动指定哪个是价格因子，语义更一致。

### 5. Neo4j 策略节点设计

**决定**：`(:策略)` 为独立标签（非 `(:因子)` 的子类型），策略信号因子同时作为 `(:因子)` 节点存在。

```
(策略:Strategy)                        ← 策略元数据节点
    QSID, Name, TargetTable, IDType
    OperatorConfigJSON, MetaJSON
    DefScriptPath, CreatedAt, UpdatedAt

(策略)-[:依赖因子]->(:因子)             ← 复用现有因子节点
(策略)-[:依赖策略]->(:策略)             ← 策略间依赖
(策略)-[:输出到]->(:因子表)             ← TargetTable
(策略)-[:打标签]->(:标签)

策略信号因子 (另存为 :因子)              ← 策略执行后的产物
(因子)-[:属于策略]->(:策略)             ← 反向关联
```

**理由**：策略和因子是不同的语义实体（策略是过程、因子是数据），独立标签使查询更精确（"搜索所有策略" vs "搜索所有因子"）。策略信号作为 `(:因子)` 单独存储便于在因子工作台中复用。

### 6. QSWeb 前端架构

**决定**：策略工作台为独立页面 `/strategy`，采用左右分栏布局。左侧为策略列表+配置面板，右侧使用 Tab 切换「策略代码」和「回测结果」。代码编辑器使用 Monaco Editor（`@monaco-editor/react`）。回测结果复用现有 `ResultTree` + `ResultLeaf` 组件（Series→Plotly 折线图，DataFrame→Table，Scalar→数值卡片）。

未运行回测时仅显示策略代码 Tab，运行后出现回测结果 Tab，回测完成通过 `onResultReady` 回调自动切换到结果 Tab。

```
StrategyStudio/
├── index.tsx              # 页面主组件（左右分栏，右侧 Tab 切换）
├── StrategyList.tsx       # 策略列表/搜索面板
├── StrategyEditor.tsx     # Monaco 代码编辑器封装
├── StrategyConfig.tsx     # 参数配置面板（OperatorConfig + 日期范围，使用 dayjs）
└── StrategyResult.tsx     # 回测结果可视化（复用 ResultTree + ResultLeaf，轮询检查 data.type）
```

**备选方案**：作为 BacktestStudio 的子 Tab → 放弃，两者工作流差异大（写代码迭代 vs 选模块配参数）。

### 7. 回测执行路径

**决定**：策略回测不走 `_BT_NODE_BUILDERS` 声明式路径，而是在 `QSBridge` 中新增 `run_strategy_backtest()` 方法。

```
POST /api/strategy/backtest
    → StrategyService.run_backtest()
    → QSBridge.run_strategy_backtest()
    → importlib 加载策略模块
    → 从已连接的因子库获取 IDs 和 DTs（未连接时返回明确错误）
    → 构造 StrategyDefInput (FDB, Factors, Strategies, ModelArgs, DTs, IDs)
    → defStrategy(sdi) → List[Factor] 策略实例列表
    → 取第一个策略实例 → AccountReport(strategy_factor)
    → Engine.run([AccountReport], context,
        fwd_data_list=[FactorLocalContext(DTs=dts, IDs=ids)])
    → _output_to_tree(output)
    → ResultNode
```

策略保存/注册需要 `QSWebConfig.yaml` 中 `strategy_def.settings_path` 必填，通过 `register_strategies_to_graphdb.main()` 走完整管线（含 JYDB 连接、defStrategy 执行）注册到 Neo4j。

**理由**：策略回测的输入是"代码 + 依赖 + 参数"，与模块化回测的"模块 key + 因子列表"输入完全不同，不适合复用现有 `_build_node_sync`。

## Risks / Trade-offs

- **[Risk] 动态代码执行安全性**：策略代码是用户编写的 Python 代码，`importlib` + `Engine.run()` 在服务器进程内执行。
  → **Mitigation**：策略代码运行在已有的 Engine 沙箱中（多进程执行），但 importlib 加载在服务器进程。后续可考虑 Docker 隔离。

- **[Risk] 策略依赖策略时的循环引用**：如果策略 A 依赖策略 B，策略 B 又依赖策略 A。
  → **Mitigation**：`build_dep_sd()` 维护 `_resolving` 集合，检测到重复 TargetTable 时抛出 `RuntimeError`。

- **[Risk] Neo4j Schema 膨胀**：新增 `(:策略)` 标签、多个关系类型和索引。
  → **Mitigation**：总量可控（1 个新标签、5 个新关系类型、3 个新索引），与现有的 10+ 标签/20+ 关系相比增量小。

- **[Trade-off] StrategyDefInput 包含 DTs/IDs 但不总是使用**：定义时这些字段可能为空。回测时才填充。
  → 与 `FactorDefInput` 保持一致，定义时字段留空是已建立的行为模式。

## Open Questions

1. **回测基准（Benchmark）**：`AccountReport` 支持 `bmk_nv` 参数做相对表现。第一版是否需要在 UI 中暴露基准因子选择？

2. **策略信号的 FactorStorer**：策略信号写入 HDF5 时是否需要类似 FactorDef 的 `FactorStorer` 机制，还是简化为直接写入？

## Resolved Questions

1. **策略脚本约定目录**：通过 `QSWebConfig.yaml` 的 `strategy_def.scripts_dir` 配置（默认 `~/StrategyDef/Scripts`），不支持多目录。

2. **Neo4j 注册方式**：保存策略时要求 `strategy_def.settings_path` 必填，通过 `register_strategies_to_graphdb.main()` 走完整管线注册。不再支持无 settings_path 的最小化注册路径。

3. **StrategyDef 包装类设计**：`StrategyDef` 使用 `StrategyList: List[Factor]`（支持一个定义文件产出多个策略实例），不再使用单独的 `StrategyInstance`/`StrategyClass` 字段。`defStrategy` 返回 `List[Factor]`。
