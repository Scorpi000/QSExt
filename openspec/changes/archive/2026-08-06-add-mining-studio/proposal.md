## Why

QSWeb 目前缺少一个因子挖掘的统一管理界面。QSExt/GPFactor 模块已经提供了基于遗传规划（GP）的因子自动发现能力，但使用方式仍是手工编写 Python 脚本，缺乏可视化的任务配置、运行监控和结果管理。将其集成到 QSWeb 中，可以让用户通过 Web UI 配置挖掘参数、监控进化过程、查看和导出挖掘结果，显著降低使用门槛。

## What Changes

- 新增 `/mining` 页面（MiningStudio），提供因子挖掘任务的创建、运行、监控和结果浏览
- 新增后端挖掘框架注册机制，当前集成 GPFactor（GPLearner），架构预留未来其他框架扩展点
- 适应度评估复用 QuantStudio 现有回测框架（CalcOp + BTNode），通过配置组合多个评估模块，支持自定义 transform 脚本将回测结果整合为标量适应度
- 任务持久化到 workspace 目录，结果包含 Hall of Fame、适应度进化曲线和因子树 DAG 数据
- 因子树可视化复用 React Flow（与因子工作台 DAGViewer 一致）
- 挖掘结果可导出为 FactorDef 因子定义脚本，形成"挖掘 → 评估 → 导出 → 回测验证"闭环
- 复用现有 TaskManager + WebSocket 机制实现异步任务进度推送

## Capabilities

### New Capabilities

- `mining-studio`: 因子挖掘管理页面，包含框架选择、任务配置、运行监控、结果浏览和因子导出

### Modified Capabilities

（无）

## Impact

- **新增文件**：`QSWeb/frontend/src/pages/MiningStudio/index.tsx`、`QSWeb/frontend/src/services/mining.ts`、`QSWeb/backend/app/api/mining.py`、`QSWeb/backend/app/models/mining.py`、`QSWeb/backend/app/services/mining_service.py`
- **修改文件**：`QSWeb/frontend/src/App.tsx`（路由）、`QSWeb/frontend/src/components/Layout/MainLayout.tsx`（侧边栏菜单）、`QSWeb/backend/app/api/__init__.py`（注册路由）、`QSWeb/backend/app/core/config.py`（mining 配置读取）
- **配置文件**：`~/QuantStudioConfig/QSWebConfig.yaml` 新增 `mining` 节
- **无需修改**：`QSExt/GPFactor/GPLearn.py`（直接 import 使用）
