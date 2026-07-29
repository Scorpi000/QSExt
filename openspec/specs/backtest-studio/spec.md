# backtest-studio

## Purpose

QSWeb 回测工作台模块，支持用户从全局因子池选择因子、配置模块化回测任务、异步执行回测计算，并通过树结构展示结果。因子选择通过 MainLayout 右侧全局因子池面板完成，ModulePicker 从 Zustand store 读取。

## Requirements

### Requirement: 因子选择（全局因子池）

系统 SHALL 支持用户从全局因子池中选择因子用于回测。因子池维护在 MainLayout 右侧面板，ModulePicker 从 store 读取因子列表构建模块配置。

#### Scenario: 从池中选择因子
- **WHEN** 用户在 ModulePicker 中为回测模块配置因子
- **THEN** ModulePicker 从全局因子池 Zustand store 读取因子列表，转换为 FactorRef 构建模块配置

#### Scenario: 添加新因子到池
- **WHEN** 用户需要池中不存在的因子
- **THEN** 用户从右侧因子池面板点击"添加"，打开 FactorDiscover Drawer，浏览 FactorDB 或搜索 QSRegistry 添加因子

### Requirement: 因子选择（QSRegistry 源）

系统 SHALL 支持从 QSRegistry 图数据库中搜索因子并添加到全局因子池用于回测，支持关键词搜索和语义搜索。

#### Scenario: 从 QSRegistry 搜索因子
- **WHEN** 用户在 FactorDiscover 切换到 QSRegistry Tab，选择搜索模式，输入查询
- **THEN** 系统通过 QSGraphDB 检索因子，展示结果列表（名称、QSID、因子类别、算子名称、相似度）

#### Scenario: QSRegistry 因子重建用于回测
- **WHEN** 回测任务执行时遇到 source 为 "registry" 的因子
- **THEN** 系统通过 QSGraphDB.reconstructFactor(qsid) 重建完整 Factor 对象用于回测计算

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
- **THEN** 弹出配置对话框，展示该模块所需的参数表单 + 从池中选择因子，用户配置后点击确认加入待运行列表

#### Scenario: 编辑/删除待运行模块
- **WHEN** 用户在待运行列表中点击编辑或删除按钮
- **THEN** 编辑时弹出预填配置对话框，删除时从列表中移除该模块

#### Scenario: 全局配置
- **WHEN** 用户配置全局参数
- **THEN** 系统提供日期范围、时点模式（自然日/交易日）等全局配置项

### Requirement: 异步回测执行

系统 SHALL 通过异步机制执行回测计算，对接 QuantStudio 原生回测模块。节点构造通过声明式 `_BT_NODE_BUILDERS` 字典 + `_build_node_sync` 通用方法完成。

#### Scenario: 提交回测运行
- **WHEN** 用户完成所有模块配置，点击"全部运行"
- **THEN** 后端根据 module_key 查找 `_BT_NODE_BUILDERS`，动态 import Calc/Node 类，构造 BTNode 列表，通过 Engine.run() 执行，返回 `task_id`

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

### Requirement: 后续模块扩展

系统 SHALL 支持通过 `_BT_NODE_BUILDERS` 字典声明式添加更多回测模块，包括 IC 衰减、分位数组合、换手率、截面相关性、Fama-MacBeth 回归等。

#### Scenario: 添加新模块
- **WHEN** 在 `_BT_NODE_BUILDERS` 中注册新模块定义（calc_module/calc_class/node_module/node_class）
- **THEN** 前端模块列表和配置表单自动支持新模块，无需额外开发
