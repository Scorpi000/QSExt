## ADDED Requirements

### Requirement: 输入 `/` 触发命令面板

`AiChatPanel` SHALL 在用户于输入框中输入 `/` 字符时，弹出 SlashCommandPalette 下拉菜单，展示所有从 `system/init` 中获取的可用 slash 命令。

面板 SHALL 定位在输入框上方，不遮挡输入框和聊天内容。

面板 SHALL 在以下情况下关闭：
- 用户按下 Escape 键
- 用户点击面板外部区域
- 用户选择了一个命令

面板 SHALL 在用户删除 `/` 字符（输入框不以 `/` 开头）时自动关闭。

#### Scenario: 在空白输入框输入 `/`

- **WHEN** 输入框为空，用户键入 `/`
- **THEN** SlashCommandPalette 出现，展示所有可用命令

#### Scenario: 在已有文本的输入框中间输入 `/`

- **WHEN** 输入框已有文本 "请帮我 "，用户在末尾键入 `/`
- **THEN** SlashCommandPalette 出现（仅在 `/` 是行首或空格后的首个字符时）

#### Scenario: 输入 `/` 后直接是一个字符

- **WHEN** 输入框内容为 `/c`，slash_commands 包含 `["compact", "clear", "context"]`
- **THEN** SlashCommandPalette 展示过滤后的命令：`["compact", "clear"]`（前缀匹配 `/c`）

#### Scenario: 删除 `/` 后面板关闭

- **WHEN** SlashCommandPalette 正在显示，用户删除 `/` 字符（输入框不再以 `/` 开头）
- **THEN** SlashCommandPalette 关闭

### Requirement: 命令面板展示

SlashCommandPalette SHALL 以列表形式展示命令，每项包含：
- 命令名（带 `/` 前缀，如 `/compact`）
- 命令描述（如有）

列表 SHALL 支持键盘上下键选择，Enter 键确认。

列表 SHALL 支持鼠标点击选择。

当前选中项 SHALL 有视觉高亮。

#### Scenario: 键盘选择命令

- **WHEN** SlashCommandPalette 显示 3 个命令，用户按 2 次下箭头键
- **THEN** 第 3 个命令高亮显示

#### Scenario: Enter 确认选择

- **WHEN** SlashCommandPalette 显示，第 2 个命令高亮，用户按下 Enter
- **THEN** 输入框内容替换为 "/该命令名 "，面板关闭，焦点回到输入框

#### Scenario: 鼠标点击选择

- **WHEN** SlashCommandPalette 显示，用户点击第 1 个命令
- **THEN** 输入框内容替换为 "/该命令名 "，面板关闭，焦点回到输入框

### Requirement: 命令从 system/init 动态获取

SlashCommandPalette SHALL 以 4 个内置命令（`compact`、`clear`、`context`、`usage`）作为初始种子，在收到 `system/init` 消息后用 Claude Code 返回的完整 `slash_commands` 列表替换。

这样用户在发送第一条消息之前即可使用内置 slash 命令。

#### Scenario: 初始状态展示内置命令

- **WHEN** AiChatPanel 刚挂载，尚未收到 `init` 消息，用户在输入框键入 `/`
- **THEN** SlashCommandPalette 展示 4 个内置命令：`/compact`、`/clear`、`/context`、`/usage`

#### Scenario: init 消息到达后更新命令列表

- **WHEN** `slashCommands` 初始值为 `["compact", "clear", "context", "usage"]`，收到 `{"type":"init","data":{"slash_commands":["compact","clear","context","usage","develop-factor"]}}`
- **THEN** `slashCommands` 更新为 `["compact","clear","context","usage","develop-factor"]`
