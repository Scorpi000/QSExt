## Context

QSWeb 当前有两条平行的因子库管理路径：（1）QSWebConfig.json 文件存储连接配置，ConnectionService 做 CRUD；（2）QSGraphDB.registerFactorDB 将 FactorDB 实例写入 Neo4j，供 reconstructFactor 使用。两条路径互不知晓，需要 QSBridge.register_factor_dbs() 手动同步。因子选择在六个页面各自独立实现，选中的因子无法跨页面共享。

QuantStudio 的 `__QS_Object__.serialize()` 已支持完整的参数加密序列化，QSGraphDB 的 `_autoBuildFactorDB` 已有从 ConnectionJSON 重建 FactorDB 实例的完整能力——基础设施已就绪，只缺上层对接。

## Goals / Non-Goals

**Goals:**
- 统一因子库连接管理到 QSGraphDB，消除 QSWebConfig.json 的 factor_dbs 节
- 以 QSID 为因子库的唯一标识，取代随机 UUID 和 Name
- 建立跨页面共享的全局因子池，支持手动添加、移除和可选持久化
- 消除 QSBridge 中的重复回测节点构造代码
- 拆分前端三个巨型页面，添加 Error Boundary 防护

**Non-Goals:**
- 不改动 QuantStudio Core 的 FactorDB 接口
- 不改变 QSWebConfig.json 中非连接配置节（backtest、section_id_sources 等）
- 不在本变更中实现因子池的多人协作/共享功能
- 不引入新的外部依赖（React Query 等留待后续）

## Decisions

### D1: QSGraphDB FactorDB API 设计

**registerFactorDB MERGE 键从 Name → QSID**

当前：
```cypher
MERGE (d:`因子库` {Name: $name})
```

改为：
```cypher
MERGE (d:`因子库` {QSID: $qsid})
```

`fdb.QSID` 由 `__QS_Object__` 基类基于类名+参数自动生成，相同类型相同参数产生相同 QSID，天然去重。

**新增四个公共方法**（配合已有 `_autoBuildFactorDB` 形成完整 CRUD）：

| 方法 | 说明 |
|------|------|
| `listFactorDBs()` | MATCH 所有 `因子库` 节点，返回 `[{QSID, Name, DBType, ...}]` |
| `getFactorDB(qsid)` | 按 QSID 查询单条 + `_autoBuildFactorDB` 重建实例 |
| `deleteFactorDB(qsid)` | 删除节点 + 清理 `_FactorDBRegistry` |
| `reconstructFactorDB(qsid)` | `getFactorDB` + `connect()` 的便捷包装 |

**备选方案**：继续用 Name 作键 + 用户手动去重。拒绝原因：Name 是显示名，用户可能给不同物理库取相同名；QSID 基于参数自动生成，保证同配置唯一。

**重复 QSID 处理**：`create_connection` 时，先通过 QSID 检查图中是否已有相同节点。若已存在，拒绝创建并返回错误，前端弹出消息提示"已存在相同配置的因子库连接"，阻止用户重复创建。

### D2: ConnectionService 重写

```
当前: ConnectionService → QSWebConfig.json (factor_dbs 节)
改为: ConnectionService → QSGraphDB (因子库 节点)
```

ConnectionService 的公开接口保持不变（`list_connections`、`create_connection`、`update_connection`、`delete_connection`、`test_connection`），但实现改为对 QSGraphDB 的薄封装：

- `list_connections()` → `gdb.listFactorDBs()`，返回格式保持 `ConnectionResponse`
- `create_connection(req)` → 先用参数 connect FactorDB → 再 `gdb.registerFactorDB(fdb)` → 返回含 QSID 的响应
- `update_connection(qsid, req)` → 用新参数 connect → 比较新旧 QSID：若相同则直接 `gdb.registerFactorDB` 更新属性；若不同则先检查新 QSID 冲突 → 查询旧 QSID 影响范围 → 返回给前端确认 → 确认后迁移因子表和因子关系到新节点 + 删除旧节点 + 更新池中 conn_id 引用
- `delete_connection(qsid)` → 先调用 `gdb.getImpactAnalysis(qsid)` 查询受影响的因子表和因子 → 返回影响范围给前端 → 用户确认后 `gdb.deleteFactorDB(qsid)` 级联删除所有依赖节点 + `factor_service.disconnect(qsid)` + 清理全局因子池中的对应 PoolItem
- `get_impact(qsid)` → 新接口，Cypher 查询该因子库下直接因子（`(因子)-[:属于因子表]->(因子表)-[:属于因子库]->(因子库)`），再沿 `(因子)-[:依赖*1..]->` 递归查找所有间接依赖的衍生因子，返回完整的影响范围（直接+间接），供前端确认
- `test_connection(req)` → 保持现有瞬时连接测试逻辑（不改）

**ID 字段过渡**：前端 `ConnectionResponse.id` 从 UUID 改为 QSID。向后兼容：迁移脚本将旧连接的 `id` 作为初始 `Name`，新 QSID 由 FactorDB 实例自动生成。

**配置迁移**：
```
QSWebConfig.json 中 factor_dbs 节
  → 遍历每条连接
  → 按 db_type + args 创建 FactorDB 实例并 connect
  → gdb.registerFactorDB(fdb)
  → 写入完成后删除 QSWebConfig.json 中的 factor_dbs 节
```

迁移脚本作为独立 CLI 工具 `python -m QSWeb.scripts.migrate_connections` 提供。

### D3: 全局因子池架构

```
┌─────────────────────────────────────────────────────────────┐
│ MainLayout（全局）                                           │
│                                                              │
│  ┌──────────────────────────────┐  ┌──────────────────────┐ │
│  │ 页面内容区                    │  │ 右侧因子池面板        │ │
│  │                              │  │ (hover 展开 / 📌 固定) │ │
│  │  BacktestStudio              │  │                      │ │
│  │  PortfolioOptimizer          │  │  FactorPoolPanel     │ │
│  │  ReportCenter                │  │  [💾 保存] [📂 加载]  │ │
│  │  ...                         │  │  [+ 添加因子到池]     │ │
│  │                              │  │                      │ │
│  └──────────────────────────────┘  └──────────────────────┘ │
│                                                              │
│  FactorDiscover (Drawer)  ← 点击"添加因子"按钮打开          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ [FactorDB Tab] [QSRegistry Tab]                     │    │
│  │ 连接 ▾ → 表 ▾ → 因子列表 → [加入池]                  │    │
│  │ QSRegistry: [关键词/语义] 搜索 → 结果列表 → [加入池]   │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘

前端 (Zustand store) — 跨页面共享

factorPoolStore:
  items: PoolItem[]       ← 池中因子
  selectedIds: string[]   ← 当前选中的因子 ID

  addItems(refs)   — 前端直接操作 store
  removeItem(id)
  toggleSelect(id)
  savePool(name)   → POST /api/pool/save    (持久化到图库)
  loadPool(name)   → GET  /api/pool/load/{name}
  listPools()      → GET  /api/pool/list
───────────────────────────────────────────────────────────────
后端 FactorPoolService

resolve(factorRefs) → {pool_id → Factor 对象}  (双源解析 + 内存缓存)
getStats(qsid)      → FactorStats (懒加载)

savePool(name, items) → resolve → storeFactors(factors) → saveFactorPool(name, qsids):
  MERGE (p:`因子池` {Name: $name})
  MATCH (f:`因子` {QSID: qsid})
  MERGE (p)-[:`包含`]->(f)

loadPool(name) → loadFactorPool(name) → 遍历 (因子池)-[:包含]->(因子) 还原 PoolItem[]
listPools()   → MATCH (p:`因子池`) OPTIONAL MATCH (p)-[:包含]->(f) RETURN p, count(f)
```

**PoolItem 统一格式**：
```typescript
interface PoolItem {
  id: string         // 池内唯一 ID = `${source}:${qsid}`
  qsid: string       // 因子 QSID
  source: "db" | "registry"
  label: string      // 显示名
  ref: {             // 解析所需信息
    conn_id?: string
    table_name?: string
    factor_name?: string
  }
  stats?: FactorStats
}
```

**持久化策略**：用户显式操作时才持久化（点击"保存池子"按钮），不自动保存。加载时从图中读取 `[:包含]` 关系恢复因子列表，再通过 `reconstructFactor` 或 FactorDB 路径解析。

### D4: FactorSelector 组件替换

原有 `FactorSelector` 同时负责「发现因子」和「管理已选」，已删除。替换为：

- **FactorPoolPanel**：展示池中所有因子，支持选中/取消、移除操作。位于 MainLayout 右侧滑出面板，所有页面可见。
- **FactorDiscover**：Drawer 弹窗，FactorDB Tab + QSRegistry Tab（关键词/语义搜索），浏览并「添加到池」。由 MainLayout 中 FactorPoolPanel 的"添加"按钮和右侧面板的"+"按钮触发。

各页面不再内嵌独立的因子选择组件，而是通过 `useFactorPoolStore` 读取池中数据：
- **BacktestStudio ModulePicker** → 从 store 读取因子列表构建模块配置
- **PortfolioOptimizer PoolFactorPicker** → 从 store 读取因子列表供下拉选择
- **ReportCenter** → 从 store 读取 `selectedIds` 生成报告因子列表

### D5: QSBridge 重构

当前 `_run_backtest_sync` 中的 if/elif 链替换为声明式模块定义 + 通用构造器。

`_BT_NODE_BUILDERS` 字典定义在 `QSWeb/backend/app/services/qs_bridge.py`，使用类路径字符串（`"calc_module"` + `"calc_class"`）动态 import，避免模块级循环引用：

```python
_BT_NODE_BUILDERS = {
    "ic": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.IC",
        "calc_class": "CalcIC",
        "node_module": "QuantStudio.BackTest.SectionFactor.IC",
        "node_class": "IC",
        "requires_price": True,
        "calc_params": ["lookback", "period_lookback", "corr_method"],
        "node_params_map": {"RollingAvgPeriod": "rolling_avg_period"},
        "default_node_params": {"GenReport": False},
    },
    "ic_decay": {
        ...
        "per_factor": True,    # 标记：每个因子分别构造 calc
    },
    ...
}

def _build_node_sync(self, cfg, price_factor, descriptor_ids, dts):
    builder = _BT_NODE_BUILDERS[cfg.module_key]
    # 动态 import calc/node 类
    calc_cls = getattr(importlib.import_module(builder["calc_module"]), builder["calc_class"])
    ...
```

各 `_build_*_node_sync` 方法（~300 行）移除，`_run_backtest_sync` 的 if/elif 链塌缩为一行 `_build_node_sync` 调用。

### D6: 前端页面拆分

**DataManager (1081→3 子组件)**：
- `ConnectionPanel.tsx` — 连接 CRUD 表单 + 列表（含新建/编辑弹窗 + 删除影响确认）
- `FactorTreePanel.tsx` — 因子树（FactorTree 组件 + 右键菜单）
- `DataPreviewPanel.tsx` — 数据预览表格 + 日期/ID 筛选 + 元数据编辑器（MetadataEditor）
- `DataManager/index.tsx` — 布局编排 + 状态提升

**PortfolioOptimizer (1014→3 子组件)**：
- `ObjectiveConfig.tsx` — 求解器选择 + 目标类型 + 动态参数表单
- `ConstraintsEditor.tsx` — 约束列表 + 添加/编辑弹窗
- `ResultView.tsx` — 状态卡片 + 权重分布图 + 风险分解图
- `PortfolioOptimizer/index.tsx` — 布局编排 + PoolFactorPicker（从全局因子池选取预期收益/Mask/基准）

**ReportCenter (864→3 子组件)**：
- `ScenarioPicker.tsx` — 场景选择 + 参数配置 + PoolRefPicker（从池选取价格/Mask/行业/权重）
- `ReportList.tsx` — 报告表格 + 筛选 + 预览/下载/注册/删除操作
- `ReportPreview.tsx` — 报告预览弹窗（HTML iframe / Markdown 纯文本）
- `ReportCenter/index.tsx` — 布局编排 + 从 store 读取 selectedIds 生成因子列表

### D7: Error Boundary

```tsx
// components/ErrorBoundary.tsx
class ErrorBoundary extends React.Component<...> {
  state = { hasError: false, error: null }
  static getDerivedStateFromError(error) { return { hasError: true, error } }
  render() {
    if (this.state.hasError)
      return <Result status="error" title="页面出错" subTitle={...} extra={<Button onClick={reset}>重试</Button>} />
    return this.props.children
  }
}
```

App.tsx 中每个 `<Route>` 的 `<Suspense>` 外面包一层 `<ErrorBoundary>`。

### D8: FactorService 模板消除

在 FactorService 中新增一个私有方法：
```python
async def _run_in_executor(self, func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
```

各公开方法从 8 行模板缩减为 2 行。注意不在装饰器层面实现（Python 的 async/sync 混合装饰器有隐式复杂度）。

## Risks / Trade-offs

| 风险 | 应对 |
|------|------|
| QSGraphDB 不可用时 ConnectionService 完全不可用 | ConnectionService 初始化时检测连接；新增 `/api/connections/health` 端点；前端显示连接状态 |
| QSID 冲突：两个不同物理库刚好参数相同 | 极低概率（QSID 基于类路径+参数 hash）；创建时检测 QSID 重复并直接拒绝；更新时允许覆盖自身的 QSID 节点 |
| 因子池持久化后恢复时对应 FactorDB 已不可用 | 恢复时标记不可解析的因子为 "stale"，显示为灰色但不阻塞其他因子 |
| 旧 QSWebConfig.json 中有连接但 Neo4j 不可用 → 迁移失败 | 迁移脚本先检测 Neo4j 可达性；提供 `--dry-run` 模式预览变更 |
| QSBridge 声明式重构引入回归 | 保留现有 `BACKTEST_MODULE_REGISTRY` 中的参数定义不变，仅改变节点构造逻辑；利用已有测试 `test_qs_bridge_registry.py` 验证 |

## Migration Plan

1. **Phase 1: QSGraphDB 增强** — 无破坏性，仅新增 API
2. **Phase 2: 迁移脚本** — 用户手动执行 `python -m QSWeb.scripts.migrate_connections`，将 QSWebConfig.json → Neo4j
3. **Phase 3: ConnectionService 切换** — 切换读写路径；前端自动适配新的 QSID 字段
4. **回滚**：恢复 QSWebConfig.json 中的 `factor_dbs` 节即可（迁移脚本执行前自动备份）；ConnectionService 代码回退到上一版本
