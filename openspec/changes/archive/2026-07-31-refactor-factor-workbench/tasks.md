## 1. 配置与基础设施

- [x] 1.1 在 `core/config.py` 中新增 `factor_def` 配置段加载逻辑（从 `QSWebConfig.json` 读取，浅合并默认值）
- [x] 1.2 `repo_root` 默认值从 `config.py` 位置自动计算（`_qsweb_root`，向上 5 级）
- [x] 1.3 在 `QSWebConfig.json` 中添加 `factor_def` 完整配置（scripts_dir、settings_path、skill_dir、claude 段含 mode/repo_root/system_prompt/session_persist_wait_sec/mcp_servers 等）

## 2. 后端 - 因子脚本导入

- [x] 2.1 新建 `services/import_service.py`：`ImportService` 类
  - `validate_import(code, filename)`：`importlib` 加载模块，读取 `__FACTOR_META__` + 验证 `defFactor` 签名
  - `save_script(code, filename)`：保存到 `scripts_dir`，重名自动后缀
  - `register_to_graph(module_path)`：调用 `register_factors_to_graphdb.py` 注册到 Neo4j
- [x] 2.2 新建 `api/import_factor.py`：`POST /api/factors/import` + `/preview`
  - 接收参数：`code`、`filename`、`register_graph`
  - 注册作为后台任务（`task_manager.submit`），通过 `GET /api/tasks/{task_id}` 轮询状态

## 3. 后端 - AI 因子助手（CLI 模式，默认）

- [x] 3.1 新建 `services/ai_service_cli.py`：`AiServiceCLI` 类
  - `start(prompt, scripts_dir)`：创建新会话（UUID），`_launch(resume=False)`
  - `query(prompt)`：等待旧进程退出 → `_launch(resume=True)` 恢复会话，`loop.run_in_executor` 避免阻塞
  - `interrupt()`：终止子进程
  - `disconnect()`：清理子进程
  - `_launch(prompt, scripts_dir, resume)`：构建 CLI 命令、启动子进程、启 stdout/stderr 线程、发送 stdin 消息
  - `_read_stdout(proc)`：读取 JSON 行，调用 `_parse_cli_message`，put 到 `msg_queue`
  - `_parse_cli_message(data)`：CLI stream-json → 前端统一格式（assistant/thinking/tool_use/tool_result/result/stream/error）
  - `_send_json(data)`：向子进程 stdin 写 JSON 行
  - `_ensure_workspace(repo_root)`：`os.makedirs(.claude/skills/)` + `git init` + `_link_skill`
  - `_link_skill(skills_dir, skill_name, source_parent)`：创建/修复 skills junction（跨平台）
  - `_write_mcp_config(mcp_servers)`：写临时 MCP JSON 配置文件
  - `format_message(msg)`：静态方法，dict 透传
- [x] 3.2 消息显示修复
  - `ThinkingBlock` → `kind: "thinking"`，前端 `Collapse` 折叠
  - `ResultMessage` 正常完成时不发可见消息，仅触发 `done` 信号
  - 去掉 `--include-partial-messages`，避免 stream_event 与 assistant text 重复
  - `--replay-user-messages` 回显消息跳过不展示
- [x] 3.3 会话持久化修复
  - 去掉 `--no-session-persistence`，允许 `--resume` 恢复
  - `query()` 改为 `wait()` 等待自然退出而非 `interrupt()` kill
  - `session_persist_wait_sec` 可配置超时（默认 10s）

## 4. 后端 - AI 因子助手（SDK 模式，备选）

- [x] 4.1 新建 `services/ai_service.py`：`AiService` 类
  - `start(prompt, scripts_dir)`：daemon 线程启动 `ClaudeSDKClient`
  - `query(prompt)`：`asyncio.run_coroutine_threadsafe` 发送命令
  - `interrupt()` / `disconnect()`：线程安全清理
  - `_run_client(prompt, scripts_dir)`：`connect` → `asyncio.wait` (recv_loop + cmd_loop) → `disconnect`
  - `format_message(msg)`：SDK 对象 → 前端统一格式（含 ThinkingBlock 处理）
  - `_build_prompt(user_prompt, scripts_dir)`：从配置模板渲染

## 5. 后端 - 模式切换与 WebSocket

- [x] 5.1 新建/更新 `api/ai.py`：WebSocket 端点 `/ws/ai/chat`
  - 按 `factor_def.claude.mode` 条件导入 `AiServiceCLI`（cli）或 `AiService`（sdk）
  - 双向协议：`start` / `query` / `interrupt` / `disconnect`
  - `forward_ai_messages()` 后台任务：从 `msg_queue` 轮询 → `format_message` → WebSocket 推送
  - `start` 创建会话 + 启动 forward task
  - `query` → `loop.run_in_executor` 执行 service.query + 重建 forward task
  - `interrupt` / `disconnect` → 调用 service 方法
- [x] 5.2 注册路由：`ai_router` 挂载到 `main.py`

## 6. 后端 - 清理旧代码

- [x] 6.1 从 `api/registry.py` 删除 `POST /api/factors/derivative` 路由
- [x] 6.2 从 `services/registry_service.py` 删除 `create_derivative_factor()` 方法
- [x] 6.3 注册新路由：`import_factor_router` 挂载到 `api/__init__.py`

## 7. 前端 - 导入因子对话框

- [x] 7.1 新建 `components/ImportFactorDialog/index.tsx`
  - 两个 Tab：粘贴代码（TextArea + 文件名输入）| 上传文件（Dragger，限制 .py）
  - 预览按钮 → `POST /api/factors/import/preview` → 展示 `__FACTOR_META__` 元信息
  - 确认导入 → `POST /api/factors/import` → 保存 + 可选注册到 Neo4j
  - 注册状态轮询（`GET /api/tasks/{task_id}`）、注册失败错误 Alert（不自动关闭）
- [x] 7.2 新建 `services/import.ts`：`previewImport` / `importFactor` / `importFactorFile` API 封装

## 8. 前端 - AI 因子助手面板

- [x] 8.1 新建 `components/AiFactorAssistant/index.tsx`
  - 消息列表：用户消息 / AI 回复 / 思考过程（Collapse 折叠）/ 工具调用卡片 / 代码块（深色语法高亮）
  - 状态指示：运行中（Badge processing + spinner）/ 已中断 / 已完成
  - 输入区：TextArea + 发送/追问按钮 + 停止按钮
  - 多轮逻辑：`runState=idle` → `handleSend`（start 新会话），其他 → `handleSendFollowup`（query 续接）
  - 新建会话：断开 Claude + 清空消息
  - 代码生成后：自动调用 `importFactor` 预览元信息，提供保存/放弃按钮
- [x] 8.2 新建 `services/ai.ts`：`AiChatClient` 类
  - `start(prompt)` → `{"action": "start"}`
  - `sendQuery(prompt)` → `{"action": "query"}`
  - `interrupt()` → `{"action": "interrupt"}`
  - `disconnect()` → `{"action": "disconnect"}`
  - `onMessage(handler)` → 消息回调注册

## 9. 前端 - 因子工作台页面更新

- [x] 9.1 修改 `pages/FactorWorkbench/index.tsx`
  - 替换"创建衍生因子"按钮为："导入因子脚本" + "AI 辅助创建"

## 10. 前端 - 清理旧代码

- [x] 10.1 删除 `components/CreateFactorWizard/` 整个目录
- [x] 10.2 从 `services/registry.ts` 删除 `createDerivativeFactor` 函数

## 11. 跨平台支持

- [x] 11.1 `_is_junction(path)`：Windows WinAPI reparse point 检测，Linux/macOS 退化为 `os.path.islink`
- [x] 11.2 `_remove_path(path)`：Windows `cmd /c rmdir`，Linux/macOS `os.unlink`/`shutil.rmtree`
- [x] 11.3 `_link_skill`：Windows `mklink /J` junction，Linux/macOS `os.symlink`
- [x] 11.4 所有异常均有 logger 日志，不再静默吞错

## 12. 验证

- [x] 12.1 CLI 模式端到端：`--output-format stream-json` + `--resume` 多轮对话
- [x] 12.2 SDK 模式端到端：`ClaudeSDKClient` 消息流 + 线程隔离
- [x] 12.3 导入管道：`importlib` 验证 + 脚本保存 + 图数据库注册
- [x] 12.4 前端交互：多轮追问、中断、新建会话、思考折叠、代码生成后导入
- [x] 12.5 配置切换：`mode: "cli"` ↔ `mode: "sdk"` 重启生效
- [x] 12.6 工作目录自动初始化：git init + skill junction 创建/修复
- [x] 12.7 前端 runState 逻辑：idle→start，done/interrupted/running→query
