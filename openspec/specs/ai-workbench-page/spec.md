# ai-workbench-page

## Purpose

独立 AI 工作台页面 `/ai`，提供全屏的 AI 对话界面，包含会话历史列表和当前会话的聊天面板，支持多会话管理（新建/切换/删除/重命名）和上下文切换。

## Requirements

### Requirement: 页面布局

`/ai` 页面 SHALL 采用左侧会话列表（宽度 ~280px，可收起）+ 右侧 `AiChatPanel`（全屏）的布局。首次访问且无历史会话时，自动创建新会话（context 为 `default_context`）。已有会话时自动选中最近更新的会话并加载消息历史。

### Requirement: 会话列表

会话列表 SHALL 展示所有历史会话，每个列表项显示：会话标题、context 标签、更新时间、消息数量。支持选中切换、内联重命名（双击标题或点 ✎ 图标进入编辑，Enter/失焦保存）、删除（Popconfirm 确认）。顶部只保留标题栏，新建统一走 AiChatPanel 标题栏入口。

### Requirement: 上下文选择

`/ai` 页面标题栏显示上下文选择器（下拉菜单），列出 `ai_workbench.contexts` 中所有已配置的 context。切换时更新输入框占位文字和后续消息的 system_prompt/skills/tools。

### Requirement: 会话恢复

选中历史会话后，聊天面板从 `GET /api/ai/sessions/{id}` 加载消息历史（最近 200 条）。AI 消息文本从 `data.blocks` 中 `kind === 'text'` 提取，思考过程从 `kind === 'thinking'` 提取。`runState` 设为 `'done'`，后续追问通过 SDK 的 `client.query()` 在同一 session 内发送。

### Requirement: 新建会话自动保存

新会话首次收到 AI 回复时，后端通过 `SessionStore`（fire-and-forget 模式）自动创建 session 文件并注册索引条目。标题取自用户第一条消息的前 50 字符。新建会话后延迟 500ms 刷新列表等待磁盘写入完成。
