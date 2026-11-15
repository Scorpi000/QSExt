# FactorService MCP

独立的只读因子发现与小规模数据读取服务。它只通过 HTTP 调用 FactorService，不导入
QSWeb，也不直接访问 DBPool。

## 安装与配置

```powershell
pip install -e ".[factor-mcp]"
$env:QS_FACTOR_SERVICE_TOKEN = "FactorService 下游令牌"
```

主要环境变量：

- `QS_FACTOR_MCP_SERVER_URL`：FactorService 地址，默认 `http://127.0.0.1:8765`。
- `QS_FACTOR_MCP_CATALOG_PATH`：SQLite 目录路径。
- `QS_FACTOR_MCP_DATABASES`：需要索引的数据库白名单，逗号分隔；大库建议显式配置。
- `QS_FACTOR_MCP_CATALOG_TTL`：目录过期提示时间，默认 300 秒；过期目录仍可查询。
- `QS_FACTOR_MCP_MAX_CELLS`：单次内联读取上限，默认 2000。
- `QS_FACTOR_MCP_TOKEN`：Streamable HTTP 的入站 Bearer Token。

FactorService 更新到包含批量 catalog 接口的版本后需重启。MCP 兼容旧服务，但旧服务会退回
逐表同步，速度显著较慢。

## 首次构建目录

目录刷新是显式操作，不会阻塞首次搜索。建议在启动服务前执行：

```powershell
python -m QSExt.FactorServiceMCP --refresh-only --databases LDB
```

HTTP 服务启动后会在目录为空时进行后台初始化，并按 `QS_FACTOR_MCP_REFRESH_INTERVAL`
（默认 86400 秒，即每天一次）自动刷新。刷新采用 SQLite 事务原子替换；失败时继续使用旧目录。
手动刷新由 QSWeb 管理员页面调用仅监听回环地址的内部管理接口，普通 MCP 用户无法触发。

## 启动

本机 stdio：

```powershell
python -m QSExt.FactorServiceMCP --transport stdio
```

Streamable HTTP：

```powershell
$env:QS_FACTOR_MCP_TOKEN = "独立的 MCP 入站令牌"
python -m QSExt.FactorServiceMCP --transport streamable-http --port 28002
```

MCP 地址为 `http://127.0.0.1:28002/mcp`。MCP 入站令牌与 FactorService 下游令牌相互独立。

## 工具

- `factor_list_databases`
- `factor_list_tables`
- `factor_search_factors`
- `factor_get_factor`
- `factor_get_coverage`
- `factor_read_data`

`factor_read_data` 只接受同一因子表中的因子，返回
`date/asset_id/factor_id/factor/value` 长表。超过单元格或响应字节限制时应缩小范围。
