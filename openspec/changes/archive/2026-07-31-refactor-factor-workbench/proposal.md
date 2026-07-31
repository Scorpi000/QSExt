## Why

当前因子工作台的衍生因子创建功能仅向 Neo4j 写入元数据节点，无法产生可执行的因子定义代码，功能严重受限。QSExt 已有完整的 FactorDef 框架（支持依赖解析、参数透传、自定义算子、批量执行）和 develop-factor AI 技能（可自动生成因子定义脚本），但两者均未接入 Web 端。此次重构将因子工作台从"Web 元数据创建"模式升级为"FactorDef 框架的完整 Web 入口"。

## What Changes

- **BREAKING**: 移除前端 `CreateFactorWizard` 组件（4 步向导：选算子 → 选依赖 → 配参数 → 预览创建）
- **BREAKING**: 移除后端 `POST /api/factors/derivative` API 及 `registry_service.create_derivative_factor()` 方法
- 新增因子脚本导入功能：支持上传 `.py` 文件或粘贴代码，经 `ast` 静态解析验证 `__FACTOR_META__` 和 `defFactor` 签名后存储到可配置的脚本目录，可选注册到 Neo4j
- 新增 AI 因子助手：Chat 面板通过 WebSocket 与后端通信，后端使用 `claude-agent-sdk` 调用 Claude，加载 `develop-factor` 技能和已有 MCP 工具（jy_base_doc、qs-registry），流式返回思考过程和生成的脚本
- AI 生成的脚本与手动导入的脚本走同一条导入管道（验证 → 存储 → 可选注册）
- 因子脚本存放路径通过 `QSWebConfig.json` 的 `factor_def.scripts_dir` 配置

## Capabilities

### New Capabilities
- `factor-script-import`: 导入符合 FactorDef 框架规范的因子定义脚本，支持文件上传和代码粘贴，ast 静态验证，存储到可配置目录，可选注册到 Neo4j
- `ai-factor-assistant`: AI 辅助因子创建，Chat 面板 + WebSocket 流式通信，通过 claude-agent-sdk 调用 Claude，加载 develop-factor 技能和 MCP 工具，生成 FactorDef 脚本并通过导入管道处理

### Modified Capabilities
- `factor-workbench`: 移除衍生因子创建需求（"衍生因子创建" Requirement 及其 Scenarios），新增因子脚本导入和 AI 辅助创建入口

## Impact

- **前端**: 删除 `CreateFactorWizard/`，新增 `ImportFactorDialog/` 和 `AiFactorAssistant/`，修改 `FactorWorkbench` 页面按钮和入口
- **后端**: 删除 `registry_service.create_derivative_factor()` 和对应 API 路由，新增 `ai_service.py`（claude-agent-sdk 集成）、`import_service.py`（ast 解析 + 存储），新增 `api/ai.py`（WebSocket 端点）、`api/import_factor.py`（导入 API）
- **配置**: `QSWebConfig.json` 新增 `factor_def` 配置段（`scripts_dir`、`register_to_graph`、`auto_execute`）
- **依赖**: `claude-agent-sdk`（已安装 v0.2.112），无新增依赖
- **不动**: `develop-factor` 技能、jy_base_doc/qs-registry MCP 服务器、FactorDef 框架、QSWeb 搜索/DAG/详情/连接管理功能全部保留
