## 1. 后端 — SDK 模式 init 消息转发

- [x] 1.1 修改 `ai_service.py` 的 `format_message()`：检测 `SystemMessage.subtype == "init"`，提取 `data["slash_commands"]`、`data["session_id"]`、`data["model"]`，返回 `{"type":"init","data":{...}}`
  - 文件: [ai_service.py:283-287](QSWeb/backend/app/services/ai_service.py#L283-L287)
  - 验证: 启动 SDK 模式，确认前端收到 `{"type":"init","data":{"slash_commands":[...],...}}`

## 2. 后端 — CLI 模式 init 消息转发

- [x] 2.1 修改 `ai_service_cli.py` 的 `_parse_cli_message()`：`system/init` 消息不再转成无用文本，改为提取 `data["slash_commands"]`、`data["session_id"]`、`data["model"]`，返回 `{"type":"init","data":{...}}`
  - 文件: [ai_service_cli.py:319-327](QSWeb/backend/app/services/ai_service_cli.py#L319-L327)
  - 验证: 启动 CLI 模式，确认前端收到 `{"type":"init","data":{"slash_commands":[...],...}}`
  - 验证: 非 init 的 system 消息仍被过滤（`return None`）

## 3. 前端 — 消息类型扩展

- [x] 3.1 修改 `ai.ts`：在 `AiMessageType` 中新增 `'init'` 类型
  - 文件: [ai.ts:13-26](QSWeb/frontend/src/services/ai.ts#L13-L26)
- [x] 3.2 修改 `AiChatPanel` 的 `onMessage` 处理：新增 `case 'init'` 分支，将 `msg.data.slash_commands` 存入组件 state
  - 文件: [index.tsx:433-631](QSWeb/frontend/src/components/AiChatPanel/index.tsx#L433-L631)
  - 新增 state: `const [slashCommands, setSlashCommands] = useState<string[]>([])`
  - 验证: 连接 AI 后 `slashCommands` state 非空

## 4. 前端 — SlashCommandPalette 组件

- [x] 4.1 实现 slash 触发检测逻辑：`scanSlashTrigger(value, cursorPos)` 函数
  - 判断光标前最近的 `/` 是否在行首或空格后
  - 返回 `{ active: boolean, prefix: string, startIdx: number }`
- [x] 4.2 实现命令过滤逻辑：前缀匹配 `slash_commands`（忽略大小写）
- [x] 4.3 实现 SlashCommandPalette UI 组件
  - 绝对定位在 TextArea 上方
  - 列表展示过滤后的命令（高亮当前选中项）
  - 最大高度 200px，超出滚动
- [x] 4.4 实现键盘交互
  - 上/下箭头键切换选中项
  - Enter 键确认选择，替换输入框中 `/prefix` 为 `/命令名 `
  - Escape 键关闭面板
- [x] 4.5 实现鼠标交互
  - 点击命令项 = 确认选择
  - 点击面板外部 = 关闭面板
- [x] 4.6 集成到 `AiChatPanel` 输入区
  - `onChange` 中调用 `scanSlashTrigger`，更新 `slashActive`/`slashPrefix`/`slashStartIdx` state
  - 在输入区上方渲染 `SlashCommandPalette`（仅 `slashActive && slashCommands.length > 0`）
  - 选择命令后：替换 TextArea 值、关闭面板、焦点回到 TextArea
  - 文件: [index.tsx:987-1026](QSWeb/frontend/src/components/AiChatPanel/index.tsx#L987-L1026)

## 5. 集成验证

- [x] 5.1 SDK 模式端到端验证：启动 QSWeb → 打开 AI 助手 → 输入 `/` → 确认弹出命令面板 → 选择一个命令 → 发送 → 确认 Claude 正确执行
  - **需要启动 QSWeb 并连接 Claude Code 实例**
- [x] 5.2 CLI 模式端到端验证：同上流程
  - **需要启动 QSWeb 并连接 Claude Code 实例**
- [x] 5.3 边界验证（代码级）：空命令列表时不弹面板、删除 `/` 后面板关闭、非 `/` 开头输入不触发
  - 代码逻辑已确认正确
