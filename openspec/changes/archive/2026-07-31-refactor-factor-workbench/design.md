## Context

当前 QSWeb 因子工作台的衍生因子创建功能（`CreateFactorWizard`）仅向 Neo4j 写入元数据节点和关系，不生成任何可执行的因子定义代码。QSExt 已有 FactorDef 框架（`__FACTOR_META__` + `defFactor(fdi) -> List[Factor]` 契约）和 `develop-factor` AI 技能，但两者均未接入 Web 端。

此次重构需要：
- 前端框架：React 18 + TypeScript + Vite + Ant Design 5
- 后端框架：Python FastAPI + WebSocket
- AI 调用双模式：CLI 子进程（默认）+ `claude-agent-sdk` `ClaudeSDKClient`（备选），通过 `QSWebConfig.json` 切换
- MCP 工具：`jy_base_doc`（查询聚源数据表）、`qs-registry`（搜索因子/算子）
- 所有配置集中在 `QSWebConfig.json` 的 `factor_def` 段

## Goals / Non-Goals

**Goals:**
- 移除现有的衍生因子创建向导（前端 + 后端）
- 提供因子脚本导入功能：上传文件或粘贴代码 → `importlib` 验证 → 存储 → 可选注册到 Neo4j
- 提供 AI 因子助手：Chat 面板 → WebSocket → Claude → develop-factor skill → 生成的脚本走导入管道
- AI 生成和手动导入共享同一条后端导入管道
- 支持多轮对话：用户可追问、中断 Claude

**Non-Goals:**
- 不考虑代码安全性（沙箱执行、代码注入扫描）
- 不修改 `develop-factor` 技能内容
- 不修改 `jy_base_doc` / `qs-registry` MCP 服务器
- 不修改 FactorDef 框架本身
- 不修改 QSWeb 现有的搜索、DAG、详情、连接管理功能
- 不在 Web 端提供因子脚本的在线编辑功能

## Decisions

### Decision 1: 双模式 AI 调用架构（CLI 默认，SDK 备选）

**选择**: 通过 `factor_def.claude.mode` 配置切换，默认 `"cli"`

**CLI 模式** (`ai_service_cli.py`):
- 直接 spawn Claude CLI 子进程：`claude -p --verbose --output-format stream-json --input-format stream-json`
- stdin/stdout JSON 行协议通信，纯 `subprocess` + 线程，零 SDK 依赖
- 无 anyio 事件循环冲突
- 完整保留 Claude Code 所有能力（skills、MCP、hooks）
- `-p` 模式每轮退出，多轮通过 `--resume <session_id>` 恢复上下文
- 每轮 `query()` 等待旧进程自然退出（`session_persist_wait_sec` 超时）后重启新进程

**SDK 模式** (`ai_service.py`):
- 使用 `ClaudeSDKClient`（持久进程，`connect` → `query` → `receive_messages`）
- daemon 线程 + `asyncio.run()` 隔离 anyio 与 uvicorn 事件循环
- `asyncio.run_coroutine_threadsafe()` 实现主线程 → 客户端线程的命令传递
- 消息通过 `queue.Queue` 传回主事件循环

**对比**:

| | CLI 模式 | SDK 模式 |
|---|---|---|
| 进程生命周期 | 每轮重启 | 持久连接 |
| 多轮机制 | `--resume` 恢复会话 | 原生持久 |
| 依赖 | 仅 `subprocess` | `claude-agent-sdk` + `anyio` |
| 事件循环冲突 | 无 | daemon 线程隔离 |
| 默认 | ✅ | — |

### Decision 2: 多轮会话通过 `--resume` 维持（CLI 模式）

**选择**: 首轮 `--session-id <uuid>` 创建会话，后续轮 `--resume <uuid>` 恢复

**理由**:
- `-p`（print mode）是 CLI 唯一支持 `--output-format stream-json` 的模式，其语义为"输出后退出"，每轮必退出
- `--resume` 是 `-p` 模式下唯一的多轮桥梁——从磁盘加载会话历史，新 stdin 消息追加到该会话
- 会话持久化到 `~/.claude/projects/<project-key>/<session-id>.jsonl`

**`query()` 等待策略**:
- 旧进程自然退出（等待 `session_persist_wait_sec`，默认 10s）→ 会话完整写入磁盘
- 超时后 `terminate()` → `kill()` 强制清理
- `loop.run_in_executor()` 避免阻塞 WebSocket 事件循环

### Decision 3: AI 生成和手动导入走同一条导入管道

**选择**: `POST /api/factors/import` 统一处理所有来源

```
手动上传/粘贴 ──┐
                 ├──→ importlib 验证 → 存储到 scripts_dir → 返回元信息 → (可选)注册到 Neo4j
AI Write 后 ────┘

AI Chat 流程:
  WebSocket ──→ [mode=cli] claude subprocess ←stdin/stdout→ 
            ──→ [mode=sdk] ClaudeSDKClient (daemon thread)
       │
       ◄── 流式消息推送（assistant / thinking / tool_use / tool_result / stream / result）
       │
       代码生成 → POST /api/factors/import → 统一导入管道
```

### Decision 4: 全部配置集中在 QSWebConfig.json

**配置结构** (`factor_def` 段):

```jsonc
{
  "factor_def": {
    "scripts_dir": "D:/Data/FactorDef/Scripts",       // 因子脚本存放目录
    "settings_path": ".../settings_dev.py",            // register_factors 的 settings
    "skill_dir": "D:/HST/QSExt/QSExt/FactorDef/skill", // develop-factor 技能目录
    "claude": {
      "mode": "cli",                                   // "cli" | "sdk"
      "cli_path": ".../claude",                        // Claude CLI 路径
      "repo_root": "D:/Data/Workspace/ClaudeCode",     // Claude 工作目录 (cwd)
      "skills": ["develop-factor"],
      "permission_mode": "acceptEdits",
      "max_budget_usd": 1.0,
      "allowed_tools": [...],
      "system_prompt": "使用 develop-factor 技能...\n{user_prompt}\n...保存到 {scripts_dir}",
      "session_persist_wait_sec": 10,                  // query() 等待旧进程退出的超时
      "env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1"},
      "mcp_servers": {
        "qs-registry": { "command": "...", "args": [...], "env": {...} },
        "jy_base_doc":  { "command": "...", "args": [...], "env": {...} }
      }
    }
  }
}
```

`repo_root` 默认值从 `config.py` 自动计算（向上 5 级到 QSWeb 所在目录）。

### Decision 5: `importlib` 动态加载验证脚本

**选择**: 使用 `importlib` 实际加载模块读取 `__FACTOR_META__` 和验证 `defFactor` 函数

**理由**:
- 相比 AST 静态解析，`importlib` 能获取真实运行时值（如 `MaxLookBack = 365 * 10` 等表达式）
- 仅执行 `import`（模块顶层代码），不调用 `defFactor`，风险可控
- 能检测 `ImportError`、语法错误等 AST 无法捕获的问题

### Decision 6: WebSocket 双向通信协议

**前端 → 后端**:

| Action | 触发时机 | 后端行为 |
|--------|---------|---------|
| `{"action": "start", "prompt": "..."}` | 首次发送（runState=idle） | 创建新会话，启动 Claude |
| `{"action": "query", "prompt": "..."}` | 追问（runState≠idle） | `--resume` 恢复会话 |
| `{"action": "interrupt"}` | 点击停止 | 终止 Claude 进程 |
| `{"action": "disconnect"}` | 关闭面板 | 清理进程资源 |

**后端 → 前端**:

| Type | 触发条件 | 前端展示 |
|------|---------|---------|
| `assistant` (blocks: text/thinking/tool_use/tool_result) | Claude 回复 | 文本 + 思考折叠 + 工具卡片 |
| `stream` | CLI `stream_event` | 流式增量（仅 SDK 模式） |
| `result` (is_error=true) | Claude 异常 | 红色错误消息 |
| `done` | 本轮完成 | 停止 spinner，runState='done' |
| `interrupted` | 用户中断 | 灰色"已中断"标记 |
| `error` | 后端异常 | 红色错误消息 |

### Decision 7: 思考过程折叠显示

`ThinkingBlock` 转为 `kind: "thinking"`，前端用 `Collapse` 组件默认为收起状态，标签为"💭 思考过程"。

`ResultMessage` 正常完成时不产生可见消息（文本已在 `assistant` 中展示），仅触发 `done` 信号。错误时才显示红色消息。

### Decision 8: 工作目录自动初始化

每次启动 Claude 前执行 `_ensure_workspace(repo_root)`:

1. `os.makedirs(.claude/skills/)` — 确保目录存在
2. `git init`（若 `.git` 不存在）— Claude Code 需要 git 仓库
3. 创建 `develop-factor` 技能链接（Windows: `mklink /J` junction，Linux: `os.symlink`）
   - 每次检查链接有效性，指向错误则删除重建
   - 支持切换 `repo_root` 后自动适配

## Risks / Trade-offs

1. **[风险] CLI `-p` 模式每轮重启，多轮有延迟**
   → **缓解**: `session_persist_wait_sec` 可配置；SDK 模式作为备选方案提供持久连接

2. **[风险] Claude 生成的脚本可能引用不存在的表名或字段**
   → **缓解**: `develop-factor` 技能强制要求通过 `jy_base_doc` MCP 工具验证所有表名和字段名

3. **[风险] 因子脚本的 `FactorDeps` 依赖模块可能不存在**
   → **缓解**: `importlib` 验证时提取 `FactorDeps`，在导入预览中展示警告

4. **[权衡] SDK 模式 anyio 与 uvicorn asyncio 的事件循环冲突**
   → daemon 线程 + `asyncio.run()` 创建独立事件循环，`run_coroutine_threadsafe` 跨线程通信

5. **[风险] `interrupt()` 过早终止可能损坏会话文件**
   → `query()` 改为 `wait()` 等待自然退出而非 `terminate()`；仅在超时后强制 kill

## 文件清单

| 文件 | 说明 |
|------|------|
| `QSWeb/backend/app/services/ai_service_cli.py` | CLI 模式：`AiServiceCLI`，subprocess + 线程 |
| `QSWeb/backend/app/services/ai_service.py` | SDK 模式：`AiService`，`ClaudeSDKClient` + daemon 线程 |
| `QSWeb/backend/app/api/ai.py` | WebSocket 端点 `/ws/ai/chat`，按 `mode` 选择实现 |
| `QSWeb/backend/app/services/import_service.py` | `ImportService`：`importlib` 验证 + 保存 + 注册 |
| `QSWeb/backend/app/api/import_factor.py` | `POST /api/factors/import` + `/preview` |
| `QSWeb/backend/app/core/config.py` | `factor_def` 配置加载，`_qsweb_root` 自动检测 |
| `QSWeb/frontend/src/components/AiFactorAssistant/` | AI Chat 面板（多轮对话、中断、思考折叠） |
| `QSWeb/frontend/src/components/ImportFactorDialog/` | 导入对话框（粘贴/上传、预览、确认） |
| `QSWeb/frontend/src/services/ai.ts` | `AiChatClient` WebSocket 封装 |
| `QSWeb/frontend/src/services/import.ts` | 导入 API 封装 |
| `~/QuantStudioConfig/QSWebConfig.json` | 运行时配置（`factor_def` 段） |
