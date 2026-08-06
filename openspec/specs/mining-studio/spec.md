# mining-studio

## Purpose

定义 MiningStudio 多框架因子挖掘平台的前后端接口规范，支持 GP（遗传规划）和 LLMFactor 等多种挖掘框架的统一管理，涵盖框架注册、任务提交、接续挖掘、进度推送、结果浏览、因子持久化与导出、前端页面等完整功能。

## Requirements

### Requirement: 挖掘框架列表

系统 SHALL 提供 API 返回可用的挖掘框架列表，支持 GP 和 LLMFactor 至少两个框架，每个条目包含框架的名称、描述和配置模板。

#### Scenario: 获取框架列表

- **WHEN** 前端请求 `GET /mining/frameworks`
- **THEN** 返回框架列表，至少包含 `gp`（遗传规划）和 `llm_factor`（LLM 因子挖掘），每个条目包含 `key`, `name`, `description`, `config_schema`

#### Scenario: 获取框架配置模板

- **WHEN** 前端请求 `GET /mining/frameworks/{name}/config`
- **THEN** 返回该框架的完整配置模板，包括默认参数、可用选项、字段定义等

### Requirement: 挖掘任务提交

系统 SHALL 支持提交多框架的因子挖掘任务。配置结构由各框架的 `config_schema` 定义，提交时接受 `Dict[str, Any]` 配置，由 Service 层按 `framework` 字段分发和校验。

#### Scenario: 提交 LLMFactor 挖掘任务

- **WHEN** 用户在 MiningStudio 选择"LLM 因子挖掘"框架，填写研究方向、市场、频率等参数后点击提交
- **THEN** 系统创建任务和第一个 run，通过子进程启动 `QSExt.LLMFactor.scripts.run_pipeline`，返回 `task_id` 和 `run_id`

#### Scenario: 提交 GP 挖掘任务

- **WHEN** 用户在前端配置终端因子（从因子库选择）、算子、GP 参数（种群大小、代数、深度范围等）和适应度评估方案后点击"开始挖掘"
- **THEN** 系统创建任务和第一个 run（run_001），返回 `task_id`，任务通过 TaskManager 在后台异步执行，通过 WebSocket 推送进度

#### Scenario: 适应度评估多模块组合

- **WHEN** 用户在 eval 配置中指定多个回测模块（如 IC + 分位数组合）
- **THEN** 系统对每个候选因子运行所有评估模块，将结果列表传给 transform 函数计算标量适应度

### Requirement: 接续挖掘

系统 SHALL 支持从已有任务接续挖掘，继承最终种群继续进化，可调整 GP 参数和评估方案。

#### Scenario: 接续挖掘

- **WHEN** 用户在已完成任务上点击"接续挖掘"，调整 GP 参数（代数、变异率等）和/或评估方案后提交
- **THEN** 系统从 `checkpoint.pkl` 加载最终种群和适应度，创建新 run，调用 `evolve(parents=population, parent_fitness=fitness, n_generations=n)` 继续进化，前端将多个 run 的适应度曲线拼接展示

#### Scenario: 接续时不可修改算子或终端因子

- **WHEN** 用户在接续挖掘配置中尝试修改算子列表或终端因子选择
- **THEN** 系统在配置面板中锁定这些字段，不允许修改

### Requirement: 任务进度与状态

系统 SHALL 复用 TaskManager 和 WebSocket 实时推送挖掘任务的状态和进度。GP 和 LLMFactor 统一通过 TaskManager + WebSocket 推送进度。

#### Scenario: WebSocket 进度推送（GP）

- **WHEN** GP 挖掘任务正在运行
- **THEN** 前端通过 WebSocket 接收当前代数、最佳适应度、预计剩余时间等实时进度信息

#### Scenario: LLMFactor WebSocket 进度

- **WHEN** LLMFactor 任务正在运行
- **THEN** 前端通过 WebSocket 接收阶段描述（"假设生成中…""因子开发中…""因子评测中…"）和进度百分比

#### Scenario: 任务状态查询

- **WHEN** 前端请求 `GET /mining/tasks/{id}`
- **THEN** 返回任务状态（pending/running/completed/failed）、进度百分比和进度消息

### Requirement: 任务列表管理

系统 SHALL 支持列出和删除挖掘任务。删除时统一通过 `TaskManager.cancel()` 停止运行中的任务。

#### Scenario: 列出任务

- **WHEN** 前端请求 `GET /mining/tasks`
- **THEN** 返回所有挖掘任务的摘要列表（task_id, 名称, 状态, 创建时间），按创建时间倒序

#### Scenario: 删除任务

- **WHEN** 前端请求 `DELETE /mining/tasks/{id}`
- **THEN** 系统通过 `TaskManager.cancel()` 停止运行中的任务（如有）并清理任务数据

#### Scenario: 删除运行中的 LLMFactor 任务

- **WHEN** 前端请求删除一个运行中的 LLMFactor 任务
- **THEN** 系统调用 `TaskManager.cancel()`，触发 LLMFactor 注册的 `on_cancel` 回调 → `proc.kill()`，等待进程退出（最多 10s），再清理任务目录

### Requirement: 挖掘结果浏览

系统 SHALL 按框架返回不同形状的结果数据。GP 返回 Hall of Fame、适应度进化历史和因子树 DAG 数据，支持按 run 切换查看和多 run 适应度曲线拼接；LLMFactor 返回评测指标和因子列表。

#### Scenario: 获取 GP 挖掘结果

- **WHEN** 前端请求 `GET /mining/tasks/{id}/result?run=N`
- **THEN** 返回指定 run 的 `hall_of_fame`（按适应度降序排列的因子列表，含表达式字符串）、`fitness_history`（各代最佳/平均适应度）、以及该 run 的世代起止编号（用于多 run 拼接）

#### Scenario: 获取因子树 DAG 数据

- **WHEN** 前端请求 `GET /mining/tasks/{id}/factor-tree/{index}`
- **THEN** 返回该因子的 React Flow 兼容的 DAG 数据 `{nodes: [{id, name, type}], edges: [{source, target}]}`，节点 type 为 `operator` 或 `terminal`

#### Scenario: 获取 LLMFactor 评测指标

- **WHEN** 前端请求 `GET /mining/tasks/{id}/runs/{run_id}/eval-metrics`
- **THEN** 返回因子评测指标列表，每个因子包含 `name`, `status`, `metrics`（ic_mean, ic_ir, rank_ic, sharpe, max_drawdown）

### Requirement: 因子持久化

系统 SHALL 在每次 run 完成时自动将 Hall of Fame 中的因子导出为 FactorDef 脚本，持久化到任务目录。同时保存 checkpoint 供接续使用。

#### Scenario: Run 完成自动导出

- **WHEN** 一次 run 完成
- **THEN** 系统将 Hall of Fame 中所有因子导出为单个 FactorDef 脚本 `factors.py`，写入任务根目录。一个 `defFactor(fdi)` 通过 `rename()` 批量返回全部因子。同时将最终种群保存为 `checkpoint.pkl`

#### Scenario: 从导出脚本重建因子

- **WHEN** 用户需要查看因子树或重新评估已挖掘的因子
- **THEN** 系统从持久化的 FactorDef 脚本加载，注入当前 FactorDB 连接等运行时上下文，重建完整的 Factor 对象用于可视化或评估

### Requirement: 因子导出

系统 SHALL 支持手动将挖掘出的因子导出到指定目录（如 FactorDef 的 scripts_dir），便于因子工作台发现和回测。

#### Scenario: 手动导出到因子脚本目录

- **WHEN** 前端请求 `POST /mining/tasks/{id}/export` 并指定 Hall of Fame 中的因子索引和目标目录
- **THEN** 系统将该因子的 FactorDef 脚本写入目标目录，返回文件路径

### Requirement: 配置驱动

系统的挖掘相关配置 SHALL 从 `QSWebConfig.yaml` 的 `mining` 节读取。

#### Scenario: 加载挖掘配置

- **WHEN** 后端启动或首次访问 mining 相关 API
- **THEN** 从 `QSWebConfig.yaml` 读取 `mining.workspace`、`mining.frameworks` 配置

#### Scenario: 缺少配置时使用默认值

- **WHEN** `QSWebConfig.yaml` 不存在或缺少 `mining` 节
- **THEN** 挖掘相关 API 返回明确提示需要配置的信息，不会崩溃

### Requirement: 前端页面

MiningStudio 页面 SHALL 支持按框架类型切换配置表单和结果面板，在 `/mining` 路由提供因子挖掘管理页面。

#### Scenario: 页面布局

- **WHEN** 用户导航到 `/mining`
- **THEN** 显示左侧任务列表（含"新建任务"按钮）、右侧 Tabs（配置/结果/因子树），侧边栏菜单包含"因子挖掘"条目

#### Scenario: 框架选择驱动态渲染

- **WHEN** 用户点击"新建任务"
- **THEN** 显示框架选择器（GP / LLM 因子挖掘），选择后表单和结果面板按框架配置动态渲染

#### Scenario: GP 配置面板

- **WHEN** 用户选择 GP 框架
- **THEN** 显示框架选择（GPFactor）、算子多选、终端因子搜索选择器、GP 参数字段（种群大小、代数、深度范围等）、评估模块选择

#### Scenario: LLMFactor 配置面板

- **WHEN** 用户选择 LLM 因子挖掘框架
- **THEN** 显示研究方向输入框、市场/频率选择器、运行模式、轮次和时长等配置字段（按 `config_schema.fields` 渲染）

#### Scenario: 运行中显示进度

- **WHEN** 任���务正在运行
- **THEN** 配置面板切换为进度视图，显示 TaskProgress 组件（进度条 + 状态标签），结果 Tab 可用

#### Scenario: GP 结果面板

- **WHEN** 用户查看 GP 任务的结果
- **THEN** 结果 Tab 显示适应度进化曲线（Plotly 折线图）、Hall of Fame 排名表（排名/适应度/表达式/操作列），因子树 Tab 可查看选中因子的 React Flow 树图

#### Scenario: LLMFactor 结果面板

- **WHEN** 用户查看 LLMFactor 任务的结果
- **THEN** Tab 显示"日志"（LogViewer 组件）和"评测指标"（EvalMetrics 表格），不显示"因子树"Tab

#### Scenario: 任务列表框架标签

- **WHEN** 任务列表渲染
- **THEN** 每个任务显示框架标签（`GP` / `LLM`），用颜色区分
