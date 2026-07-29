# backtest-studio

## Purpose

QSWeb 回测工作台模块，支持用户从因子库选择因子、配置模块化回测任务、异步执行回测计算，并通过树结构展示结果。

## Requirements

### Requirement: 因子选择（FactorDB 源）

系统 SHALL 支持用户从已连接的因子库中多选因子用于回测。

#### Scenario: 从因子库浏览并选择因子
- **WHEN** 用户在回测工作台打开因子选择器，选择因子库 Tab，选择连接和因子表
- **THEN** 系统展示该表下所有因子列表，用户可多选加入已选列表

#### Scenario: 查看已选因子
- **WHEN** 用户选择了多个因子
- **THEN** 系统以 Tag 形式展示已选因子列表，支持点击删除单个因子

### Requirement: 回测模块注册表

系统 SHALL 提供可用的回测模块列表，每个模块声明其名称、描述、类别和配置参数。

#### Scenario: 获取模块列表
- **WHEN** 前端加载回测工作台
- **THEN** 系统调用 `GET /api/backtest/modules` 返回所有已注册的回测模块元信息（名称、描述、参数定义）

#### Scenario: 查看模块参数
- **WHEN** 用户准备添加某个回测模块
- **THEN** 系统根据该模块的 params 定义动态渲染配置表单

### Requirement: 模块化回测配置

系统 SHALL 支持用户从模块列表中选择回测模块，独立配置每个模块的参数和因子，加入待运行列表。

#### Scenario: 添加回测模块
- **WHEN** 用户点击"添加模块"，从下拉列表中选择一个模块类型（如"IC 分析"）
- **THEN** 弹出配置对话框，展示该模块所需的参数表单 + 因子选择，用户配置后点击确认加入待运行列表

#### Scenario: 重复添加同一模块
- **WHEN** 用户再次添加相同类型的模块
- **THEN** 系统允许重复添加，每次可配置不同的参数和因子（如用不同因子各跑一次 IC 分析）

#### Scenario: 编辑/删除待运行模块
- **WHEN** 用户在待运行列表中点击编辑或删除按钮
- **THEN** 编辑时弹出预填配置对话框，删除时从列表中移除该模块

#### Scenario: 全局配置
- **WHEN** 用户配置全局参数
- **THEN** 系统提供日期范围、价格因子选择、截面 ID 输入等全局配置项

### Requirement: 异步回测执行

系统 SHALL 通过异步机制执行回测计算，对接 QuantStudio 原生回测模块。

#### Scenario: 提交回测运行
- **WHEN** 用户完成所有模块配置，点击"全部运行"
- **THEN** 后端将请求中的模块配置转换为 QuantStudio BTNode 列表，通过 Engine.run() 执行，返回 `task_id`

#### Scenario: QSBridge 桥接
- **WHEN** 后端构造回测节点
- **THEN** 系统通过 FactorDB 获取因子对象，构造对应回测算子（如 CalcIC → IC），打包为 BTReport 提交给计算引擎

#### Scenario: 运行时进度推送
- **WHEN** 回测任务执行过程中
- **THEN** 后端通过 WebSocket 推送 `{status, progress}` 更新，前端实时显示进度条

### Requirement: 结果树展示

系统 SHALL 将回测结果以树结构展示，用户点击节点查看具体内容。

#### Scenario: 查看结果树
- **WHEN** 回测任务完成
- **THEN** 后端将 Engine.run() 的输出递归提取为 ResultNode 树，每个节点标记类型（branch/series/dataframe/scalar）

#### Scenario: 查看叶子节点内容
- **WHEN** 用户点击结果树中的叶子节点
- **THEN** 系统根据节点 type 渲染：series → Plotly 折线图，dataframe → 表格，scalar → 统计数值

### Requirement: 因子选择（QSRegistry 源，后续扩展）

系统 SHALL 未来支持从 QSRegistry 图数据库中搜索和选择因子。

#### Scenario: 从 QSRegistry 搜索因子
- **WHEN** 用户在因子选择器切换到 QSRegistry Tab，输入关键词搜索
- **THEN** 系统通过 QSGraphDB 检索因子，用户可多选加入已选列表

#### Scenario: QSRegistry 因子重建
- **WHEN** 用户选择了 QSRegistry 中的因子
- **THEN** 系统通过 QSGraphDB.reconstructFactor(qsid) 重建完整 Factor 对象用于回测

### Requirement: 后续模块扩展

系统 SHALL 支持逐步添加更多回测模块，包括 IC 衰减、分位数组合、换手率、截面相关性、Fama-MacBeth 回归、策略回测等。

#### Scenario: 添加新模块
- **WHEN** 在 BACKTEST_MODULE_REGISTRY 中注册新模块定义
- **THEN** 前端模块列表和配置表单自动支持新模块，无需额外前端开发
