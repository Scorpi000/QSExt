# Tasks: add-strategy-studio

## 1. StrategyDef 框架核心

- [x] 1.1 创建 `QSExt/StrategyDef/` 目录结构和 `__init__.py`
- [x] 1.2 实现 `StrategyDefInput` 类（FDB, Factors, Strategies, ModelArgs, DTs, DTRuler, IDs, SectionIDs）
- [x] 1.3 实现 `StrategyMeta` 类（TargetTable, IDType, OperatorConfig, FactorDeps, StrategyDeps, DBDeps, ModelArgs, Author, Description, Tags, MaxLookBack, DefScriptPath）
- [x] 1.4 实现 `StrategyDef` 包装类（Strategy + StrategyClass + Meta）
- [x] 1.5 实现 `build_dep_sd()` 递归依赖解析（先解析 FactorDeps→复用 build_dep_fd，再解析 StrategyDeps→递归执行 defStrategy，注入 sdi.Factors 和 sdi.Strategies）
- [x] 1.6 实现 `compute_max_lookback` 对策略链的适配
- [x] 1.7 编写策略框架单元测试（StrategyMeta 校验、build_dep_sd 基础/循环依赖场景）

## 2. StrategyDef 配置和执行管线

- [x] 2.1 实现 `StrategyDefSettings` 类（与 FactorDefSettings 对齐，from_module 工厂方法）
- [x] 2.2 实现 `StrategyDefInputBuilder` 类（从 settings 构造 StrategyDefInput，含因子库连接、DTs/IDs 解析）
- [x] 2.3 创建 `conf/settings.example.py` 配置模板（含策略目录、输出 HDF5 配置、Neo4j 配置）
- [x] 2.4 实现 `scripts/run_strategy_def.py` 执行管线（settings → builder → build_dep_sd → defStrategy → 写 HDF5）
- [x] 2.5 创建示例策略模块 `example_strategy.py`（含 __STRATEGY_META__ + MakeStrategy 子类 + defStrategy）

## 3. Neo4j 策略持久化

- [x] 3.1 在 QSGraphDB 中新增 `_serializeStrategy()` 辅助方法（策略 → Neo4j 节点属性 dict）
- [x] 3.2 实现 `storeStrategies(strategies, tags)` 批量写入方法（MERGE 策略节点 + 依赖关系 + 标签关系）
- [x] 3.3 实现 `searchStrategies(name, tags, factor_qsid)` 检索方法
- [x] 3.4 实现 `searchStrategiesByDescription(query_text)` 语义搜索方法
- [x] 3.5 实现 `getStrategyByQSID(qsid)` 和 `getStrategyCode(qsid)` 查询方法
- [x] 3.6 实现 `getStrategyDependencyGraph(qsid)` 依赖图查询
- [x] 3.7 实现 `getStrategyDependents(qsid)` 下游影响查询
- [x] 3.8 实现 `updateStrategyMeta(qsid, meta)` 和 `deleteStrategy(qsid)` 方法
- [x] 3.9 实现 `scripts/register_strategies_to_graphdb.py` 注册脚本
- [x] 3.10 创建 Neo4j 约束和索引（strategy QSID UNIQUE, strategy_name, strategy_embedding vector index）

## 4. QSWeb 后端 API

- [x] 4.1 创建 `models/strategy.py` Pydantic 模型（StrategyMetaModel, StrategySearchResult, StrategyBacktestRequest, StrategyBacktestResult）
- [x] 4.2 创建 `services/strategy_service.py`（代码验证、文件存储、Neo4j 注册、回测执行）
- [x] 4.3 实现 `POST /api/strategy/import` — 接收代码文件/字符串，验证 + 存储 + 后台注册
- [x] 4.4 实现 `POST /api/strategy/import/preview` — 仅预览元信息
- [x] 4.5 实现 `GET /api/strategy/search` — 搜索策略列表
- [x] 4.6 实现 `GET /api/strategy/{qsid}` — 获取策略详情
- [x] 4.7 实现 `GET /api/strategy/{qsid}/code` — 获取策略源代码
- [x] 4.8 实现 `DELETE /api/strategy/{qsid}` — 删除策略
- [x] 4.9 实现 `POST /api/strategy/backtest` — 提交策略回测（异步 task，含代码/QSID 两种方式）
- [x] 4.10 实现 `GET /api/strategy/backtest/{task_id}/result` — 获取回测结果
- [x] 4.11 实现 `GET /api/strategy/factors/available` — 可选因子列表
- [x] 4.12 在 QSBridge 中新增 `run_strategy_backtest()` 方法
- [x] 4.13 在 `api/__init__.py` 注册 `/api/strategy` 路由
- [x] 4.14 编写 API 集成测试

## 5. QSWeb 前端策略工作台

- [x] 5.1 创建 `services/strategy.ts`（TypeScript 接口 + API 函数）
- [x] 5.2 创建 `pages/StrategyStudio/index.tsx` 页面主组件（左右分栏布局）
- [x] 5.3 创建 `pages/StrategyStudio/StrategyList.tsx`（策略搜索/列表/新建）
- [x] 5.4 创建 `pages/StrategyStudio/StrategyEditor.tsx`（Monaco Editor 封装，Python 语法高亮）
- [x] 5.5 创建 `pages/StrategyStudio/StrategyConfig.tsx`（OperatorConfig 表单 + 因子/策略依赖选择器）
- [x] 5.6 创建 `pages/StrategyStudio/StrategyResult.tsx`（回测结果展示：净值曲线 Plotly + 绩效卡片 + 交易记录表格 + 持仓 Tab）
- [x] 5.7 在 `App.tsx` 添加 `/strategy` 路由（lazy load）
- [x] 5.8 在 `MainLayout.tsx` 添加"策略工作台"导航菜单项

## 6. 配置和文档

- [x] 6.1 在 `QSWebConfig.yaml` schema 中添加 `strategy` 配置节（scripts_dir, neo4j 配置引用）
- [x] 6.2 更新 `CLAUDE.md` 中的项目架构说明（新增 StrategyDef 模块）
- [x] 6.3 编写 StrategyDef 框架使用文档（docs/策略定义/）
- [x] 6.4 更新 MCP 服务 `qs_registry.py` 暴露策略相关工具（search_strategies, get_strategy_info, get_strategy_code）
