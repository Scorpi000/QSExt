# QSRegistry — MCP Server

> 返回 [总览](QSGraphDB设计.md)

## 概述

基于 FastMCP 3.x 构建的本地 stdio MCP Server，将 QSGraphDB 的核心能力暴露给 Claude Code 等 MCP 客户端。部署为本地 stdio 模式，因为需要访问本地 Neo4j、Ollama 和文件系统。

**文件位置**：`mcp/qs_registry.py`

## 架构

```
Claude Code (.mcp.json)           MCP Server (stdio)           QSGraphDB
      │                              │                            │
      ├── search_factors ────────────┼── searchFactorsByDescription ──┤
      │                              │   (fallback: searchFactors)    │
      ├── get_factor_info ───────────┼── getFactorByQSID ────────────┤
      │                              │   getDescriptors               │
      │                              │   getDependents                │
      ├── get_factor_code ───────────┼── getFactorByQSID ────────────┤
      │                              │   标签推断 → importlib → 文件  │
      ├── search_backtests ──────────┼── searchBacktests ────────────┤
      │                              │   (name/category/factor_qsid)  │
      ├── get_backtest_info ─────────┼── getBacktestByQSID ──────────┤
      │                              │   getBacktestResults           │
      ├── get_backtest_result ───────┼── getBacktestResult ──────────┤
      │                              │   HDF5 读取 + 摘要             │
      ├── register_report ───────────┼── storeReport ────────────────┤
      │                              │   本地文件 → 节点 + 关系      │
      ├── search_reports ────────────┼── searchReports ──────────────┤
      ├── get_report_info ───────────┼── getReport + 关联因子/回测   │
      ├── search_risk_tables ────────┼── searchRiskTables ───────────┤
      ├── get_risk_table_info ───────┼── getRiskTableByQSID ─────────┤
      ├── search_optimizers ─────────┼── searchOptimizers ───────────┤
      ├── get_optimizer_info ────────┼── getOptimizerByQSID ─────────┤
```

GDB 为懒加载单例，首次调用时初始化 Neo4j 和 Ollama 连接。

## 配置加载

| 配置项 | 来源 | 说明 |
|--------|------|------|
| Neo4j 连接 | `~/QuantStudioConfig/Neo4jDBConfig.json` | IPAddr, Port, User, Pwd, DBName |
| Ollama 地址 | 环境变量 `OLLAMA_BASE_URL` | 默认 `http://127.0.0.1:11434` |
| Ollama API Key | 环境变量 `OLLAMA_API_KEY` | 默认 `ollama` |
| 嵌入模型 | 环境变量 `EMBEDDING_MODEL` | 默认 `bge-m3`(1024维)；也支持 `qwen3-embedding:8b`(4096维) |
| 工具过滤 | 环境变量 `QS_TOOLS` | 默认 `all`；详见下方 [工具组过滤](#工具组过滤) |

## 工具组过滤

通过 `QS_TOOLS` 环境变量控制暴露哪些工具，适用于只想暴露特定功能子集的部署场景。

| 组名 | 包含工具 |
|------|---------|
| `factor` | `search_factors`, `get_factor_info`, `get_factor_code` |
| `backtest` | `search_backtests`, `get_backtest_info`, `get_backtest_result` |
| `report` | `register_report`, `search_reports`, `get_report_info` |
| `risk_table` | `search_risk_tables`, `get_risk_table_info` |
| `optimizer` | `search_optimizers`, `get_optimizer_info` |

**使用示例**：

```bash
# 全部启用（默认）
QS_TOOLS=all python mcp/qs_registry.py

# 仅启用因子和回测
QS_TOOLS=factor,backtest python mcp/qs_registry.py

# 排除报告和风险表
QS_TOOLS=-report,-risk_table python mcp/qs_registry.py
```

在 `.mcp.json` 中配置：

```json
"env": {
    "QS_TOOLS": "factor,backtest"
}
```

## 工具

### `search_factors(query, limit=20)`

搜索因子列表。优先使用语义向量检索（若启用），回退到关键词匹配，结果合并时向量结果优先。

**参数**：
- `query`: 查询文本，如 "动量因子"、"成交量相关"、"财务质量"
- `limit`: 返回结果数量上限，默认 20

**返回**：`[{name, qsid, factor_class, operator_type, data_type, similarity?}]`

**回退策略**：向量检索抛出异常或返回空时，自动回退到关键词匹配（`searchFactors(name=query)`）。

### `get_factor_info(qsid)`

查询因子的详细信息，包括名称、描述、数据类型、算子信息、依赖关系等。

**参数**：
- `qsid`: 因子的 QSID（唯一标识符）

**返回**：
```json
{
  "name": "turnover",
  "qsid": "6e36e315...",
  "factor_class": "DerivativeFactor",
  "data_type": "double",
  "module_path": "QuantStudio.Factor.FactorOperation",
  "description": "",
  "operator_name": "where",
  "operator_type": "Point",
  "operator_qsid": "b04bd7e2...",
  "meta": {},
  "descriptors": [{"name": "换手率(%)", "qsid": "84b907cd..."}],
  "dependents": [],
  "dependency_depth": 2,
  "tags": ["麦冬", "stock_cn_day_bar_nafilled", "A股"]
}
```

### `get_factor_code(qsid)`

返回定义该因子的 Python 源代码。查找路径：

1. 通过 `属于因子表` → 因子表 → `MetaDataJSON.DefScriptPath`
2. 回退：通过因子标签 → `importlib.import_module("QSResearch.FactorDef.JY.{tag}")` → `__file__`

**参数**：
- `qsid`: 因子的 QSID（唯一标识符）

**返回**：`{qsid, factor_name, script_path, source_code}`，若无法定位则返回 `{error: "..."}`

### `search_backtests(query="", category=None, factor_qsid=None, limit=20)`

搜索回测列表。

**参数**：
- `query`: 回测名称（模糊匹配），传空字符串查全部
- `category`: 回测类别筛选，可选：`SectionFactor` / `Strategy` / `Risk` / `TimeSeriesFactor` / `PerformanceAnalysis` / `Event`
- `factor_qsid`: 因子 QSID，查找使用了该因子的所有回测
- `limit`: 返回数量上限，默认 20

**返回**：`[{name, qsid, class_name, category, created_at}]`

### `get_backtest_info(qsid)`

查询回测的详细信息，包括配置参数、依赖因子、结果摘要。

**参数**：
- `qsid`: 回测节点的 QSID

**返回**：
```json
{
  "name": "IC",
  "qsid": "d4e5f6a7...",
  "class_name": "IC",
  "category": "SectionFactor",
  "module_path": "QuantStudio.BackTest.SectionFactor.IC",
  "qs_args": {"RollingAvgPeriod": 12, ...},
  "factors": [{"name": "momentum_1d", "qsid": "..."}],
  "sub_backtests": [],
  "results": [
    {"result_id": "...", "key": "IC", "data_type": "DataFrame", "dtrange": "...", "summary": {...}},
    {"result_id": "...", "key": "统计数据", "data_type": "DataFrame", "dtrange": "...", "summary": {...}}
  ],
  "tags": ["A股", "IC分析"],
  "created_at": "2026-07-02T..."
}
```

### `get_backtest_result(result_id)`

获取回测结果的详细数据。若数据存储在 HDF5 文件中，自动读取并返回元信息和预览。

**参数**：
- `result_id`: 回测结果的 ResultID

**返回**：`{result_id, key, data_type, summary, data_ref?, data_preview?, data?}`

### `register_report(report_path, factor_qsids, bt_qsid=None, scenario_name=None, name=None)`

将本地报告文件注册到因子图数据库。报告文件保留在本地，图数据库仅存储路径和元数据。

**参数**：
- `report_path`: 报告文件的本地绝对路径
- `factor_qsids`: 报告涉及的因子 QSID 列表，通过 `(因子)-[:有报告]->(报告)` 关联
- `bt_qsid`: 产生此报告的回测 QSID（可选）
- `scenario_name`: 生成报告的场景名称（如 `"single_factor"`）
- `name`: 报告名称，默认使用文件名

**返回**：`{report_id, name, file_path, format, file_size, scenario_name, factor_names, created_at}`

### `search_reports(query="", scenario_name=None, factor_qsid=None, fmt=None, limit=20)`

搜索已注册的报告列表。可按报告名称、场景、关联因子、格式进行组合查询。

**参数**：
- `query`: 查询文本，匹配报告名称（模糊匹配）；传空字符串查全部
- `scenario_name`: 场景名称筛选，如 `"single_factor"`
- `factor_qsid`: 因子 QSID，查找关联该因子的所有报告
- `fmt`: 格式筛选，可选 `html` / `markdown` / `pdf`
- `limit`: 返回数量上限，默认 20

**返回**：`[{report_id, name, file_path, format, file_size, scenario_name, created_at}]`

### `get_report_info(report_id)`

获取报告的详细元信息。不返回报告文件内容（内容请通过 file_path 直接读取）。

**参数**：
- `report_id`: 报告的 ReportID

**返回**：`{report_id, name, file_path, file_exists, format, file_size, scenario_name, factor_qsids, bt_qsid, file_mtime, created_at, updated_at}`

`file_exists` 字段指示报告文件当前是否在磁盘上可访问。

### `search_risk_tables(query="", limit=20)`

搜索风险表列表。支持按名称模糊匹配。

**参数**：
- `query`: 查询文本，匹配风险表名称（模糊匹配）；传空字符串查全部
- `limit`: 返回数量上限，默认 20

**返回**：`[{name, qsid, class_name, module_path}]`

### `get_risk_table_info(qsid)`

查询风险表的详细信息。

**参数**：
- `qsid`: 风险表的 QSID

**返回**：`{name, qsid, class_name, module_path, qs_args}`

### `search_optimizers(query="", optimizer_type=None, limit=20)`

搜索组合优化器列表。

**参数**：
- `query`: 查询文本，匹配优化器名称（模糊匹配）；传空字符串查全部
- `optimizer_type`: 优化器类型筛选，如 `CVXPC` / `MatlabPC`
- `limit`: 返回数量上限，默认 20

**返回**：`[{name, qsid, optimizer_type, class_name, created_at}]`

### `get_optimizer_info(qsid)`

查询组合优化器的详细信息。

**参数**：
- `qsid`: 组合优化器的 QSID

**返回**：`{name, qsid, optimizer_type, class_name, module_path, description, qs_args, created_at, updated_at}`

## Claude Code 配置

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "qs-registry": {
      "command": "D:/miniforge/envs/QS312/python.exe",
      "args": ["D:/HST/QSExt/mcp/qs_registry.py"],
      "env": {
        "PYTHONPATH": "D:/HST/Project/QuantStudio;D:/HST/QSExt;D:/HST/QSResearch",
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        "OLLAMA_API_KEY": "ollama",
        "EMBEDDING_MODEL": "bge-m3",
        "QS_TOOLS": "all"
      }
    }
  }
}
```

## 调试

**Python 直接调用**：
```python
from mcp.qs_registry import search_factors, get_factor_info, get_factor_code
from mcp.qs_registry import search_risk_tables, search_optimizers
results = search_factors("动量因子", limit=5)
info = get_factor_info(results[0]["qsid"])
code = get_factor_code(results[0]["qsid"])
risk_tables = search_risk_tables("协方差")
optimizers = search_optimizers(optimizer_type="CVXPC")
```

**MCP Inspector**（FastMCP 3.x）：
```powershell
$env:PYTHONPATH = "D:/HST/Project/QuantStudio;D:/HST/QSExt;D:/HST/QSResearch"
D:/miniforge/envs/QS312/Scripts/fastmcp.exe dev inspector D:/HST/QSExt/mcp/qs_registry.py
```

**注意**：Inspector 调试时必须传入脚本文件路径直接运行，否则 `mcp/qs_registry.py` 中的相对导入会失败。

## 依赖

- `fastmcp` (≥3.0) — MCP 框架
- `neo4j` — Neo4j 驱动（间接依赖，通过 QSGraphDB）
- `requests` — Ollama HTTP 调用（间接依赖）
