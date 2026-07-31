## 1. 后端配置层 — ai_workbench 配置系统

- [x] 1.1 在 `backend/app/core/config.py` 新增 `ai_workbench` 属性，从 `QSWebConfig.json` 加载配置段，含默认值回退逻辑
- [x] 1.2 定义 `ai_workbench` 配置的默认值（含 `general` context），内置 `default_context`、`route_context_map`、`contexts` 结构
- [x] 1.3 新增 `GET /api/ai/contexts` 路由，返回可用 context 列表（不含完整 system_prompt）

## 2. 后端存储层 — SessionStore 会话持久化

- [x] 2.1 创建 `backend/app/services/session_store.py`：定义 `SessionMeta`/`SessionData` 数据类 + `SessionStore` 抽象接口
- [x] 2.2 实现 `JsonFileSessionStore`：基于 `~/.qsweb/ai_sessions/` 的 JSON 文件存储，含原子写入（tmp + rename）和并发锁
- [x] 2.3 实现 `list_sessions()`、`get_session()`、`save_message()`、`delete_session()` 方法

## 3. 后端 API 层 — 会话管理路由

- [x] 3.1 创建 `backend/app/api/ai_sessions.py`：`GET /api/ai/sessions`、`GET /api/ai/sessions/{id}`、`DELETE /api/ai/sessions/{id}`
- [x] 3.2 在 `backend/app/main.py` 注册新路由

## 4. 后端核心重构 — AiServiceCLI 配置驱动化

- [x] 4.1 重构 `AiServiceCLI.start()`：签名从 `start(prompt, scripts_dir)` 改为 `start(prompt, context_config)`，根据 context_config 动态组装 system_prompt
- [x] 4.2 重构 `_ensure_workspace()`：遍历 `context_config.skills` 列表动态链接技能目录（替代硬编码 `develop-factor`）
- [x] 4.3 重构 MCP config 写入：根据 `context_config.tools` 过滤 + `context_config.mcp_servers` 合并生成 MCP 配置 JSON
- [x] 4.4 重构 WebSocket handler：接收前端 `context` 参数，从 `settings.ai_workbench` 查找配置，传给 `AiServiceCLI.start()`
- [x] 4.5 在 `_parse_cli_message()` 中新增 action_card 消息的检测和提取逻辑
- [x] 4.6 在 WebSocket 消息处理中集成 `SessionStore`：新会话首次收到 assistant 消息时自动 `save_message()`

## 5. 前端基础设施 — AiChatPanel 通用聊天组件

- [x] 5.1 创建 `components/AiChatPanel/index.tsx`：从 `AiFactorAssistant` 提取通用逻辑（消息渲染、输入处理、WebSocket 管理、状态管理）
- [x] 5.2 实现 props 接口：`context`、`placeholder`、`headerExtra`、`initialMessages`、`onAction`、`sessionId?`
- [x] 5.3 实现 action_card 消息渲染器（ActionCard 子组件）
- [x] 5.4 实现 data_block 消息渲染器（根据 kind 调度 DataTable/Plotly/DAG 渲染器）
- [x] 5.5 保留流式消息追加、思考过程折叠、工具调用展示、代码块语法高亮等现有功能

## 6. 前端入口 — AiChatDrawer 全局入口 + FAB + 快捷键

- [x] 6.1 创建 `components/AiChatDrawer/index.tsx`：Drawer 包装 + 路由感知 context 推断逻辑（读取 `route_context_map`）
- [x] 6.2 在 `MainLayout` 添加 FAB 悬浮按钮（右下角，RobotOutlined 图标，点击打开 AiChatDrawer）
- [x] 6.3 在 `MainLayout` 添加 Ctrl+K/Cmd+K 快捷键监听（打开/关闭 AiChatDrawer，输入框内不触发）
- [x] 6.4 在 `MainLayout` 侧边栏导航新增"AI 工作台"菜单项（`/ai` 路由），图标 RobotOutlined

## 7. 前端页面 — /ai 独立 AI 工作台

- [x] 7.1 创建 `pages/AiWorkbench/index.tsx`：左侧 SessionList + 右侧 AiChatPanel 布局
- [x] 7.2 创建 `components/SessionList/index.tsx`：会话列表（标题/context标签/时间/消息数），支持选中、新建、删除
- [x] 7.3 创建 `services/session.ts`：会话 CRUD API 的 TypeScript 客户端（`listSessions`、`getSession`、`deleteSession`）
- [x] 7.4 在 `App.tsx` 注册 `/ai` 路由（lazy load AiWorkbench 页面）
- [x] 7.5 实现上下文选择器（标题栏下拉菜单，从 `GET /api/ai/contexts` 获取选项）

## 8. 因子工作台集成 — 替换 AiFactorAssistant

- [x] 8.1 重写 `components/AiFactorAssistant/index.tsx` 为薄包装：调用 `AiChatDrawer`（或直接调用 `AiChatPanel`），context 硬编码为 `"factor"`
- [x] 8.2 实现 `onAction` 回调：匹配 `key === "save"` → 调用 `POST /api/factors/import` 保存脚本
- [x] 8.3 更新 `FactorWorkbench` 的"AI 辅助创建"按钮：改为打开 AiChatDrawer（带 context="factor"），移除旧的 AiFactorAssistant Drawer 调用方式
- [x] 8.4 更新 `factor` context 的 system_prompt 配置为 action_card 输出格式

## 9. QSWebConfig.json 配置与迁移

- [x] 9.1 创建 `ai_workbench` 默认配置文档/示例，含 `general` 和 `factor` context 的完整定义
- [x] 9.2 将现有 `factor_def.claude` 配置内容迁移到 `ai_workbench.contexts.factor`，`factor_def.claude` 保留只读兼容
- [x] 9.3 为其他页面预置 context 骨架（`backtest`、`risk`、`portfolio`），使用 `general` 配置作为默认值

## 10. 前端服务层 — ai.ts 协议扩展

- [x] 10.1 在 `services/ai.ts` 中 `AiMessageType` 新增 `'action_card'` 和 `'data_block'` 类型
- [x] 10.2 扩展 `AiBlock` 接口，新增 `action_card` 和 `data_block` 相关的类型定义
- [x] 10.3 更新 `AiChatClient`：`start()` 方法额外发送 `context` 字段

## 11. 测试与清理

- [x] 11.1 手动测试 AI 因子创建完整流程（因子工作台 → 打开 AI → 输入需求 → 生成脚本 → action_card 保存）
- [x] 11.2 手动测试全局入口（FAB/Ctrl+K/侧边栏）在不同页面的 context 注入
- [x] 11.3 手动测试 /ai 页面：会话列表、会话切换、新建会话、删除会话、恢复对话
- [x] 11.4 手动测试 action_card 错误处理（保存失败、网络断开等）
- [x] 11.5 清理旧的因子代码检测逻辑（在 AiChatPanel 中不应残留 `__FACTOR_META__` 匹配逻辑）

## 12. CLI 模式问题修复（实现过程中发现并修复）

- [x] 12.1 修复 `forward_ai_messages` 中 `save_message` 未包 try/except 导致 forward 任务崩溃
- [x] 12.2 修复 `_send_json` 进程已退出时静默返回不报错的问题
- [x] 12.3 修复 `_read_stdout` 进程异常退出时错误未入 msg_queue 的问题
- [x] 12.4 修复 `session_store.save_message()` 阻塞消息转发启动的问题（改为 fire-and-forget）
- [x] 12.5 发现 CLI `-p` 模式不持久化 session 导致 `--resume` 永远失败，`query()` 改为新会话

## 13. SDK 模式迁移

- [x] 13.1 重构 `AiService`（SDK 版）为 `context_config` 驱动，与 CLI 版接口统一
- [x] 13.2 将 SDK 的 `connect(prompt=str)` 改为 `connect(prompt=AsyncIterable)` 流式输入模式（`can_use_tool` 要求）
- [x] 13.3 重构 `query()` 为 `client.query()` 直接写 transport，替代 CLI 的杀进程 + `--resume`
- [x] 13.4 添加 `mode` 字段到 `ai_workbench` 配置和 `_default_ai_workbench()`
- [x] 13.5 QSWebConfig.json 设置 `mode: "sdk"` 切换实现

## 14. AskUserQuestion 支持

- [x] 14.1 SDK 版：实现 `can_use_tool` 回调，拦截 `AskUserQuestion`，通过 `asyncio.Event` 等待前端答案
- [x] 14.2 SDK 版：`_can_use_tool` 发出 `ask_user` 消息类型，`format_message` 支持 raw dict 透传
- [x] 14.3 SDK 版：新增 `answer()` 方法 + `_resolve_question()`，主线程安全唤醒 SDK 事件循环
- [x] 14.4 前端：`AiMessageType` 新增 `'ask_user'`，`AiChatClient` 新增 `sendAnswer()` 方法
- [x] 14.5 前端：`AskUserPanel` 子组件（Radio/Checkbox UI，支持单选/多选，默认值填充）
- [x] 14.6 后端：`ai.py` WS handler 新增 `answer` action 处理

## 15. system_prompt 架构优化

- [x] 15.1 将所有 context 的 `system_prompt` 中的 `{user_prompt}`/`{scripts_dir}` 占位符移除
- [x] 15.2 SDK 模式：`system_prompt` 通过 `ClaudeAgentOptions(system_prompt=...)` 作为系统指令传递
- [x] 15.3 删除 `ai_service.py` 的 `_build_prompt` 方法，`input_stream` 直接 yield 原始用户输入
- [x] 15.4 CLI 模式：`_build_prompt` 兼容处理（新格式直接透传，旧模板仍支持 format）
- [x] 15.5 `_default_ai_workbench()` 默认值同步更新

## 16. `ai.ts` 前端协议完善

- [x] 16.1 修复 `pendingStart` 不包含 `context` 字段的 bug
- [x] 16.2 `start()` 中 WS 非 OPEN 时自动重连一次，失败抛出明确错误（替代静默 hang）
- [x] 16.3 `onclose` 非正常关闭时通过 handlers 通知前端

## 17. SessionStore 稳定性修复

- [x] 17.1 修复 `save_message` 锁范围不足导致文件与索引不一致（per-session 锁内只写文件，`_global_lock` 保护索引）
- [x] 17.2 所有索引操作加 3 秒 `asyncio.timeout` + 异常日志，避免死锁阻塞 API
- [x] 17.3 `_safe_update_index` 容错：索引条目不存在时自动从 session 文件重建
- [x] 17.4 `delete_session` 始终清理索引（文件不存在时不报 404，UI 能正常移除）
- [x] 17.5 完整重写 `session_store.py`，修复缩进/语法/`await` 误用等问题

## 18. 会话恢复与重命名

- [x] 18.1 修复 AI 消息恢复时内容为空：从 `blocks[].kind === 'text'` 提取文本（之前只读 `msg.data?.content`）
- [x] 18.2 `AiChatPanel` 新增 `initialMessages` 同步 `useEffect`，切换会话时正确更新消息列表
- [x] 18.3 新增 `PUT /api/ai/sessions/{id}/title` 重命名 API
- [x] 18.4 SessionList 支持内联重命名（双击/✎图标 → Input → Enter/失焦保存）
- [x] 18.5 SessionList 移除顶部"新建会话"按钮，统一由 AiChatPanel 标题栏入口
- [x] 18.6 新建会话后延迟 500ms 刷新列表，等 fire-and-forget save_message 完成

## 19. Bug 修复汇总

- [x] 19.1 `AiChatClient.start()` WS 重连机制 + `onclose` 错误通知
- [x] 19.2 SDK `AiService._session_id` 误删导致 `AttributeError`（加回 + `start()` 中 UUID 生成）
- [x] 19.3 `format_message` raw dict 透传（`ask_user` 等自定义消息不被转成 `unknown`）
- [x] 19.4 `pendingStart` 遗漏 `context` 字段导致 WS 重连后上下文丢失
- [x] 19.5 因子工作台移除"AI 辅助创建"按钮，统一走 FAB/Ctrl+K 全局入口
