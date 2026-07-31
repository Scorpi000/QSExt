# ai-chat-panel

## Purpose

通用 AI 聊天面板组件 `AiChatPanel`，提供文本/Markdown/思考过程/工具调用/action_card/data_block/ask_user 的多消息类型渲染能力。作为所有 AI 对话交互的底层 UI 组件，不包含任何业务逻辑，通过 props 注入 context、placeholder、action handlers 等差异化行为。被 `AiChatDrawer`、`AiWorkbench` 页面、`AiFactorAssistant` 等复用。

## Requirements

### Requirement: 通用消息渲染

`AiChatPanel` SHALL 支持以下消息类型的渲染：用户消息（文本气泡）、AI 文本回复（Markdown 渲染）、思考过程（可折叠，默认收起）、工具调用（绿色卡片）、流式增量文本（追加到上一条 AI 消息）。

#### Scenario: 渲染用户消息

- **WHEN** 用户发送一条消息
- **THEN** 消息以右对齐蓝色气泡显示，顶部显示"你"标签

#### Scenario: 渲染 AI 文本回复

- **WHEN** AI 返回 `type: "assistant"` 消息，blocks 中包含 `kind: "text"` 块
- **THEN** 消息以左对齐灰色气泡显示，顶部显示"AI 助手"标签，内容支持 Markdown 渲染

#### Scenario: 渲染思考过程

- **WHEN** AI 返回的消息中包含 `kind: "thinking"` 块
- **THEN** 在消息气泡内部显示可折叠的"💭 思考过程"区域，默认收起；展开后以灰色小字等宽字体显示，最大高度 200px

#### Scenario: 渲染工具调用

- **WHEN** AI 返回 `kind: "tool_use"` 或 `kind: "tool_result"` 块
- **THEN** 显示绿色边框卡片，展示工具名称和结果内容

#### Scenario: 流式文本追加

- **WHEN** AI 返回 `type: "stream"` 消息
- **THEN** 若上一条消息是 AI 文本回复（非工具调用），将流式内容追加到该消息末尾；否则创建新消息

### Requirement: 代码块与富媒体渲染

`AiChatPanel` SHALL 支持代码块语法高亮和结构化数据块的富媒体渲染。

#### Scenario: 代码块检测

- **WHEN** AI 回复包含 Markdown 代码块（```language ... ```）
- **THEN** 代码块以深色背景、等宽字体展示，语言标签显示在右上角

#### Scenario: data_block 渲染

- **WHEN** AI 返回 `type: "data_block"` 消息，`data.kind` 为 `"factor_table"`、`"chart"`、`"dag"` 等
- **THEN** 根据 `kind` 选择对应的富媒体渲染器；未知 kind 以 JSON 格式展示 `data.payload`

### Requirement: 会话状态管理

`AiChatPanel` SHALL 管理 Claude 运行状态并在 UI 上反馈。

#### Scenario: 状态指示

- **WHEN** `runState` 为 `'idle'` → 输入框显示 `placeholder` prop，发送按钮为"发送"
- **WHEN** `runState` 为 `'running'` → 旋转 spinner + "AI 正在思考..."，显示红色"停止"按钮
- **WHEN** `runState` 为 `'done'` → spinner 消失，绿色"已完成" Badge

#### Scenario: 发送初始消息

- **WHEN** `runState` 为 `'idle'` 且用户输入非空内容后点击发送
- **THEN** 通过 `AiChatClient.start(prompt, context)` 发送 `{action: "start", context, prompt}`，`runState` → `'running'`

#### Scenario: 多轮追问

- **WHEN** `runState` 为 `'done'` 且用户输入非空内容后点击发送
- **THEN** 通过 `AiChatClient.sendQuery(prompt)` 发送 `{action: "query", prompt}`，`runState` → `'running'`

#### Scenario: 新建会话

- **WHEN** 用户点击"新建会话"按钮
- **THEN** 调用 `AiChatClient.disconnect()`，清空消息列表，重置 `runState` 为 `'idle'`

### Requirement: 可配置 Props

`AiChatPanel` SHALL 通过 props 支持差异化配置：`context`、`placeholder`、`headerExtra`、`initialMessages`、`onAction`、`sessionId`。`initialMessages` 变化时通过 `useEffect` 同步到 `messages` 状态支持会话恢复。

### Requirement: action_card 渲染

`AiChatPanel` SHALL 通用渲染 `action_card` 消息类型。收到后渲染 `ActionCard` 子组件（绿色边框卡片、标题、摘要 key-value、操作按钮），按钮点击调用 `onAction(key, payload)`，成功显示"✓ 操作成功"，失败显示"✗ {error.message}"，`style: "default"` 按钮点击后卡片收起。

### Requirement: ask_user 消息渲染

`AiChatPanel` SHALL 支持 `ask_user` 消息类型的交互式问题面板。渲染 `AskUserPanel` 组件，单选用 `Radio.Group`、多选用 `Checkbox.Group`。用户提交后调用 `clientRef.current.sendAnswer(answers)` 通过 WebSocket 发送答案到后端，按钮变为 disabled 显示"已提交"。未回答的单选问题自动取第一个选项，多选取空数组。
