# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

### FactorRegistry（MCP 服务）

`QSExt/FactorRegistry/` 提供因子注册中心，基于 Neo4j 图数据库存储因子元数据和依赖关系。
- `FactorGraphDB`：图数据库操作封装
- `mcp_server.py`：MCP 服务端点，提供 `search_factors`、`get_factor_info`、`get_factor_code` 三个工具

## 配置文件

数据库连接配置存放在 `~/QuantStudioConfig/` 目录：
- `JYDBConfig.json`：聚源数据库（PostgreSQL）
- `Neo4jDBConfig.json`：Neo4j 图数据库
- 其他数据库配置文件

## 约定

- 文档、注释、变量命名中大量使用中文
- QS 对象普遍继承 `__QS_Object__`，通过 `__QS_ArgClass__` 和 `__QS_initArgs__` 管理参数
- 参数系统使用 traits（`Int`、`Str`、`Enum`、`Instance` 等）声明参数类型和 UI 属性
