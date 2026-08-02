## Why

`QSWebConfig.json` 作为纯 JSON 文件，不支持注释、无法书写多行字符串、没有引用/继承机制，导致配置文件（尤其是 `ai_workbench` 段中的 `system_prompt` 和重复的 `mcp_servers`）难以阅读和维护。切换到 YAML 格式可以解决以上所有痛点。

## What Changes

- **BREAKING**: 配置文件从 `~/QuantStudioConfig/QSWebConfig.json` 迁移为 `QSWebConfig.yaml`，所有读取和写入该配置的代码改为使用 YAML 解析器
- 使用 YAML anchor/alias 消除 `ai_workbench.contexts` 中各 context 之间的重复配置
- `system_prompt` 等长文本字段使用 YAML 多行字符串（`|`）提升可读性
- 统一 `QS_CONFIG_PATH` 常量到 `core/config.py`，消除各服务模块中的重复路径定义
- 配置文件写入使用 `ruamel.yaml` 以保留注释和格式

## Capabilities

### New Capabilities

- `yaml-config-format`: QSWeb 配置文件从 JSON 切换到 YAML，支持注释、多行字符串和 anchor/alias 引用

### Modified Capabilities

- `ai-context-config`: 配置文件路径从 `QSWebConfig.json` 变更为 `QSWebConfig.yaml`，格式从 JSON 变更为 YAML

## Impact

- `QSWeb/backend/app/core/config.py` — `json.load` → `yaml.safe_load`
- `QSWeb/backend/app/services/risk_service.py` — 读写路径和格式变更
- `QSWeb/backend/app/services/qs_bridge.py` — 路径常量和格式变更
- `QSWeb/backend/app/services/report_service.py` — 读写路径和格式变更
- `QSWeb/backend/app/services/portfolio_service.py` — 读写路径和格式变更
- `QSWeb/backend/app/services/ai_service_cli.py` — 间接影响（通过 `config.py`）
- `QSWeb/scripts/migrate_connections.py` — 路径变更
- `QSWeb/frontend/src/pages/BacktestStudio/index.tsx` — Tooltip 文字更新
- `QSWeb/README.md`、`CLAUDE.md` — 文档路径更新
- 新增依赖：`pyyaml`（读取）、`ruamel.yaml`（写入保留格式）
