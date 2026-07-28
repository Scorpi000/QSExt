## 1. 基础设施修复（Phase 1 补全）

- [x] 1.1 修复阻塞 I/O：将 FactorService 中的 QuantStudio 同步调用包装到 `run_in_executor`
- [x] 1.2 接入自定义异常处理：使用 `exceptions.py` 中定义的 `APIException`/`NotFoundException` 替代 raw `HTTPException`
- [x] 1.3 清理 `requirements.txt` 中未使用的依赖（SQLAlchemy、Alembic、python-jose、passlib）
- [x] 1.4 添加 Docker Compose 配置（frontend + backend）
- [x] 1.5 补充连接编辑功能（前端 UI 调用已有的 `updateConnection` API）

## 2. 因子工作台 — 后端（Phase 2）

- [x] 2.1 实现 QSRegistry 因子搜索 API：`GET /api/factors/search`（关键词匹配）
- [x] 2.2 实现语义搜索 API：`GET /api/factors/search/semantic`（Ollama 嵌入向量检索）
- [x] 2.3 实现因子 DAG 数据 API：`GET /api/factors/{qsid}/dag`（从 Neo4j 获取依赖关系，计算布局）
- [x] 2.4 实现因子详情 API：`GET /api/factors/{qsid}`（元信息 + 依赖 + 统计）
- [x] 2.5 实现 QSArgs JSON Schema API：`GET /api/args/{class_name}/schema`（基于 Pydantic `model_json_schema()`，处理 `frozen`/`exclude` 等元数据）
- [x] 2.6 实现算子列表 API：`GET /api/operators`（返回已注册算子及其 QSArgs schema）
- [x] 2.7 实现衍生因子创建 API：`POST /api/factors/derivative`

## 3. 因子工作台 — 前端（Phase 2）

- [x] 3.1 创建 FactorWorkbench 页面骨架（路由 + 布局）
- [x] 3.2 实现因子搜索组件（搜索框 + 结果列表 + 筛选器）
- [x] 3.3 实现 DAG 可视化组件（React Flow 集成 + 自定义节点类型 + 自动布局）
- [x] 3.4 实现因子详情面板（元信息 + 依赖列表 + 数据统计）
- [x] 3.5 实现动态表单组件（@rjsf/antd 集成，根据 JSON Schema 自动渲染）
- [x] 3.6 实现衍生因子创建向导（算子选择 → 依赖选择 → 参数配置 → 预览）

## 4. 异步任务框架

- [x] 4.1 实现后端 TaskManager（任务提交、进度跟踪、结果存储）
- [x] 4.2 实现 WebSocket 端点：`/ws/tasks/{task_id}`
- [x] 4.3 实现前端 `useTaskProgress` Hook（WebSocket 连接 + 状态管理）
- [x] 4.4 实现通用进度条组件

## 5. 回测工作台 — 后端骨架 + IC 模块打通（仅 FactorDB）

- [x] 5.1 定义 Pydantic 模型（`FactorRef`、`PriceRef`、`ParamDef`、`ModuleInfo`、`ModuleRunConfig`、`BacktestRunRequest`、`ResultNode`）和 `BACKTEST_MODULE_REGISTRY`（仅含 `ic` 模块）
- [x] 5.2 实现 `GET /api/backtest/modules` 和 `GET /api/backtest/modules/{key}` API
- [x] 5.3 实现 `QSBridge`：`_get_factor_from_db(conn_id, table_name, factor_name)` 通过 `ft.getFactor()` 获取 Factor 对象
- [x] 5.4 实现 `QSBridge.build_bt_nodes`：根据 `ModuleRunConfig` 列表构造 `CalcIC → IC` 回测节点，打包为 `BTReport`
- [x] 5.5 实现 `QSBridge.run_backtest`（在 executor 中执行 `Engine.run()`）和 `_output_to_tree`（输出 dict → `ResultNode` 树）
- [x] 5.6 实现 `POST /api/backtest/run`（异步任务提交，返回 `task_id`）和 `GET /api/backtest/tasks/{task_id}/result`

## 6. 回测工作台 — 前端 IC 模块全链路（仅 FactorDB）

- [x] 6.1 创建 FactorSelector 组件（仅 FactorDB Tab：连接选择 → 因子表选择 → 因子多选 + 已选 Tag 展示）
- [x] 6.2 创建 ModulePicker 组件（下拉选择模块 → 根据 params 定义动态弹出配置表单 → 加入待运行列表）
- [x] 6.3 创建 ModuleList 组件（待运行模块列表展示，支持编辑/删除）
- [x] 6.4 创建 BacktestStudio 页面骨架（左侧：配置区，右侧：结果区）和全局配置面板（日期范围、价格因子选择、截面 ID）
- [x] 6.5 创建 ResultTree 组件（Ant Tree 渲染结果节点，按 type 区分图标）
- [x] 6.6 创建 ResultLeaf 组件（series → Plotly 折线图、dataframe → Ant Table、scalar → Statistic）和点击选中交互
- [x] 6.7 集成 `POST /api/backtest/run`，提交时组装完整请求，通过 `useTaskProgress` 跟踪进度
- [x] 6.8 注册 BacktestStudio 路由，启用导航菜单

## 7. 风险管理 — 后端（Phase 4）

- [x] 7.1 实现风险库浏览 API：`GET /api/risk/databases` + `GET /api/risk/databases/{id}/tables`
- [x] 7.2 实现协方差矩阵 API：`GET /api/risk/tables/{id}/covariance`
- [x] 7.3 实现相关系数矩阵 API：`GET /api/risk/tables/{id}/correlation`
- [x] 7.4 实现因子风险分解 API：`GET /api/risk/tables/{id}/factor-decomposition`

## 8. 风险管理 — 前端（Phase 4）

- [x] 8.1 创建 RiskManager 页面骨架（左侧风险库树 + 右侧内容区）
- [x] 8.2 实现协方差矩阵热力图组件（ECharts heatmap）
- [x] 8.3 实现因子风险分解表格 + 柱状图
- [x] 8.4 实现特异性风险分布直方图

## 9. 组合优化 — 后端（Phase 4）

- [x] 9.1 实现优化求解 API：`POST /api/portfolio/optimize`（CVXPY 集成）
- [x] 9.2 实现求解结果 API：`GET /api/portfolio/solutions/{id}`
- [x] 9.3 实现权重导出 API：`GET /api/portfolio/solutions/{id}/weights`（CSV 格式）

## 10. 组合优化 — 前端（Phase 4）

- [x] 10.1 创建 PortfolioOptimizer 页面骨架
- [x] 10.2 实现优化目标配置组件（目标类型选择 + 参数表单）
- [x] 10.3 实现约束条件编辑器（Box/行业暴露/换手率/基数约束）
- [x] 10.4 实现求解结果展示（权重分布图 + 风险分解图）
- [x] 10.5 实现权重导出功能

## 11. 报告中心 — 后端（Phase 5）

- [x] 11.1 实现报告生成 API：`POST /api/reports/generate`（异步任务，调用 ReportGenerator）
- [x] 11.2 实现报告列表 API：`GET /api/reports`（按因子/场景/日期筛选）
- [x] 11.3 实现报告内容 API：`GET /api/reports/{id}/content`
- [x] 11.4 实现报告注册 API：`POST /api/reports/{id}/register`（调用 QSRegistry MCP）

## 12. 报告中心 — 前端（Phase 5）

- [x] 12.1 创建 ReportCenter 页面骨架
- [x] 12.2 实现报告生成表单（场景选择 + 参数配置）
- [x] 12.3 实现报告列表（表格 + 筛选）
- [x] 12.4 实现报告预览（HTML 内嵌渲染 + Markdown 渲染）
- [x] 12.5 实现报告下载功能

## 13. 打磨与部署（Phase 5）

- [x] 13.1 前端懒加载：页面组件按路由动态导入
- [x] 13.2 统一错误处理：后端全局异常处理器 + 前端 Axios 拦截器
- [x] 13.3 统一加载状态：全局 Loading 组件 + 骨架屏
- [x] 13.4 Docker 镜像优化（多阶段构建）
- [x] 13.5 编写部署文档（docker-compose 使用说明）

## 14. QSRegistry 因子源接入

- [x] 14.1 实现 `QSBridge._get_factor_from_registry(name)`：通过 `QSGraphDB.searchFactors → reconstructFactor` 获取 Factor 对象
- [x] 14.2 实现 `QSBridge.register_factor_dbs`：将 `FactorService` 中已连接的 FactorDB 注册到 `QSGraphDB`
- [x] 14.3 FactorSelector 增加 QSRegistry Tab（搜索框 + 结果列表 + 多选 + 已选 Tag 展示）
- [x] 14.4 实现因子名 → QSID 查找 → 重建的完整链路端到端测试

## 15. 后续回测模块添加

- [x] 15.1 在 `BACKTEST_MODULE_REGISTRY` 中添加 `ic_decay` 模块（IC 衰减曲线）
- [x] 15.2 添加 `multi_portfolio` 模块（分位数组合）
- [x] 15.3 添加 `factor_turnover` 模块（因子换手率）
- [x] 15.4 添加 `section_correlation` 模块（截面相关性）
- [x] 15.5 添加 `fama_macbeth` 模块（Fama-MacBeth 回归）