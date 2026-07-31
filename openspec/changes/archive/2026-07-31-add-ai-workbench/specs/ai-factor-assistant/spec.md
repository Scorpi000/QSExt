# ai-factor-assistant (Delta)

## MODIFIED Requirements

### Requirement: Chat 面板

系统 SHALL 在因子工作台提供 AI 助手 Chat 面板，底层使用通用 `AiChatPanel` 组件 + `context="factor"` 配置驱动。

#### Scenario: 打开 AI 助手

- **WHEN** 用户在因子工作台点击"AI 辅助创建"按钮
- **THEN** 系统打开 `AiChatDrawer`（复用全局 Drawer 组件），context 显式指定为 `"factor"`

#### Scenario: 发送初始消息

- **WHEN** 用户在输入框中输入因子需求描述并发送（runState=idle）
- **THEN** 系统发送 `{"action": "start", "context": "factor", "prompt": "..."}` 到后端，后端创建新 Claude 会话（加载 `factor` context 配置的 system_prompt/skills/tools），开始流式接收 AI 回复

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

- **WHEN** Claude 生成包含代码块的回复
- **THEN** 前端以深色背景语法高亮展示代码块（不再特殊检测 `__FACTOR_META__` 或 `defFactor` 关键词）

#### Scenario: 结果不重复展示

- **WHEN** 正常完成（ResultMessage, is_error=false）
- **THEN** 后端不发可见消息，仅发送 `done` 信号停止 spinner
- **WHEN** 异常完成（is_error=true）
- **THEN** 前端显示红色错误消息

### Requirement: 生成结果处理

系统 SHALL 通过 action_card 协议处理 AI 生成的脚本结果。

#### Scenario: action_card 展示操作

- **WHEN** Claude 完成脚本生成后返回 `type: "action_card"` 消息，`kind` 为 `"save_script"`
- **THEN** 前端渲染操作卡片，显示脚本次元信息（TargetTable/IDType/defFactor），提供"保存脚本"和"放弃"按钮

#### Scenario: 用户保存脚本

- **WHEN** 用户点击"保存脚本"按钮
- **THEN** 调用 `POST /api/factors/import` 保存脚本；成功显示"脚本已保存: {path}"

#### Scenario: 用户放弃脚本

- **WHEN** 用户点击"放弃"按钮
- **THEN** action_card 卡片收起，不执行任何操作

#### Scenario: 生成失败处理

- **WHEN** Claude 未能成功生成脚本（API 错误等）
- **THEN** 前端显示错误信息，用户可在同一会话中发送后续消息继续尝试

### Requirement: 会话管理

系统 SHALL 支持 AI 会话的持久化管理。

#### Scenario: 会话自动保存

- **WHEN** AI 会话中产生消息
- **THEN** 后端通过 `SessionStore` 自动持久化会话和消息（替代仅内存保存）

#### Scenario: 关闭面板

- **WHEN** 用户关闭 AI 助手面板
- **THEN** 前端断开 Claude 连接（发送 `disconnect`），关闭 WebSocket，已保存的会话可通过 `/ai` 页面恢复

### Requirement: 配置管理

系统 SHALL 通过 `QSWebConfig.json` 的 `ai_workbench.contexts.factor` 管理因子场景的 AI 配置。

#### Scenario: 因子上下文配置

- **WHEN** 后端处理 `context="factor"` 的 AI 请求
- **THEN** 使用 `ai_workbench.contexts.factor` 中的 system_prompt、skills、tools 配置（替代旧的 `factor_def.claude` 路径，旧路径保持只读兼容）

### ADDED: SDK 模式迁移

系统 SHALL 使用 `ClaudeSDKClient`（SDK 模式）替代 CLI 子进程模式，以支持原生多轮对话和 AskUserQuestion。

#### Scenario: SDK 模式选择

- **WHEN** `QSWebConfig.json` 中 `ai_workbench.mode` 设置为 `"sdk"`
- **THEN** 后端使用 `AiService`（基于 `ClaudeSDKClient`）处理所有 AI 请求
- **AND** `client.query(prompt)` 在同一 session 内发送后续消息，无需重启进程

#### Scenario: system_prompt 作为系统指令

- **WHEN** context 的 `system_prompt` 不含 `{user_prompt}` 占位符
- **THEN** 通过 `ClaudeAgentOptions(system_prompt=...)` 作为系统指令传给 Claude
- **AND** 用户消息保持纯文本，不做模板格式化

#### Scenario: AskUserQuestion 交互

- **WHEN** Claude 调用 `AskUserQuestion` 内置工具
- **THEN** `can_use_tool` 回调拦截，通过 `asyncio.Event` 等待前端返回答案
- **AND** 前端渲染 `AskUserPanel` 选择界面，用户提交后通过 `answer` action 返回答案
