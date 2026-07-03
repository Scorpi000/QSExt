# CLAUDE.md

此文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指导。

## 行为准则

**权衡**：本准则优先考量稳妥性而非开发速度，对于简单任务可结合实际灵活判断。

### 1. 编码前先思考
**不要主观臆断，不要隐藏疑惑，明确呈现相关权衡。**

实现前需满足：
* 明确列出你的所有假设，存在不确定之处时主动提问；
* 若存在多种解读可能，需将所有可能性列明说明，不要默认选择其中一种而不告知；
* 若存在更简洁的实现方案，要明确指出。在合理范围内可提出异议；
* 若需求存在模糊之处，先暂停操作，明确指出困惑点，完成确认后再继续。

### 2. 简洁优先
**仅编写能解决问题的必要代码，不做无依据的额外拓展。**

* 不要实现需求之外的功能；
* 不要为仅使用一次的单段代码创建抽象层；
* 不要添加需求未要求的“灵活性”或“可配置性”；
* 不要为不可能出现的场景编写错误处理逻辑；
* 若实现方案能用50行代码写完却写了200行，直接重写。
可以自问：“资深工程师会认为这份代码过于复杂吗？”如果答案是肯定的，就对其进行简化。

### 3. 精准改动
**只修改必须改动的部分，只清理你自己引入的冗余内容。**

编辑现有代码时：
* 不要“优化”相邻的代码、注释或格式；
* 不要重构没有问题的代码；
* 哪怕你有更习惯的写法，也要匹配现有代码的风格；
* 若发现无关的无效代码，仅需指出，不要直接删除。
若你的改动产生了孤立无用内容：
* 移除因你的改动而不再使用的导入、变量或函数；
* 不要删除改动前就存在的无效代码，除非收到明确要求。
验证标准：每一行改动的代码都必须直接对应用户提出的需求。

### 4. 目标导向执行
**明确成功标准，循环验证直至达成。**

将任务转化为可验证的目标：
* 需求为“新增校验逻辑” → 转化为“为非法输入编写测试用例，再让测试全部通过”
* 需求为“修复缺陷” → 转化为“编写可复现该缺陷的测试用例，再让测试通过”
* 需求为“重构X模块” → 转化为“确保重构前后所有测试都能通过”

处理多步骤任务时，先列简要计划：
```
1. [步骤1] → 验证：[验证方式]
2. [步骤2] → 验证：[验证方式]
3. [步骤3] → 验证：[验证方式]
```
清晰的成功标准能让你独立循环完成验证，模糊的标准（例如“做出来能用就行”）需要不断确认需求。

## 项目概述

QuantStudio 是一个 Python 量化投资框架，提供因子管理、回测、风险建模和组合优化等功能。本仓库 QSExt 是其扩展包，依赖核心库 `QuantStudio`。

## 核心架构

### 双仓库结构

- **QSExt**（本仓库）：扩展包，包含额外的因子库适配器、策略、GUI 等
- **QuantStudio**：核心框架，提供基础类和引擎

QSExt 通过 `from QuantStudio.xxx import yyy` 引用核心库。两个包的 `__init__.py` 都定义了 `__QS_MainPath__` 和 `__QS_ConfigPath__` 路径常量。

### 计算图引擎（Core）

QuantStudio 底层是基于有向无环图（DAG）的计算引擎：
- `Node`：计算图节点基类，支持 `__QS_start__`、`__QS_move__`、`__QS_end__` 生命周期
- `CalcEngine` / `TreeEngine`：驱动计算图的执行
- `ParallelEngine`：多进程并行执行
- `PregelEngine`（QSExt）：基于 Pregel 模型的图计算引擎，用于大规模图并行计算

### 因子框架（Factor）

因子是框架的核心抽象，分为两类：
- **AtomicFactor**：原子因子，直接从数据源读取
- **DerivativeFactor**：衍生因子，由算子（Operator）作用于其他因子产生

关键组件：
- **FactorDB**：因子数据库，连接和管理因子表。QSExt 支持 HDF5、SQLite3、ClickHouse、MongoDB、ElasticSearch、Neo4j、Tushare、AKShare、BaoStock 等多种后端
- **FactorTable**：因子表，包含多个因子，提供 `readData(factor_names, dts, ids)` 读取接口
- **FactorOperator**：算子，定义因子的计算逻辑（时序运算、截面运算等）
- **CustomFT**：自定义因子表，通过 `addFactors` 组合因子

数据流：`FactorDB.connect() -> getTable() -> readData() -> DataFrame (Panel-like, index=[datetime, code])`

### 回测框架（BackTest）

- **SectionFactor**：截面因子回测（IC 分析、分位数组合、收益分解）
- **Strategy**：策略回测（`PortfolioStrategy`、`OptimizerStrategy`、`TimingStrategy`）
- **PerformanceAnalysis**：业绩归因（Brinson 模型、FMP 模型、收益分解模型）
- **TimeSeriesFactor**：时序因子分析（相关性、价差、择时）

回测引擎驱动 Node 的生命周期：`__QS_start__` -> 多次 `__QS_move__`（逐时点推进）-> `__QS_end__`

### 风险模型（Risk）

- **RiskDB** / **RiskTable**：风险数据存储，支持协方差矩阵、因子暴露、特异性风险等
- **BarraModel**：Barra 多因子风险模型

### 组合优化（PortfolioConstructor）

- **BasePC**：组合优化器基类
- **CVXPC**：基于 cvxpy 的凸规划优化器
- **MatlabPC**：Matlab 优化器接口

### GUI

- **Notebook**：基于 ipywidgets 的 Jupyter 交互界面
- **QtGUI**：基于 PyQt 的桌面 GUI

### QSRegistry（MCP 服务）

`QSExt/QSRegistry/` 提供 QuantStudio 计算图注册中心，基于 Neo4j 图数据库存储因子、回测、风险模型等计算节点的元数据和依赖关系，以及算子、因子表、风险库、组合优化器等支撑节点的注册信息。
- `QSGraphDB`：图数据库操作封装
- `mcp/qs_registry.py`：MCP 服务端点，提供 `search_factors`、`get_factor_info`、`get_factor_code`、`search_backtests`、`get_backtest_info`、`get_backtest_result`、`search_risk_tables`、`search_optimizers` 等工具

## 配置文件

数据库连接配置存放在 `~/QuantStudioConfig/` 目录：
- `JYDBConfig.json`：聚源数据库（PostgreSQL）
- `Neo4jDBConfig.json`：Neo4j 图数据库
- 其他数据库配置文件

## 约定

- 文档、注释、变量命名中大量使用中文
- QS 对象普遍继承 `__QS_Object__`，通过 `__QS_ArgClass__` 和 `__QS_initArgs__` 管理参数
- 参数系统使用 traits（`Int`、`Str`、`Enum`、`Instance` 等）声明参数类型和 UI 属性
