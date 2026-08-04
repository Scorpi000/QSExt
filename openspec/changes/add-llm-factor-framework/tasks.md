## 1. 后端模型层多态化

- [x] 1.1 `QSWeb/backend/app/models/mining.py` — `SubmitRunRequest.config` 改为 `Dict[str, Any]`；`RunResult` 新增 `framework` 和 `data` 字段，旧字段标记 deprecated 但保留写入
- [x] 1.2 `QSWeb/backend/app/models/mining.py` — 新增 `LLMFactorRunConfig`（Pydantic 模型，用于校验 LLMFactor 配置）
- [x] 1.3 `QSWeb/backend/app/models/mining.py` — 新增 `RunLogResponse`、`EvalMetricsResponse` 模型

## 2. 后端 Service 层 — LLMFactor 框架

- [x] 2.1 `QSWeb/backend/app/services/mining_service.py` — `list_frameworks()` 注册 `llm_factor` 条目
- [x] 2.2 `QSWeb/backend/app/services/mining_service.py` — 新增 `_llm_factor_config_schema()` 返回配置模板
- [x] 2.3 `QSWeb/backend/app/services/mining_service.py` — `get_framework_config()` 支持 `llm_factor`
- [x] 2.4 `QSWeb/backend/app/services/mining_service.py` — `submit_run()` 按 `framework` 分发：`gp` → 现有逻辑，`llm_factor` → `_execute_llm_factor_run()`
- [x] 2.5 `QSWeb/backend/app/services/mining_service.py` — 新增 `_execute_llm_factor_run()`：构建命令行、`asyncio.create_subprocess_exec`、stdout 双路处理（逐行写日志文件 + 解析阶段标记 → `task_manager.update_progress()`）、`proc.wait()` 后扫描 FM_* 目录提取结果
- [x] 2.6 `QSWeb/backend/app/services/mining_service.py` — `submit_run()` 中 llm_factor 分支通过 `task_manager.submit(name=..., coro_or_func=_execute_llm_factor_run(...))` 提交
- [x] 2.7 `QSWeb/backend/app/services/mining_service.py` — 在 `TaskManager` 增加 `on_cancel` 回调钩子，LLMFactor 注册 `proc.kill()`；`delete_task()` 调用 `task_manager.cancel()` 统一停止

## 3. 后端 API 路由 — 日志与评测指标

- [x] 3.1 `QSWeb/backend/app/api/mining.py` — 新增 `GET /mining/tasks/{task_id}/runs/{run_id}/log` 端点（offset + tail 参数）
- [x] 3.2 `QSWeb/backend/app/api/mining.py` — 新增 `GET /mining/tasks/{task_id}/runs/{run_id}/eval-metrics` 端点

## 4. 后端配置

- [x] 4.1 `QSWeb/backend/app/core/config.py` — `_default_mining().frameworks` 增加 `llm_factor` 默认配置

## 5. 前端 Service 层

- [x] 5.1 `QSWeb/frontend/src/services/mining.ts` — 新增 LLMFactor 类型定义（`LLMFactorRunConfig`、`RunLogResponse`、`EvalMetricsResponse`）
- [x] 5.2 `QSWeb/frontend/src/services/mining.ts` — 新增 API 调用（`getRunLog`、`getEvalMetrics`）

## 6. 前端组件 — LogViewer

- [x] 6.1 新建 `QSWeb/frontend/src/components/LogViewer/index.tsx`
  - 深色终端风格（黑底绿字，等宽字体）
  - 运行中每 2s 轮询增量日志
  - 自动滚到底部（用户手动上滚时暂停自动滚动）
  - 关键词搜索/高亮
  - 进程结束后显示 "进程已结束" 提示并停止轮询

## 7. 前端组件 — EvalMetrics

- [x] 7.1 新建 `QSWeb/frontend/src/components/EvalMetrics/index.tsx`
  - 表格：排名、因子名称、状态、IC Mean、IC IR、Rank IC、Sharpe、最大回撤
  - 列排序
  - 指标值颜色编码（绿→红渐变）
  - 运行中每 5s 轮询更新

## 8. 前端页面 — MiningStudio 框架感知

- [x] 8.1 `QSWeb/frontend/src/pages/MiningStudio/index.tsx` — `handleNewTask()` 增加框架选择步骤（GP / LLM）
- [x] 8.2 `QSWeb/frontend/src/pages/MiningStudio/index.tsx` — 根据 `framework` 动态渲染配置表单（`config_schema.fields` → 表单控件）
- [x] 8.3 `QSWeb/frontend/src/pages/MiningStudio/index.tsx` — 根据 `framework` 切换结果 Tab（GP: 结果+因子树 / LLMFactor: 日志+评测指标）
- [x] 8.4 `QSWeb/frontend/src/pages/MiningStudio/index.tsx` — `handleSubmit()` 按框架构建不同的 config 对象
- [x] 8.5 `QSWeb/frontend/src/pages/MiningStudio/index.tsx` — 任务列表项增加框架标签（Tag 组件，蓝色 GP / 绿色 LLM）
- [x] 8.6 `QSWeb/frontend/src/pages/MiningStudio/index.tsx` — LLMFactor 任务运行时通过 WebSocket 接收进度（阶段描述），自动切换到结果区

## 9. 集成验证

- [x] 9.1 启动 QSWeb 后端，验证 `GET /mining/frameworks` 返回 gp + llm_factor
- [x] 9.2 通过 API 提交 LLMFactor 挖掘任务，验证子进程启动、status.json 写入、日志文件生成
- [x] 9.3 验证前端动态表单渲染和框架切换
- [x] 9.4 验证 LogViewer 实时日志轮询
- [x] 9.5 验证进程停止和数据清理（删除任务）
