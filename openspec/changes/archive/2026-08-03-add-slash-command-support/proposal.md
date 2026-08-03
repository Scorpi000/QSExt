## Why

QSWeb 的 AI 助手基于 Claude Code（SDK/CLI），Claude Code 原生支持通过 `/` 前缀的内置命令和自定义 skill 命令，但 QSWeb 的后端消息解析丢弃了包含可用命令列表的 `system/init` 消息，前端也无 slash 命令的发现和补全 UI，导致用户完全无法使用这一能力。项目中已有 13 个 `.claude/skills/`（如 `/develop-factor`、`/openspec-propose` 等），它们本就可作为 slash 命令使用，只是从未被暴露给用户。

## What Changes

- 后端 `_parse_cli_message()` 和 `format_message()` 不再丢弃 `system/init` 消息，而是提取 `slash_commands` 列表并转发给前端
- 前端新增 `init` 消息类型处理，存储可用命令列表
- **BREAKING**: `system/init` 消息格式变更——从无用的 `{"type":"system","data":{"content":"session: xxx"}}` 改为 `{"type":"init","data":{"session_id":"...","slash_commands":[...],"model":"..."}}`
- AiChatPanel 新增 SlashCommandPalette：输入 `/` 时弹出下拉命令菜单，支持键盘选择和点击选择
- 所有 `.claude/skills/` 下的 skill 自动作为 slash 命令可用

## Capabilities

### New Capabilities

- `slash-command-discovery`: Claude Code 启动时通过 `system/init` 消息获取可用 slash 命令列表，后端转发、前端存储
- `slash-command-palette`: AiChatPanel 输入框中输入 `/` 时弹出命令下拉菜单，展示可用命令及其描述，支持键盘/鼠标选择自动填充

### Modified Capabilities

<!-- 不修改任何现有 spec 的 requirement，仅新增能力 -->

## Impact

- `QSWeb/backend/app/services/ai_service_cli.py` (`_parse_cli_message` 方法，system/init 分支)
- `QSWeb/backend/app/services/ai_service.py` (`format_message` 静态方法，SystemMessage 分支)
- `QSWeb/frontend/src/services/ai.ts` (新增 `InitMessage` 类型)
- `QSWeb/frontend/src/components/AiChatPanel/index.tsx` (新增 SlashCommandPalette 组件 + onMessage 处理)
- 消息协议：`system/init` 消息格式变更（BREAKING，但前端此前从未使用该消息）
