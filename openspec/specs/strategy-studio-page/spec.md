# strategy-studio-page

## Purpose

QSWeb 策略工作台页面（`/strategy`），提供策略脚本的代码编辑、参数配置、回测执行和结果分析的一站式 Web 界面。

## Requirements

### Requirement: 页面路由和导航

系统 SHALL 在 `/strategy` 路径下提供策略工作台页面，并将其添加到左侧导航菜单中「回测工作台」之后。页面采用左右分栏布局（左侧策略列表+配置，右侧 Tab 切换）。

#### Scenario: 导航到策略工作台

- **WHEN** 用户点击左侧导航"策略工作台"（位于回测工作台下方）
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

### Requirement: 右侧 Tab 布局

右侧面板 SHALL 使用 Tab 切换「策略代码」和「回测结果」。未运行回测时仅展示策略代码 Tab，运行后出现回测结果 Tab，回测完成后自动切换到结果 Tab。

#### Scenario: 仅代码 Tab

- **WHEN** 页面加载且未运行回测
- **THEN** 仅显示「策略代码」Tab，编辑器占满右侧区域

#### Scenario: 回测完成后自动切换

- **WHEN** 回测任务完成，StrategyResult 组件获取到有效结果（数据含 `type` 字段）
- **THEN** 通过 `onResultReady` 回调通知父组件，自动从代码 Tab 切换到「回测结果」Tab

#### Scenario: 手动切换 Tab

- **WHEN** 回测结果已加载
- **THEN** 用户可在「策略代码」和「回测结果」Tab 之间自由切换

### Requirement: 回测结果可视化

系统 SHALL 复用现有 `ResultTree` + `ResultLeaf` 组件展示回测结果。结果数据通过 `_output_to_tree()` 序列化为 `ResultNode` 树，与回测工作台使用相同的数据结构。

结果树包含：
- `统计数据`（series 节点）：年化收益、夏普比率、最大回撤、Calmar 比率、胜率、盈亏比
- `时间序列`（dataframe 节点）：账户价值、净值、收益率、累计收益率

#### Scenario: 查看结果树

- **WHEN** 回测完成，用户切换到回测结果 Tab
- **THEN** 左侧显示结果树（按 type 区分图标：series→折线图、dataframe→表格、scalar→数值），右侧显示选中节点的详情

#### Scenario: 查看绩效统计

- **WHEN** 用户在结果树中点击「统计数据」节点（type=series）
- **THEN** 右侧 ResultLeaf 渲染 Plotly 折线图 + 数据表，index 为指标名，values 为数值

#### Scenario: 查看时间序列

- **WHEN** 用户在结果树中点击「时间序列」节点（type=dataframe）
- **THEN** 右侧 ResultLeaf 渲染 Ant Table，列为指标名（账户价值、净值等），行为日期
