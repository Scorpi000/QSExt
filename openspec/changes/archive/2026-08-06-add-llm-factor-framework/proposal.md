## Why

QSWeb 当前的因子挖掘页面（MiningStudio）仅集成了遗传规划（GP）框架。QSExt/LLMFactor 模块是刚迁入的新因子挖掘框架，基于 LLM 驱动的"假设生成 → 因子开发 → 因子评测"循环，与 GP 的表达式演化范式互补。它目前只有 Streamlit 管理界面（`QSExt/LLMFactor/web/`），缺乏与 QSWeb 的集成。将其作为第二个挖掘框架注册到 MiningStudio 中，可以让用户在同一界面中按需选择挖掘策略，复用已有的任务管理、进度推送和结果展示基础设施。

## What Changes

- **后端**：在 `MiningService` 中注册 `llm_factor` 框架；实现子进程执行模型（通过 `subprocess.Popen` 运行 `QSExt.LLMFactor.scripts.run_pipeline`）；新增实时日志流和评测指标提取 API
- **前端**：MiningStudio 页面按框架切换表单和结果面板；LLMFactor 配置表单（研究方向、市场、频率、模式）；新增实时日志查看器组件；新增评测指标对比组件
- **模型层**：`SubmitRunRequest.config` 从强类型 `GPRunConfig` 改为 `Dict[str, Any]`，各框架自行解析；`RunResult` 支持多态 `data` 字段
- **无 Streamlit 依赖**：LLMFactor 的 Streamlit web 保留独立使用，QSWeb 集成不依赖它

## Capabilities

### New Capabilities

- `llm-factor-framework`: LLMFactor 作为 MiningStudio 的第二挖掘框架，提供研究方向配置、子进程执行、实时日志监控、评测指标对比

### Modified Capabilities

- `mining-studio`: 框架选择器驱动动态表单渲染和结果面板切换；任务提交接口接受多态配置

## Impact

- **修改文件**：`QSWeb/backend/app/models/mining.py`（多态配置/结果）、`QSWeb/backend/app/services/mining_service.py`（框架注册+LLMFactor执行）、`QSWeb/backend/app/api/mining.py`（日志/评测指标端点）、`QSWeb/backend/app/core/config.py`（llm_factor默认配置）、`QSWeb/frontend/src/services/mining.ts`（新类型+API）、`QSWeb/frontend/src/pages/MiningStudio/index.tsx`（框架感知表单/结果面板）
- **新增文件**：`QSWeb/frontend/src/components/LogViewer/index.tsx`（实时日志流）、`QSWeb/frontend/src/components/EvalMetrics/index.tsx`（评测指标对比）
- **无需修改**：`QSExt/LLMFactor/` 模块代码（直接通过 subprocess 使用）
