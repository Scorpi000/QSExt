## Why

当前 FactorDef/StrategyDef 框架中，`build_dep_fd()`/`build_dep_sd()` 以 `__FACTOR_META__["TargetTable"]` 作为内部字典的唯一键，导致多个定义文件声明相同 TargetTable 时，第二个模块被静默跳过，defFactor/defStrategy 不被执行，因子/信号丢失。多人协作开发时，不同开发者各自撰写定义脚本但需要将产出写入同一张表，当前设计不支持此场景。

## What Changes

- **重构唯一索引**：将 `dep_fd`/`dep_sd` 字典的 key 从 `TargetTable` 改为 `DefKey`（`module.__file__` 文件系统绝对路径 + `ModelArgs` 的组合标识），使去重粒度从"表级别"变为"文件+参数级别"，且不受模块加载方式影响
- **新增 `make_def_key()` 工具函数**：根据模块路径和 ModelArgs 生成唯一的 DefKey 字符串
- **新增 `_dep_key_to_def_key()` 辅助函数**：将 FactorDeps/StrategyDeps 声明的模块路径映射到 dep_fd/dep_sd 中的 DefKey，解决 key 语义变化后的依赖查找问题
- **重构 `_build_factors()`**：签名从 `(meta, dep_fd, ...)` 改为 `(resolved_deps, dep_fd, ...)`，由调用方预解析 DefKey→entries 映射
- **重构 `compute_max_lookback()` / `compute_max_lookback_sd()`**：递归变量从 TargetTable 改为 DefKey，依赖遍历改用 `_dep_key_to_def_key` 查找
- **FactorStorer 合并**：当多个模块写入同一 TargetTable 时，`run_factor_def.py` 和 `register_factors_to_graphdb.py` 按表分组合并因子到单个 FactorStorer，并校验因子名唯一性
- **StrategyDef 同步改造**：`build_dep_sd()`、`_build_factors_for_strategy()`、`compute_max_lookback_sd()` 等镜像逻辑同步改为 DefKey 方案
- **TargetTable 角色变化**：从唯一索引变为分组标签（多个 FactorDef 可共享同一 TargetTable）

## Capabilities

### New Capabilities

- `factor-def-shared-table`: FactorDef 框架支持多个定义文件的因子写入同一张 TargetTable，通过 DefKey（模块路径 + ModelArgs）实现唯一标识和依赖解析

### Modified Capabilities

无现有 spec 需要修改（FactorDef/StrategyDef 尚未有对应的 spec 文件）。

## Impact

- **核心文件**：`QSExt/FactorDef/FactorDefContent.py`（`build_dep_fd`、`_build_factors`、`_ensure`、`compute_max_lookback`）
- **镜像文件**：`QSExt/StrategyDef/StrategyDefContent.py`（`build_dep_sd`、`_build_factors_for_strategy`、`compute_max_lookback_sd`）
- **调用方**：`run_factor_def.py`、`register_factors_to_graphdb.py`、`run_strategy_def.py`、`register_strategies_to_graphdb.py`（FactorStorer 合并逻辑）
- **无 API 破坏**：`build_dep_fd`/`build_dep_sd` 返回值结构不变，`__FACTOR_META__`/`__STRATEGY_META__` 格式不变，现有单模块用法完全兼容
- **QSWeb 无需修改**：`factor_def_context.py` 仅迭代 `factor_defs` 列表，不受 dep_fd key 变更影响
