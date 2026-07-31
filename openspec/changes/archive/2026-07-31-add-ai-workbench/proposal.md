## Why

当前 QSWeb 的 AI 能力仅限于因子工作台上的 AI 辅助创建因子（`AiFactorAssistant`），用户无法在回测、风险、组合优化等其他工作场景中获得 AI 辅助。同时，AI 助手只能通过因子工作台页面的特定按钮打开，缺乏全局可达性和独立的深度使用入口。现在是扩展 AI 能力的最佳时机——`AiChatClient`（前端 WebSocket 客户端）和 `AiServiceCLI`（后端 Claude CLI 子进程管理）的基础设施已经成熟且高度通用化，只需泛化配置和 UI 层即可覆盖所有量化工作场景。

## What Changes

- **BREAKING**：移除现有的 `AiFactorAssistant` 组件，替换为通用的 `AiChatPanel` 组件 + `context="factor"` 配置驱动
- 新增通用 AI 聊天面板组件 `AiChatPanel`，支持文本/Markdown/图表/表格/action_card 等多消息类型渲染
- 新增全局 AI 入口：右下角 FAB 悬浮按钮、`Ctrl+K` 快捷键
- 新增侧边栏导航项 `/ai`，对应独立 AI 工作台页面（含会话历史列表）
- 新增 `AiChatDrawer` 全局组件，在各页面及全局入口复用同一个聊天面板
- 后端新增 REST API：`GET/DELETE /api/ai/sessions`（会话管理）
- 后端 `AiServiceCLI` 重构为配置驱动：根据 context 动态组装 system_prompt、skills、MCP tools
- WebSocket 协议扩展：新增 `action_card` 消息类型，支持前端通用渲染操作按钮
- `QSWebConfig.json` 新增 `ai_workbench` 配置段，定义多个 context（general/factor/backtest/risk/portfolio）及其 skills/tools/prompt/placeholder
- 新增会话持久化：`~/.qsweb/ai_sessions/` 目录存储会话元数据和消息历史
- 现有 `factor_def.claude` 配置段保持兼容，迁移至 `ai_workbench.contexts.factor`

## Capabilities

### New Capabilities
- `ai-chat-panel`：通用 AI 聊天面板组件，支持多消息类型渲染（文本/Markdown/思考过程/工具调用/action_card），通过 props 接收 context 配置
- `ai-workbench-page`：独立 AI 工作台页面 `/ai`，含会话历史列表 + 全屏聊天面板
- `ai-global-entry`：全局 AI 入口（FAB 悬浮按钮 + Ctrl+K 快捷键 + 导航菜单项），从任意页面快速唤起
- `ai-context-config`：基于 `QSWebConfig.json` 的上下文配置系统，每个 context 定义 skills/tools/system_prompt/placeholder/route_map
- `ai-session-store`：基于本地 JSON 文件的轻量会话持久化，支持列表/恢复/删除
- `ai-action-card`：通用 action_card 消息协议，后端驱动操作按钮，前端通用渲染

### Modified Capabilities
- `ai-factor-assistant`：移除独立组件，功能合并到 `ai-chat-panel` + `context="factor"` 配置驱动；因子特有的"保存脚本"后处理改为 action_card 协议实现

## Impact

- **前端组件**：
  - 新增：`AiChatPanel`（通用聊天面板）、`AiChatDrawer`（全局 Drawer 入口）、`FAB`（悬浮按钮）、`AiWorkbench`（独立页面）、`SessionList`（会话列表）、`ActionCard`（操作卡片渲染器）
  - 重写：`AiFactorAssistant` → 薄包装调用 `AiChatPanel`
  - 修改：`MainLayout`（新增 `/ai` 导航项、FAB、快捷键绑定）、`FactorWorkbench`（按钮改用 `AiChatDrawer`）、`App.tsx`（新增 `/ai` 路由）
- **前端服务**：`ai.ts` 扩展 `AiMessageType` 增加 `action_card`、`data_block`；新增 `session.ts`（会话 CRUD API）
- **后端**：
  - 新增：`backend/app/api/ai_sessions.py`（会话管理路由）、`backend/app/services/session_store.py`（文件存储层）
  - 重构：`backend/app/services/ai_service_cli.py`（硬编码 → 配置驱动）
  - 修改：`backend/app/core/config.py`（新增 `ai_workbench` 配置项）、`backend/app/main.py`（注册新路由）
- **配置**：`QSWebConfig.json` 新增 `ai_workbench` 配置段
- **现有功能**：`AiFactorAssistant` 用户可见行为不变（仍可从因子工作台打开），但底层实现替换
