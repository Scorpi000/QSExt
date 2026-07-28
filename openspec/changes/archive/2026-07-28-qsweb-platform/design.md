## Context

QuantStudio 是一个 Python 量化投资框架，提供因子管理、回测、风险建模和组合优化等功能。现有交互方式为 Jupyter Notebook（ipywidgets）和 PyQt 桌面 GUI，存在布局受限、无法远程访问、不支持团队协作等问题。

QSWeb 在 `QSWeb/` 目录下构建前后端分离的 Web 应用。Phase 1（数据管理）已基本实现，包括连接 CRUD、因子树浏览、数据预览和元数据编辑。

## Goals / Non-Goals

**Goals:**
- 覆盖因子管理、回测、风险建模、组合优化、报告生成五大核心功能
- 支持小团队远程协作使用
- 前后端分离，清晰的 API 边界，便于长期维护
- 复用 QuantStudio 现有核心 API，不重写业务逻辑

**Non-Goals:**
- 不替代现有 Notebook GUI 和 QtGUI（三者并存）
- 不实现实时盘中监控
- 不支持大规模并发用户（面向小团队，非 SaaS）
- 不在本阶段实现移动端适配

## Decisions

### D1: 技术栈

| 层 | 技术 | 理由 |
|---|------|------|
| 前端 | React + TypeScript | 生态成熟，组件库丰富，适合复杂交互 |
| UI 组件 | Ant Design 5 | 企业级组件库，表格/表单/图表支持完善 |
| 图表 | ECharts + Plotly | ECharts 做仪表盘，Plotly 做金融分析（与现有 Python 代码复用） |
| DAG 可视化 | React Flow | 比 ipycytoscape 更强大，支持自定义节点/边 |
| 后端 | FastAPI | Python 原生，异步支持好，自动生成 OpenAPI 文档 |
| 前端状态管理 | Zustand | 轻量，适合中等复杂度应用 |
| 部署 | Docker Compose | 小团队自部署，一键启动 |

备选方案评估：
- Streamlit/Dash：开发快但复杂交互支持差，不适合全功能平台
- Jupyter 扩展：受 widget 布局模型限制，现有 Notebook GUI 已遇瓶颈
- Electron：安装部署复杂，不适合团队协作

### D2: 分层架构

```
Frontend (React)  →  API Layer (FastAPI)  →  Service Layer (QS Bridge)  →  QuantStudio Core
```

- **表现层**：React 页面组件 + 通用组件 + Zustand 状态管理
- **API 层**：RESTful 路由 + 参数验证 + WebSocket 连接管理
- **服务层**：封装 QuantStudio API 调用，业务逻辑处理，数据转换
- **数据层**：Neo4j（计算图元数据）、ClickHouse/HDF5/MongoDB（因子数据）、Redis（缓存/任务队列）

### D3: 动态表单生成

QuantStudio 的 `QSArgs` 已基于 Pydantic BaseModel 实现，字段使用 `Field(title=..., frozen=..., ge=...)` 定义约束，支持 `Literal`、`Optional`、`List`、`Dict`、`Tuple` 等标准 Python 类型注解。

方案：后端利用 Pydantic 的 `model_json_schema()` 方法直接生成 JSON Schema（无需手写转换），前端使用 `@rjsf/antd`（react-jsonschema-form）自动渲染表单。

| Pydantic 类型注解 | JSON Schema | 前端组件 |
|---|---|---|
| `int`（含 `Field(ge=..., le=...)`） | `{"type": "integer", "minimum": ..., "maximum": ...}` | InputNumber |
| `float` | `{"type": "number"}` | InputNumber |
| `str` | `{"type": "string"}` | Input |
| `bool` | `{"type": "boolean"}` | Switch |
| `Literal["a", "b"]` | `{"type": "string", "enum": ["a", "b"]}` | Select |
| `List[str]` / `List[Enum]` | `{"type": "array", "items": {...}}` | MultiSelect |
| `Dict[str, Any]` | `{"type": "object"}` | JSON Editor |
| `Optional[T]` | `{"anyOf": [{"type": ...}, {"type": "null"}]}` | 可选输入 |

注意：`frozen=True` 的字段为只读参数，前端应渲染为禁用状态；`exclude=True` 的字段不展示在表单中。

### D4: 异步任务处理

回测计算可能耗时数秒到数分钟，同步请求会超时。

方案：`TaskManager` 管理异步任务，通过 WebSocket 推送进度更新。
- 前端提交任务后获得 `task_id`
- 通过 WebSocket 或轮询获取进度
- 完成后通过 REST API 获取结果

### D11: 模块化回测架构

回测工作台采用**模块注册表 + 可组合运行**的设计，对齐 QuantStudio 的 `BTReport(bt_node_list=[...])` 模式。

#### 因子来源双通道

```
QSRegistry (Neo4j) ──→ QSGraphDB.searchFactors() → reconstructFactor()
                                                         ↓
FactorDB (数据连接) ─→ FactorTable.getFactor() ──→ Factor 对象
                                                         ↓
                                              CalcIC / MultiPortfolio / ...
                                                         ↓
                                                  Engine.run()
```

- **QSRegistry 路径**：适用于已注册到图数据库的因子，通过 `QSGraphDB.reconstructFactor(qsid)` 从图元数据还原完整 Factor 对象图（含算子链和依赖）
- **FactorDB 路径**：适用于因子库中的原始因子，通过 `ft.getFactor(name)` 获取 Factor 对象
- **`reconstructFactor` 前置条件**：对应的 FactorDB 实例需通过 `QSGraphDB.registerFactorDB(name, fdb)` 注册。QSWeb 的 `FactorService` 中已连接的 FactorDB 实例可复用

#### 模块注册表

在后端维护声明式的模块注册表 `BACKTEST_MODULE_REGISTRY`，描述每个 QuantStudio 回测模块的元信息：

```python
BACKTEST_MODULE_REGISTRY = {
    "ic": {
        "name": "IC 分析", "category": "SectionFactor",
        "qs_class": "IC", "qs_operator": "CalcIC",
        "import_path": "QuantStudio.BackTest.SectionFactor.IC",
        "params": [
            {"name": "corr_method", "type": "select", "options": ["spearman", "pearson"], ...},
            {"name": "lookback", "type": "int", "default": 1, ...},
            ...
        ],
        "requires_price": True,
        "requires_descriptor_ids": True,
    },
    "multi_portfolio": {...},
    "factor_turnover": {...},
    "strategy": {...},
}
```

前端通过 `GET /api/backtest/modules` 获取模块列表，根据每个模块的 `params` 定义动态渲染配置表单（复用 QSArgs → JSON Schema → `@rjsf/antd` 的动态表单方案）。

#### 用户流程

```
1. 选择因子（多选，双源） + 价格因子 + 截面 ID + 日期范围
2. 从模块列表中选择回测模块 → 弹出配置对话框 → 加入待运行列表
3. 同一模块可重复添加，每次配置不同的因子和参数
4. [▶ 全部运行] → 后端构造 BTReport(bt_node_list) → Engine.run()
5. 结果以树结构返回，前端用 Tree 组件展示
```

#### 结果树

Engine.run() 的输出是嵌套 dict，递归提取为：

| type | 含义 | 前端渲染 |
|------|------|---------|
| `branch` | 嵌套 dict 节点 | Tree 可展开节点 |
| `series` | Series | Plotly 折线图 + Ant Table 切换 |
| `dataframe` | DataFrame | Ant Table（排序/筛选/virtual scroll） |
| `scalar` | 字符串/数字 | Statistic 或纯文本 |

用户点击树节点选中叶子，右侧面板展示对应内容。

#### QSBridge 桥接层

新增 `app/services/qs_bridge.py`，职责：
- FactorDB 自动注册：将 `FactorService` 中已连接的 FactorDB 实例注册到 `QSGraphDB`
- 因子解析：统一处理双源因子引用 → Factor 对象
- 节点构造：根据模块配置构造 QuantStudio 原生 BTNode
- 引擎执行：在 `run_in_executor` 中执行 `Engine.run()`
- 结果转换：BTNode 输出 → 结果树 JSON

### D5: DAG 可视化

使用 React Flow 替代 ipycytoscape，支持自定义节点类型（因子/因子表/因子库）、拖拽、缩放、自动布局（dagre 算法）。

节点类型着色：

| 节点类型 | 颜色 | 说明 |
|---|---|---|
| 因子库 (FactorDB) | 黄色 | 数据库连接 |
| 因子表 (FactorTable) | 浅绿 | 因子集合 |
| 原子因子 (AtomicFactor) | 天蓝 | 直接从数据源读取 |
| 衍生因子 (DerivativeFactor) | 钢蓝 | 由算子计算得出 |

### D6: 数据预览性能

因子数据可能包含数百万行。方案：后端分页查询 + 前端虚拟滚动（Ant Design 5 Table virtual 模式）。

### D7: 状态管理

前端使用 Zustand 管理跨页面共享状态（连接列表、当前选中因子等），后端使用 Redis 缓存频繁查询的因子元数据。

### D8: 错误处理

统一错误响应格式 `{code, message, detail}`，后端定义 `APIError` 基类 + 全局异常处理器，前端 Axios 拦截器统一展示错误消息。

### D9: 项目结构

```
QSWeb/
├── frontend/
│   ├── src/
│   │   ├── pages/          # DataManager, FactorWorkbench, BacktestStudio, ...
│   │   ├── components/     # FactorTree, DAGViewer, DataTable, ArgForm, ...
│   │   ├── services/       # API 调用封装
│   │   ├── stores/         # Zustand stores
│   │   ├── hooks/          # useTaskProgress, useWebSocket, ...
│   │   ├── types/          # TypeScript 类型定义
│   │   └── utils/          # 工具函数
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── app/
│   │   ├── api/            # 路由（factors, backtest, risk, portfolio, report）
│   │   ├── services/       # 业务服务（FactorService, BacktestService, ...）
│   │   ├── models/         # Pydantic 数据模型
│   │   ├── tasks/          # 异步任务
│   │   ├── core/           # 配置、异常、安全
│   │   └── utils/          # dag_layout, data_converter
│   ├── tests/
│   └── requirements.txt
└── docker-compose.yml
```

### D10: 与现有系统的关系

| 现有组件 | QSWeb 关系 |
|---|---|
| `QSExt/GUI/Notebook/` | 保留，用于快速原型和 Jupyter 用户 |
| `QSExt/GUI/QtGUI/` | 保留，用于桌面用户 |
| `QSExt/QSRegistry/` | Web GUI 后端直接调用 QSGraphDB API（因子搜索、DAG 数据、注册） |
| `QSExt/ReportGenerator/` | Web GUI 复用组件库和渲染器 |
| `QuantStudio/Factor/` | Web GUI 通过 Service 层桥接 FactorDB API |

## Risks / Trade-offs

| 风险 | 影响 | 应对 |
|---|---|---|
| QuantStudio 同步 API 阻塞 FastAPI event loop | 并发请求卡死 | 使用 `run_in_executor` 包装同步调用 |
| DAG 渲染节点过多时性能差 | 浏览器卡顿 | 限制可见节点数量，使用 Web Worker 布局 |
| 长时间计算任务超时 | 功能不可用 | 异步任务 + WebSocket 进度推送 |
| Redis / PostgreSQL 引入增加部署复杂度 | 运维负担 | Docker Compose 一键编排；小规模部署可用内存缓存替代 Redis |
| 前端状态管理跨页面数据一致性 | 用户体验 | Zustand 单一 store，避免重复状态 |
