# ai-chat-panel

## Purpose

通用 AI 聊天面板组件 `AiChatPanel`，提供文本/Markdown/思考过程/工具调用/action_card/data_block 的多消息类型渲染能力。作为所有 AI 对话交互的底层 UI 组件，不包含任何业务逻辑，通过 props 注入 context、placeholder、action handlers 等差异化行为。

## ADDED Requirements

### Requirement: 通用消息渲染

`AiChatPanel` SHALL 支持以下消息类型的渲染：

- 用户消息（文本气泡）
- AI 文本回复（Markdown 渲染）
- 思考过程（可折叠，默认收起）
- 工具调用（绿色卡片，展示工具名称和结果）
- 流式增量文本（追加到上一条 AI 消息）

#### Scenario: 渲染用户消息

- **WHEN** 用户发送一条消息
- **THEN** 消息以右对齐蓝色气泡显示，顶部显示"你"标签

#### Scenario: 渲染 AI 文本回复

- **WHEN** AI 返回 `type: "assistant"` 消息，blocks 中包含 `kind: "text"` 块
- **THEN** 消息以左对齐灰色气泡显示，顶部显示"AI 助手"标签，内容支持 Markdown 渲染

#### Scenario: 渲染思考过程

- **WHEN** AI 返回的消息中包含 `kind: "thinking"` 块
- **THEN** 在消息气泡内部显示可折叠的"💭 思考过程"区域，默认收起
- **WHEN** 思考过程被展开
- **THEN** 以灰色小字等宽字体显示思考内容，最大高度 200px，超出滚动

#### Scenario: 渲染工具调用

- **WHEN** AI 返回 `kind: "tool_use"` 块
- **THEN** 显示绿色边框卡片，包含"调用工具: {tool_name}"标签
- **WHEN** AI 返回 `kind: "tool_result"` 块
- **THEN** 显示绿色边框卡片，内容为工具返回结果（文本截断，可展开）

#### Scenario: 流式文本追加

- **WHEN** AI 返回 `type: "stream"` 消息
- **THEN** 若上一条消息是 AI 文本回复（非工具调用、非代码），将流式内容追加到该消息末尾；否则创建新消息

### Requirement: 代码块与富媒体渲染

`AiChatPanel` SHALL 支持代码块语法高亮和结构化数据块的富媒体渲染。

#### Scenario: 代码块检测

- **WHEN** AI 回复包含 Markdown 代码块（```language ... ```）
- **THEN** 代码块以深色背景、等宽字体展示，语言标签显示在右上角

#### Scenario: data_block 渲染

- **WHEN** AI 返回 `type: "data_block"` 消息，`data.kind` 为 `"factor_table"`、`"chart"`、`"dag"`、`"risk_heatmap"` 等
- **THEN** 根据 `kind` 选择对应的富媒体渲染器（表格→DataTable，图表→Plotly，DAG→DAGViewer），将 `data.payload` 传递给渲染器

#### Scenario: 未知 data_block 类型

- **WHEN** data_block 的 `kind` 无对应渲染器
- **THEN** 以 JSON 格式展示 `data.payload`

### Requirement: 会话状态管理

`AiChatPanel` SHALL 管理 Claude 运行状态并在 UI 上反馈。

#### Scenario: 状态指示

- **WHEN** `runState` 为 `'idle'`
- **THEN** 输入框占位文字为 `placeholder` prop 的值（默认"描述你想做的事情..."），发送按钮文字为"发送"
- **WHEN** `runState` 为 `'running'`
- **THEN** 显示旋转 spinner + "AI 正在思考..."，发送按钮文字变为"追问"，同时显示红色"停止"按钮
- **WHEN** `runState` 为 `'done'`
- **THEN** spinner 消失，显示绿色"已完成" Badge，发送按钮文字恢复为"发送"

#### Scenario: 发送初始消息

- **WHEN** `runState` 为 `'idle'` 且用户输入非空内容后点击发送（或 Ctrl+Enter）
- **THEN** 通过 `AiChatClient.start(prompt)` 发送 `{action: "start", context: "...", prompt: "..."}` 到后端，`runState` 变为 `'running'`

#### Scenario: 多轮追问

- **WHEN** `runState` 为 `'done'` 且用户输入非空内容后点击发送
- **THEN** 通过 `AiChatClient.sendQuery(prompt)` 发送 `{action: "query", prompt: "..."}` 到后端，`runState` 变为 `'running'`

#### Scenario: 中断 AI

- **WHEN** `runState` 为 `'running'` 且用户点击"停止"按钮
- **THEN** 调用 `AiChatClient.interrupt()`，前端显示"已中断"状态

#### Scenario: 新建会话

- **WHEN** 用户点击"新建会话"按钮
- **THEN** 调用 `AiChatClient.disconnect()`，清空消息列表，重置 `runState` 为 `'idle'`

### Requirement: 可配置 Props

`AiChatPanel` SHALL 通过 props 支持差异化配置，不包含任何业务逻辑。

#### Scenario: 自定义输入框占位文字

- **WHEN** 传入 `placeholder` prop
- **THEN** 输入框使用此值作为占位文字；未传入时使用默认值

#### Scenario: 自定义标题栏扩展

- **WHEN** 传入 `headerExtra` prop（ReactNode）
- **THEN** 在标题栏右侧渲染此内容

#### Scenario: 预设初始消息

- **WHEN** 传入 `initialMessages` prop
- **THEN** 组件初始化时消息列表包含这些消息而非空数组

### Requirement: action_card 渲染

`AiChatPanel` SHALL 通用渲染 `action_card` 消息类型。

#### Scenario: 渲染操作卡片

- **WHEN** AI 返回 `type: "action_card"` 消息
- **THEN** 渲染带绿色边框的卡片，包含 `data.title`（标题）、`data.summary`（Key-Value 摘要信息）、操作按钮列表

#### Scenario: 操作按钮点击

- **WHEN** 用户点击 action_card 中的按钮
- **THEN** 调用 `onAction(key, payload)` prop 回调，按钮进入 loading 状态
- **WHEN** `onAction` 返回的 Promise resolve
- **THEN** 按钮恢复；若 resolve 为 `{success: true}`，卡片显示"操作成功"；若 reject，卡片显示错误信息

#### Scenario: 放弃操作

- **WHEN** 用户点击 action_card 中的 `style: "default"` 按钮（如"放弃"）
- **THEN** 卡片收起或隐藏，不执行任何服务端操作

### Requirement: ask_user 消息渲染

`AiChatPanel` SHALL 支持 `ask_user` 消息类型的交互式问题面板。

#### Scenario: 接收 ask_user 消息

- **WHEN** 后端发送 `type: "ask_user"` 消息，`data.questions` 包含问题列表
- **THEN** 渲染 `AskUserPanel` 组件，每个问题显示 header 标签 + question 文本 + 选项列表

#### Scenario: 单选问题

- **WHEN** 问题 `multiSelect: false`
- **THEN** 使用 `Radio.Group` 渲染选项，默认选中第一个，点击选项切换

#### Scenario: 多选问题

- **WHEN** 问题 `multiSelect: true`
- **THEN** 使用 `Checkbox.Group` 渲染选项，支持多选

#### Scenario: 提交答案

- **WHEN** 用户点击"提交"按钮
- **THEN** 调用 `clientRef.current.sendAnswer(answers)` 通过 WebSocket 发送答案到后端
- **AND** 按钮变为 disabled 状态显示"已提交"

#### Scenario: 未回答问题的默认值

- **WHEN** 用户提交时某问题未选择
- **THEN** 单选自动取第一个选项，多选自动取空数组
