# GPLearn — 基于遗传编程的因子挖掘

## 概述

GPLearn 是一个基于遗传编程 (Genetic Programming, GP) 的量化因子挖掘模块。它将因子表达式建模为树结构，通过进化算法（选择、交叉、变异）自动搜索具有预测能力的因子组合。

核心思想：将 QuantStudio 的因子算子（如 `add`、`sub`、`mul`）作为树的内部节点，基础因子（如 `Open`、`Close`）作为叶节点，通过 GP 演化出新的因子表达式。

## 核心概念

### 因子树与波兰表示法

GP 算法不直接操作树结构，而是将因子树展平为**波兰表示法 (Polish Notation, PN)** 的线性序列，便于进行子树提取、交叉和变异等操作。

```
因子树:           PN 表示法:
    mul            [mul, add, Open, Close, Volume]
   /   \
  add   Volume
 /  \
Open Close
```

- **PN (Polish Notation)**: 前缀表示，算子在前，操作数在后。用于算法内部表示。
- **RPN (Reverse Polish Notation)**: 后缀表示，操作数在前，算子在后。用于求值。

### 算子与终端

- **算子 (Operator)**: QuantStudio 的 `FactorOperator` 子类实例，如 `fo.add`、`fo.neg`。分为固定入参（`Arity` 为具体数值）和可变入参（`Arity=None`）两种。
- **终端 (Terminal)**: 基础因子（`DataFactor`）或常数。GP 树的叶节点。

### 演化流程

```
初始种群 → 适应度评估 → 选择 → 遗传操作(交叉/变异) → 新一代种群 → 适应度评估 → ...
```

## 工具函数

#### `flattenFactor2PN(f)` / `flattenFactor2RPN(f)`

将因子树转换为波兰表示法 / 逆波兰表示法。

#### `calcDepth(f)`

计算因子树的最大深度。基础因子深度为 0。

#### `toExprStr(f)`

将因子对象转换为中缀表达式字符串，如 `toExprStr(fo.add(Open, Close))` → `"add(Open, Close)"`。

#### `toNameList(expr)`

将 PN 序列转换为名称列表。

#### `exportGraphviz(pn_expr, fade_nodes=None)`

将 PN 序列渲染为 Graphviz DOT 脚本。

## 类参考

### `GPConfig`

遗传编程配置参数（`dataclass`），所有字段都有默认值：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `population_size` | `int` | 1000 | 种群大小 |
| `tournament_size` | `int` | 20 | 锦标赛选择的参赛者数量 |
| `init_depth` | `tuple` | (2, 6) | 初始树深度范围 |
| `init_method` | `str` | "half and half" | 初始化方法: "grow"/"full"/"half and half" |
| `min_arity` | `int` | 1 | 可变入参算子的最小入参数量 |
| `max_arity` | `int` | 3 | 可变入参算子的最大入参数量 |
| `const_range` | `tuple\|None` | (-1.0, 1.0) | 常数范围，None 表示不使用常数 |
| `p_crossover` | `float` | 0.9 | 交叉概率 |
| `p_subtree_mutation` | `float` | 0.01 | 子树变异概率 |
| `p_hoist_mutation` | `float` | 0.01 | 提升变异概率 |
| `p_point_mutation` | `float` | 0.01 | 点变异概率 |
| `p_point_replace` | `float` | 0.05 | 点变异中每个节点被替换的概率 |
| `parsimony_coefficient` | `float` | 0.0 | 复杂度惩罚系数（适应度 -= 系数 × 表达式长度） |

### `GPLearner`

核心进化引擎类。

```python
GPLearner(
    operator_list: List[FactorOperator],    # 可用算子列表
    terminal_factors: List[DataFactor],      # 终端因子列表
    fitness_fun: Callable[[List], ndarray],  # 适应度函数
    config: GPConfig | None = None,          # 配置参数
)
```

**属性**：
- `operator_arity` — 自动构建的 `{arity: [operator]}` 映射
- `hall_of_fame` — 历史最优因子列表 `[(fitness, pn_expr), ...]`

**主要方法**：

| 方法 | 说明 |
|------|------|
| `buildRandomPNExpr()` | 随机生成一个因子表达式 |
| `crossover(pn_expr, donor)` | 交叉操作 |
| `mutateSubtree(pn_expr)` | 子树变异 |
| `mutateHoist(pn_expr)` | 提升变异（控制膨胀） |
| `mutatePoint(pn_expr)` | 点变异 |
| `evolve(n_generations, ...)` | 执行完整进化循环 |
| `generate_initial_population()` | 生成初始种群并计算适应度 |

## 使用示例

### 推荐用法：使用 GPLearner 类

```python
import datetime as dt
import numpy as np
import pandas as pd

from QuantStudio.Factor.Factor import DataFactor
import QuantStudio.Factor.BasicOperator as fo
from QSResearch.GPFactor.GPLearn import GPLearner, GPConfig, toExprStr

# 1. 准备基础因子
np.random.seed(42)
IDs = [f"00000{i}.SZ" for i in range(1, 6)]
DTs = [dt.datetime(2020, 1, 1) + dt.timedelta(i) for i in range(7)]

Open = DataFactor(
    data=pd.DataFrame(np.random.rand(7, 5) * 10, index=DTs, columns=IDs),
    args={"Name": "Open"},
)
Close = DataFactor(
    data=pd.DataFrame(np.random.rand(7, 5) * 10, index=DTs, columns=IDs),
    args={"Name": "Close"},
)
Volume = DataFactor(
    data=pd.DataFrame(np.random.rand(7, 5) * 10000, index=DTs, columns=IDs),
    args={"Name": "Volume"},
)

# 2. 定义适应度函数
def calc_fitness(factors):
    return np.array([
        f.readData(ids=IDs, dts=DTs).values.std()
        for f in factors
    ])

# 3. 创建 GPLearner
config = GPConfig(
    population_size=100,
    tournament_size=5,
    init_depth=(2, 5),
    const_range=(-2.0, 2.0),
)
learner = GPLearner(
    operator_list=[fo.add, fo.sub, fo.mul, fo.div, fo.qs_abs, fo.neg],
    terminal_factors=[Open, Close, Volume],
    fitness_fun=calc_fitness,
    config=config,
)

# 4. 一键进化
populations, fitness, ancestry = learner.evolve(n_generations=10)

# 5. 查看结果
best_factor = learner.hall_of_fame[0][1][0]
print(f"最佳因子: {toExprStr(best_factor)}")
print(f"适应度: {learner.hall_of_fame[0][0]:.4f}")
```

### 带复杂度惩罚

```python
config = GPConfig(parsimony_coefficient=0.01)  # 每个节点惩罚 0.01
learner = GPLearner(operator_list, terminal_factors, calc_fitness, config)
populations, fitness, ancestry = learner.evolve(n_generations=20)
```

### 可变入参算子

```python
from QuantStudio.Factor.FactorOperation import PointOperator

class Mean(PointOperator):
    """均值算子，可接受任意数量的输入"""
    class __QS_ArgClass__(PointOperator.__QS_ArgClass__):
        def __init__(self, /, **data):
            Args = {"Name": "mean", "Arity": None, "DTMode": "多时点", "IDMode": "多ID"}
            Args.update(data)
            return super().__init__(**Args)

    def calculate(self, f, idt, iid, x, args):
        return np.nanmean(x, axis=0)

    def __call__(self, *x, factor_args={}, **kwargs):
        factor_args = {"CacheEnabled": False} | factor_args
        return super().__call__(*x, factor_args=factor_args, **kwargs)

config = GPConfig(min_arity=2, max_arity=4)
learner = GPLearner(
    operator_list=[fo.add, fo.sub, fo.mul, fo.div, fo.qs_abs, fo.neg, Mean()],
    terminal_factors=[Open, Close, Volume],
    fitness_fun=calc_fitness,
    config=config,
)
```

### 可视化因子树

```python
import graphviz
from QSResearch.GPFactor.GPLearn import flattenFactor2PN, exportGraphviz

factor = fo.mul(fo.sub(Open, Close), Volume)
pn = flattenFactor2PN(factor)
dot_script = exportGraphviz(pn)

graph = graphviz.Source(dot_script)
graph.render(filename="factor_tree", format="png", view=True)
```

## 参数调优建议

| 参数 | 推荐范围 | 说明 |
|------|----------|------|
| `population_size` | 100~5000 | 种群越大搜索越广，但计算成本越高 |
| `n_generations` | 10~100 | 代数越多收敛越好，但注意过拟合 |
| `tournament_size` | 5~20 | 越大选择压力越强，收敛更快但多样性降低 |
| `init_depth` | (2, 6) | 初始深度不宜过深，避免初始种群过于复杂 |
| `p_crossover` | 0.7~0.9 | 交叉概率通常最高 |
| `p_subtree_mutation` | 0.01~0.1 | 子树变异引入新结构 |
| `p_hoist_mutation` | 0.01~0.1 | 提升变异控制表达式膨胀 |
| `p_point_mutation` | 0.01~0.1 | 点变异做微调 |
| `const_range` | (-1, 1) 或 None | 按需启用常数系数 |
| `parsimony_coefficient` | 0.0~0.1 | 复杂度惩罚，抑制表达式膨胀 |

## 依赖

- **QuantStudio** — 因子框架（`Factor`、`FactorOperator`、`DataFactor` 等）
- **NumPy** — 数值计算
- **pandas** — 数据处理
- **graphviz** — 可选，用于因子树可视化

## 模块结构

```
QSResearch/GPFactor/
├── __init__.py
├── GPLearn.py          # GP 核心算法（GPLearner 类 + 工具函数）
└── requirements.txt
```

## 测试

```bash
python -m pytest tests/test_gp_learn.py -v
```

## 待优化项

### 性能优化

| # | 项目 | 说明 |
|---|------|------|
| 1 | **适应度缓存** | 同一棵因子树可能在不同代中重复出现，可基于 `QSID` 缓存适应度值，避免重复计算 |
| 2 | **并行计算** | 适应度计算是主要瓶颈。`evolve` 中可引入 `joblib.Parallel` 并行评估种群，或用 `ProcessPoolExecutor` 并行化单个因子的 `readData` |
| 3 | **因子数据预取** | 进化过程中多棵因子树共享相同的终端因子数据，可在一代开始前批量预取，减少 IO |

### 搜索质量

| # | 项目 | 说明 |
|---|------|------|
| 4 | **语义化常数** | 当前常数是随机浮点数，可引入常见金融常数（0.5、1.0、-1.0 等）作为特殊终端，提升搜索效率 |
| 5 | **表达式去重** | GP 种群中经常出现重复的因子表达式。可在繁殖后基于 `QSID` 或表达式字符串去重，维护种群多样性 |
| 6 | **早停 (Early Stopping)** | 当最优适应度连续 N 代无改善时提前终止，避免浪费计算 |
| 7 | **自适应变异率** | 当种群收敛过快（多样性下降）时自动增大变异概率，陷入局部最优时增大交叉概率 |

### 功能扩展

| # | 项目 | 说明 |
|---|------|------|
| 8 | **支持时序算子** | 当前只支持 `PointOperator`。扩展支持 `TimeOperator`（如 `ts_mean`、`ts_std`、`ts_rank`）可大幅扩展因子搜索空间 |
| 9 | **支持截面算子** | 支持 `SectionOperator`（如 `cs_rank`、`cs_zscore`），在截面维度上做变换 |
| 10 | **Pareto 前沿** | 同时优化适应度和简洁度（表达式长度），保留 Pareto 最优解集，而非单一最优 |
| 11 | **与 FactorMining 集成** | 将 GP 作为 FactorMining 的一种挖掘策略，接入假设生成 → 开发 → 评测流水线 |
| 12 | **因子序列化** | 已通过 `QSExt.FactorDef.FactorScriptWriter.generate_script()` 实现，可将 GP 产出的最优因子自动导出为 FactorDef 脚本（`.py`），详见 [FactorScriptWriter 文档](../因子定义/FactorScriptWriter.md)
