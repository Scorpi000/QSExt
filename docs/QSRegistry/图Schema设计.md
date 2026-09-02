# QSRegistry — 图 Schema 设计

> 返回 [总览](QSGraphDB设计.md)

## 节点类型

### Factor 节点

表示一个因子实例，是图中最核心的节点类型。

| 属性 | 类型 | 说明 |
|------|------|------|
| `QSID` | string | **唯一标识**，SHA-256 内容哈希，同 QSID 的因子行为一致 |
| `Name` | string | 因子名称（人类可读，不参与 QSID 计算） |
| `ClassName` | string | Python 类名（`PointOperation`、`TimeOperation`、`DataFactor` 等） |
| `ModulePath` | string | Python 完整模块路径 |
| `FactorClass` | string | 因子类别：`DataFactor` / `DerivativeFactor` / `FactorTableFactor` |
| `DataType` | string | 输出数据类型：`double` / `string` / `object` |
| `OperatorName` | string | 算子名称（仅 DerivativeFactor） |
| `OperatorType` | string | 算子类型：`Point` / `Time` / `Section` / `Panel`（仅 DerivativeFactor） |
| `OperatorQSID` | string | 算子 QSID（仅 DerivativeFactor） |
| `QSArgsJSON` | string | JSON 编码的参数集（排除 Operator 字段） |
| `MetaJSON` | string | JSON 编码的用户元信息字典 |
| `DataRef` | string | DataFactor 的数据引用（JSON） |
| `FactorTableQSID` | string | 所属因子表 QSID（仅 FactorTableFactor） |
| `NameInFT` | string | 在因子表中的因子名称（仅 FactorTableFactor） |
| `Embedding` | List[float] | 因子描述文本的嵌入向量（由 Ollama 生成） |
| `EmbeddingModel` | string | 生成 Embedding 所使用的模型名称 |
| `EmbeddingDim` | int | 嵌入向量的维度 |
| `CreatedAt` | datetime | 创建时间 |
| `UpdatedAt` | datetime | 最后更新时间 |

**FactorClass 分类说明：**

- `DataFactor`：叶子节点，持有内联数据（标量、Series、DataFrame），无依赖
- `DerivativeFactor`：由算子作用于描述子因子计算得到，有依赖
- `FactorTableFactor`：数据来源于外部因子表（如 HDF5DB、JYDB），通过 `属于因子表` 关系关联

### FactorOperator 节点

表示一个算子实例（计算逻辑的封装）。

| 属性 | 类型 | 说明 |
|------|------|------|
| `QSID` | string | **唯一标识** |
| `Name` | string | 算子名称（如 `log`、`rolling_mean`） |
| `ClassName` | string | Python 类名（如 `Log`、`RollingApply`） |
| `ModulePath` | string | Python 完整模块路径 |
| `OperatorType` | string | `Point` / `Time` / `Section` / `Panel` |
| `Arity` | int | 输入因子数量（None 表示可变） |
| `DataType` | string | 输出数据类型 |
| `Description` | string | 人类可读描述 |
| `ModelArgsJSON` | string | JSON 编码的模型参数字典 |
| `LookBackJSON` | string | JSON 编码的回溯窗口列表（Time/Panel 类型） |
| `CalculateRef` | string | 计算函数引用（JSON），用于重建自定义算子 |
| `IsCustom` | bool | 是否为 `makeFactorOperator` 创建的自定义算子 |
| `CreatedAt` | datetime | 创建时间 |
| `UpdatedAt` | datetime | 最后更新时间 |

### FactorTable 节点

表示一个因子表（数据集）。

| 属性 | 类型 | 说明 |
|------|------|------|
| `QSID` | string | **唯一标识** |
| `Name` | string | 因子表名称 |
| `FactorNamesJSON` | string | JSON 编码的因子名称列表 |
| `MetaDataJSON` | string | JSON 编码的表元信息 |
| `QSArgsJSON` | string | JSON 编码的 `ft._QSArgs.model_dump()`，用于跨 session 重建时保证 QSID 一致 |

### FactorDB 节点

表示一个因子库（数据源连接）。

| 属性 | 类型 | 说明 |
|------|------|------|
| `Name` | string | **唯一标识**，因子库名称 |
| `DBType` | string | 类型标识：`HDF5` / `JYDB` / `BaoStock` 等 |
| `ClassName` | string | Python 类名 |
| `ModulePath` | string | Python 完整模块路径 |
| `ConnectionJSON` | string | JSON 编码的连接参数 |

### Tag 节点

用户自定义的分类标签。

| 属性 | 类型 | 说明 |
|------|------|------|
| `Name` | string | **唯一标识**，标签名称 |
| `Description` | string | 标签描述 |

### RiskDB 节点 (`风险库`)

表示一个风险数据库（数据源连接）。

| 属性 | 类型 | 说明 |
|------|------|------|
| `Name` | string | **唯一标识**，风险库名称 |
| `DBType` | string | 类型标识：`RiskDB` / `HDF5RiskDB` 等 |
| `ClassName` | string | Python 类名 |
| `ModulePath` | string | Python 完整模块路径 |
| `ConnectionJSON` | string | JSON 编码的连接参数 |
| `CreatedAt` | datetime | 注册时间 |
| `UpdatedAt` | datetime | 最后更新时间 |

### RiskTable 节点 (`风险表`)

表示一个风险数据集（协方差矩阵、因子暴露等）。

| 属性 | 类型 | 说明 |
|------|------|------|
| `QSID` | string | **唯一标识** |
| `Name` | string | 风险表名称 |
| `ClassName` | string | Python 类名 |
| `ModulePath` | string | Python 完整模块路径 |
| `MetaDataJSON` | string | JSON 编码的表元信息 |
| `QSArgsJSON` | string | JSON 编码的参数集 |
| `CreatedAt` | datetime | 注册时间 |
| `UpdatedAt` | datetime | 最后更新时间 |

### FactorStorer 节点 (`因子存储器`)

表示一个因子数据存储器（QuantStudio `FactorStorer`），是计算图中负责将因子计算结果持久化写入目标因子库/表的节点。

| 属性 | 类型 | 说明 |
|------|------|------|
| `QSID` | string | **唯一标识**，继承 `FactorStorer.QSID`（内容哈希） |
| `Name` | string | 存储器名称（如 "FactorStorer"） |
| `ClassName` | string | Python 类名（`FactorStorer`） |
| `ModulePath` | string | Python 完整模块路径 |
| `TargetFDBName` | string | 目标因子库名称 |
| `TargetFDBType` | string | 目标因子库类型（`HDF5DB`、`SQLite3DB` 等） |
| `TargetTable` | string | 目标因子表名称 |
| `IfExists` | string | 写入方式：`update` / `replace` / `append` |
| `QSArgsJSON` | string | JSON 编码的参数集（TargetFDB 序列化为类型+名称引用） |
| `CreatedAt` | datetime | 注册时间 |
| `UpdatedAt` | datetime | 最后更新时间 |

### Optimizer 节点 (`组合优化器`)

表示一个策略优化引擎。

| 属性 | 类型 | 说明 |
|------|------|------|
| `QSID` | string | **唯一标识** |
| `Name` | string | 优化器名称 |
| `ClassName` | string | Python 类名（`CVXPC`、`MatlabPC` 等） |
| `ModulePath` | string | Python 完整模块路径 |
| `OptimizerType` | string | 优化器类型标识 |
| `Description` | string | 人类可读描述 |
| `QSArgsJSON` | string | JSON 编码的参数集 |
| `CreatedAt` | datetime | 注册时间 |
| `UpdatedAt` | datetime | 最后更新时间 |

## 关系类型

```
因子    -[:`依赖` {order: int}]-> 因子
因子    -[:`使用算子`]-> 算子
因子    -[:`属于因子表`]-> 因子表
因子    -[:`打标签`]-> 标签
因子表  -[:`属于因子库`]-> 因子库
风险表  -[:`属于风险库`]-> 风险库
回测    -[:`使用优化器`]-> 组合优化器
回测    -[:`依赖风险表`]-> 风险表
因子存储器 -[:`依赖`]->    因子
因子存储器 -[:`写入因子表`]-> 因子表
因子存储器 -[:`打标签`]->  标签
因子     -[:`存入因子表`]-> 因子表
策略       -[:`产生结果集`]->  回测结果集
回测结果集 -[:`存储于`]->      回测结果库
回测结果集 -[:`打标签`]->      标签
```

| 关系 | 方向 | 属性 | 语义 |
|------|------|------|------|
| `依赖` | 因子 → 因子 | `order: int` | 因子依赖（描述子），order 为 0-based 索引，保持 descriptor 顺序 |
| `使用算子` | 因子 → 算子 | 无 | DerivativeFactor 使用的算子 |
| `属于因子表` | 因子 → 因子表 | 无 | FactorTableFactor 属于某个因子表 |
| `打标签` | 因子 → 标签 | 无 | 因子被标记了某个标签 |
| `属于因子库` | 因子表 → 因子库 | 无 | 因子表属于某个因子库 |
| `属于风险库` | 风险表 → 风险库 | 无 | 风险表属于某个风险库 |
| `使用优化器` | 回测 → 组合优化器 | 无 | 策略使用该优化引擎 |
| `依赖风险表` | 回测 → 风险表 | 无 | 回测（风险模型）引用风险表数据 |
| `依赖` | 因子存储器 → 因子 | 无 | 因子存储器依赖该因子（将其数据持久化） |
| `写入因子表` | 因子存储器 → 因子表 | 无 | 存储器写入目标因子表（若目标表在因子库中存在但未注册，则自动注册后再建立关系） |
| `存入因子表` | 因子 → 因子表 | 无 | 因子数据被 FactorStorer 存入目标因子表（若目标表在因子库中存在但未注册，则自动注册后再建立关系） |
| `产生结果集` | 策略 → 回测结果集 | 无 | 策略产生该回测结果集 |
| `存储于` | 回测结果集 → 回测结果库 | 无 | 结果集存储在目标结果库中 |
| `打标签` | 回测结果集 → 标签 | 无 | 结果集被标记了某个标签 |

## 约束与索引

```cypher
-- 唯一性约束
CREATE CONSTRAINT factor_qsid IF NOT EXISTS
    FOR (f:`因子`) REQUIRE f.QSID IS UNIQUE;
CREATE CONSTRAINT operator_qsid IF NOT EXISTS
    FOR (o:`算子`) REQUIRE o.QSID IS UNIQUE;
CREATE CONSTRAINT table_qsid IF NOT EXISTS
    FOR (t:`因子表`) REQUIRE t.QSID IS UNIQUE;
CREATE CONSTRAINT fdb_name IF NOT EXISTS
    FOR (d:`因子库`) REQUIRE d.Name IS UNIQUE;
CREATE CONSTRAINT riskdb_name IF NOT EXISTS
    FOR (d:`风险库`) REQUIRE d.Name IS UNIQUE;
CREATE CONSTRAINT risktable_qsid IF NOT EXISTS
    FOR (t:`风险表`) REQUIRE t.QSID IS UNIQUE;
CREATE CONSTRAINT optimizer_qsid IF NOT EXISTS
    FOR (o:`组合优化器`) REQUIRE o.QSID IS UNIQUE;
CREATE CONSTRAINT tag_name IF NOT EXISTS
    FOR (t:`标签`) REQUIRE t.Name IS UNIQUE;
CREATE CONSTRAINT storer_qsid IF NOT EXISTS
    FOR (s:`因子存储器`) REQUIRE s.QSID IS UNIQUE;

-- 查询索引
CREATE INDEX factor_name IF NOT EXISTS FOR (f:`因子`) ON (f.Name);
CREATE INDEX factor_class IF NOT EXISTS FOR (f:`因子`) ON (f.FactorClass);
CREATE INDEX factor_op_name IF NOT EXISTS FOR (f:`因子`) ON (f.OperatorName);
CREATE INDEX factor_op_type IF NOT EXISTS FOR (f:`因子`) ON (f.OperatorType);
CREATE INDEX operator_name IF NOT EXISTS FOR (o:`算子`) ON (o.Name);
CREATE INDEX operator_type IF NOT EXISTS FOR (o:`算子`) ON (o.OperatorType);
CREATE INDEX fdb_type IF NOT EXISTS FOR (d:`因子库`) ON (d.DBType);
CREATE INDEX riskdb_type IF NOT EXISTS FOR (d:`风险库`) ON (d.DBType);
CREATE INDEX risktable_name IF NOT EXISTS FOR (t:`风险表`) ON (t.Name);
CREATE INDEX optimizer_type IF NOT EXISTS FOR (o:`组合优化器`) ON (o.OptimizerType);
CREATE INDEX storer_name IF NOT EXISTS FOR (s:`因子存储器`) ON (s.Name);
CREATE INDEX storer_target_table IF NOT EXISTS FOR (s:`因子存储器`) ON (s.TargetTable);

-- 向量索引
CREATE VECTOR INDEX factor_embedding IF NOT EXISTS
    FOR (f:`因子`) ON (f.Embedding)
    OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};
```

## 图结构示例

以一个典型的因子计算链为例：

```
ClosePrice(DataFactor) ── Log() ── PointOp("log_Close") ── Lag(5) ── TimeOp("lag5_log_Close")
```

对应的图结构：

```
(PointOp:`因子` {FactorClass: "DerivativeFactor", Name: "log_Close"})
    -[:`依赖` {order: 0}]->
(ClosePrice:`因子` {FactorClass: "DataFactor"})
PointOp -[:`使用算子`]-> (Log:`算子` {Name: "log"})

(LagOp:`因子` {FactorClass: "DerivativeFactor", Name: "lag5_log_Close"})
    -[:`依赖` {order: 0}]-> (PointOp)
LagOp -[:`使用算子`]-> (Lag5:`算子` {Name: "lag", Arity: 1})
```

## 回测节点类型

### Backtest 节点 (`回测`)

表示一个回测配置实例（基于 BTNode 的 QSID），同一配置多次运行幂等合并。

| 属性 | 类型 | 说明 |
|------|------|------|
| `QSID` | string | **唯一标识**，继承 BTNode.QSID（内容哈希，包含完整因子 DAG） |
| `Name` | string | 回测名称（如 "IC"、"因子截面相关性"） |
| `ClassName` | string | Python 类名（`IC`、`QuantilePortfolio`、`Strategy`...） |
| `ModulePath` | string | Python 完整模块路径 |
| `BacktestCategory` | string | 回测类别：`SectionFactor` / `Strategy` / `Risk` / `TimeSeriesFactor` / `PerformanceAnalysis` / `Event` |
| `QSArgsJSON` | string | JSON 编码的 `__QS_ArgClass__` 参数集 |
| `DTRangeJSON` | string | 时点范围（可选，记录最近一次运行的时点范围） |
| `CreatedAt` | datetime | 首次注册时间 |
| `UpdatedAt` | datetime | 最后更新时间 |

### BacktestResult 节点 (`回测结果`)

挂载在回测节点上的单项结果数据。

| 属性 | 类型 | 说明 |
|------|------|------|
| `ResultID` | string | **唯一标识**，`hash(bt_qsid + key + dtrange)` |
| `Key` | string | 结果键名（`"IC"`、`"统计数据"`、`"截面宽度"`、`"Report"`...） |
| `DataType` | string | 数据类型：`DataFrame` / `Series` / `scalar` / `str` / `dict` |
| `SummaryJSON` | string | 轻量摘要 JSON（shape, columns, 起止索引等），无需加载 HDF5 即可了解概况 |
| `DataRef` | string | HDF5 文件路径（存完整 DataFrame/Series/长文本），可为 null |
| `DTRangeJSON` | string | 本次运行的时点范围 |
| `CreatedAt` | datetime | 创建时间 |
| `UpdatedAt` | datetime | 最后更新时间 |

## 回测关系类型

```
回测   -[:`依赖`]->   因子       # 回测使用了哪些因子
回测   -[:`依赖`]->   回测       # 回测间的依赖（BTReport 依赖 BTNode）
回测   -[:`产生结果`]-> 回测结果  # 回测产出的结果数据
回测   -[:`产生报告`]-> 报告      # 回测产出的报告文件
回测   -[:`打标签`]->  标签       # 复用标签机制
因子   -[:`有报告`]->   报告      # 因子关联的报告
```

| 关系 | 方向 | 语义 |
|------|------|------|
| `依赖` | 回测 → 因子 | 回测使用了该因子作为输入 |
| `依赖` | 回测 → 回测 | 回测间的层次依赖（如 BTReport 聚合多个 BTNode） |
| `产生结果` | 回测 → 回测结果 | 回测产出的单项结果 |
| `产生报告` | 回测 → 报告 | 回测产出的报告文件 |
| `有报告` | 因子 → 报告 | 因子与报告的关联（直接查找因子有哪些报告） |
| `打标签` | 回测 → 标签 | 回测被标记了某个标签 |

## 回测约束与索引

```cypher
-- 唯一性约束
CREATE CONSTRAINT backtest_qsid IF NOT EXISTS
    FOR (b:`回测`) REQUIRE b.QSID IS UNIQUE;
CREATE CONSTRAINT backtest_result_id IF NOT EXISTS
    FOR (r:`回测结果`) REQUIRE r.ResultID IS UNIQUE;
CREATE CONSTRAINT report_id IF NOT EXISTS
    FOR (r:`报告`) REQUIRE r.ReportID IS UNIQUE;

-- 查询索引
CREATE INDEX backtest_name IF NOT EXISTS FOR (b:`回测`) ON (b.Name);
CREATE INDEX backtest_category IF NOT EXISTS FOR (b:`回测`) ON (b.BacktestCategory);
CREATE INDEX backtest_class IF NOT EXISTS FOR (b:`回测`) ON (b.ClassName);
CREATE INDEX backtest_result_key IF NOT EXISTS FOR (r:`回测结果`) ON (r.Key);
CREATE INDEX report_name IF NOT EXISTS FOR (r:`报告`) ON (r.Name);
CREATE INDEX report_scenario IF NOT EXISTS FOR (r:`报告`) ON (r.ScenarioName);
CREATE INDEX report_format IF NOT EXISTS FOR (r:`报告`) ON (r.Format);
```

## 报告节点类型

### Report 节点 (`报告`)

表示一份已生成的报告文件。报告保留在本地文件系统，图节点仅存储路径和元数据。

| 属性 | 类型 | 说明 |
|------|------|------|
| `ReportID` | string | **唯一标识**，`sha256(filepath + filesize + mtime)` 前16位 |
| `Name` | string | 报告名称（如 "动量因子 — 单因子测试报告"） |
| `FilePath` | string | 报告文件的本地绝对路径 |
| `Format` | string | 文件格式：`html` / `markdown` / `pdf` |
| `FileSize` | int | 文件大小（字节） |
| `ScenarioName` | string | 生成报告的场景名称（如 "single_factor"） |
| `FactorNames` | string | JSON 编码的关联因子名列表 |
| `FileMtime` | datetime | 文件最后修改时间 |
| `CreatedAt` | datetime | 注册时间 |
| `UpdatedAt` | datetime | 最后更新时间 |

## 回测图结构示例

```
(momentum:`因子` {FactorClass: "DerivativeFactor", Name: "momentum_1d"})
(return_1d:`因子` {FactorClass: "FactorTableFactor", Name: "Return_1D"})
(return_5d:`因子` {FactorClass: "FactorTableFactor", Name: "Return_5D"})

(IC:`回测` {BacktestCategory: "SectionFactor", ClassName: "IC", Name: "IC"})
    -[:`依赖`]-> (momentum)
    -[:`依赖`]-> (return_1d)
    -[:`产生结果`]-> (IC_Series:`回测结果` {Key: "IC", DataType: "DataFrame"})
    -[:`产生结果`]-> (IC_Stats:`回测结果` {Key: "统计数据", DataType: "DataFrame"})
    -[:`产生结果`]-> (IC_MA:`回测结果` {Key: "IC的移动平均", DataType: "DataFrame"})

(QuantilePF:`回测` {BacktestCategory: "SectionFactor", ClassName: "QuantilePortfolio"})
    -[:`依赖`]-> (momentum)
    -[:`依赖`]-> (return_5d)
    -[:`产生结果`]-> (PF_Returns:`回测结果` {Key: "组合收益率", DataType: "DataFrame"})

(BTReport:`回测` {BacktestCategory: "Other", ClassName: "BTReport"})
    -[:`依赖`]-> (IC)
    -[:`依赖`]-> (QuantilePF)
    -[:`产生结果`]-> (ReportHTML:`回测结果` {Key: "Report", DataType: "str"})
```

从这个图可以自然地回答：
- "momentum 因子被哪些回测用过？" → `IC`、`QuantilePF`
- "IC 回测产出了哪些结果？" → `IC序列`、`统计数据`、`IC移动平均`
- "BTReport 包了哪些子回测？" → `IC`、`QuantilePF`

## 策略 + 优化器 + 风险表示例

```
(momentum:`因子` {FactorClass: "DerivativeFactor", Name: "momentum_1d"})
(return_1d:`因子` {FactorClass: "FactorTableFactor", Name: "Return_1D"})

(cvx_pc:`组合优化器` {OptimizerType: "CVXPC", Name: "均值方差优化器"})
(cov_rt:`风险表` {Name: "协方差矩阵"})
    -[:`属于风险库`]-> (risk_db:`风险库` {Name: "HDF5RiskDB"})

(strategy:`回测` {BacktestCategory: "Strategy", ClassName: "OptimizerStrategy"})
    -[:`依赖`]-> (momentum)
    -[:`依赖`]-> (return_1d)
    -[:`使用优化器`]-> (cvx_pc)
    -[:`依赖风险表`]-> (cov_rt)
    -[:`产生结果`]-> (pnl:`回测结果` {Key: "PnL", DataType: "DataFrame"})
```

从这个图可以回答：
- "该策略使用了什么优化器？" → `CVXPC（均值方差优化器）`
- "该策略引用了哪些风险数据？" → `协方差矩阵`
- "协方差矩阵来自哪个风险库？" → `HDF5RiskDB`

## 因子存储器示例

```
(momentum:`因子` {FactorClass: "DerivativeFactor", Name: "momentum_1d"})
(return_1d:`因子` {FactorClass: "DerivativeFactor", Name: "return_1d"})

(hdf5_db:`因子库` {Name: "HDF5DB", DBType: "HDF5"})
(stock_ft:`因子表` {Name: "TestTable"})
    -[:`属于因子库`]-> (hdf5_db)

(storer:`因子存储器` {Name: "FactorStorer", TargetFDBName: "HDF5DB", TargetTable: "TestTable"})
    -[:`依赖`]-> (momentum)
    -[:`依赖`]-> (return_1d)
    -[:`写入因子表`]-> (stock_ft)

(momentum)-[:`存入因子表`]->(stock_ft)
(return_1d)-[:`存入因子表`]->(stock_ft)
```

从这个图可以回答：
- "momentum 因子被哪些存储器持久化？" → 查找 `(因子存储器)-[:依赖]->(momentum)`
- "哪些因子数据被存入 HDF5DB/TestTable？" → 查找 `(因子)-[:存入因子表]->(TestTable)`
- "momentum 因子被存入了哪些表？" → 查找 `(momentum)-[:存入因子表]->(因子表)`

## 回测结果库 / 回测结果集

### 回测结果库节点 (`回测结果库`)

表示一个回测结果存储后端（QuantStudio `BTResultDB`），对标的 `因子库` / `风险库`。

| 属性 | 类型 | 说明 |
|------|------|------|
| `Name` | string | **唯一标识**，结果库名称（如 "BTResultDB"） |
| `ClassName` | string | Python 类名（`HDF5BTResultDB`） |
| `ModulePath` | string | Python 完整模块路径 |
| `QSArgsJSON` | string | JSON 编码的参数集（如 MainDir） |
| `CreatedAt` | datetime | 注册时间 |
| `UpdatedAt` | datetime | 最后更新时间 |

### 回测结果集节点 (`回测结果集`)

表示一个策略回测结果集，以 GroupName 为唯一标识，连接策略和回测结果库。

| 属性 | 类型 | 说明 |
|------|------|------|
| `Name` | string | **唯一标识**，即 GroupName |
| `GroupName` | string | 同 Name，结果组名称（如 "A股/strategy_signals/MACrossStrategy"） |
| `MetadataJSON` | string | JSON 编码的元信息标签 |
| `CreatedAt` | datetime | 注册时间 |
| `UpdatedAt` | datetime | 最后更新时间 |

### 回测结果集关系类型

```
策略       -[:`产生结果集`]->  回测结果集   # 策略产生该结果集
回测结果集 -[:`存储于`]->      回测结果库   # 结果集存储在哪个结果库
回测结果集 -[:`打标签`]->      标签         # 复用标签机制
```

| 关系 | 方向 | 语义 |
|------|------|------|
| `产生结果集` | 策略 → 回测结果集 | 策略产生该回测结果集 |
| `存储于` | 回测结果集 → 回测结果库 | 结果集存储在目标结果库中 |
| `打标签` | 回测结果集 → 标签 | 结果集被标记了某个标签 |

### 回测结果集约束与索引

```cypher
-- 唯一性约束
CREATE CONSTRAINT bt_resultdb_name IF NOT EXISTS
    FOR (d:`回测结果库`) REQUIRE d.Name IS UNIQUE;
CREATE CONSTRAINT bt_resultset_name IF NOT EXISTS
    FOR (s:`回测结果集`) REQUIRE s.Name IS UNIQUE;

-- 查询索引
CREATE INDEX bt_resultdb_class IF NOT EXISTS FOR (d:`回测结果库`) ON (d.ClassName);
CREATE INDEX bt_resultset_group IF NOT EXISTS FOR (s:`回测结果集`) ON (s.GroupName);
```

### 回测结果集示例

```
(ma_cross:`策略` {Name: "MACrossStrategy", TargetTable: "strategy_signals_example"})

(bt_result_db:`回测结果库` {Name: "BTResultDB", ClassName: "HDF5BTResultDB"})

(result_set:`回测结果集` {Name: "A股/strategy_signals_example/MACrossStrategy"})
    -[:`存储于`]-> (bt_result_db)
    -[:`打标签`]-> (标签)

(ma_cross)-[:`产生结果集`]->(result_set)
```

从这个图可以回答：
- "MACrossStrategy 的回测结果存在哪里？" → `(策略)-[:产生结果集]->(回测结果集)-[:存储于]->(BTResultDB)`
- "BTResultDB 存储了哪些策略的结果？" → `(策略)-[:产生结果集]->(回测结果集)-[:存储于]->(BTResultDB)`
- "GroupName 为 'A股/...' 的结果集关联了哪个策略？" → `(策略)-[:产生结果集]->(回测结果集 {GroupName: ...})`

## 脚本节点（规划中）

计划引入 `脚本` 节点，将因子/策略定义脚本纳入计算图，支持源码级容灾和脚本间依赖分析。新增关系：`因子-[:定义于]->脚本`、`脚本-[:依赖脚本]->脚本`。详见 [脚本节点设计.md](脚本节点设计.md)。
