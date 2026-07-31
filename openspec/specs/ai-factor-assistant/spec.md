# ai-factor-assistant

## Purpose

AI 因子助手模块，提供 Chat 面板供用户用自然语言描述因子需求。后端通过双模式（CLI 子进程 或 `claude-agent-sdk` `ClaudeSDKClient`）调用 Claude，加载 `develop-factor` 技能和 MCP 工具（jy_base_doc、qs-registry），流式生成符合 FactorDef 框架规范的因子定义脚本，生成的脚本通过导入管道处理。

## Requirements

### Requirement: Chat 面板

系统 SHALL 在因子工作台提供 AI 因子助手 Chat 面板，支持用户通过自然语言描述因子需求。

#### Scenario: 打开 AI 助手
- **WHEN** 用户在因子工作台点击"AI 辅助创建"按钮
- **THEN** 系统打开 AI 因子助手 Drawer，显示欢迎语和输入框

#### Scenario: 发送初始消息
- **WHEN** 用户在输入框中输入因子需求描述并发送（runState=idle）
- **THEN** 系统发送 `{"action": "start", "prompt": "..."}` 到后端，后端创建新 Claude 会话，开始流式接收 AI 回复

#### Scenario: 多轮追问
- **WHEN** Claude 完成回复后（runState=done），用户输入新消息并发送
- **THEN** 系统发送 `{"action": "query", "prompt": "..."}`，后端通过 `--resume` 恢复会话上下文后处理新消息

#### Scenario: 中断 Claude
- **WHEN** 用户点击"停止"按钮
- **THEN** 系统发送 `{"action": "interrupt"}`，后端终止 Claude 进程，前端显示"已中断"状态

#### Scenario: 新建会话
- **WHEN** 用户点击"新建会话"按钮
- **THEN** 系统断开当前 Claude 连接（发送 `{"action": "disconnect"}`），清空对话历史，重置 idle 状态

#### Scenario: 状态指示
- **WHEN** Claude 正在处理（running）
- **THEN** 前端显示 "运行中" Badge + 旋转 spinner
- **WHEN** Claude 完成（done）
- **THEN** 前端显示 "已完成" Badge，spinner 停止
- **WHEN** Claude 被中断（interrupted）
- **THEN** 前端显示 "已中断" Badge

### Requirement: WebSocket 流式通信

系统 SHALL 通过 WebSocket 将 AI 的思考过程和生成结果实时推送到前端。

#### Scenario: 流式接收思考过程
- **WHEN** Claude 进行推理（ThinkingBlock）
- **THEN** 前端展示可折叠的"💭 思考过程"区域，默认收起

#### Scenario: 流式接收工具调用
- **WHEN** Claude 调用 MCP 工具（ToolUseBlock / ToolResultBlock）
- **THEN** 前端展示工具调用卡片："调用工具: {tool_name}" 和结果内容

#### Scenario: 流式接收生成的代码
- **WHEN** Claude 生成包含 `__FACTOR_META__` 或 `defFactor` 的回复
- **THEN** 前端在代码块中展示生成的代码，带深色背景语法高亮

#### Scenario: 结果不重复展示
- **WHEN** 正常完成（ResultMessage, is_error=false）
- **THEN** 后端不发可见消息，仅发送 `done` 信号停止 spinner
- **WHEN** 异常完成（is_error=true）
- **THEN** 前端显示红色错误消息

### Requirement: Claude Code 集成（CLI 模式）

系统 SHALL 在 CLI 模式下通过 `claude -p --output-format stream-json --input-format stream-json` 子进程调用 Claude。

#### Scenario: 启动 Claude 会话（CLI）
- **WHEN** 前端发送 `{"action": "start", "prompt": "..."}`
- **THEN** 后端执行 `_ensure_workspace()` 初始化工作目录（git init + skill 链接），启动 Claude CLI 子进程（`--session-id <uuid>`），通过 stdin 发送包装模板后的 system_prompt

#### Scenario: 加载 develop-factor 技能（CLI）
- **WHEN** 后端执行 `_ensure_workspace()`
- **THEN** 在 `<repo_root>/.claude/skills/develop-factor` 创建指向 `skill_dir/develop-factor` 的目录链接（Windows: junction，Linux: symlink），Claude CLI 自动发现并加载

#### Scenario: 配置 MCP 工具（CLI）
- **WHEN** 后端启动 Claude CLI
- **THEN** 将 `mcp_servers` 配置写入临时 JSON 文件，通过 `--mcp-config <file>` 和 `--strict-mcp-config` 传递给 CLI

#### Scenario: 预算控制（CLI）
- **WHEN** 后端启动 Claude CLI
- **THEN** `--max-budget-usd` 参数设置为配置值（默认 1.0）

#### Scenario: 多轮会话恢复（CLI）
- **WHEN** 前端发送 `{"action": "query", "prompt": "..."}`
- **THEN** 后端等待旧 CLI 进程自然退出（`session_persist_wait_sec` 秒），然后启动新 CLI 进程（`--resume <session_id>`），发送原始用户消息

#### Scenario: 中断 Claude 操作（CLI）
- **WHEN** 前端发送 `{"action": "interrupt"}`
- **THEN** 后端调用 `process.terminate()` 终止 CLI 子进程

### Requirement: Claude Code 集成（SDK 模式）

系统 SHALL 在 SDK 模式下通过 `ClaudeSDKClient` 调用 Claude。

#### Scenario: 启动 Claude 会话（SDK）
- **WHEN** 前端发送 `{"action": "start", "prompt": "..."}`
- **THEN** 后端创建 `AiService`，在 daemon 线程中运行 `ClaudeSDKClient.connect(prompt)`

#### Scenario: 发送后续消息（SDK）
- **WHEN** 前端发送 `{"action": "query", "prompt": "..."}`
- **THEN** 后端通过 `asyncio.run_coroutine_threadsafe()` 调用 `ClaudeSDKClient.query(prompt)`

### Requirement: 生成结果处理

系统 SHALL 在 AI 生成完成后，通过导入管道处理生成的脚本。

#### Scenario: 自动触发导入预览
- **WHEN** Claude 完成脚本生成且 runState=done，且回复中包含 `__FACTOR_META__` 或 `defFactor`
- **THEN** 前端自动调用 `POST /api/factors/import` 对生成的脚本执行验证，展示元信息预览

#### Scenario: 用户确认操作
- **WHEN** 导入预览展示后
- **THEN** 前端提供操作按钮：保存脚本、放弃

#### Scenario: 生成失败处理
- **WHEN** Claude 未能成功生成脚本（API 错误等）
- **THEN** 前端显示错误信息，用户可在同一会话中发送后续消息继续尝试

### Requirement: 会话管理

系统 SHALL 支持基本的 AI 会话管理。

#### Scenario: 会话历史
- **WHEN** 用户在同一个 AI 助手面板中多次对话
- **THEN** 前端保留当前会话的消息历史（不清空）

#### Scenario: 关闭面板
- **WHEN** 用户关闭 AI 助手面板
- **THEN** 前端断开 Claude 连接（发送 `disconnect`），关闭 WebSocket

### Requirement: 配置管理

系统 SHALL 支持通过 `QSWebConfig.json` 集中管理所有 AI 功能配置。

#### Scenario: 模式切换
- **WHEN** 管理员修改 `factor_def.claude.mode` 配置
- **THEN** 重启后端后生效：`"cli"` 使用子进程方案，`"sdk"` 使用 SDK 方案

#### Scenario: 初始提示模板
- **WHEN** 后端构造发送给 Claude 的初始提示
- **THEN** 使用 `factor_def.claude.system_prompt` 模板，替换 `{user_prompt}` 和 `{scripts_dir}` 占位符；模板为空时直接透传用户输入

#### Scenario: 工作目录配置
- **WHEN** 后端启动 Claude
- **THEN** 使用 `factor_def.claude.repo_root` 作为 `cwd`，默认值从 `config.py` 位置自动计算
