# ai-context-config

## Purpose

基于 `QSWebConfig.json` 的 AI 上下文配置系统，定义多个工作场景（general/factor/backtest/risk/portfolio），每个场景配置独立的 system_prompt、skills、MCP tools、placeholder 和路由映射。

## ADDED Requirements

### Requirement: 配置结构

系统 SHALL 在 `QSWebConfig.json` 中新增 `ai_workbench` 顶级配置段。

#### Scenario: 配置加载

- **WHEN** 后端启动
- **THEN** 从 `QSWebConfig.json` 加载 `ai_workbench` 配置，若该段不存在则使用内置默认配置（含 `general` context）
- **WHEN** 配置加载失败（JSON 格式错误等）
- **THEN** 后端日志警告，使用内置默认配置启动

#### Scenario: 默认 context

- **WHEN** `ai_workbench.default_context` 设置为 `"general"`
- **THEN** 所有未匹配路由或未指定 context 的 AI 请求使用 `general` context

#### Scenario: 路由映射

- **WHEN** `ai_workbench.route_context_map` 包含 `{"/factor": "factor", "/backtest": "backtest"}`
- **THEN** 前端在对应路由打开 AI 助手时自动使用对应的 context

### Requirement: Context 配置项

每个 context SHALL 包含以下必填和可选配置项。

#### Scenario: 必填配置

- **WHEN** 定义一个 context
- **THEN** 必须包含：`system_prompt`（Claude 初始提示模板）、`placeholder`（前端输入框占位文字）

#### Scenario: 可选配置

- **WHEN** 定义一个 context
- **THEN** 可选包含：`skills`（技能目录名列表）、`tools`（允许的 MCP 工具模式列表）、`mcp_servers`（该 context 专用的 MCP 服务器配置）、`max_budget_usd`（预算上限）、`permission_mode`（权限模式）、`allowed_actions`（该 context 支持的 action_card action key 列表）

#### Scenario: 继承默认值

- **WHEN** context 未指定 `skills`、`tools`、`max_budget_usd` 等字段
- **THEN** 使用 `ai_workbench.defaults` 中对应的值（若存在）；否则使用系统硬编码默认值

### Requirement: System Prompt 模板

`system_prompt` SHALL 支持 `{user_prompt}` 和 `{scripts_dir}` 占位符替换。

#### Scenario: 模板替换

- **WHEN** 后端构造初始提示
- **THEN** 将模板中的 `{user_prompt}` 替换为用户实际输入，`{scripts_dir}` 替换为配置的脚本目录路径；若模板为空则直接透传用户输入

### Requirement: Skills 动态链接

系统 SHALL 根据 context 配置的 `skills` 列表动态链接技能目录。

#### Scenario: 链接多个技能

- **WHEN** context 配置 `skills: ["develop-factor", "develop-backtest"]`
- **THEN** `_ensure_workspace()` 在 `.claude/skills/` 下创建每个技能名的目录链接，指向 `skill_dir/<name>`

#### Scenario: 空技能列表

- **WHEN** context 配置 `skills: []`
- **THEN** 不创建任何技能链接，Claude 在无技能模式下运行

### Requirement: Tools 过滤

系统 SHALL 根据 context 配置的 `tools` 列表限制 MCP 工具可用性。

#### Scenario: 工具白名单

- **WHEN** context 配置 `tools: ["mcp__qs-registry__*", "Read"]`
- **THEN** Claude 只能使用匹配这些模式的工具

#### Scenario: 通配符匹配

- **WHEN** `tools` 包含 `"mcp__qs-registry__*"`
- **THEN** 匹配所有 `mcp__qs-registry__` 前缀的工具（如 `search_factors`、`get_factor_info` 等）

### Requirement: 前端配置接口

系统 SHALL 提供 REST API 供前端获取可用的 context 列表。

#### Scenario: 获取 context 列表

- **WHEN** 前端调用 `GET /api/ai/contexts`
- **THEN** 返回 `[{key: "general", description: "...", placeholder: "..."}, {key: "factor", ...}, ...]`，仅包含每个 context 的关键信息（不含完整 system_prompt）

### Requirement: 配置热加载

系统 SHALL 支持在开发模式下热加载 `QSWebConfig.json` 的 AI 配置变更。

#### Scenario: 热加载

- **WHEN** 后端运行在 `debug=True` 模式且 `QSWebConfig.json` 被修改
- **THEN** 新的 AI 会话使用更新后的配置；已有会话保持原配置不变
