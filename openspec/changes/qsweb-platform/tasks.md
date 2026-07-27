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

## 5. 回测工作台 — 后端（Phase 3）

- [x] 5.1 实现 IC 分析 API：`POST /api/backtest/ic-analysis`
- [x] 5.2 实现分位数组合 API：`POST /api/backtest/quantile-portfolio`
- [x] 5.3 实现因子换手率 API：`POST /api/backtest/turnover`
- [x] 5.4 实现策略回测 API：`POST /api/backtest/strategy/run`（异步任务）
- [x] 5.5 实现回测结果 API：`GET /api/backtest/tasks/{task_id}/result`
- [x] 5.6 实现回测历史 API：`GET /api/backtest/history`
- [x] 5.7 实现回测注册 API：`POST /api/backtest/{task_id}/register`

## 6. 回测工作台 — 前端（Phase 3）

- [x] 6.1 创建 BacktestStudio 页面骨架
- [x] 6.2 实现回测配置表单（因子选择、日期范围、再平衡频率、账户参数）
- [x] 6.3 实现 IC 分析结果展示（IC 时间序列图、IC 衰减曲线）
- [x] 6.4 实现分位数组合结果展示（多空净值曲线）
- [x] 6.5 实现策略回测结果展示（净值曲线 + 统计指标表格 + 交易记录）
- [x] 6.6 集成 Plotly 图表组件（净值曲线、IC 图表）
- [x] 6.7 实现回测历史列表 + 对比功能
