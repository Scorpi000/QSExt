## Context

当前 QSWeb 的 AI 功能由三个组件构成：

```
AiFactorAssistant (前端 Drawer, ~570行)
    ↕ WebSocket /ws/ai/chat
AiServiceCLI (后端, ~470行) — 硬编码因子专用 prompt/skills/tools
    ↕ Claude CLI stream-json
Claude Code
```

`AiChatClient`（前端）和 `AiServiceCLI`（后端）的核心逻辑——WebSocket 连接管理、消息路由、流式解析、CLI 子进程管理——与因子业务无关。因子特定的内容仅集中在：system_prompt 模板（`config.py:74-84`）、skill 链接（`develop-factor`）、前端代码检测（`__FACTOR_META__`/`defFactor`）、导入预览后处理。

本设计将这些通用部分抽象出来，通过 `QSWebConfig.json` 的 `ai_workbench` 配置段驱动不同场景的差异化行为。

## Goals / Non-Goals

**Goals:**
- 将 `AiChatPanel` 抽取为纯通用组件（无因子业务逻辑），支持任意场景复用
- 提供全局 AI 入口（FAB + 快捷键 + 导航菜单），用户在任意页面都能快速唤起
- 提供独立 AI 工作台页面 `/ai`，支持会话历史管理和深度使用
- 后端 `AiServiceCLI` 根据 `context` 动态组装 system_prompt、skills、MCP tools
- 支持 `action_card` 消息协议，实现后端驱动的通用操作按钮
- 基于本地 JSON 文件的轻量会话持久化
- 保持因子工作台现有 AI 功能的用户体验不变

**Non-Goals:**
- 不支持多用户/登录/权限（当前无此需求）
- 不实现 AI 自动执行操作（action_card 必须用户手动确认）
- 不修改 Claude CLI 的调用方式（继续使用子进程 + stream-json 协议）
- 不实现会话跨设备同步

## Decisions

### D1: 上下文感知 — 配置文件驱动 vs 前端路由推断

**选择：`QSWebConfig.json` 配置驱动，前端路由辅助注入。**

```
QSWebConfig.json:
{
  "ai_workbench": {
    "sessions_dir": "~/.qsweb/ai_sessions",
    "default_context": "general",
    "route_context_map": {
      "/factor": "factor",
      "/backtest": "backtest",
      "/risk": "risk",
      "/portfolio": "portfolio"
    },
    "contexts": {
      "general": { ... },
      "factor": { ... },
      ...
    }
  }
}
```

- 各页面通过按钮显式指定 context 时，优先级高于路由映射
- 未匹配路由 + 无显式指定时，回退到 `default_context`
- 后端加载 `contexts.<context>` 配置，组装 system_prompt、skills、tools

**替代方案**：全前端路由推断。缺点是不可配置、不可扩展，后端无法差异化处理。

### D2: 组件架构 — AiChatPanel 的职责边界

**选择：`AiChatPanel` 是纯通用组件，业务逻辑通过 props 注入。**

```
AiChatPanel  (通用，不感知业务)
├── props:
│   ├── context: string              // 传给后端的上下文标识
│   ├── placeholder?: string         // 输入框占位文字
│   ├── extraActions?: ActionDef[]   // 额外的 action_card 处理器
│   ├── onAction?: (key, payload) => Promise<void>  // action 回调
│   └── initialMessages?: ChatMessage[]  // 恢复会话时使用
├── 内部状态:
│   ├── messages, input, runState
│   ├── WebSocket 连接 (AiChatClient)
│   └── 消息渲染 (文本/Markdown/思考/工具/action_card/data_block)
└── 不负责:
    ├── 业务逻辑（保存脚本、注册图库等）→ onAction 回调
    ├── 上下文选择 → 由调用方决定
    └── 会话存储/加载 → 由 AiWorkbench 页面管理

AiChatDrawer (全局入口封装)
├── 包装 AiChatPanel
├── 从当前路由 + route_context_map 推断 context
├── FAB / Ctrl+K / 全局按钮 唤起

AiWorkbench 页面 (/ai)
├── SessionList (左侧) + AiChatPanel (右侧，全屏)
├── 管理会话 CRUD
├── 用户显式选择 context（下拉菜单）
```

### D3: action_card 协议

**选择：后端驱动，前端通用渲染。**

AI 生成的脚本/配置/结果通过 `action_card` 消息类型推送：

```json
{
  "type": "action_card",
  "data": {
    "kind": "save_script",
    "title": "因子脚本已生成",
    "summary": {
      "TargetTable": "因子表名",
      "IDType": "A股",
      "has_def_factor": true
    },
    "actions": [
      { "key": "save", "label": "保存脚本", "style": "primary" },
      { "key": "discard", "label": "放弃", "style": "default" }
    ],
    "payload": {
      "code": "...",
      "filename": "factor.py"
    }
  }
}
```

前端 `ActionCard` 组件负责：
1. 渲染标题 + 摘要信息（通用 key-value 展示）
2. 渲染操作按钮，点击时调用 `onAction(key, payload)`
3. 跟踪按钮 loading 状态

action 的实际请求（如调用 `POST /api/factors/import`）由调用方在 `onAction` 回调中处理。

**替代方案**：前端代码检测（当前做法）。缺点：脆弱、不可扩展、每个场景需写专门的检测逻辑。

### D4: 会话持久化 — 本地 JSON vs 数据库

**选择：本地 JSON 文件 (`~/.qsweb/ai_sessions/`)。**

```
~/.qsweb/ai_sessions/
├── index.json            # [{ id, title, context, created_at, updated_at, message_count }]
├── {session_id}.json     # { messages: [...], context: "...", ... }
```

- Claude CLI 的 `--session-id` / `--resume` 机制已管理 AI 侧的会话状态
- 我们只需存储：元数据（标题/时间/上下文）+ 前端展示用的消息历史副本
- 消息历史限制最近 200 条，超出截断
- 独立页面 `/ai` 加载时读 `index.json` 展示列表，选中时读 `{id}.json` 恢复消息

**替代方案**：Neo4j 图数据库。过度设计——AI 会话不像因子那样有依赖关系需要图遍历。

### D5: 后端 AiServiceCLI 重构策略

**选择：渐进式重构，保持接口兼容。**

当前调用方式：
```python
ai_service.start(prompt, scripts_dir)
```
重构后：
```python
ai_service.start(prompt, context_config)
```
其中 `context_config` 是从 `QSWebConfig.json` 解析的 context 配置字典，包含：
- `system_prompt`（模板字符串）
- `skills`（技能名列表）
- `tools`（允许的工具列表）
- `mcp_servers`（MCP 服务器配置）
- `max_budget_usd`
- `permission_mode`

`_ensure_workspace()` 改为遍历 `skills` 列表，按需链接每个技能目录。

影响范围：
- `config.py`：`factor_def` 属性保持读取旧路径，新增 `ai_workbench` 属性
- `ai_service_cli.py`：`start()` 方法接受 context_config，内部逻辑泛化
- WebSocket handler：从 context 参数查找配置，传给 `AiServiceCLI.start()`

### D6: 前端状态管理

**选择：单组件 `useState` + `useRef`（不引入全局 store）。**

`AiChatPanel` 是自包含组件：
- `messages`, `input`, `runState` — `useState`
- `AiChatClient` 实例 — `useRef`
- context 通过 props 传入，不存储在组件内部状态

会话管理状态在 `AiWorkbench` 页面中管理，不需要全局 store（zustand）。`AiChatDrawer` 从当前 URL 读取路由，不从 store 读取。

### D7: Ctrl+K 快捷键

**选择：在 `MainLayout` 中监听全局键盘事件。**

```typescript
useEffect(() => {
  const handler = (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault()
      setAiDrawerOpen(true)
    }
  }
  window.addEventListener('keydown', handler)
  return () => window.removeEventListener('keydown', handler)
}, [])
```

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| 会话文件损坏或丢失 | 消息历史仅用于前端展示，AI 侧状态由 Claude CLI 管理；文件损坏只影响历史查看，不影响功能 |
| `index.json` 并发写入冲突 | FastAPI 单线程事件循环下串行执行，`asyncio.Lock` 按 session_id 粒度加锁，原子写入（tmp + rename） |
| action_card 协议过于通用，无法满足某些场景 | 允许 `payload` 携带任意 JSON，前端根据 `kind` 选择自定义渲染器；保留扩展点 |
| 上下文配置错误（缺少必填字段） | 后端启动时校验 `ai_workbench` 配置段完整性，缺失字段使用 `default_context` 回退 |
| `AiChatPanel` 抽象后因子场景功能回归 | 复用现有 WebSocket 测试场景（手动测试 AI 因子创建全流程），验证 action_card 保存脚本功能 |
| FAB 按钮遮挡页面内容 | 放在右下角标准位置，与因子池面板不重叠（因子池在右上侧）；z-index 低于 Drawer |

## Implementation Decisions (新增)

### D8: CLI 模式 vs SDK 模式

**最终选择：SDK 模式（`ClaudeSDKClient`），CLI 模式保留但不再维护。**

CLI 模式（子进程 + `stream-json`）发现的关键问题：
- `-p` 模式下 Claude Code **不持久化 session**，`--resume` 永远失败
- 多轮对话需要每次创建新会话，丢失上下文连续性
- 进程生命周期管理复杂（stdin/stdout 管道、线程同步）

SDK 模式优势：
- **原生 `query()`**：同一 session 内发送后续消息，上下文自动保留
- **`can_use_tool` 回调**：`AskUserQuestion` 通过回调 + `asyncio.Event` 等待前端答案
- **`receive_messages()`**：持续接收消息流，forward 任务无需重启
- **`ClaudeAgentOptions`**：统一管理 skills、tools、MCP、system_prompt 等配置

| 对比维度 | CLI 模式 | SDK 模式 |
|---------|---------|---------|
| 多轮对话 | ❌ 需新会话 | ✅ `client.query()` |
| Session 持久化 | ❌ `-p` 不保存 | ✅ SDK 内部管理 |
| AskUserQuestion | ❌ 无 TTY 自动空答 | ✅ `can_use_tool` 回调 |
| 消息流 | 管道 + 线程 | `receive_messages()` |
| 配置 | 手动构建 CLI 参数 | `ClaudeAgentOptions` |

### D9: 流式输入模式

SDK 的 `can_use_tool` 回调要求 `connect(prompt)` 参数为 `AsyncIterable` 而非字符串。实现方案：

```python
async def input_stream():
    yield {"type": "user", "message": {"role": "user", "content": prompt}}
    await asyncio.Event().wait()  # 永久等待，保持 stdin 打开
await client.connect(prompt=input_stream())
```

`asyncio.Event().wait()` 是必需的，不是 hack。原因：SDK 的 `wait_for_result_and_end_input()` 在 input_stream 结束后会关闭 stdin，导致后续 `client.query()` 无法写入 transport。保活 stdin 是正确做法——后续消息通过 `client.query()` 写入同一 transport pipe，两者共享底层 stdin。

### D10: SessionStore 异步保存策略

消息持久化采用 **fire-and-forget** 模式，避免阻塞消息推送：

```python
# WS handler start: 先启动 forward_task，再异步保存用户消息
forward_task = asyncio.create_task(forward_ai_messages())
asyncio.create_task(_safe_save_message(...))

# forward 循环: 先推送消息到前端，再异步保存
await _safe_send(websocket, formatted)
asyncio.create_task(_safe_save_message(...))
```

不直接在 forward 循环中 `await save_message()`——如果文件写入失败或卡住，forward 任务崩溃，后续消息全部丢失。

### D11: AskUserQuestion 在无 TTY 环境下的处理

Claude Code 在 headless/`-p` 模式下 `AskUserQuestion` 会自动返回空答案。解决方案：
- `ClaudeAgentOptions(can_use_tool=callback)` 拦截工具调用
- 回调中通过 `asyncio.Event` 阻塞等待前端答案
- 前端 `AskUserPanel` 组件渲染问题 UI，用户提交后通过 `client.sendAnswer()` 发送答案
- 后端 `ai.py` 接收 `answer` action，通过 `call_soon_threadsafe` 唤醒 SDK 事件循环

### D12: system_prompt 传递方式

完成重构后，system_prompt 不含 `{user_prompt}` 等占位符，直接通过 `ClaudeAgentOptions(system_prompt=...)` 传给 Claude（系统指令），用户消息保持纯文本：

```
之前: user_message = template.format(user_prompt=...)
之后: ClaudeAgentOptions.system_prompt = "角色指令"
      user_message = raw_prompt
```

CLI 模式兼容处理：含 `{user_prompt}` 的旧模板仍走 format 路径，新格式直接透传。
