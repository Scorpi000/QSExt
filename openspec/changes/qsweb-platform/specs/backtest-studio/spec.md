## ADDED Requirements

### Requirement: IC 分析

系统 SHALL 支持用户对截面因子进行 IC（信息系数）分析。

#### Scenario: 运行 IC 分析
- **WHEN** 用户选择因子、价格表、日期范围和频率，点击运行
- **THEN** 系统计算 IC/Rank IC/ICIR/胜率，返回时间序列结果

#### Scenario: IC 衰减分析
- **WHEN** 用户选择因子并设置最大滞后期数
- **THEN** 系统计算多期 IC，展示衰减曲线

### Requirement: 分位数组合

系统 SHALL 支持用户构建分位数组合并查看净值曲线。

#### Scenario: 构建分位数组合
- **WHEN** 用户配置因子、分组数、再平衡频率，点击运行
- **THEN** 系统按因子值分组，计算各组净值，返回多空净值曲线

#### Scenario: 因子换手率分析
- **WHEN** 用户对某因子运行换手率分析
- **THEN** 系统计算各期持仓变动比例，展示换手率时间序列

### Requirement: 策略回测

系统 SHALL 支持用户配置信号、账户参数和再平衡频率运行策略回测。

#### Scenario: 运行策略回测
- **WHEN** 用户配置信号来源、初始资金、手续费、滑点、再平衡频率，点击运行
- **THEN** 系统提交异步任务，返回 task_id，通过 WebSocket 推送进度

#### Scenario: 查看回测结果
- **WHEN** 回测任务完成
- **THEN** 系统展示净值曲线（Plotly）、统计指标（年化收益/最大回撤/夏普/信息比率/胜率）、交易记录表格

### Requirement: 异步任务管理

系统 SHALL 通过异步机制执行长时间计算任务，支持进度推送和结果获取。

#### Scenario: 提交异步任务
- **WHEN** 前端提交回测/分析请求
- **THEN** 后端创建 `TaskManager` 任务，立即返回 `task_id`

#### Scenario: 接收进度更新
- **WHEN** 任务执行过程中
- **THEN** 后端通过 WebSocket 推送 `{status, progress}` 更新，前端实时显示进度条

#### Scenario: 获取任务结果
- **WHEN** 任务状态变为 `completed`
- **THEN** 前端通过 `GET /api/backtest/tasks/{task_id}/result` 获取完整结果

### Requirement: 回测历史

系统 SHALL 支持用户查看、搜索和对比历史回测。

#### Scenario: 搜索历史回测
- **WHEN** 用户输入筛选条件（因子、日期范围）
- **THEN** 系统查询历史回测列表，支持分页

#### Scenario: 对比回测结果
- **WHEN** 用户选择多个历史回测，点击对比
- **THEN** 系统并排展示多个回测的净值曲线和统计指标

#### Scenario: 注册回测到 QSRegistry
- **WHEN** 用户点击"注册到 QSRegistry"
- **THEN** 系统将回测配置和结果元数据写入 Neo4j 图数据库

### Requirement: 报告导出

系统 SHALL 支持用户将回测结果导出为 HTML 报告。

#### Scenario: 导出 HTML 报告
- **WHEN** 用户点击"导出报告"，选择 HTML 格式
- **THEN** 系统调用 ReportGenerator 生成 HTML 报告并提供下载
