## Why

QSWeb 目前缺少策略开发调试的工具支持——回测工作台只提供模块化因子分析（IC、分位数组合等），用户无法在 Web 端编写、回测和管理自定义交易策略。同时，开发好的策略无法持久化，缺少类似因子注册中心（QSRegistry）的策略版本管理和复用机制。本次变更填补这一空白。

## What Changes

- **新增 StrategyDef 框架** (`QSExt/StrategyDef/`)：与 FactorDef 对齐的策略定义模块，包含元信息约定、依赖解析、执行管线和图数据库注册
- **Neo4j 图模型扩展**：在 QSGraphDB 中新增 `(:策略)` 节点的 CRUD 能力，支持策略-因子、策略-策略的依赖关系存储
- **新增 QSWeb 策略工作台页面** (`/strategy`)：策略列表/搜索、Monaco 代码编辑器、参数配置、一键回测、结果可视化（净值曲线、绩效统计、交易记录）
- **新增 QSWeb 后端 API**：策略导入/验证/保存、回测执行（异步任务）

## Capabilities

### New Capabilities

- `strategy-def-framework`: StrategyDef 模块——策略元信息约定（`__STRATEGY_META__`）、标准入口 `defStrategy()`、依赖解析 `build_dep_sd()`、注册到图数据库、策略信号 HDF5 持久化
- `strategy-graphdb-persistence`: QSGraphDB 策略节点 CRUD——`(:策略)` 节点的创建/查询/更新/删除，以及 `[:依赖因子]`、`[:依赖策略]`、`[:输出到]` 关系的管理
- `strategy-studio-page`: QSWeb 策略工作台页面——策略列表/搜索、Monaco 代码编辑器、参数配置面板、回测结果可视化
- `strategy-backtest-api`: 策略回测 API——策略代码动态加载、`defStrategy` 调用、`AccountReport` 执行、结果序列化返回

### Modified Capabilities

- `backtest-studio`: 策略回测复用现有 `ResultTree` + `ResultLeaf` 组件和 `ResultNode` 数据结构，无需扩展新类型

## Impact

| 影响范围 | 说明 |
|----------|------|
| `QSExt/StrategyDef/` | 新增模块（StrategyDefContent.py, run_strategy_def.py, register_strategies_to_graphdb.py） |
| `QSExt/QSRegistry/QSGraphDB.py` | 新增策略节点 CRUD 方法组（_serializeStrategy, storeStrategies, searchStrategies 等） |
| `QSWeb/backend/app/api/strategy.py` | 新增路由（import, search, detail, code, delete, backtest） |
| `QSWeb/backend/app/models/strategy.py` | 新增 Pydantic 模型 |
| `QSWeb/backend/app/services/strategy_service.py` | 新增服务层（代码验证、文件存储、Neo4j 注册） |
| `QSWeb/backend/app/services/qs_bridge.py` | 新增 run_strategy_backtest() 方法 |
| `QSWeb/backend/app/core/config.py` | 新增 strategy_def 配置属性 |
| `QSWeb/backend/app/api/__init__.py` | 注册新路由 |
| `QSWeb/frontend/src/pages/StrategyStudio/` | 新增页面组件（Tab 布局，复用 ResultTree/ResultLeaf） |
| `QSWeb/frontend/src/services/strategy.ts` | 新增前端服务层 |
| `QSWeb/frontend/src/App.tsx` | 新增 `/strategy` 路由 |
| `QSWeb/frontend/src/components/Layout/MainLayout.tsx` | 导航菜单新增"策略工作台"（位于回测工作台下方） |
| `~/QuantStudioConfig/QSWebConfig.yaml` | 新增 strategy_def 配置节（scripts_dir, settings_path【必填】, default_id_type） |
| `d:\Project\QuantStudio\...\Strategy.py` | 修复 numpy dtype 兼容性（unstructured_to_structured） |
