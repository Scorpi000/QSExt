## Context

QSWeb AI 助手通过 WebSocket 连接 Claude Code（支持 SDK `ClaudeSDKClient` 和 CLI `claude -p` 两种模式）。Claude Code 在会话初始化时通过 `system/init` 消息返回当前可用的 slash 命令列表（`data["slash_commands"]`），但当前后端代码在两个地方丢弃了该信息：

- **SDK 模式**：[ai_service.py:283-287](QSWeb/backend/app/services/ai_service.py#L283-L287) `format_message()` 对 `SystemMessage` 使用 `str(msg)` → 丢失 `data` 字典内容
- **CLI 模式**：[ai_service_cli.py:319-327](QSWeb/backend/app/services/ai_service_cli.py#L319-L327) `_parse_cli_message()` 把 `system/init` 转成 `"session: xxx"` 文本 → 丢弃 `slash_commands`

Slash 命令的发送路径不需要任何修改：它们就是普通 prompt 文本（`"/compact"`、`"/develop-factor"`），当前的 `query()` 和 `_send_json()` 已经透传。

## Goals / Non-Goals

**Goals:**
- 后端将 `system/init` 中的 `slash_commands` 列表完整转发给前端
- 前端在 AiChatPanel 输入框中输入 `/` 时弹出命令下拉菜单
- 已有 `.claude/skills/` 下的 13 个 skill 自动可用
- 支持键盘上下选择 + Enter 确认 + 鼠标点击

**Non-Goals:**
- 不修改 WebSocket 通信协议（协议已透传 slash 命令）
- 不新增 CLI 参数或 Claude Code 配置
- 不将 CLI `-p` 模式改为持久连接（`/compact` 等历史依赖命令在 CLI 模式下的限制不在范围内）
- 不新增对自定义命令参数（如 `/fix-issue 123`）的智能补全——用户选择命令后手动输入参数

## Decisions

### 1. 消息格式：`"init"` 替代 `"system"`

**决定**：`system/init` 消息以独立的 `"init"` 类型转发，而非套在 `"system"` 类型下。

**理由**：
- `"system"` 类型目前已被前端忽略（onMessage 中无对应 case），复用 `"system"` 容易与新 system 消息混淆
- `"init"` 有明确的初始化语义，前端只需处理一次来存储 `slash_commands`
- 前端 `ai.ts` 的 `AiMessageType` 已支持任意字符串联合类型

**替代方案**：在 `"system"` 消息中加 `subtype` 字段 → 增加前端解析复杂度，不如直接扁平化

### 2. Slash 检测：onChange 中解析光标位置

**决定**：在 TextArea 的 `onChange` 回调中检测当前输入是否以 `/` 开头且光标在词末。

**实现**：
```typescript
// 检测是否触发 slash 面板
function scanSlashTrigger(
  value: string,
  cursorPos: number
): { active: boolean; prefix: string } {
  // 找到光标前最近的 `/`，检查它是否在行首或空格后
  const beforeCursor = value.slice(0, cursorPos)
  const slashIdx = beforeCursor.lastIndexOf('/')
  if (slashIdx === -1) return { active: false, prefix: '' }
  // 检查 `/` 前面的字符：必须是行首或空格
  if (slashIdx > 0 && beforeCursor[slashIdx - 1] !== ' ') {
    return { active: false, prefix: '' }
  }
  // `/` 后面到光标的文本作为过滤前缀
  const prefix = beforeCursor.slice(slashIdx + 1)
  return { active: true, prefix }
}
```

**理由**：
- antd `TextArea` 不提供原生 autocomplete hooks
- cursor position 通过 `e.target.selectionStart` 获取
- 简单正则无法覆盖光标位置变化（用户在中间编辑）

**替代方案**：使用 `contentEditable` div + 自定义 mention 系统 → 过度设计，TextArea 够用

### 3. SlashCommandPalette：绝对定位 overlay

**决定**：SlashCommandPalette 是一个绝对定位的 `<div>`，渲染在输入框上方，不修改 TextArea 本身。

**架构**：
```
AiChatPanel
├── 消息列表 (scrollable)
├── SlashCommandPalette (absolute, bottom-aligned to input area)
└── 输入区
    └── TextArea + 发送按钮
```

**理由**：
- 不需要修改 antd TextArea 的内部行为
- 面板可通过 `useRef` + `getBoundingClientRect()` 定位到输入框上方
- portal 渲染到 body 避免 overflow:hidden 裁剪（输入区容器可能有 overflow）

**替代方案**：使用 antd `AutoComplete` 包裹 TextArea → AutoComplete 对多行文本支持不佳

### 4. 命令过滤：前缀匹配

**决定**：用户输入 `/abc` 时，面板展示 `slash_commands` 中以 `"abc"` 开头（忽略大小写）的命令。

不对命令添加 `"/"` 前缀到过滤字符串中——`slash_commands` 中的命令名本身不含 `/`（如 `"compact"`、`"develop-factor"`），用户输入 `/develop` 时实际过滤前缀是 `"develop"`。

**理由**：
- `slash_commands` 列表中的名称不含 `/` 前缀（这是 Claude Code SDK 的格式）
- 前缀匹配是最直觉的过滤方式
- 命令数量少（通常 <20），不需要模糊匹配

### 5. 无命令描述缓存

**决定**：当前版本不为 slash 命令提供描述文本。Claude Code 的 `system/init` 返回的是命令名字符串列表（`string[]`），不包含描述。

**理由**：
- SDK 的 `slash_commands` 格式为 `string[]`，无内建描述
- 可以通过 `.claude/skills/<name>/SKILL.md` 的 YAML frontmatter 获取描述，但这需要后端额外读取——超出当前范围
- 命令名通常足够自描述（`compact`、`clear`、`develop-factor`）

如果未来需要描述，可以在后端 `system/init` 处理时，额外扫描 `.claude/skills/` 目录读取 `description` 字段来增强。

## Risks / Trade-offs

- **[CLI 模式] `-p` 进程退出后 session 丢失**：`/compact`、`/clear` 等依赖历史上下文的命令在跨 `query()` 调用时不可用 → Mitigation: 面板仍展示这些命令（因为 `system/init` 返回了它们），用户可以使用但需理解 CLI 模式的限制。SDK 模式无此问题。
- **[UI] 命令面板可能遮挡聊天内容**：面板定位在输入框上方，消息列表滚动到底部时可能被遮挡 → Mitigation: 面板高度控制在 200px 以内，带滚动条；消息列表加 `padding-bottom` 在面板激活时自动增大
- **[协议] `init` 消息类型为新增，旧前端不兼容**：如果部署后端但未更新前端，`"init"` 消息被前端忽略（无对应 case）→ Mitigation: 旧前端本来就不处理 `system` 消息，不影响已有功能；这是一个向前兼容的增量变更

## Open Questions

1. **是否需要为每个 context（factor/backtest/risk）展示不同的命令？** → 当前方案所有 context 共享同一组 `slash_commands`，但 `skills` 配置在 context 级别。可以在 `system/init` 后端处理时，根据当前 context 的 `skills` 列表过滤。
2. **是否需要在命令旁显示图标？** → 当前文档未提，实际测试后决定。
