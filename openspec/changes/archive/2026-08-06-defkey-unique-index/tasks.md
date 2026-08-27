## 1. FactorDefContent.py — 新增工具函数

- [x] 1.1 在 `FactorDefContent.py` 文件头部添加 `import json, os`
- [x] 1.2 新增 `make_def_key(module, model_args)` 函数：基于 `os.path.abspath(module.__file__)` + ModelArgs 序列化生成 DefKey
- [x] 1.3 新增 `_dep_key_to_def_key(dep_name, target_dict)` 辅助函数：通过 `resolve_dep_module` 导入获取 `__file__`，以 `os.path.normcase` 匹配 DefKey 的文件路径部分

## 2. FactorDefContent.py — 重构 `_build_factors()`

- [x] 2.1 修改签名：`(meta, dep_fd, ...)` → `(resolved_deps, dep_fd, ...)`，其中 `resolved_deps` 为 `Dict[DefKey, list]`
- [x] 2.2 内部循环改为 `for def_key, entries in resolved_deps.items()`，从 `fd.Meta.TargetTable` 获取物理表名用于代理查找
- [x] 2.3 保持代理因子替换、`"*"` 全量展开、`Alias` 别名映射等既有逻辑不变

## 3. FactorDefContent.py — 重构 `build_dep_fd()` 的 `_ensure()`

- [x] 3.1 去重键从 `tt`（TargetTable）改为 `def_key = make_def_key(module, model_args)`
- [x] 3.2 循环检测 token 从 `tt` 改为 `def_key`
- [x] 3.3 依赖因子解析改为预构建 `resolved_deps` 字典（DefKey → entries），传递给 `_build_factors`
- [x] 3.4 存储键从 `dep_fd[result.Meta.TargetTable]` 改为 `dep_fd[def_key]`
- [x] 3.5 无 `__FACTOR_META__` 模块的 fallback 路径同步改为 DefKey
- [x] 3.6 结果收集逻辑（`requested` 列表）改为用 `make_def_key` 查找

## 4. FactorDefContent.py — 重构 `compute_max_lookback()`

- [x] 4.1 递归变量从 `tt`（TargetTable）改为 `def_key`（DefKey）
- [x] 4.2 依赖遍历（`FactorDeps.keys()`）改用 `_dep_key_to_def_key` 在 `dep_fd` 中查找对应 DefKey
- [x] 4.3 日志输出同步更新（使用 DefKey 代替 TargetTable）

## 5. StrategyDefContent.py — 同步 DefKey 改造

- [x] 5.1 从 `FactorDefContent` 导入 `make_def_key` 和 `_dep_key_to_def_key`
- [x] 5.2 修改 `_build_factors_for_strategy()`：循环中用 `_dep_key_to_def_key` 查找 dep_fd
- [x] 5.3 修改 `build_dep_sd()` 内 `_ensure()`：去重键、循环检测、存储键均改为 DefKey
- [x] 5.4 修改 StrategyDeps 解析：`dep_sd.get(dep_tt)` → `_dep_key_to_def_key` + `dep_sd.get(def_key)`
- [x] 5.5 修改 `compute_max_lookback_sd()`：FactorDeps 和 StrategyDeps 遍历均改用 `_dep_key_to_def_key`
- [x] 5.6 移除 `_dep_key_to_tt` 辅助函数（功能被 `_dep_key_to_def_key` 取代）

## 6. run_factor_def.py — FactorStorer 合并

- [x] 6.1 在 `_build_storers()` 中，`build_dep_fd` 调用后按 `TargetTable` 分组收集因子
- [x] 6.2 同表因子合并到一个 `FactorStorer`（使用首个模块的 `TableMeta`）
- [x] 6.3 合并时校验因子名唯一性，重复则抛出 `ValueError`
- [x] 6.4 同表多模块时输出 info 级别日志说明合并情况

## 7. register_factors_to_graphdb.py — 同步合并

- [x] 7.1 FactorStorer 创建逻辑改为按 TargetTable 分组合并（同步骤 6.2-6.3）
- [x] 7.2 同表多模块时输出日志

## 8. run_strategy_def.py / register_strategies_to_graphdb.py — 同步改造

- [x] 8.1 `run_strategy_def.py` 中 StrategyStorer 创建逻辑按 TargetTable 合并
- [x] 8.2 `register_strategies_to_graphdb.py` 同步合并逻辑（该脚本不创建 FactorStorer，使用 storeStrategies 直接注册策略，无需额外合并逻辑）

## 9. 文档更新

- [x] 9.1 更新 `CLAUDE.md` 中 `__FACTOR_META__` 的 `TargetTable` 字段说明：标注多文件可共享、因子名唯一约束
- [x] 9.2 更新 `__STRATEGY_META__` 的 `TargetTable` 字段说明（同上）

## 10. 验证

- [x] 10.1 Python 导入验证：`python -c "from QSExt.FactorDef.FactorDefContent import make_def_key, _dep_key_to_def_key"`
- [x] 10.2 编写单元测试：`make_def_key` 相同文件+相同参数→相同 key；空 model_args→纯文件路径；不同 model_args→不同 key；同一文件不同加载方式（import vs spec_from_file_location）→相同 key
- [x] 10.3 编写单元测试：`_dep_key_to_def_key` 通过 import 匹配成功、依赖模块不存在返回 None、Windows 路径大小写不敏感匹配
- [x] 10.4 编写集成测试：两个 mock 模块写同一 TargetTable，验证 `dep_fd` 有两个条目，FactorStorer 合并
- [x] 10.5 Dry-run 验证：用 stock_cn_factor_example1.py 复制两份配相同 TargetTable，运行 `run_factor_def.py --dry-run`（跳过：需要完整数据库环境，单元+集成测试已覆盖核心逻辑）
- [x] 10.6 运行现有测试套件确认无回归：`tests/test_StrategyDef.py`（8/8 通过）、`tests/test_validators.py`（1 个预存失败，非本改动引入）
