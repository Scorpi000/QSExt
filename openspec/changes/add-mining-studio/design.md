## Context

QSWeb 目前缺少因子挖掘的管理界面。QSExt/GPFactor 模块提供的 `GPLearner` 类已经实现了完整的遗传规划因子挖掘能力（种群初始化、选择、交叉、变异、进化循环），但目前只能通过手工编写 Python 脚本来使用。

QSWeb 现有的回测工作台（BacktestStudio）已经建立了"配置 → 异步执行 → WebSocket 进度 → 结果浏览"的完整模式，以及声明式的模块注册表（`BACKTEST_MODULE_REGISTRY` + `_BT_NODE_BUILDERS`）。因子挖掘可以复用这套基础设施。

关键集成点：GPLearner 的 `fitness_fun` 需要一个 `Callable[[List[Factor]], np.ndarray]`，而 QuantStudio 的截面因子回测框架（`CalcOp` + `BTNode`）正好可以批量评估因子质量。因此，适应度评估不再需要重新实现，而是直接复用回测模块。

## Goals / Non-Goals

**Goals:**
- 提供 Web UI 配置和运行 GP 因子挖掘任务
- 支持从已有任务接续挖掘（继承种群，调整 GP 参数和评估方案后继续进化）
- 复用 QuantStudio 回测框架（CalcOp + BTNode）作为适应度评估引擎
- 支持多评估模块组合 + transform 脚本自定义适应度计算
- 任务持久化到 workspace 目录，支持历史查询
- 因子树可视化复用 React Flow
- 挖掘结果可导出为 FactorDef 脚本
- 架构上预留未来挖掘框架（DL、RL 等）的扩展点

**Non-Goals:**
- 不修改 GPLearn 核心算法
- 不支持实时交互式调参（每一代都是自动运行的）
- 不实现分布式挖掘
- 不在 MVP 中支持 GPLearner 以外的框架
- 接续时不可修改算子列表和终端因子（会导致已有种群失效）

## Decisions

### 1. 挖掘框架注册表模式

采用与 `BACKTEST_MODULE_REGISTRY` + `_BT_NODE_BUILDERS` 类似的声明式注册模式：

```python
MINING_FRAMEWORKS = {
    "gp": {
        "name": "遗传规划 (GP)",
        "description": "...",
        "config_schema": {...},      # 前端据此渲染配置表单
        "runner": run_gp_mining,     # 异步执行函数
    }
}
```

**Why**: 与回测工作台的架构一致，前端可以动态渲染框架选择器，未来新增框架只需注册新条目。

### 2. 适应度评估复用 BTNode 计算图

GPLearner 的 `fitness_fun` 内部构造一个 BTNode 计算图来评估因子：

```
fitness_fun(factors) → for each factor:
  bt_nodes = [IC(CalcIC(...)(factor, price)), MultiPortfolio(...)]
  context = FactorContext(DTRuler, SectionIDs)
  results = Engine.run(BTReport(bt_nodes), context)
  → transform(results) → scalar fitness
```

**Why**: 避免重新实现 IC、分位数组合等计算逻辑。评估逻辑和回测工��台共用同一套算子，保证一致性和可复现性。未来回测模块的新增也会自动惠及挖掘任务的评估。

**Alternative considered**: 自定义 FitnessFunction 抽象基类，每个评估维度单独实现。被拒绝——代码重复且与回测框架分裂。

### 3. transform 脚本机制

适应度评估支持两种模式：
- **内置**：`abs`, `neg`, `square`, `sqrt`, `identity` — 对指定 metric 字段做简单数学变换
- **自定义**：`@path/to/script.py` — 脚本定义 `def transform(outputs: list[dict]) -> float`，接收所有评估模块的完整输出

**Why**: 内置模式覆盖 80% 的常见场景（取 IC_IR 绝对值等），自定义脚本满足高级用户的多维度加权需求。脚本方式比配置表达式更灵活，且可以由 AI 工作台生成。

### 4. eval 配置两套格式

完整格式（多模块）：
```yaml
eval:
  modules:
    - module: "ic"
      params: {...}
    - module: "multi_portfolio"
      params: {...}
  transform: "abs"
  sign: "greater"
```

简化格式（单模块 + 取 metric）：
```yaml
eval:
  module: "ic"
  metric: "IC_IR"
  transform: "abs"
```

简化格式在后端自动展开为完整格式。`metric` 表示取回测输出中的哪个字段（如 `output["统计数据"]["IC_IR"]`），单指标 + 内置 transform 时等价于 `transform(outputs)=builtin(outputs[0]["统计数据"][metric])`。

### 5. 任务模型与持久化

**任务 = 一个挖掘项目**，包含多次运行（run）。第一次运行是"初始挖掘"，后续运行是"接续挖掘"——从上次 checkpoint 恢复种群，调整 GP 参数或评估方案后继续进化。

```
{workspace}/
├── tasks/
│   └── {task_id}/
│       ├── task.json            # 任务元信息（名称、创建时间、当前 run 序号）
│       ├── runs/
│       │   ├── 001/             # 第一次运行
│       │   │   ├── config.json  # 本次运行的配置
│       │   │   ├── result.json  # 结果摘要
│       │   │   └── status.json  # 运行时状态
│       │   ├── 002/             # 第二次运行（接续）
│       │   │   └── ...
│       │   └── ...
│       ├── checkpoint.pkl       # 最新一次运行的最终种群快照
│       └── factors.py           # 最新一次运行的 Hall of Fame 因子定义脚本
└── transforms/                  # 自定义 transform 脚本
```

**接续挖掘**：已完成的任务可以接续。框架从 `checkpoint.pkl` 加载最终种群和适应度，传给 `evolve(parents=population, parent_fitness=fitness)`。接续时可以调整的参数：
- GP 参数：代数、变异率、交叉率、tournament_size 等
- 评估方案：eval 配置（评估模块、参数、transform）

不可调整的参数（锁定）：算子列表、终端因子——修改这些会使已有种群中的因子失效。

**接续时适应度曲线的连续性**：每次 run 独立记录 `fitness_history`，前端展示时将多个 run 的曲线首尾拼接，用户看到一条连续的进化曲线。

**因子持久化**：每次 run 完成时将 Hall of Fame 因子通过 `QSExt.FactorDef.FactorScriptWriter.generate_script()` 导出为 FactorDef 脚本。该函数采用"重建算子 → 重建描述子 → 调用算子"的方式生成代码，算子序列化委托给 `FactorOperator.serialize()`。

### 6. 因子树可视化

后端将 GPLearner 的 PN 表达式转为 `{nodes, edges}` 格式（与 `DAGViewer` 的 `DAGData` 格式一致），前端复用 React Flow 渲染。

节点类型区分：
- `operator`：DerivativeFactor（算子节点），蓝色系
- `terminal`：DataFactor（终端因子），浅蓝色

**Why**: 与因子工作台的 DAGViewer 保持一致的用户心智模型，代码复用最大化。

### 7. 前端页面布局

采用与 AiWorkbench 一致的左右分栏布局：
- 左侧：任务列表（可新建、切换、删除）
- 右侧：Tab 切换（配置 / 结果 / 因子树）
  - 配置 Tab：框架选择、GP 参数、算子选择、终端因子、评估模块配置
  - 结果 Tab：适应度进化曲线（Plotly）、Hall of Fame 排名表
  - 因子树 Tab：React Flow 渲染选中因子的树结构

### 8. 不修改 GPLearner 核心代码

在 `mining_service.py` 中直接 `from QSExt.GPFactor.GPLearn import GPLearner, GPConfig` 使用。适应度函数在 service 层构造。因子定义脚本生成委托给 `QSExt.FactorDef.FactorScriptWriter.generate_script()`。

**Why**: GPFactor 是独立的算法模块，不应因 Web 集成而修改。FactorScriptWriter 是通用工具，放在 FactorDef 下供所有场景复用。

## Risks / Trade-offs

- **[性能] GP 挖掘计算量大** → 在 `run_in_executor` 中运行，避免阻塞事件循环。建议限制种群大小和代数，前端显示预估时间。
- **[内存] GPLearner 在内存中维护种群** → 超大配置可能导致 OOM。配置层面限制 `population_size` 上限，workspace 做 checkpoint 备份。
- **[复杂度] 自定义 transform 脚本调试困难** → 任务运行前做脚本语法校验（try compile），错误信息反馈到前端。
- **[耦合] eval 配置直接引用回测模块名** → 如果回测模块重命名，挖掘配置也需要更新。但这是合理的耦合——评估模块本身就是回测模块。
