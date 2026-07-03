# QSRegistry — QuantStudio 计算图注册中心

## 目录

- [1. 背景与动机](#1-背景与动机)
- [2. 模块结构](#2-模块结构)
- [3. 图 Schema 概述](#3-图-schema-概述) → 详见 [图Schema设计.md](图Schema设计.md)
- [4. API 参考](#4-api-参考) → 详见 [API参考.md](API参考.md)
- [5. 序列化机制](#5-序列化机制) → 详见 [序列化机制.md](序列化机制.md)
- [6. Cypher 查询模式](#6-cypher-查询模式) → 详见 [Cypher查询模式.md](Cypher查询模式.md)
- [7. 使用示例](#7-使用示例) → 详见 [使用示例.md](使用示例.md)
- [8. 测试策略](#8-测试策略) → 详见 [测试策略.md](测试策略.md)
- [9. QSID 跨 Session 一致性问题](#9-qsid-跨-session-一致性问题) → 详见 [QSID一致性问题.md](QSID一致性问题.md)
- [10. MCP Server](#10-mcp-server) → 详见 [MCP-Server.md](MCP-Server.md)
- [11. 依赖与集成](#11-依赖与集成)
- [12. 未来扩展方向](#12-未来扩展方向)

---

## 1. 背景与动机

QuantStudio 以计算图（DAG）为核心架构：`Factor`、`BTNode`（回测/策略/风险模型）等 `__QS_Object__` 实例构成计算图的节点，通过 `Deps` 记录依赖关系。但这些计算图仅存在于运行时内存中，无持久化存储，导致以下问题：

- **无法跨会话复用**：计算图随进程结束而丢失，每次需重新构建
- **缺乏全局目录**：无法按名称、类型、标签等条件检索已有的因子、回测、策略
- **依赖关系不可追溯**：无法回答"哪些回测使用了某个因子"之类的拓扑查询
- **影响分析困难**：修改底层因子时，无法快速确定受影响的下游因子和回测
- **支撑实体无统一管理**：算子、组合优化器、风险库等不参与 DAG 执行但与计算节点密切相关的实体缺少注册和检索机制

本方案建立 `QSExt.QSRegistry` 模块作为 **QuantStudio 计算图注册中心**，以 Neo4j 图数据库为存储引擎，实现：

- **计算节点**（因子、回测）的存储、检索、重建计算和依赖分析
- **支撑节点**（算子、因子表、风险库、风险表、组合优化器）的注册和检索
- 报告文件的注册与溯源
- 通过 MCP Server 向 AI 编码助手暴露这些能力

---

## 2. 模块结构

```
QSExt/QSRegistry/
├── __init__.py              # 包初始化，模块级日志
├── api.py                   # 对外 API 导出
├── QSGraphDB.py         # Neo4j 图数据库实现（主文件）
└── _serialization.py        # 序列化/反序列化辅助函数

mcp/
└── qs_registry.py       # MCP Server（因子/回测/报告/风险表/优化器共 13 个工具，stdio 模式）
```

### `api.py` 导出内容

```python
from .QSGraphDB import QSGraphDB
```

### 顶层包集成

`QSExt/api.py` 中增加：

```python
from .QSRegistry.api import *
```

---

## 3. 图 Schema 概述

> 详见 [图Schema设计.md](图Schema设计.md)

### 节点类型一览

| 节点标签 | 唯一键 | 用途 |
|----------|--------|------|
| `因子` | `QSID` (SHA-256) | 因子实例，分为 DataFactor / DerivativeFactor / FactorTableFactor |
| `算子` | `QSID` | 计算逻辑封装（Log、Lag、RollingApply 等），因子重建时使用 |
| `因子表` | `QSID` | 数据集（如 HDF5 表、SQL 表），因子数据来源 |
| `因子库` | `Name` | 数据源连接（HDF5DB、JYDB 等） |
| `风险库` | `Name` | 风险数据存储（RiskDB） |
| `风险表` | `QSID` | 风险数据集（协方差矩阵、因子暴露等） |
| `组合优化器` | `QSID` | 策略优化引擎（CVXPC、MatlabPC 等） |
| `标签` | `Name` | 用户自定义分类标签 |
| `回测` | `QSID` | BTNode 实例（IC、Strategy、Risk 等），计算节点 |
| `回测结果` | `ResultID` | 回测产出的单项结果数据 |
| `报告` | `ReportID` | 已生成的报告文件（仅存路径和元数据） |

### 关系类型一览

| 关系 | 方向 | 语义 |
|------|------|------|
| `依赖` | 因子 → 因子 | 因子依赖（描述子），含 `order` 排序 |
| `使用算子` | 因子 → 算子 | DerivativeFactor 使用的算子 |
| `属于因子表` | 因子 → 因子表 | FactorTableFactor 的数据来源 |
| `属于因子库` | 因子表 → 因子库 | 因子表的存储后端 |
| `属于风险库` | 风险表 → 风险库 | 风险表的存储后端 |
| `使用优化器` | 回测 → 组合优化器 | 策略使用优化引擎 |
| `依赖风险表` | 回测 → 风险表 | 回测（风险模型）引用风险表数据 |
| `打标签` | 因子/回测 → 标签 | 分类标记 |
| `依赖` | 回测 → 因子 | 回测使用的因子 |
| `依赖` | 回测 → 回测 | 回测间层次依赖（如 BTReport） |
| `产生结果` | 回测 → 回测结果 | 回测产出的数据 |
| `产生报告` | 回测 → 报告 | 回测产出的报告文件 |
| `有报告` | 因子 → 报告 | 因子关联的报告 |

---

## 4. API 参考

> 详见 [API参考.md](API参考.md)

`QSGraphDB` 继承 `QSNeo4jObject`，提供以下 API 分类：

| 分类 | 方法 | 说明 |
|------|------|------|
| **存储** | `registerFactorDB`, `storeFactorTable`, `storeFactorOperator`, `storeFactors` | 因子及依赖 DAG 的批量持久化 |
| **检索** | `searchFactors`, `searchFactorsByDescription`, `getFactorByQSID`, `getDependencyGraph`, `getDescriptors`, `getDependents` | 关键词/语义搜索、拓扑查询 |
| **重建** | `reconstructFactor`, `reconstructOperator` | 从图元数据重建可计算的 Factor 对象 |
| **管理** | `deleteFactor`, `updateFactorMetaData`, `updateFactorTags`, `renameFactor` | 因子生命周期管理 |
| **分析** | `impactAnalysis`, `findSimilarFactors`, `getGraphStats`, `toMermaid` | 影响范围、相似因子、Mermaid 可视化 |
| **回测** | `storeBacktest`, `storeBacktestResults`, `searchBacktests`, `getBacktestByQSID`, `getBacktestResults`, `getFactorBacktests`, `deleteBacktest` | 回测注册、检索、结果管理 |
| **报告** | `storeReport`, `searchReports`, `getReport`, `getFactorReports`, `getBacktestReports`, `deleteReport` | 报告文件注册与检索 |
| **风险库** | `registerRiskDB`, `storeRiskTable`, `getRiskTableByQSID`, `searchRiskTables`, `linkBacktestRiskTable` | 风险库/表注册与检索 |
| **优化器** | `storeOptimizer`, `getOptimizerByQSID`, `searchOptimizers`, `deleteOptimizer`, `linkBacktestOptimizer` | 组合优化器注册与检索 |
| **工具** | `executeCypher` | 原始 Cypher 查询 |

---

## 5. 序列化机制

> 详见 [序列化机制.md](序列化机制.md)

核心要点：

- `_sanitizeForJSON` / `_desanitizeFromJSON` 处理 numpy 类型、datetime、函数引用等非标准 JSON 类型
- 三种因子类型（DataFactor / DerivativeFactor / FactorTableFactor）有各自的序列化策略
- DataFactor 的 Series/DataFrame 数据持久化到 HDF5 文件
- 自定义算子通过 `dill` 或模块引用序列化

---

## 6. Cypher 查询模式

> 详见 [Cypher查询模式.md](Cypher查询模式.md)

涵盖存储操作（MERGE upsert）、检索查询（多条件组合）、图遍历（依赖 DAG、传递闭包）、分析查询（影响范围、相似因子）和向量检索（ANN 近似最近邻）的完整 Cypher 语句参考。

---

## 7. 使用示例

> 详见 [使用示例.md](使用示例.md)

包含基本流程（连接→注册→存储→检索→重建）、向量语义检索、自定义算子注册、回测注册与检索、报告注册等完整代码示例。

---

## 8. 测试策略

> 详见 [测试策略.md](测试策略.md)

包含单元测试（序列化往返、各类型因子输出验证）和集成测试（连接生命周期、存储幂等性、往返重建、多层 DAG、多条件搜索、依赖遍历、影响分析等 10 个场景），通过环境变量控制 Neo4j 集成测试。

---

## 9. QSID 跨 Session 一致性问题

> 详见 [QSID一致性问题.md](QSID一致性问题.md)

记录 `storeFactors` → `reconstructFactor` 往返过程中 QSID 不一致的三层根因分析及修复方案：

1. **已修复**：`_sanitizeForJSON` numpy 类型检查顺序
2. **已部分修复**：`JYDB.getTable` FTArgs/DefaultArgs 合并导致 FactorTable QSID 变化
3. **待修复**：`SQL_Table.__QS_ArgClass__.__init__` 中 `AdditionalCondition` 非幂等

---

## 10. MCP Server

> 详见 [MCP-Server.md](MCP-Server.md)

基于 FastMCP 3.x 的 stdio MCP Server，将 QSGraphDB 能力暴露给 Claude Code。提供 13 个工具，支持通过 `QS_TOOLS` 环境变量按组选择性启用。

| 工具 | 组 | 说明 |
|------|-----|------|
| `search_factors` | factor | 语义向量检索 + 关键词回退 |
| `get_factor_info` | factor | 因子详情（含描述子、依赖、标签） |
| `get_factor_code` | factor | 因子定义源代码 |
| `search_backtests` | backtest | 回测列表搜索 |
| `get_backtest_info` | backtest | 回测详情（含依赖因子、结果摘要） |
| `get_backtest_result` | backtest | 回测结果数据（含 HDF5 读取） |
| `register_report` | report | 报告文件注册 |
| `search_reports` | report | 报告搜索 |
| `get_report_info` | report | 报告元信息 |
| `search_risk_tables` | risk_table | 风险表搜索 |
| `get_risk_table_info` | risk_table | 风险表详情 |
| `search_optimizers` | optimizer | 组合优化器搜索 |
| `get_optimizer_info` | optimizer | 组合优化器详情 |

**工具组过滤**：通过环境变量 `QS_TOOLS` 控制，支持 `all`（默认）/ `factor,backtest`（启用指定组）/ `-report`（排除指定组）。详见 [MCP-Server.md](MCP-Server.md)。

---

## 11. 依赖与集成

### 外部依赖

| 包 | 用途 | 安装方式 |
|---|------|---------|
| `neo4j` | Neo4j Python 驱动 | `pip install neo4j`（加入 `requirements_optional.txt`） |
| `dill`（可选） | 自定义算子序列化 | 已在框架可选依赖中 |
| `requests` | Ollama HTTP API 调用 | Python 标准依赖，框架已包含 |
| Ollama (外部服务) | 嵌入向量生成 | 需独立安装运行，模型: `bge-m3` 或 `qwen3-embedding:8b` |

### 与现有代码的集成

**需修改的文件：**

- `QuantStudio/api.py`：增加 `from .QSRegistry.api import *` 导出
- `requirements_optional.txt`：增加 `neo4j`

**不修改现有类**：`QSGraphDB` 独立于现有的 `FactorDB`/`WritableFactorDB` 体系，因为它存储的是图元数据而非因子数据。通过 `_FactorDBRegistry` 在重建时桥接到已有的 FactorDB 实例。

### 配置文件

支持 `~/QuantStudioConfig/QSGraphDBConfig.json` 或 `~/QuantStudioConfig/Neo4jDBConfig.json`（兼容旧配置）：

```json
{
    "IPAddr": "127.0.0.1",
    "Port": 7687,
    "User": "neo4j",
    "Pwd": "password",
    "DBName": "neo4j",
    "DataDir": "/path/to/data",
    "EmbeddingModel": "bge-m3",
    "EmbeddingDim": 1024,
    "OllamaBaseURL": "http://127.0.0.1:11434",
    "OllamaAPIKey": "ollama"
}
```

MCP Server 还支持以下环境变量：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `QS_TOOLS` | `all` | 启用的工具组，逗号分隔；`-group` 排除 |
| `EMBEDDING_MODEL` | `bge-m3` | 嵌入模型名称 |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama 服务地址 |
| `OLLAMA_API_KEY` | `ollama` | Ollama API Key |

---

## 12. 未来扩展方向

当前实现为 QSRegistry v3（因子 + 回测 + 风险库 + 优化器图数据库存储层），以下为可扩展方向：

- **因子版本管理** — 同一因子多次迭代时保留历史版本，支持 diff 比较和回滚
- **因子生命周期管理** — draft → testing → production 状态流转，标记哪些因子已通过回测验证
- **因子血缘追踪** — 关联数据源表名/字段名，追踪从数据源头到最终因子的完整链路
- **因子共享与协作** — 多人团队共享因子库，支持导入/导出因子包（序列化整棵依赖子树）
- **因子自动发现** — 与 FactorStorer 联动，定期扫描数据源自动注册新因子
- **因子评估元数据** — ~~在图节点中关联 IC、IR、换手率等绩效指标，支持按绩效筛选~~ ✅ 已实现（回测结果挂载）
- **风险库/表入图** — ~~RiskDB、RiskTable 注册到图数据库~~ ✅ 已实现
- **组合优化器入图** — ~~BasePC、CVXPC 注册到图数据库~~ ✅ 已实现
- **算子市场** — 独立管理自定义算子的注册、版本和共享
- **回测参数优化记录** — 同一回测配置下不同参数的多次运行结果对比
- **回测结果比较** — 支持多个回测结果的横向对比分析
- **调度集成** — 与定时任务集成，自动运行回测并注册结果到图数据库
