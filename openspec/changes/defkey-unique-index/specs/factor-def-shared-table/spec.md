## ADDED Requirements

### Requirement: Multiple modules can write to the same TargetTable

FactorDef 框架 SHALL 允许多个定义模块将因子写入同一张 TargetTable。
`dep_fd` 字典以 DefKey（`module.__file__` 文件系统绝对路径 + ModelArgs 的组合标识）作为唯一键，
而非 TargetTable。相同文件 + 相同 ModelArgs 仍会去重（视为重复定义）；
不同文件或不同 ModelArgs 即使 TargetTable 相同也各自独立执行。

#### Scenario: Two modules declare the same TargetTable with different factor names

- **WHEN** 模块 A 声明 `TargetTable: "stock_cn_factor"` 并定义因子 `["momentum", "volatility"]`
- **AND** 模块 B 声明 `TargetTable: "stock_cn_factor"` 并定义因子 `["pe_ttm", "pb"]`
- **THEN** `build_dep_fd` 对两个模块均调用其 `defFactor`
- **AND** `dep_fd` 包含两个条目（key 分别为 A 和 B 的 DefKey）
- **AND** `run_factor_def.py` 创建一个合并的 FactorStorer，包含全部 4 个因子

#### Scenario: Two modules declare the same TargetTable with conflicting factor names

- **WHEN** 模块 A 定义因子 `["momentum"]` 写入 `TargetTable: "stock_cn_factor"`
- **AND** 模块 B 也定义因子 `["momentum"]` 写入 `TargetTable: "stock_cn_factor"`
- **THEN** `run_factor_def.py` 在校验阶段抛出 `ValueError`，提示表内因子名重复

#### Scenario: Same module with different ModelArgs writes to the same table

- **WHEN** 同一模块以 `ModelArgs: {"lookback": 20}` 和 `ModelArgs: {"lookback": 60}` 分别配置
- **AND** 两次配置均声明 `TargetTable: "stock_cn_factor"`
- **THEN** `dep_fd` 包含两个条目（DefKey 因 ModelArgs 不同而不同）
- **AND** 两个实例的 `defFactor` 均被独立调用

### Requirement: FactorDeps resolution uses DefKey lookup

`_build_factors()` 和 `compute_max_lookback()` SHALL 通过 `_dep_key_to_def_key()`
将 FactorDeps 声明的模块路径映射到 `dep_fd` 中的 DefKey，而非假设 FactorDeps key
等于 TargetTable。

#### Scenario: FactorDeps key differs from TargetTable

- **WHEN** 模块 A 文件路径为 `D:\factors\my_status.py`，声明 `TargetTable: "custom_status_table"`
- **AND** 模块 B 声明 `FactorDeps: {"my_status": ["is_listed"]}`（通过 `resolve_dep_module` 解析到模块 A）
- **THEN** `_dep_key_to_def_key("my_status", dep_fd)` 通过 import 模块 A 获取其 `__file__` 并匹配到 DefKey
- **AND** `_build_factors` 正确从模块 A 的 FactorDef 中提取 `is_listed` 因子

#### Scenario: Same file loaded differently resolves to same DefKey

- **WHEN** 模块 A 通过 `importlib.import_module` 加载，`__name__` 为 `"pkg.status"`
- **AND** 同一文件通过 `spec_from_file_location` 加载，`__name__` 为 `"_qsweb_fd_status"`
- **THEN** `make_def_key` 对两次加载返回相同的 DefKey（均基于 `__file__` 绝对路径）

### Requirement: StrategyDef mirrors the same DefKey pattern

StrategyDef 框架 SHALL 与 FactorDef 一致：`dep_sd` 以 DefKey 为键，
`build_dep_sd()` 中的去重、存储、StrategyDeps 解析、`compute_max_lookback_sd()`
均使用 DefKey 和 `_dep_key_to_def_key()` 替代原 TargetTable 逻辑。

#### Scenario: Two strategy modules write to the same TargetTable

- **WHEN** 策略模块 A 和 B 均声明 `TargetTable: "strategy_signals"`
- **THEN** `build_dep_sd` 对两个模块均调用 `defStrategy`
- **AND** `dep_sd` 包含两个条目，key 分别为各自的 DefKey

#### Scenario: StrategyDeps resolution after DefKey change

- **WHEN** 策略模块 C 声明 `StrategyDeps: {"module_a": {"signal_x": "alias_x"}}`
- **THEN** `build_dep_sd` 通过 `_dep_key_to_def_key("module_a", dep_sd)` 找到模块 A 的 StrategyDef
- **AND** 正确提取 `signal_x` 并注入为 `alias_x`

### Requirement: Backward compatibility for single-module usage

现有单模块→单表的 FactorDef/StrategyDef 使用方式 SHALL 完全不受影响。
`__FACTOR_META__` / `__STRATEGY_META__` 字段不变，`build_dep_fd` / `build_dep_sd`
返回值结构不变，现有因子定义脚本无需任何修改。

#### Scenario: Single module unchanged after migration

- **WHEN** 一个现有因子定义模块（单模块单表，无 ModelArgs）通过 `build_dep_fd` 运行
- **THEN** `dep_fd` 包含一个条目，key 为 `module.__file__` 的绝对路径（即 DefKey）
- **AND** `requested` 列表返回该模块的 `FactorDef`，行为与改造前一致
