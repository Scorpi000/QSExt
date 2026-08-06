# strategy-backtest-api

## Purpose

QSWeb 后端策略回测 API，提供策略代码的动态加载、策略实例化、回测执行和结果序列化能力。

## ADDED Requirements

### Requirement: 策略导入和验证

系统 SHALL 提供 API 接收策略脚本代码（上传文件或粘贴代码），通过 importlib 动态加载模块，验证 `__STRATEGY_META__` 和 `defStrategy` 签名。

#### Scenario: 上传策略文件验证

- **WHEN** 用户上传 `.py` 策略文件到 `POST /api/strategy/import`
- **THEN** 后端 importlib 加载模块，读取 `__STRATEGY_META__` 字典，检测 `defStrategy` 函数存在且签名正确，返回验证结果（成功/失败/警告）

#### Scenario: 验证失败返回错误

- **WHEN** 上传的代码有语法错误或缺少 `__STRATEGY_META__`
- **THEN** 返回具体错误信息（行号、错误类型），不保存文件

#### Scenario: 预览策略元信息

- **WHEN** 调用 `POST /api/strategy/import/preview`
- **THEN** 仅验证和返回元信息摘要，不执行磁盘写入和 Neo4j 注册

### Requirement: 策略代码存储与 Neo4j 注册

`POST /api/strategy/import` SHALL 将验证通过的策略脚本保存到约定目录（通过 `QSWebConfig.yaml` 中 `strategy_def.scripts_dir` 配置），若文件名重复自动重命名。保存后通过 `register_strategies_to_graphdb.main()` 异步注册到 Neo4j。

注册要求 `QSWebConfig.yaml` 中 `strategy_def.settings_path` 必填，指向 StrategyDef 的 settings.py。若未配置则返回 400 错误。

#### Scenario: 保存策略脚本并注册

- **WHEN** 验证通过且 `strategy_def.settings_path` 已配置
- **THEN** 策略 `.py` 文件写入 `scripts_dir` 目录，后台调用 `register_strategies_to_graphdb.main()` 通过完整管线（含 JYDB 连接、ID 解析、defStrategy 执行）注册到 Neo4j

#### Scenario: 未配置 settings_path 时拒绝

- **WHEN** `strategy_def.settings_path` 为空
- **THEN** 返回 HTTP 400，提示"未配置 strategy_def.settings_path，请在 QSWebConfig.yaml 中设置"

### Requirement: 策略元信息查询

系统 SHALL 提供策略详情和代码查询 API，从 Neo4j 获取元信息，从文件系统读取源代码。

#### Scenario: 获取策略详情

- **WHEN** 调用 `GET /api/strategy/{qsid}`
- **THEN** 从 Neo4j 查询策略节点，返回 Name、OperatorConfig、FactorDeps、StrategyDeps、Tags、DefScriptPath 等完整元信息

#### Scenario: 获取策略源代码

- **WHEN** 调用 `GET /api/strategy/{qsid}/code`
- **THEN** 根据 `DefScriptPath` 读取 `.py` 文件，返回完整源代码文本

### Requirement: 策略搜索

系统 SHALL 提供策略搜索 API，支持按名称模糊匹配和语义搜索，结果从 Neo4j 查询。

#### Scenario: 关键词搜索策略

- **WHEN** 调用 `GET /api/strategy/search?q=均线`
- **THEN** 返回名称或描述包含"均线"的策略列表，每项含 Name、QSID、Description、Tags、UpdatedAt

#### Scenario: 按标签过滤

- **WHEN** 调用 `GET /api/strategy/search?tag=趋势跟踪`
- **THEN** 返回所有标记为"趋势跟踪"的策略

### Requirement: 策略回测执行

`POST /api/strategy/backtest` SHALL 接收策略代码/QSID、依赖因子映射、参数覆盖和日期范围，通过异步任务执行策略回测。

回测执行流程：
1. 动态加载策略模块（从代码字符串或文件路径）
2. 连接因子库获取 IDs（证券列表）和 DTs（交易日列表），未连接时返回明确错误
3. 构造 `StrategyDefInput`（含 FDB、Factors、Strategies、ModelArgs 覆盖值、DTs、IDs）
4. 调用 `defStrategy(sdi)` 得到策略因子实例列表
5. 取第一个策略实例构造 `AccountReport(strategy_factor)` 作为 BTNode
6. 通过 `Engine.run()` 执行，`fwd_data_list=[FactorLocalContext(DTs=dts, IDs=ids)]`（IDs 为必填字段）
7. 序列化结果为 `ResultNode` 树

#### Scenario: 以代码方式提交回测

- **WHEN** POST 请求包含 `code` 字段（策略 Python 代码字符串）、`factor_refs`（因子映射）、`start_date`、`end_date`
- **THEN** 后端动态 import 策略代码、实例化策略、执行回测，返回 `task_id`

#### Scenario: 以 QSID 方式提交回测

- **WHEN** POST 请求包含 `strategy_qsid` 字段
- **THEN** 后端从 Neo4j 查询 `DefScriptPath`，加载策略文件，实例化并回测

#### Scenario: 依赖策略的递归解析

- **WHEN** 策略依赖另一个策略（StrategyDeps 非空）
- **THEN** 后端先加载并实例化依赖策略，将其输出因子注入 `sdi.Strategies`，再执行主策略

### Requirement: 回测结果轮询

前端 SHALL 通过轮询 `GET /api/strategy/backtest/{task_id}/result` 获取回测结果。因后端 202 响应被 axios 视为成功（2xx），轮询逻辑通过检查返回数据是否含 `type` 字段判断是否完成（有效 ResultNode 必有 `type` 字段）。

#### Scenario: 回测运行中

- **WHEN** 轮询返回 202 状态的 `{"detail": "任务正在运行中"}`
- **THEN** 前端检测到数据无 `type` 字段，保持 loading 状态继续轮询

#### Scenario: 回测完成

- **WHEN** 轮询返回含 `type` 字段的 ResultNode 数据
- **THEN** 停止轮询，渲染结果树

### Requirement: 回测结果序列化

系统 SHALL 将策略回测结果（`AccountReport.backward_compute` 的 output dict）序列化为统一的 `ResultNode` 树结构，与现有模块化回测结果格式兼容。

策略回测结果包含：
- 时间序列：账户价值、净值、收益率、累计收益率
- 统计数据：年化收益、夏普比率、最大回撤、Calmar 比率、胜率、盈亏比
- 交易信号：信号时点列表（DataFrame）
- 交易记录：交易时点、证券 ID、交易量、成交价、交易费
- 持仓数量：时点 × 证券 DataFrame

#### Scenario: 序列化账户净值曲线

- **WHEN** 回测完成，output 包含 `时间序列` DataFrame
- **THEN** 序列化为 `ResultNode(type="series")`，data 包含 index（日期）和 values（净值）

#### Scenario: 序列化绩效统计

- **WHEN** 回测完成，output 包含 `统计数据` DataFrame
- **THEN** 序列化为 `ResultNode(type="dataframe")`，data 包含 columns（指标名）和 data（数值矩阵）

### Requirement: 策略删除

`DELETE /api/strategy/{qsid}` SHALL 删除策略的 Neo4j 节点（及其关系），可选同时删除 `.py` 文件。

#### Scenario: 删除策略保留文件

- **WHEN** 调用 `DELETE /api/strategy/{qsid}?keep_file=true`
- **THEN** 仅从 Neo4j DETACH DELETE 策略节点，`.py` 文件保留

#### Scenario: 删除策略含文件

- **WHEN** 调用 `DELETE /api/strategy/{qsid}?keep_file=false`
- **THEN** 删除 Neo4j 节点，同时删除 `DefScriptPath` 指向的 `.py` 文件

### Requirement: 可用因子列表

`GET /api/strategy/factors/available` SHALL 返回可选因子列表，合并全局因子池（FactorDB）和 QSRegistry 已注册因子，供策略配置依赖时选择。

#### Scenario: 获取可选因子

- **WHEN** 用户在策略配置面板选择依赖因子
- **THEN** 前端调用此 API 获取因子列表，每项含因子名、来源、因子表/QSID
