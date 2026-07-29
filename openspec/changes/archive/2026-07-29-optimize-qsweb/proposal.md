## Why

QSWeb 当前有三层技术债：因子库连接管理绕过 QSGraphDB 另建 JSON 文件体系，六个页面各自独立检索因子互不可见，QSBridge 等核心模块存在大量重复代码。三者叠加导致维护成本高、用户体验割裂、后续功能扩展受阻。本次变更统一这三个方向，建立以 QSGraphDB 为单一真相源的架构基础。

## What Changes

### QSRegistry 深度绑定
- ConnectionService 重写为 QSGraphDB 的薄封装，因子库连接的 CRUD 直接操作图数据库中的 `因子库` 节点
- registerFactorDB 的 MERGE 键从 `Name` 改为 `QSID`，实现因子库的唯一化标识
- QSGraphDB 新增 `listFactorDBs`、`getFactorDB`、`deleteFactorDB`、`reconstructFactorDB` API
- **BREAKING**: QSWebConfig.json 的 `factor_dbs` 节废弃，提供迁移脚本将已有连接写入 Neo4j
- 前端 Connection 模型新增 `qsid` 字段

### 全局因子池
- 前端新增 Zustand store `factorPoolStore`，跨页面共享因子选择状态
- 后端新增 FactorPoolService，负责因子解析、元数据懒加载和内存缓存
- FactorSelector 删除，拆分为 FactorDiscover（发现新因子，Drawer）+ FactorPoolPanel（管理池中因子，MainLayout 右侧滑出面板）
- 用户可选将因子池持久化到图数据库（`因子池` 节点 -[:包含]-> `因子` 节点），下次访问自动恢复
- FactorRef 格式统一为以 QSID 为核心标识的 `PoolItem`

### 代码质量
- QSBridge 的 6 个 `_build_*_node_sync` 方法合并为声明式模块注册表 + 通用构造器，消除约 250 行重复代码
- FactorService 抽取 `_run_sync` 辅助方法消除 `run_in_executor` 模板代码
- 前端巨型页面拆分：DataManager（1081 行→4 个子组件）、PortfolioOptimizer（1014 行→3 个子组件）、ReportCenter（864 行→3 个子组件）
- 新增 React Error Boundary 包裹每个页面路由，防止单页崩溃导致白屏

## Capabilities

### New Capabilities
- `qsregistry-factor-db-integration`: 因子库连接以 QSGraphDB 的 `因子库` 节点为存储后端，QSID 唯一标识，支持完整的 CRUD 和自动重建
- `global-factor-pool`: 跨页面共享的因子池（MainLayout 右侧面板），支持从 FactorDB/QSRegistry 双源添加，持久化到图数据库（通过 storeFactors 完整注册因子节点）

### Modified Capabilities
- `data-manager`: 因子库连接管理的数据源从 QSWebConfig.json 变更为 QSGraphDB 图数据库；连接标识从 UUID 变更为 QSID
- `backtest-studio`: 因子选择从 FactorSelector 变更为 ModulePicker 从 store 读取；QSRegistry 因子源完整支持
- `portfolio-optimizer`: SingleFactorPicker 替换为 PoolFactorPicker，从 store 读取因子
- `report-center`: FactorRefSelector 替换为 PoolRefPicker，被测因子从 store.selectedIds 读取

## Impact

- **QSExt/QSRegistry/QSGraphDB.py**: registerFactorDB 修改 MERGE 键；新增 FactorDB CRUD 和 FactorPool 持久化 API（约 200 行）
- **QSWeb/backend/app/services/connection_service.py**: 完全重写为 QSGraphDB 封装（约 150 行 → 约 100 行）
- **QSWeb/backend/app/services/factor_pool_service.py**: 新文件，因子池后端服务（约 200 行）
- **QSWeb/backend/app/services/qs_bridge.py**: 声明式模块注册表替代 if/elif 链（约 957 行 → 约 700 行）
- **QSWeb/backend/app/services/factor_service.py**: 抽取 _run_sync 模板（约 386 行 → 约 300 行）
- **QSWeb/backend/app/api/**: connection、factor_pool 路由调整
- **QSWeb/frontend/src/stores/**: 新增 factorPoolStore.ts（Zustand）
- **QSWeb/frontend/src/pages/**: DataManager(3 子组件)、PortfolioOptimizer(3 子组件)、ReportCenter(3 子组件) 拆分；各页面因子选择改为从 store 读取
- **QSWeb/frontend/src/components/**: FactorSelector 删除，拆分为 FactorDiscover（Drawer）+ FactorPoolPanel（嵌入 MainLayout）；新增 ErrorBoundary
- **QSWeb/frontend/src/services/**: 新增 factorPool.ts 前端 API 封装；Connection 模型增加 qsid
- **QSWebConfig.json**: factor_dbs 节废弃（迁移后），保留 backtest/config 节
