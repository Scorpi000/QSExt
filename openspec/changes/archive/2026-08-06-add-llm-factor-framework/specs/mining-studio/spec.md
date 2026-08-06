# MiningStudio — 多框架支持（修改）

## MODIFIED Requirements

### Requirement: 挖掘框架列表（修改）

系统 SHALL 提供 API 返回可用的挖掘框架列表，支持 GP 和 LLMFactor 至少两个框架。

#### Scenario: 获取框架列表
- **WHEN** 前端请求 `GET /mining/frameworks`
- **THEN** 返回框架列表，至少包含 `gp`（遗传规划）和 `llm_factor`（LLM 因子挖掘），每个条目包含 `key`, `name`, `description`, `config_schema`

### Requirement: 挖掘任务提交（修改）

系统 SHALL 支持提交多框架的因子挖掘任务。配置结构由各框架的 `config_schema` 定义，提交时接受 `Dict[str, Any]` 配置，由 Service 层按 `framework` 字段分发和校验。

#### Scenario: 提交 LLMFactor 挖掘任务
- **WHEN** 用户在 MiningStudio 选择"LLM 因子挖掘"框架，填写研究方向、市场、频率等参数后点击提交
- **THEN** 系统创建任务和第一个 run，通过子进程启动 `QSExt.LLMFactor.scripts.run_pipeline`，返回 `task_id` 和 `run_id`

#### Scenario: 提交 GP 挖掘任务（行为不变）
- **WHEN** 用户在 MiningStudio 选择"遗传规划"框架，配置终端因子、算子、GP 参数等后点击提交
- **THEN** 行为与现有一致——通过 TaskManager 异步执行 GP 进化

### Requirement: 任务进度与状态（修改）

GP 和 LLMFactor 统一通过 TaskManager + WebSocket 推送进度。LLMFactor 的子进程 stdout 被解析为阶段标记 → `update_progress()`。

#### Scenario: LLMFactor WebSocket 进度
- **WHEN** LLMFactor 任务正在运行
- **THEN** 前端通过 WebSocket 接收阶段描述（"假设生成中…""因子开发中…""因子评测中…"）和进度百分比

### Requirement: 挖掘结果浏览（修改）

系统 SHALL 按框架返回不同形状的结果数据。GP 返回 Hall of Fame 和适应度曲线；LLMFactor 返回评测指标和因子列表。

#### Scenario: 获取 LLMFactor 评测指标
- **WHEN** 前端请求 `GET /mining/tasks/{id}/runs/{run_id}/eval-metrics`
- **THEN** 返回因子评测指标列表，每个因子包含 `name`, `status`, `metrics`（ic_mean, ic_ir, rank_ic, sharpe, max_drawdown）

### Requirement: 任务列表管理（修改）

删除任务时统一通过 `TaskManager.cancel()` 停止运行中的任务。

#### Scenario: 删除运行中的 LLMFactor 任务
- **WHEN** 前端请求删除一个运行中的 LLMFactor 任务
- **THEN** 系统调用 `TaskManager.cancel()`，触发 LLMFactor 注册的 `on_cancel` 回调 → `proc.kill()`，等待进程退出（最多 10s），再清理任务目录

### Requirement: 前端页面（修改）

MiningStudio 页面 SHALL 支持按框架类型切换配置表单和结果面板。

#### Scenario: 框架选择驱动态渲染
- **WHEN** 用户点击"新建任务"
- **THEN** 显示框架选择器（GP / LLM 因子挖掘），选择后表单和结果面板按框架配置动态渲染

#### Scenario: LLMFactor 配置面板
- **WHEN** 用户选择 LLM 因子挖掘框架
- **THEN** 显示研究方向输入框、市场/频率选择器、运行模式、轮次和时长等配置字段（按 `config_schema.fields` 渲染）

#### Scenario: LLMFactor 结果面板
- **WHEN** 用户查看 LLMFactor 任务的结果
- **THEN** Tab 显示"日志"（LogViewer 组件）和"评测指标"（EvalMetrics 表格），不显示"因子树"Tab

#### Scenario: 任务列表框架标签
- **WHEN** 任务列表渲染
- **THEN** 每个任务显示框架标签（`GP` / `LLM`），用颜色区分
