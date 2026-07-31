# ai-workbench-page

## Purpose

独立 AI 工作台页面 `/ai`，提供全屏的 AI 对话界面，包含会话历史列表和当前会话的聊天面板，支持多会话管理（新建/切换/删除）和上下文切换。

## ADDED Requirements

### Requirement: 页面布局

`/ai` 页面 SHALL 采用左侧会话列表 + 右侧聊天面板的布局。

#### Scenario: 默认布局

- **WHEN** 用户导航到 `/ai`
- **THEN** 左侧显示会话列表（宽度 ~280px，可收起），右侧显示 `AiChatPanel`（全屏）

#### Scenario: 首次访问

- **WHEN** 用户首次访问 `/ai` 且无历史会话
- **THEN** 自动创建新会话（context 为 `default_context`），会话列表为空，聊天面板显示欢迎语

#### Scenario: 已有会话时访问

- **WHEN** 用户访问 `/ai` 且有历史会话
- **THEN** 自动选中最近更新的会话，加载其消息历史到聊天面板

### Requirement: 会话列表

会话列表 SHALL 展示所有历史会话并支持基本管理。

#### Scenario: 显示会话列表

- **WHEN** 会话列表加载完成
- **THEN** 每个列表项显示：会话标题（或自动生成的摘要）、context 标签、更新时间、消息数量

#### Scenario: 切换会话

- **WHEN** 用户点击某个会话
- **THEN** 右侧聊天面板切换为该会话：断开当前 WebSocket，加载新会话的消息历史，显示已加载状态

#### Scenario: 新建会话

- **WHEN** 用户点击"新建会话"按钮
- **THEN** 创建新会话（context 默认为当前页面的 context 选择器的值或 `default_context`），清空聊天面板，新建列表项

#### Scenario: 删除会话

- **WHEN** 用户点击某个会话的删除按钮并确认
- **THEN** 调用 `DELETE /api/ai/sessions/{id}` 删除该会话及其消息文件，列表中移除该条目
- **WHEN** 删除的是当前活跃会话
- **THEN** 自动切换到最近更新的其他会话

### Requirement: 上下文选择

`/ai` 页面 SHALL 支持用户手动选择 AI 上下文。

#### Scenario: 上下文选择器

- **WHEN** 用户在 `/ai` 页面
- **THEN** 聊天面板标题栏显示上下文选择器（下拉菜单），列出 `ai_workbench.contexts` 中所有已配置的 context

#### Scenario: 切换上下文

- **WHEN** 用户选择不同的 context（如从 "general" 切换到 "factor"）
- **THEN** 输入框占位文字更新为该 context 的 `placeholder`；后续消息将使用新 context 的 system_prompt/skills/tools

### Requirement: 会话恢复

`/ai` 页面 SHALL 支持从历史会话恢复对话。

#### Scenario: 点击恢复会话

- **WHEN** 用户在 `/ai` 页面选中一个历史会话
- **THEN** 聊天面板加载该会话的消息历史（最近 200 条），`runState` 为 `'done'`
- **WHEN** 用户发送追问消息
- **THEN** 后端通过 `--resume {session_id}` 恢复 Claude 对话上下文

### Requirement: 新建会话自动保存

系统 SHALL 在新会话首次收到 AI 回复时自动保存会话。

#### Scenario: 自动保存

- **WHEN** 新会话中 AI 首次返回 `assistant` 消息
- **THEN** 后端自动创建 `{session_id}.json` 文件并在 `index.json` 中注册会话条目

#### Scenario: 保存会话标题

- **WHEN** 会话首次保存
- **THEN** 使用用户第一条消息的前 50 个字符作为会话标题
