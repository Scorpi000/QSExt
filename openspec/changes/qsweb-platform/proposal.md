## Why

QuantStudio 目前的交互界面有两个：Jupyter Notebook（ipywidgets）和 PyQt 桌面 GUI。两者各有局限：
- Notebook GUI 受限于 widget 布局模型，复杂交互（拖拽、多面板、右键菜单）体验差
- PyQt 桌面端需要安装部署，不支持团队协作
- 两者都无法远程访问，限制了使用场景

QSWeb 旨在提供一个**基于浏览器的全功能量化研究平台**，覆盖因子管理、回测、风险建模、组合优化、报告生成等核心功能，服务于小团队协作场景。

## What Changes

在 `QSWeb/` 目录下构建完整的前后端分离 Web 应用：

**后端（FastAPI）**：桥接 QuantStudio 核心 API，提供 RESTful 接口 + WebSocket 进度推送
**前端（React + TypeScript + Ant Design）**：6 个功能模块的单页应用

Phase 1（数据管理）已基本实现，本次变更覆盖 Phase 2–5 的全部功能。

## Capabilities

### New Capabilities

- `factor-workbench`: 因子搜索（QSRegistry 关键词 + 语义）、DAG 可视化（React Flow）、衍生因子创建、动态表单（QSArgs → JSON Schema）
- `backtest-studio`: 截面因子测试（IC 分析、分位数组合、换手率）、策略回测、异步任务 + WebSocket 进度推送、回测结果展示与导出
- `risk-manager`: 风险库浏览、协方差矩阵热力图、多因子风险分解
- `portfolio-optimizer`: 优化目标配置（均值方差/风险预算/最大分散化）、约束条件编辑、CVXPY 求解、结果展示
- `report-center`: 报告生成（单因子分析等场景）、报告浏览与预览、报告注册到 QSRegistry

### Modified Capabilities

- `data-manager`: 已实现的 Phase 1 功能，需补充 Docker Compose 部署配置和测试

## Impact

- **新增代码**：后端 ~5 个 API 模块 + 5 个 Service 模块，前端 ~5 个页面 + 多个组件
- **依赖变更**：前端新增 reactflow、plotly.js、zustand、@rjsf/antd；后端新增 redis、websockets
- **QuantStudio 集成**：通过 Service 层桥接 FactorDB、BackTest、Risk、PortfolioConstructor 等核心 API
- **QSRegistry 集成**：因子搜索、DAG 数据、回测注册等依赖 Neo4j 图数据库
- **异步任务**：引入 TaskManager + WebSocket 处理长时间计算任务
- **部署**：Docker Compose 编排（frontend + backend + redis + postgres + neo4j）
