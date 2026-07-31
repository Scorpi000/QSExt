# ai-context-config

## Purpose

基于 `QSWebConfig.json` 的 AI 上下文配置系统，定义多个工作场景（general/factor/backtest/risk/portfolio），每个场景配置独立的 system_prompt、skills、MCP tools、placeholder 和路由映射。

## Requirements

### Requirement: 配置结构

系统 SHALL 在 `QSWebConfig.json` 中新增 `ai_workbench` 顶级配置段。包含 `mode`（sdk/cli）、`default_context`、`route_context_map`、`contexts`、`sessions_dir`。

#### Scenario: 配置加载

- **WHEN** 后端启动
- **THEN** 从 `QSWebConfig.json` 加载 `ai_workbench` 配置，若该段不存在则使用内置默认配置

#### Scenario: 路由映射

- **WHEN** `route_context_map` 包含 `{"/factor": "factor", "/backtest": "backtest"}`
- **THEN** 前端在对应路由打开 AI 助手时自动使用对应的 context，未匹配使用 `default_context`

### Requirement: Context 配置项

每个 context SHALL 包含：`description`、`placeholder`、`system_prompt`、`skills`、`tools`、`mcp_servers`、`max_budget_usd`、`permission_mode`、`allowed_actions`、`env`。

#### Scenario: system_prompt 不含占位符

- **WHEN** system_prompt 不含 `{user_prompt}` 等占位符
- **THEN** SDK 模式通过 `ClaudeAgentOptions(system_prompt=...)` 作为系统指令传递，用户消息保持纯文本

#### Scenario: 继承默认值

- **WHEN** context 未指定 `skills`、`tools`、`max_budget_usd` 等字段
- **THEN** 使用 `ai_workbench.defaults` 中对应的值

### Requirement: Skills 动态链接

系统 SHALL 根据 context 配置的 `skills` 列表动态链接技能目录（CLI 模式），SDK 模式通过 `ClaudeAgentOptions(skills=...)` 传递。

### Requirement: Tools 过滤

系统 SHALL 根据 context 配置的 `tools` 列表限制可用工具，SDK 模式通过 `ClaudeAgentOptions(allowed_tools=...)` 传递。

### Requirement: 前端配置接口

系统 SHALL 提供 `GET /api/ai/contexts` 返回可用 context 列表（不含完整 system_prompt），包含 `key`、`description`、`placeholder`。
