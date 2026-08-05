# strategy-studio-page

## Purpose

QSWeb 策略工作台页面（`/strategy`），提供策略脚本的代码编辑、参数配置、回测执行和结果分析的一站式 Web 界面。

## ADDED Requirements

### Requirement: 页面路由和导航

系统 SHALL 在 `/strategy` 路径下提供策略工作台页面，并将其添加到左侧导航菜单。页面采用与现有 BacktestStudio 一致的左右分栏布局。

#### Scenario: 导航到策略工作台

- **WHEN** 用户点击左侧导航"策略工作台"
- **THEN** 路由跳转到 `/strategy`，页面标题显示为"策略工作台"

#### Scenario: 页面懒加载

- **WHEN** 用户首次访问 `/strategy`
- **THEN** 策略工作台页面组件通过 React.lazy 异步加载，加载中显示 Loading 骨架

### Requirement: 策略列表和搜索

系统 SHALL 提供策略列表，支持从 Neo4j 搜索已注册的策略（关键词和语义搜索），以及新建空白策略。

#### Scenario: 加载策略列表

- **WHEN** 页面首次加载
- **THEN** 调用后端 API 获取已注册策略列表，展示策略名称、信号类型、作者、更新日期

#### Scenario: 搜索策略

- **WHEN** 用户在搜索框输入关键词
- **THEN** 调用 `GET /api/strategy/search?q=xxx`，结果按匹配度排序展示

#### Scenario: 新建策略

- **WHEN** 用户点击"新建策略"
- **THEN** 编辑器展示策略模板代码（含 `__STRATEGY_META__` 和 `defStrategy` 骨架），配置面板显示默认 OperatorConfig

### Requirement: 代码编辑器

系统 SHALL 集成 Monaco Editor，提供策略 `genSignal()` 代码的编辑和语法高亮。

#### Scenario: 编辑策略代码

- **WHEN** 用户从列表选中一个策略
- **THEN** 调用 `GET /api/strategy/{qsid}/code` 读取 `DefScriptPath` 文件内容，加载到 Monaco Editor

#### Scenario: 语法高亮和补全

- **WHEN** 用户在编辑器中编写 Python 代码
- **THEN** Monaco Editor 提供 Python 语法高亮、括号匹配和基本代码补全

### Requirement: 策略配置面板

系统 SHALL 提供策略参数配置面板，展示和编辑 `OperatorConfig`（SignalType、InitCash、ShortAllowed）、依赖因子选择、依赖策略选择、ModelArgs 动态表单。

#### Scenario: 配置算子参数

- **WHEN** 用户编辑配置面板中的 SignalType、InitCash、ShortAllowed
- **THEN** 参数值在回测时通过 `sdi.ModelArgs` 传递给 `defStrategy`，覆盖 `__STRATEGY_META__` 中的默认值

#### Scenario: 选择依赖因子

- **WHEN** 用户从因子池中选择因子并拖入策略依赖区
- **THEN** 依赖因子列表更新，保存时写入 `__STRATEGY_META__.FactorDeps`，回测时这些因子注入 `sdi.Factors`

#### Scenario: 选择依赖策略

- **WHEN** 用户从策略列表中选择另一个已注册策略作为依赖
- **THEN** 依赖策略列表更新，保存时写入 `__STRATEGY_META__.StrategyDeps`

### Requirement: 策略保存

系统 SHALL 支持将策略代码和元信息保存到文件系统并注册到 Neo4j 图数据库。

#### Scenario: 保存策略到文件和图库

- **WHEN** 用户点击"保存策略"
- **THEN** 策略代码写入约定目录的 `.py` 文件，同时调用后端 API 注册到 Neo4j（更新 `(:策略)` 节点）

#### Scenario: 首次保存新策略

- **WHEN** 用户输入策略文件名后点击保存
- **THEN** 在配置的策略目录下创建 `.py` 文件，包含 `__STRATEGY_META__`、MakeStrategy 子类和 `defStrategy` 函数，再注册到图库

### Requirement: 策略回测执行

系统 SHALL 支持一键执行策略回测，将策略代码、配置参数和日期范围提交后端异步执行。

#### Scenario: 提交策略回测

- **WHEN** 用户配置好策略参数和日期范围，点击"运行回测"
- **THEN** 前端将策略代码和参数 POST 到 `POST /api/strategy/backtest`，后端返回 `task_id`，前端显示进度条

#### Scenario: 回测使用配置面板覆盖参数

- **WHEN** 用户在配置面板将 InitCash 改为 500000
- **THEN** 回测调用 `defStrategy(sdi)` 时 `sdi.ModelArgs["init_cash"]` 为 500000，覆盖 `__STRATEGY_META__` 默认值

### Requirement: 回测结果可视化

系统 SHALL 展示回测结果，包括账户净值曲线（Plotly）、绩效统计表（年化收益/夏普/最大回撤/胜率/Calmar）、交易记录表、持仓历史。

#### Scenario: 查看净值曲线

- **WHEN** 回测完成
- **THEN** 右侧结果显示区渲染 Plotly 双轴图：账户价值曲线 + 收益柱状图

#### Scenario: 查看绩效统计

- **WHEN** 回测完成
- **THEN** 展示绩效统计卡片（年化收益率、年化波动率、夏普比率、最大回撤、Calmar 比率、胜率、盈亏比），如有基准同时展示相对表现

#### Scenario: 查看交易记录

- **WHEN** 用户切换到"交易记录"Tab
- **THEN** 展示交易记录表格（交易时点、证券 ID、交易量、成交价、交易费）

#### Scenario: 查看持仓历史

- **WHEN** 用户切换到"持仓历史"Tab
- **THEN** 展示持仓热力图或表格（时点 × 证券 × 持仓数量/权重）
