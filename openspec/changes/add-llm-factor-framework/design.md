## Context

`add-mining-studio` 已经建立了 MiningStudio 的完整架构：框架注册 → 任务管理 → 异步执行 → 结果展示。但当时的设计以 GP 为中心（`GPRunConfig` 强类型配置、`HallOfFameEntry` 结果模型、同步进程内执行），多框架扩展仅停留在"预留"阶段。

现在 LLMFactor 模块迁入，需要真正实现多框架共存。LLMFactor 与 GP 在以下维度本质不同：

| 维度 | GP | LLMFactor |
|------|-----|-----------|
| 执行模型 | 同步进程内 (`run_in_executor`) | 子进程 (`asyncio.create_subprocess_exec`) |
| 配置形状 | GP 超参数（population_size, crossover...） | 研究方向、市场、频率、模式 |
| 输出产物 | Hall of Fame 表达式列表 | 因子代码 + 评测报告 + 日志 |
| 进度概念 | 代数 (generation) | 阶段 (hypothesis/development/evaluation) |
| 进度推送 | 代回调 → `update_progress()` → WebSocket | 日志解析 → `update_progress()` → WebSocket |
| 生命周期管理 | `TaskManager.submit()` | `TaskManager.submit()`（统一） |

## Goals / Non-Goals

**Goals:**
- LLMFactor 作为第二框架注册到 MiningStudio
- 前端按框架选择渲染各自的配置表单和结果面板
- 子进程执行通过 TaskManager 统一管理，进度通过 WebSocket 实时推送
- 实时日志流查看（LogViewer 组件轮询日志文件）
- 评测指标提取和多因子对比展示
- 复用现有任务管理（create/list/delete）
- 模型层支持多态配置和结果，不影响 GP 现有功能

**Non-Goals:**
- 不修改 LLMFactor 核心代码
- 不依赖或迁移 Streamlit web 组件
- 不实现 LLMFactor 的"接续挖掘"（与 GP 的 checkpoint 机制不同）
- 不在此阶段实现 DAG 可视化（LLMFactor 产出的是代码而非表达式树）
- 不实现假设文档在线查看（后续迭代）

## Decisions

### 1. 模型层多态化

当前模型是 GP 专用：

```python
class SubmitRunRequest(BaseModel):
    config: GPRunConfig  # ← 强类型，只有 GP
```

改为框架无关：

```python
class SubmitRunRequest(BaseModel):
    config: Dict[str, Any] = Field(..., description="运行配置，各框架自行定义结构")
```

**Why**: 不同框架的配置 shape 完全不同，不可能用一个 union type 覆盖。`Dict[str, Any]` 让各框架自行解析，前端根据 `config_schema` 构建表单。trade-off 是失去了 Pydantic 的自动校验——改为在 `submit_run()` 中各框架手动 validate。

`RunResult` 同样多态化：

```python
class RunResult(BaseModel):
    run_id: str
    framework: str                    # ← 新增
    data: Dict[str, Any]              # ← 替代固定的 hall_of_fame + fitness_history
    gen_start: int = 0
    gen_end: int = 0
    is_partial: bool = False
```

GP 的 `data` 形状: `{"hall_of_fame": [...], "fitness_history": {...}}`
LLMFactor 的 `data` 形状: `{"stage": "evaluation", "factors": [...], "metrics": {...}}`

**向后兼容**: GP 的 `RunResult` 旧字段 (`hall_of_fame`, `fitness_history`) 保留在模型上标记为 `Optional` + `deprecated`，Service 层同时写入旧字段和新 `data` 字段，给前端迁移留缓冲期。

### 2. LLMFactor 执行模型：TaskManager + asyncio 子进程

LLMFactor 与 GP 共享 TaskManager 生命周期管理，但内部通过 `asyncio.create_subprocess_exec` 启动外部进程：

```
submit_run()
  → task_manager.submit(name="LLMFactor 挖掘", coro_or_func=_run())

_run() 内部:
  → 创建 run 目录: workspace/tasks/{task_id}/runs/{run_id}/
  → 构建命令: python -m QSExt.LLMFactor.scripts.run_pipeline \
      --target <研究方向> --market <市场> --frequency <频率> \
      --mode <skill|graph> --max-rounds <N> ...
  → asyncio.create_subprocess_exec(*cmd, stdout=PIPE, stderr=STDOUT)
  → 写 status.json: {"status": "running", "pid": <pid>}
  → stdout 双路处理循环:
      ├─ 每行写入 log 文件（持久化，供 LogViewer 轮询）
      └─ 解析阶段标记 → task_manager.update_progress() → WebSocket 推送
          "假设生成阶段" → progress=10%
          "因子开发阶段"   → progress=40%
          "因子评测阶段"   → progress=70%
  → proc.wait() → 扫描 FM_* 目录 → 更新 result.json 和 status.json
  → return result → task.result（TaskManager 写入）
```

**Why TaskManager 统一**:

1. **生命周期一致** — GP 和 LLMFactor 共享 pending → running → completed/failed 状态机，TaskManager 是现成的实现
2. **进度推送统一** — 两个框架都通过 `task_manager.update_progress()` + WebSocket 推送进度，前端只需一套监听逻辑
3. **取消统一** — `task_manager.cancel()` 可同时处理：对 GP 取消 `asyncio.Task`，对 LLMFactor 额外 `proc.kill()`
4. **结果收集统一** — 两个框架的执行结果都写入 `task.result`，`get_task()` 可以从同一位置获取

**Why 子进程而非进程内**:
1. `run_pipeline.py` 是完整的 CLI 入口，内部调用 LLM API、执行因子评测等复杂流程，子进程隔离更安全
2. 可能运行数小时，子进程不阻塞 FastAPI 事件循环
3. 子进程崩溃不影响 QSWeb 服务

**stdout 双路处理**: 使用 `asyncio.create_subprocess_exec` 的 `StreamReader.readline()` 逐行读取，每行同时写入日志文件和解析进度。这是 Python asyncio 的标准模式，成熟可靠。

**进度粒度**: LLMFactor 的阶段级进度（10%/40%/70%）虽然比 GP 的代数级进度粗糙，但对于数小时的任务已足够。前端展示"假设生成中…""因子开发中…"等阶段描述即可。

### 3. 进度通知：双通道

**主通道 — WebSocket 进度推送**（与 GP 一致）：

```
WebSocket 消息:
  {"task_id": "...", "status": "running", "progress": 40.0, "progress_message": "因子开发中..."}
```

TaskManager 的 `_notify()` 机制自动推送到所有订阅者。前端复用现有的 WebSocket 进度监听，按 `framework` 类型展示不同的进度 UI。

**辅助通道 — HTTP 日志轮询**（LogViewer 组件）：

```
GET /mining/tasks/{task_id}/runs/{run_id}/log?offset=<int>&tail=<int>
→ {
    "lines": ["[INFO] 假设生成阶段开始...", ...],
    "next_offset": 5678,
    "eof": false
  }
```

**Why 双通道**: WebSocket 解决"任务进行到哪了"的问题（进度百分比 + 阶段描述），HTTP 日志解决"具体发生了什么"的问题（详细日志查看）。两者互补——进度条靠 WebSocket 自动更新，LogViewer 只在用户主动切换到"日志"Tab 时才轮询。

### 4. 评测指标提取

LLMFactor 评测阶段完成后会在 `FM_*/evaluation/` 下生成结构化结果。后端解析后暴露为标准化指标：

```
GET /mining/tasks/{task_id}/runs/{run_id}/eval-metrics
→ {
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

**Why 独立端点**: 评测指标数据量大且更新频繁（评测过程中逐步产出），不应混在 run result 里。前端按需拉取，轮询间隔可独立配置。

### 5. 前端框架感知渲染

MiningStudio 当前页面结构：

```
┌──────────────────────────────────────────────┐
│  左侧任务列表  │  右侧内容区 (Tabs)             │
│                │  ┌─ 配置 ── 结果 ── 因子树 ─┐ │
│                │  │                          │ │
│                │  │  (全部是 GP 专用组件)      │ │
│                │  └──────────────────────────┘ │
└──────────────────────────────────────────────┘
```

改造后：

```
┌──────────────────────────────────────────────┐
│  左侧任务列表  │  右侧内容区 (Tabs)             │
│  (增加框架标签) │  ┌─ 配置 ── 结果 ── 因子树 ─┐ │
│                │  │                          │ │
│                │  │  framework === "gp"       │ │
│                │  │    → GP 参数面板          │ │
│                │  │    → HOF 表格 + 适应度曲线 │ │
│                │  │    → 因子树 DAG           │ │
│                │  │                          │ │
│                │  │  framework === "llm_factor"│ │
│                │  │    → LLMFactor 配置面板    │ │
│                │  │    → 日志查看器            │ │
│                │  │    → 评测指标对比          │ │
│                │  └──────────────────────────┘ │
└──────────────────────────────────────────────┘
```

框架选择器放在"新建任务"时（创建任务即绑定框架），已创建的任务框架不可变。配置表单和结果面板通过 `activeTask.framework` 做条件渲染。

### 6. LLMFactor 配置表单

```
研究方向: [________________] (如: 动量因子、低波动因子)
市场:     [A股 ▼]
频率:     [日频 ▼]
运行模式: [Skill ▼] (Skill / Graph)
最大轮次: [1] (1=单次)
最大时长: [8.0] 小时
假设阶段最大轮次: [50]
开发阶段最大轮次: [80]
阶段选择: [✓] 假设生成 [✓] 因子开发 [✓] 因子评测
清空评测缓存: [✓]
```

相比 GP 的数十个超参数，LLMFactor 的配置更偏向"任务描述"——这也符合它 LLM 驱动的本质。

### 7. `config_schema` 格式约定

沿用 `FrameworkInfo.config_schema`，定义前端表单渲染描述：

```python
LLM_FACTOR_CONFIG_SCHEMA = {
    "fields": [
        {"key": "target", "label": "研究方向", "type": "text",
         "placeholder": "如：动量因子、低波动", "required": True},
        {"key": "market", "label": "市场", "type": "select",
         "options": ["A股", "港股", "美股"], "default": "A股"},
        {"key": "frequency", "label": "频率", "type": "select",
         "options": ["日频", "周频", "月频"], "default": "日频"},
        {"key": "mode", "label": "运行模式", "type": "select",
         "options": [
             {"value": "skill", "label": "Skill — 单方向深入挖掘"},
             {"value": "graph", "label": "Graph — 多方向并行探索"},
         ], "default": "skill"},
        # ... 更多字段
    ],
    "defaults": {
        "target": "", "market": "A股", "frequency": "日频",
        "mode": "skill", "max_rounds": 1, "max_hours": 8.0,
        "max_turns_hypothesis": 50, "max_turns_development": 80,
        "stages": ["hypothesis", "development", "evaluation"],
        "clear_cache": True,
    }
}
```

前端根据 `fields` 动态渲染表单，`type` 决定组件类型（`text` → Input, `select` → Select, `number` → InputNumber, `switch` → Switch 等）。

### 8. 停止任务

两个框架统一通过 `TaskManager.cancel()` 停止：

- **GP**：取消 asyncio Task → `CancelledError` → 清理
- **LLMFactor**：在 `cancel()` 回调中额外 `proc.kill()`（Windows: `CTRL_BREAK_EVENT`），等待子进程退出（最多 10s），超时则 `proc.terminate()`

在 `TaskManager.cancel()` 上扩展一个 `on_cancel` 回调钩子，各框架注册自己的清理逻辑。

API 层面：`DELETE /mining/tasks/{task_id}` 在删除前先调用 `task_manager.cancel()`。用户不需要区分"停止"和"删除"——删除运行中的任务自动先停止。

## Risks / Trade-offs

- **[模型兼容] `config: Dict[str, Any]` 失去 Pydantic 校验** → 各框架在 `submit_run()` 入口手动 validate + 返回明确错误信息，前端展示。可接受——框架数量少（2个），手动校验可控。
- **[进程泄漏] 子进程可能成为孤儿进程 / QSWeb 重启后进程残留** → QSWeb 启动时扫描 running 状态的 task，检查 pid 是否存活，清理僵死状态。子进程使用 `CREATE_NEW_PROCESS_GROUP` 确保 kill 时连带子进程组。TaskManager 重启后内存为空，但 `status.json` 在磁盘保留权威状态。
- **[日志文件膨胀]** → 单次挖掘可能产生数 MB 日志。设置日志文件上限（10MB），超过后只 tail 最新内容。
- **[评测指标解析脆弱] LLMFactor 评测输出格式可能变化** → 解析失败时返回空 metrics + warning 日志，不阻断其他功能。
