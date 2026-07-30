## 1. 配置与基础设施

- [x] 1.1 在 `core/config.py` 中新增 `factor_def` 配置段加载逻辑（从 `QSWebConfig.json` 读取 `scripts_dir`、`register_to_graph`、`auto_execute`）
- [x] 1.2 在 `QSWebConfig.json` 中添加 `factor_def` 默认配置段（`scripts_dir`、`register_to_graph: true`、`auto_execute: false`）

## 2. 后端 - 因子脚本导入

- [x] 2.1 新建 `services/import_service.py`：实现 `ImportService` 类
  - `parse_script(code: str) -> dict`：ast.parse 提取 `__FACTOR_META__` 字典字段 + 验证 `defFactor` 签名
  - `save_script(code: str, filename: str) -> str`：保存到配置的 `scripts_dir`
  - `validate_import(code: str) -> ImportResult`：组合解析 + 返回结构化结果（元信息、警告、错误）
- [x] 2.2 新建 `api/import_factor.py`：`POST /api/factors/import`
  - 接收参数：`code`（代码内容）、`filename`（文件名）、`register`（是否注册，默认使用配置值）
  - 调用 `ImportService` 完成解析、验证、存储
  - 若 `register=true`，调用 `register_factors_to_graphdb.py` 或等效逻辑注册到 Neo4j
  - 返回元信息预览数据

## 3. 后端 - AI 因子助手

- [x] 3.1 新建 `services/ai_service.py`：实现 `AiService` 类
  - `chat(prompt: str, scripts_dir: str) -> AsyncIterator[dict]`：封装 `claude_agent_sdk.query()`
  - 配置 `ClaudeAgentOptions`：`skills=["develop-factor"]`、`mcp_servers`（jy_base_doc + qs-registry）、`allowed_tools`、`cwd=scripts_dir`、`permission_mode="acceptEdits"`、`max_budget_usd=1.0`
  - 将 SDK 消息类型（`SystemMessage`、`AssistantMessage`、`ToolUseBlock`、`ResultMessage`、`StreamEvent`）转换为统一的 JSON 消息格式
- [x] 3.2 新建 `api/ai.py`：WebSocket 端点 `/ws/ai/chat`
  - 接收用户消息，调用 `AiService.chat()`
  - 将 `AsyncIterator` 的每条消息通过 WebSocket 推送到前端
  - 处理连接断开和异常

## 4. 后端 - 清理旧代码

- [x] 4.1 从 `api/registry.py` 中删除 `POST /api/factors/derivative` 路由
- [x] 4.2 从 `services/registry_service.py` 中删除 `create_derivative_factor()` 方法
- [x] 4.3 注册新的 API 路由：`api/import_factor.py` 挂载到 `api/__init__.py`，`api/ai.py` 的 WebSocket 挂载到 `main.py`

## 5. 前端 - 导入因子对话框

- [x] 5.1 新建 `components/ImportFactorDialog/index.tsx`：导入对话框组件
  - 支持两个 Tab：上传 .py 文件 | 粘贴代码
  - 上传 Tab：Dragger 组件，限制 `.py` 后缀
  - 粘贴 Tab：TextArea 组件，Monaco Editor 或简单的代码输入框
  - 调用 `POST /api/factors/import`（先预览、再确认）
  - 预览区域：展示 AST 解析结果（TargetTable、IDType、Description、FactorDeps、依赖警告等）
  - 确认导入：调用保存 + 可选注册
- [x] 5.2 新增 `services/import.ts`：`importFactor(code, filename, register)` API 封装

## 6. 前端 - AI 因子助手面板

- [x] 6.1 新建 `components/AiFactorAssistant/index.tsx`：AI 助手 Chat 面板
  - 消息列表：区分用户消息、AI 思考过程（折叠样式）、工具调用卡片（查询中/已完成）、代码块（语法高亮）
  - 输入框 + 发送按钮
  - "新建会话"按钮（清空当前消息）
  - WebSocket 连接管理：连接、重连、断开
- [x] 6.2 新建 `services/ai.ts`：WebSocket 客户端封装
  - `connect()`：建立 WebSocket 连接
  - `send(message)`：发送用户消息
  - `onMessage(callback)`：注册消息处理回调
  - `disconnect()`：断开连接
- [x] 6.3 AI 生成完成后：自动调用 `POST /api/factors/import` 获取脚本元信息预览
- [x] 6.4 在预览中提供操作按钮：保存脚本、保存并注册、编辑脚本

## 7. 前端 - 因子工作台页面更新

- [x] 7.1 修改 `pages/FactorWorkbench/index.tsx`
  - 将"创建衍生因子"按钮替换为两个新按钮："导入因子脚本"、"AI 辅助创建"
  - "导入因子脚本" onClick → 打开 `ImportFactorDialog`
  - "AI 辅助创建" onClick → 打开 `AiFactorAssistant`

## 8. 前端 - 清理旧代码

- [x] 8.1 删除 `components/CreateFactorWizard/` 整个目录
- [x] 8.2 从 `services/registry.ts` 中删除 `createDerivativeFactor` 函数（`getOperators`/`getArgsSchema` 保留用于详情展示）
- [x] 8.3 `stores/factorWorkbench.ts` 中 `operators` 状态保留（用于算子详情展示）

## 9. 验证

- [x] 9.1 验证导入管道：AST 解析逻辑完整（`ImportService.validate_import` + `api/import_factor.py`），脚本保存到 `settings.factor_def.scripts_dir`
- [x] 9.2 验证 AI 助手：`AiService.chat()` 封装 `claude_agent_sdk.query()`，WebSocket 端点 `/ws/ai/chat` 流式推送，前端 `AiFactorAssistant` 渲染消息
- [x] 9.3 验证旧功能清理：`/api/factors/derivative` 路由已删除，`create_derivative_factor()` 方法已删除，`CreateFactorWizard` 目录已删除，`createDerivativeFactor` API 调用已删除，`FactorWorkbench` 页面改为两个新按钮
- [x] 9.4 验证现有功能不受影响：所有 Python 语法检查通过，QSWebConfig.json 有效，路由正确注册，算子/详情/搜索/DAG 组件全部保留
