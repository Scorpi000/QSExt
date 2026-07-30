# ai-factor-assistant

## Purpose

AI 因子助手模块，提供 Chat 面板供用户用自然语言描述因子需求，后端通过 `claude-agent-sdk` 调用 Claude，加载 `develop-factor` 技能和 MCP 工具（jy_base_doc、qs-registry），流式生成符合 FactorDef 框架规范的因子定义脚本，生成的脚本通过导入管道处理。

## ADDED Requirements

### Requirement: Chat 面板

系统 SHALL 在因子工作台提供 AI 因子助手 Chat 面板，支持用户通过自然语言描述因子需求。

#### Scenario: 打开 AI 助手
- **WHEN** 用户在因子工作台点击"AI 辅助创建"按钮
- **THEN** 系统打开 AI 因子助手 Drawer/Panel，显示欢迎语和输入框

#### Scenario: 发送消息
- **WHEN** 用户在输入框中输入因子需求描述（如"创建一个 20 日动量因子，A 股"）并发送
- **THEN** 系统将消息发送到后端，建立 WebSocket 连接，开始流式接收 AI 回复

#### Scenario: 新会话
- **WHEN** 用户点击"新建会话"按钮
- **THEN** 系统清空当前对话历史，重置为初始状态

### Requirement: WebSocket 流式通信

系统 SHALL 通过 WebSocket 将 AI 的思考过程和生成结果实时推送到前端。

#### Scenario: 流式接收思考过程
- **WHEN** Claude 进行推理
- **THEN** 前端实时展示思考内容（以可折叠或灰色文字展示）

#### Scenario: 流式接收工具调用
- **WHEN** Claude 调用 MCP 工具（如查询 JYDB 表结构）
- **THEN** 前端展示工具调用卡片："正在查询 {表名}..."，完成后显示"✓ 已确认表结构"

#### Scenario: 流式接收生成的代码
- **WHEN** Claude 生成因子定义脚本
- **THEN** 前端在代码块中逐段展示生成的代码，带语法高亮

#### Scenario: 连接中断处理
- **WHEN** WebSocket 连接意外中断
- **THEN** 前端显示"连接中断，正在重连..."并自动尝试重新连接

### Requirement: Claude Code 集成

系统 SHALL 通过 `claude-agent-sdk` 的 `query()` 函数调用 Claude，配置技能和 MCP 工具。

#### Scenario: 加载 develop-factor 技能
- **WHEN** 后端启动 `query()`
- **THEN** `ClaudeAgentOptions.skills` 包含 `"develop-factor"`，Claude 按技能定义的 4 步流程执行（理解需求 → 调研数据 → 生成脚本 → 保存）

#### Scenario: 配置 MCP 工具
- **WHEN** 后端启动 `query()`
- **THEN** `ClaudeAgentOptions.mcp_servers` 包含 `jy_base_doc` 和 `qs-registry`，允许的工具列表包含 `mcp__jy_base_doc__*`、`mcp__qs-registry__*`、`Read`、`Write`、`Bash`

#### Scenario: 脚本写入目录
- **WHEN** Claude 生成脚本后调用 Write 工具
- **THEN** `ClaudeAgentOptions.cwd` 指向 `QSWebConfig.json` 的 `factor_def.scripts_dir`，脚本直接保存到该目录

#### Scenario: 预算控制
- **WHEN** 后端启动 `query()`
- **THEN** `ClaudeAgentOptions.max_budget_usd` 设置为 `1.0`（可配置），防止单次调用费用失控

### Requirement: 生成结果处理

系统 SHALL 在 AI 生成完成后，通过导入管道处理生成的脚本。

#### Scenario: 自动触发导入
- **WHEN** Claude 完成脚本生成并写入磁盘
- **THEN** 前端自动调用 `POST /api/factors/import` 对生成的脚本执行 AST 验证，展示元信息预览

#### Scenario: 用户确认操作
- **WHEN** 导入预览展示后
- **THEN** 前端提供操作按钮：保存脚本、保存并注册到图数据库、编辑脚本

#### Scenario: 生成失败处理
- **WHEN** Claude 未能成功生成脚本（如超过 max_turns 或 API 错误）
- **THEN** 前端显示错误信息，提示用户重试或修改需求描述

### Requirement: 会话管理

系统 SHALL 支持基本的 AI 会话管理。

#### Scenario: 会话历史
- **WHEN** 用户在同一个 AI 助手面板中多次对话
- **THEN** 前端保留当前会话的消息历史（不清空）

#### Scenario: 关闭面板保留状态
- **WHEN** 用户关闭 AI 助手面板后重新打开
- **THEN** 前端恢复上次会话的消息历史（会话内有效，不跨页面刷新持久化）
