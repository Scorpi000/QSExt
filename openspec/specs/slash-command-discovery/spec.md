# Slash Command Discovery

后端从 Claude Code 会话初始化消息中提取可用 slash 命令列表并转发给前端。

## Requirements

### Requirement: 后端转发 slash_commands 列表

系统 SHALL 在 Claude Code 会话初始化时，从 `system/init` 消息中提取可用 slash 命令列表，并通过 WebSocket 转发给前端。

SDK 模式下，`format_message()` SHALL 检测 `SystemMessage` 的 `subtype == "init"`，提取 `data["slash_commands"]`、`data["session_id"]`、`data["model"]`，封装为 `{"type":"init","data":{...}}` 格式。

CLI 模式下，`_parse_cli_message()` SHALL 检测 `{"type":"system","subtype":"init"}` 的 JSON 消息，提取 `data["slash_commands"]`、`data["session_id"]`、`data["model"]`，封装为 `{"type":"init","data":{...}}` 格式。

两种模式下，非 `init` 的 system 消息 SHALL 保持当前行为（不转发给前端）。

`slash_commands` 列表中的每个元素 SHALL 为字符串（命令名，如 `"compact"`、`"develop-factor"`）。

#### Scenario: SDK 模式首次连接收到 init 消息

- **WHEN** SDK 模式下的 AiService 启动并收到 `SystemMessage(subtype="init", data={"slash_commands": ["compact", "clear", "context", "develop-factor"], "session_id": "abc123", "model": "claude-sonnet-5"})`
- **THEN** `format_message()` 返回 `{"type": "init", "data": {"session_id": "abc123", "slash_commands": ["compact", "clear", "context", "develop-factor"], "model": "claude-sonnet-5"}}`

#### Scenario: CLI 模式首次连接收到 init 消息

- **WHEN** CLI 模式下的 AiServiceCLI 从 stdout 读到 `{"type":"system","subtype":"init","session_id":"xyz789","slash_commands":["compact","clear"],"model":"claude-sonnet-5"}`
- **THEN** `_parse_cli_message()` 返回 `{"type": "init", "data": {"session_id": "xyz789", "slash_commands": ["compact", "clear"], "model": "claude-sonnet-5"}}`

#### Scenario: CLI 模式收到非 init 系统消息

- **WHEN** CLI 模式收到 `{"type":"system","subtype":"thinking_tokens",...}`
- **THEN** `_parse_cli_message()` 返回 `None`（消息被过滤）

### Requirement: 前端存储可用命令列表

`AiChatClient` SHALL 支持 `"init"` 消息类型，在 `onMessage` 回调中触发。

`AiChatPanel` SHALL 在收到 `"init"` 消息后，用返回的 `slash_commands` 列表替换组件状态。

`AiChatPanel` SHALL 以 4 个内置命令（`compact`、`clear`、`context`、`usage`）作为 `slashCommands` 的初始种子，确保用户在发送第一条消息之前即可使用 slash 命令。

#### Scenario: 前端收到 init 消息并更新命令

- **WHEN** `slashCommands` 初始值为 `["compact","clear","context","usage"]`，前端通过 WebSocket 收到 `{"type":"init","data":{"slash_commands":["compact","clear","context","usage","develop-factor"]}}`
- **THEN** `slashCommands` state 更新为 `["compact","clear","context","usage","develop-factor"]`

#### Scenario: 初始状态展示内置命令

- **WHEN** AiChatPanel 刚挂载，尚未收到 `init` 消息
- **THEN** `slashCommands` state 为 `["compact", "clear", "context", "usage"]`
