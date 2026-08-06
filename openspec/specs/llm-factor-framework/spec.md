# llm-factor-framework

## Purpose

定义 LLMFactor 因子挖掘框架的前后端接口规范，包括框架注册、配置表单、任务执行、实时日志流、评测指标和前端页面行为。

## Requirements

### Requirement: 框架列表包含 LLMFactor

`GET /mining/frameworks` 的响应中，除 `gp` 外增加 `llm_factor` 条目：

```json
{
  "key": "llm_factor",
  "name": "LLM 因子挖掘",
  "description": "基于 LLM 驱动的假设生成→因子开发→因子评测循环",
  "config_schema": { "fields": [...], "defaults": {...} }
}
```

#### Scenario: 获取 LLMFactor 框架配置模板

- **WHEN** 前端请求 `GET /mining/frameworks/llm_factor/config`
- **THEN** 返回 `config_schema`，包含所有可配置字段的类型、标签、选项、默认值

### Requirement: 配置表单字段定义

LLMFactor 配置表单 SHALL 包含以下字段：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `target` | text | 是 | `""` | 研究方向描述 |
| `market` | select | 是 | `"A股"` | 目标市场 |
| `frequency` | select | 是 | `"日频"` | 数据频率 |
| `mode` | select | 是 | `"skill"` | 运行模式 (skill/graph) |
| `max_rounds` | number | 否 | `1` | 最大轮次 (1=单次) |
| `max_hours` | number | 否 | `8.0` | 最大运行时长 |
| `max_turns_hypothesis` | number | 否 | `50` | 假设阶段最大轮次 |
| `max_turns_development` | number | 否 | `80` | 开发阶段最大轮次 |
| `stages` | multi-select | 否 | `["hypothesis","development","evaluation"]` | 运行阶段 |
| `clear_cache` | switch | 否 | `true` | 是否清空评测缓存 |

#### Scenario: 表单动态渲染

- **WHEN** 前端收到 `config_schema.fields`
- **THEN** 根据字段类型动态生成表单控件：`text` → Input、`select` → Select、`number` → InputNumber、`multi-select` → Select (mode="multiple")、`switch` → Switch

### Requirement: 任务执行生命周期

`POST /mining/tasks/{task_id}/run` 提交 LLMFactor 任务时，SHALL 通过 `TaskManager.submit()` 统一管理生命周期：

1. 校验 `config` 中必填字段
2. 创建 `runs/{run_id}/` 目录
3. 构建命令: `python -m QSExt.LLMFactor.scripts.run_pipeline --target ... --market ... --mode ...`
4. `task_manager.submit(name="LLMFactor 挖掘", coro_or_func=_execute_llm_factor_run(...))`
5. `_execute_llm_factor_run()` 内部：
   - `asyncio.create_subprocess_exec(*cmd, stdout=PIPE, stderr=STDOUT)`
   - 写入 `status.json`: `{"status": "running", "pid": <pid>, "started_at": "..."}`
   - stdout 双路处理循环：每行写入日志文件（供 LogViewer 轮询）；解析阶段标记 → `task_manager.update_progress()` → WebSocket 推送
   - `proc.wait()` 后扫描 FM_* 目录，提取结果写入 `result.json`

#### Scenario: 启动 LLMFactor 任务

- **WHEN** 前端提交 LLMFactor 配置
- **THEN** 系统校验必填字段、创建 run 目录、通过子进程启动 pipeline、返回 `task_id` 和 `run_id`

### Requirement: 进度推送

GP 和 LLMFactor SHALL 共用同一 WebSocket 通道推送进度。

```
TaskManager._notify() → WebSocket:
  {"task_id": "...", "status": "running", "progress": 40.0,
   "progress_message": "因子开发中..."}
```

- 假设生成阶段 → progress ≈ 10%
- 因子开发阶段 → progress ≈ 40%
- 因子评测阶段 → progress ≈ 70%

前端复用现有的 WebSocket 进度监听逻辑，按 `framework` 类型展示不同进度 UI。

#### Scenario: LLMFactor WebSocket 进度

- **WHEN** LLMFactor 任务正在运行
- **THEN** 前端通过 WebSocket 接收阶段描述和进度百分比

### Requirement: 任务停止

`DELETE /mining/tasks/{task_id}` → `TaskManager.cancel()`：
- LLMFactor 注册的 `on_cancel` 回调：`proc.kill()`（Windows: `CTRL_BREAK_EVENT`）
- 等待进程退出（最多 10s），超时则 `proc.terminate()`
- 进程退出后清理任务目录

#### Scenario: 停止运行中的 LLMFactor 任务

- **WHEN** 前端请求停止 LLMFactor 任务
- **THEN** 系统终止子进程，等待最多 10s，清理任务目录

### Requirement: 进程退出后收尾

LLMFactor 子进程退出后 SHALL：

1. 扫描 `workspace/` 下最新的 `FM_*` 目录
2. 提取评测结果写入 `runs/{run_id}/result.json`
3. 更新 `status.json`: `{"status": "completed"|"failed", "completed_at": "...", "exit_code": N}`
4. `task.result` 写入返回值 → TaskManager 标记 completed

#### Scenario: 任务正常完成

- **WHEN** LLMFactor 子进程正常退出 (exit_code=0)
- **THEN** status.json 标记 "completed"，result.json 包含评测结果

### Requirement: 实时日志流

`GET /mining/tasks/{task_id}/runs/{run_id}/log?offset=0&tail=200` SHALL 返回增量日志。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `offset` | int | `0` | 文件字节偏移量 |
| `tail` | int | `200` | 最多返回行数 |

响应：
```json
{
  "lines": ["[INFO] ...", "[WARNING] ..."],
  "next_offset": 5678,
  "eof": false,
  "status": "running"
}
```

#### Scenario: LogViewer 组件行为

- **WHEN** LogViewer 组件渲染
- **THEN** 深色终端风格（黑底绿字）、自动滚到底部、运行中每 2s 轮询增量、进程结束后停止轮询、支持搜索/高亮关键词

### Requirement: 评测指标 API

`GET /mining/tasks/{task_id}/runs/{run_id}/eval-metrics` SHALL 返回因子评测指标。

响应（运行中返回已完成的因子，完成后返回全部）：
```json
{
  "factors": [
    {
      "name": "momentum_20d",
      "status": "validated",
      "metrics": {
        "ic_mean": 0.035,
        "ic_ir": 0.42,
        "rank_ic": 0.038,
        "sharpe": 1.25,
        "max_drawdown": -0.15
      }
    }
  ],
  "updated_at": "2024-01-01T10:30:00"
}
```

#### Scenario: EvalMetrics 组件行为

- **WHEN** EvalMetrics 组件渲染
- **THEN** 表格展示所有因子指标（排名、名称、状态、IC Mean、IC IR、Rank IC、Sharpe、最大回撤），每列支持排序，指标值用颜色渐变（绿=好、红=差），选中因子可查看详细评测报告

### Requirement: 前端页面行为

MiningStudio 前端 SHALL 支持 LLMFactor 特有的页面行为。

#### Scenario: 新建任务框架选择

- **WHEN** 用户点击"新建任务"
- **THEN** 框架选择器展示两个选项：遗传规划 (GP) / LLM 因子挖掘，选择 LLMFactor 后表单渲染 LLMFactor 配置字段

#### Scenario: 结果面板

- **WHEN** 用户选择 LLMFactor 任务
- **THEN** Tab 显示"日志"（LogViewer）和"评测指标"（EvalMetrics 表格），不显示"因子树"Tab

#### Scenario: 任务列表框架标签

- **WHEN** 任务列表渲染
- **THEN** 每个任务显示框架标签：`GP`（蓝色）/ `LLM`（绿色）
