## Context

FactorDef/StrategyDef 框架通过 `build_dep_fd()`/`build_dep_sd()` 预构建依赖关系图。当前内部字典 `dep_fd: Dict[str, FactorDef]` 以 `__FACTOR_META__["TargetTable"]` 作为 key，存在两个层面的设计缺陷：

1. **key 语义混淆**：`dep_fd` 的 key 是 TargetTable（物理表名），而 `FactorDeps` 声明的 key 是模块路径（用于 `resolve_dep_module` 导入）。`_build_factors()` 和 `compute_max_lookback()` 中直接用 FactorDeps key 查找 `dep_fd`，依赖"模块路径 == TargetTable"这一未文档化的约定。
2. **去重粒度过粗**：`_ensure()` 以 TargetTable 去重（`if tt in dep_fd: return`），阻止多个模块公平地写入同一张表。

调查确认：底层 HDF5DB 以独立文件存储每个因子（`{table}/{factor}.hdf5`），有 per-factor 级锁，多模块写入同一表在存储层面安全。Neo4j 对 TargetTable 仅有索引、无唯一约束，多 FactorStorer 节点指向同一 FactorTable 节点在图层面上安全。

## Goals / Non-Goals

**Goals:**
- 允许多个 FactorDef 定义文件将因子写入同一张 TargetTable
- 允许多个 StrategyDef 定义文件将策略信号写入同一张 TargetTable
- 消除"模块路径 == TargetTable"的隐式约定，建立正确的两层映射（FactorDeps key → 模块对象 → DefKey → FactorDef）
- 保持完全向后兼容：现有单模块用法不受影响
- 同一 TargetTable 内因子名不重复时自动合并

**Non-Goals:**
- 不改变 `__FACTOR_META__` / `__STRATEGY_META__` 的对外字段
- 不改变 `build_dep_fd` / `build_dep_sd` 的返回值类型
- 不改变因子数据的物理存储格式
- 不引入新的配置文件或用户可见概念（DefKey 为框架内部实现细节）

## Decisions

### 1. DefKey 标识符：`module.__file__` 而非 `module.__name__`

**选择**：使用 `os.path.abspath(module.__file__)`（文件系统绝对路径）作为 DefKey 的模块标识部分

**替代方案及其权衡**：
- `module.__name__`（Python 导入路径）：QSWeb 通过 `spec_from_file_location` 加载时 `__name__` 变为合成名（如 `_qsweb_fd_example_factor`），无法唯一标识源文件；`__main__` 更无法使用
- `module.__file__`：加载方式无关——`import`、`spec_from_file_location`、直接运行都指向同一个 `.py` 文件。与 `__FACTOR_META__["DefScriptPath"]` 语义一致。少数模块 `__file__` 可能为 `None`（如内置模块），FactorDef 场景不会遇到

### 2. DefKey 格式：完整序列化而非哈希摘要

**选择**：`f"{os.path.abspath(module.__file__)}@{json.dumps(model_args, sort_keys=True)}"`（model_args 为空时省略 `@...` 部分）

**替代方案及其权衡**：
- MD5 前 8 位：有生日碰撞风险（4B 空间），被否决
- 完整 SHA256：过于冗长，无必要
- 完整 JSON 拼接：零碰撞风险，可逆（从 DefKey 可还原参数），最透明。DefKey 是内部字典键不面向用户，长度不构成问题

### 3. 依赖查找：`_dep_key_to_def_key()` 通过 import 解析

**选择**：新增 `_dep_key_to_def_key(dep_name, target_dict)`，内部调用 `resolve_dep_module` 导入依赖模块获取 `__file__`，再与 DefKey 的文件路径部分做 `os.path.normcase` 匹配

**替代方案及其权衡**：
- 维护反向索引 `Dict[dep_name, DefKey]`：需要额外状态，且同一模块以不同 ModelArgs 多次调用时索引会被覆盖
- 在 `_ensure` 中内联依赖解析：破坏了 `_build_factors` 的可复用性，且 `_build_factors_for_strategy` 仍需类似逻辑
- 通过 import 获取 `__file__` 后匹配：利用已有的 `resolve_dep_module`，`dep_fd` 通常 < 100 条目，线性扫描性能无影响；`os.path.normcase` 确保 Windows 大小写不敏感匹配

### 4. `_build_factors` 签名变更：接受预解析的 `resolved_deps`

**选择**：签名从 `(meta, dep_fd, fdi, ...)` 改为 `(resolved_deps, dep_fd, fdi, ...)`，由调用方（`_ensure`）负责将 FactorDeps 的 key（模块路径）解析为 DefKey

**理由**：`_build_factors` 不应知晓模块解析逻辑（那是 `resolve_dep_module` 的职责）。接收预解析的映射使其职责单一——仅做因子提取和代理替换。

### 5. FactorStorer 合并策略

**选择**：在 `run_factor_def.py` / `register_factors_to_graphdb.py` 中按 TargetTable 分组合并因子列表，创建单个 FactorStorer

**替代方案**：每个模块各创建独立 FactorStorer——虽存储层安全，但 metadata 写入会有竞争（最后一个写入者获胜），且 Neo4j 中产生冗余的 FactorStorer 节点

### 6. 因子名唯一性校验：硬错误

**选择**：合并时检测同表内因子名重复，抛出 `ValueError`

**理由**：同表内因子名重复一定是配置错误，静默覆盖会导致非预期的数据丢失。这符合 Python 之禅"错误不应静默传递"。

## Risks / Trade-offs

- **[风险] DefKey 包含完整 ModelArgs，当 ModelArgs 较大时 key 较长** → 缓解：仅作为 Python dict key 使用，不持久化，不影响性能；绝大多数场景 ModelArgs 为空或很小
- **[风险] `_dep_key_to_def_key` 需要 import 依赖模块来获取 `__file__`** → 缓解：仅在 `compute_max_lookback` 等构建阶段调用（非热路径），且依赖模块本身已在 `_ensure` 中被 import 过，Python 的 `sys.modules` 缓存使重复导入几乎零开销
- **[权衡] 因子名冲突改为硬错误可能影响现有配置** → 缓解：仅在新场景（多模块写同一表）下才可能触发；单模块场景不存在自冲突

## Open Questions

无。方案已在代码审查中完整验证。
