## 1. 后端配置与模型

- [x] 1.1 在 `QSWeb/backend/app/core/config.py` 新增 `mining` 配置读取（workspace、frameworks）
- [x] 1.2 创建 `QSWeb/backend/app/models/mining.py`（MiningTask、MiningRun、RunConfig、RunResult、EvalConfig 等 Pydantic 模型，任务含多个 run）

## 2. 后端 Service 层

- [x] 2.1 创建 `QSWeb/backend/app/services/mining_service.py`
  - 挖掘框架注册表 `MINING_FRAMEWORKS`
  - `list_frameworks()`、`get_framework_config()`
  - `create_task()`：创建任务，初始化 `task.json`
  - `run_mining()`：提交一次运行，新建 run 子目录，异步执行
  - `continue_mining()`：接续挖掘入口，从 checkpoint 恢复种群，创建新 run
  - `_build_fitness_fun()`：根据 eval 配置构造适应度函数（复用 BTNode 计算图 + transform）
  - `_run_gp_mining_sync()`：同步执行 GPLearner.evolve()
  - `_pn_to_dag()`：将 PN 表达式转为 React Flow DAG 格式
  - `_save_checkpoint()`：保存最终种群和适应度到 `checkpoint.pkl`
  - `_export_factors()`：通过 `QSExt.FactorDef.FactorScriptWriter.generate_script()` 将 Hall of Fame 导出为 `factors.py`
  - 任务持久化：读写 workspace 目录
  - 任务进度：通过 TaskManager 更新各代进度

## 3. 后端 API 路由

- [x] 3.1 创建 `QSWeb/backend/app/api/mining.py`
  - `GET /mining/frameworks` — 列出框架
  - `GET /mining/frameworks/{name}/config` — 框架配置模板
  - `POST /mining/tasks` — 创建任务
  - `POST /mining/tasks/{id}/run` — 提交初始挖掘运行
  - `POST /mining/tasks/{id}/continue` — 提交接续挖掘运行
  - `GET /mining/tasks` — 任务列表
  - `GET /mining/tasks/{id}` — 任务详情（含所有 run 摘要）
  - `GET /mining/tasks/{id}/runs/{run_id}/result` — 指定 run 的挖掘结果
  - `GET /mining/tasks/{id}/factor-tree/{index}` — 因子树 DAG
  - `DELETE /mining/tasks/{id}` — 删除任务
  - `POST /mining/tasks/{id}/export` — 导出 FactorDef 脚本到指定目录
- [x] 3.2 在 `QSWeb/backend/app/api/__init__.py` 注册 `mining_router`

## 4. 前端 Service 层

- [x] 4.1 创建 `QSWeb/frontend/src/services/mining.ts`（API 调用封装和类型定义）

## 5. 前端页面

- [x] 5.1 创建 `QSWeb/frontend/src/pages/MiningStudio/index.tsx`
  - 左侧任务列表（新建/切换/删除，已完成任务可接续）
  - 右侧配置 Tab（新建任务：框架选择 + 算子 + 终端因子 + GP 参数 + 评估模块；接续时锁定算子和终端因子）
  - 结果 Tab（Plotly 适应度曲线，多 run 拼接展示；Hall of Fame 表格含"导出到因子脚本目录"操作按钮）
  - 因子树 Tab（React Flow 渲染选中因子）
  - Run 历史选择器（切换查看各次 run 的结果）
  - 进度显示（复用 TaskProgress 组件）
- [x] 5.2 在 `QSWeb/frontend/src/App.tsx` 新增 `/mining` 路由和 MiningStudio 懒加载
- [x] 5.3 在 `QSWeb/frontend/src/components/Layout/MainLayout.tsx` 侧边栏菜单新增"因子挖掘"条目

## 6. 配置文件

- [x] 6.1 更新 `~/QuantStudioConfig/QSWebConfig.yaml` 新增 `mining` 节示例配置
