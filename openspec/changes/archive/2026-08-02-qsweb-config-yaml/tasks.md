## 1. 依赖安装

- [x] 1.1 确认 `pyyaml` 已在 QS 环境中安装（或添加到 requirements）

## 2. 创建 YAML 配置文件

- [x] 2.1 将 `QSWebConfig.json` 内容转换为 `QSWebConfig.yaml`

## 3. 核心配置模块

- [x] 3.1 `core/config.py`：新增 `QS_CONFIG_PATH` 属性指向 `QSWebConfig.yaml`，`factor_def` 和 `ai_workbench` property 改为 `yaml.safe_load`
- [x] 3.2 `core/config.py`：`_default_ai_workbench()` 中的 `system_prompt` 也改为多行字符串

## 4. 服务模块迁移

- [x] 4.1 `services/qs_bridge.py`：路径改为 `settings.QS_CONFIG_PATH`，`json.load` → `yaml.safe_load`
- [x] 4.2 `services/risk_service.py`：路径改为 `settings.QS_CONFIG_PATH`，读写改为 YAML（写使用 `ruamel.yaml`）
- [x] 4.3 `services/report_service.py`：路径改为 `settings.QS_CONFIG_PATH`，读写改为 YAML（写使用 `ruamel.yaml`）
- [x] 4.4 `services/portfolio_service.py`：路径改为 `settings.QS_CONFIG_PATH`，读写改为 YAML（写使用 `ruamel.yaml`）

## 5. 辅助模块

- [x] 5.1 `scripts/migrate_connections.py`：路径更新为 `QSWebConfig.yaml`

## 6. 文档与前端

- [x] 6.1 `QSWeb/README.md`：所有 `QSWebConfig.json` 引用改为 `QSWebConfig.yaml`
- [x] 6.2 `CLAUDE.md`：更新配置文件说明
- [x] 6.3 `QSWeb/frontend/src/pages/BacktestStudio/index.tsx`：Tooltip 文字中 `QSWebConfig.json` → `QSWebConfig.yaml`
