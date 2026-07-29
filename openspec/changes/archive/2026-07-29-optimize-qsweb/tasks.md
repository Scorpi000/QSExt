## 1. QSGraphDB 增强

- [x] 1.1 `registerFactorDB` 的 MERGE 键从 `Name` 改为 `QSID`，更新 Cypher 查询
- [x] 1.2 新增 `listFactorDBs()` 方法：MATCH 所有 `因子库` 节点，返回 QSID/Name/DBType/UpdatedAt
- [x] 1.3 新增 `getFactorDB(qsid)` 方法：按 QSID 查询单条节点，调用 `_autoBuildFactorDB` 重建实例
- [x] 1.4 新增 `deleteFactorDB(qsid)` 方法：先查询影响范围（`因子表`-[`属于因子库`]->`因子库` 链路）→ 级联删除所有依赖的因子和因子表节点 → 删除因子库节点 → 清理 `_FactorDBRegistry`
- [x] 1.5 新增 `reconstructFactorDB(qsid)` 方法：`getFactorDB` + `connect()` 的便捷包装
- [x] 1.6 新增 `getImpactAnalysis(qsid)` 方法：查询受因子库删除影响的因子表和因子列表
- [x] 1.7 新增因子池持久化方法：`saveFactorPool(name, qsids)` / `loadFactorPool(name)` / `listFactorPools()` / `deleteFactorPool(name)`

## 2. ConnectionService 重写

- [x] 2.1 ConnectionService 改为接受 QSGraphDB 实例作为依赖（构造函数注入），不再依赖 QSWebConfig.json
- [x] 2.2 `create_connection` 重写：创建瞬时 FactorDB 实例 → connect → `gdb.registerFactorDB(fdb)` → 返回含 QSID 的响应
- [x] 2.3 `list_connections` 重写：调用 `gdb.listFactorDBs()` 转换格式
- [x] 2.4 `get_connection` 重写：按 QSID 查询（替代原 UUID）
- [x] 2.5 `update_connection` 重写：用新参数 connect → 比较新旧 QSID → 相同则直接更新 → 不同则检查冲突 + 查询影响范围 + 前端确认 + 迁移因子关系 + 更新池中引用
- [x] 2.6 `delete_connection` 重写：先调用 `gdb.getImpactAnalysis(qsid)` 返回影响范围 → 前端弹出确认对话框 → 确认后 `gdb.deleteFactorDB(qsid)` 级联删除 + `factor_service.disconnect(qsid)` + 清理全局因子池
- [x] 2.7 `get_impact(qsid)` 新接口：返回受影响的因子表和因子列表
- [x] 2.8 `test_connection` 保留现有逻辑（瞬时连接测试，不写入图数据库）
- [x] 2.9 新增 `POST /api/connections/health` 端点检测 QSGraphDB 可用性

## 3. 配置迁移

- [x] 3.1 创建 `QSWeb/scripts/migrate_connections.py` CLI 脚本
- [x] 3.2 实现 `--dry-run` 模式：预览将要迁移的连接和对应的 QSID
- [x] 3.3 实现实际迁移：遍历 QSWebConfig.json 的 factor_dbs → 创建 FactorDB → gdb.registerFactorDB
- [x] 3.4 迁移前自动备份 QSWebConfig.json，迁移成功后删除 factor_dbs 节
- [x] 3.5 更新 QSWeb/README.md 添加迁移说明

## 4. 全局因子池后端

- [x] 4.1 创建 `app/services/factor_pool_service.py`：FactorPoolService 类
- [x] 4.2 实现 `resolve(factor_refs)` 方法：双源解析 Factor 对象 + 内存缓存
- [x] 4.3 实现 `get_stats(qsid)` 方法：懒加载因子统计信息
- [x] 4.4 实现 `save_pool(name, items)` / `load_pool(name)` / `list_pools()` 持久化方法
- [x] 4.5 创建 `app/api/pool.py`：因子池 REST 路由
- [x] 4.6 POST `/api/pool/factors` — 添加因子到池（resolve + 缓存）
- [x] 4.7 DELETE `/api/pool/factors/{id}` — 从池中移除因子
- [x] 4.8 POST `/api/pool/save` — 保存池子到图数据库
- [x] 4.9 GET `/api/pool/load/{name}` — 从图数据库加载池子
- [x] 4.10 GET `/api/pool/list` — 列出已保存的池子
- [x] 4.11 POST `/api/pool/factors/delete` — 删除已保存的池子
- [x] 4.12 实现因子库删除时的池子清理：监听 ConnectionService 的删除事件，自动移除池中受影响因子

## 5. QSBridge 去重

- [x] 5.1 在 `qs_bridge.py` 中定义声明式 `_BT_NODE_BUILDERS` 字典（使用类路径字符串动态 import）
- [x] 5.2 在 QSBridge 中实现通用 `_build_node_sync(cfg, price_factor, descriptor_ids, dts)` 方法
- [x] 5.3 支持 `per_factor: True` 标记（为每个因子分别构造 calc 节点）
- [x] 5.4 删除 6 个独立 `_build_*_node_sync` 方法
- [x] 5.5 `_run_backtest_sync` 中的 if/elif 链替换为 `_build_node_sync` 调用

## 6. FactorService 模板消除

- [x] 6.1 新增 `_run_in_executor(self, func, *args, **kwargs)` 私有辅助方法
- [x] 6.2 `get_tables`、`get_factors`、`get_factor_data`、`get_factor_stats`、`get_factor_metadata`、`get_table_metadata` 等方法的 `loop.run_in_executor` 模板替换为 `_run_in_executor` 调用

## 7. 前端：全局因子池 Store 和组件

- [x] 7.1 创建 `stores/factorPoolStore.ts`：Zustand store，管理 items/PoolItem[]、selectedIds、addItems/removeItem/toggleSelect
- [x] 7.2 创建 `services/factorPool.ts`：前端 API 封装（addToPool、savePool、loadPool、listPools、deletePool）
- [x] 7.3 创建 `types/pool.ts`：PoolItem、FactorRef 统一类型定义
- [x] 7.4 创建 `components/FactorPoolPanel/index.tsx`：池中因子列表 + 选中/取消/移除操作
- [x] 7.5 创建 `components/FactorDiscover/index.tsx`：Drawer，FactorDB Tab + QSRegistry Tab，浏览并添加到池
- [x] 7.6 现有 `FactorSelector` 组件标记为 deprecated（后续删除）

## 8. 前端：Connection 模型适配

- [x] 8.1 `services/connection.ts` 中 Connection 接口新增 `qsid: string` 字段
- [x] 8.2 `pages/DataManager/index.tsx` 的连接 CRUD 适配新的 QSID 标识
- [x] 8.3 连接列表中展示 QSID（可复制）
- [x] 8.4 删除连接时先查 getImpact 获取影响范围 → Modal 展示因子表+直接因子+间接因子+影响总数 → 用户确认后提交级联删除

## 9. 前端：页面集成全局因子池

- [x] 9.1 `BacktestStudio` 页面 FactorSelector 移除，ModulePicker 改为从 store 读取因子
- [x] 9.2 `PortfolioOptimizer` 页面 SingleFactorPicker 替换为 PoolFactorPicker（从 store 读取）
- [x] 9.3 `ReportCenter` 页面 FactorRefSelector 替换为 PoolRefPicker，被测因子从 selectedIds 读取
- [x] 9.4 FactorPoolPanel 和 FactorDiscover 提升到 MainLayout 右侧全局滑出面板（hover 展开/固定）

## 10. 前端：页面拆分

- [x] 10.1 DataManager 拆分为 ConnectionPanel、FactorTreePanel、DataPreviewPanel 三个子组件（元数据合入 DataPreviewPanel）
- [x] 10.2 DataManager/index.tsx 负责布局编排和状态提升
- [x] 10.3 PortfolioOptimizer 拆分为 ObjectiveConfig、ConstraintsEditor、ResultView 三个子组件
- [x] 10.4 PortfolioOptimizer/index.tsx 负责布局编排
- [x] 10.5 ReportCenter 拆分为 ScenarioPicker、ReportList、ReportPreview 三个子组件
- [x] 10.6 ReportCenter/index.tsx 负责布局编排

## 11. 前端：Error Boundary

- [x] 11.1 创建 `components/ErrorBoundary/index.tsx` 类组件
- [x] 11.2 实现错误捕获 → Result 组件展示（错误标题 + 详情 + 重试按钮）
- [x] 11.3 App.tsx 中每个路由的 `<Suspense>` 外层包裹 `<ErrorBoundary>`

## 12. 测试和验证

- [x] 12.1 更新 `test_qs_bridge_registry.py`：验证声明式模块注册表与原有逻辑输出一致
- [x] 12.2 FactorService 各方法 `_run_in_executor` 替换后行为不变
- [x] 12.3 前端手动验证：创建连接 → QSID 展示 → 切页面 → 池中因子保持
- [x] 12.4 前端手动验证：保存池子 → 刷新页面 → 加载池子 → 因子恢复
- [x] 12.5 前端手动验证：Error Boundary 对页面崩溃的捕获和恢复
