## 1. _serialization.py — 序列化函数改造

- [x] 1.1 `serializeFactorArgs` 改用 `factor._QSArgs.serialize()` 替代 `factor._QSArgs.model_dump()`，在 sanitize 前完成加密
- [x] 1.2 `serializeOperatorArgs` 对 `operator._QSArgs.ModelArgs` 走 `_QSArgs.serialize()` 路径（注意 ModelArgs 是 dict 子字段，需要走 `__QS_ArgClass__.serialize()` 而非简单调用）

## 2. FactorDB — 存储与重建全面改造

- [x] 2.1 `_extractFDBConnection` 改为返回 `fdb.serialize()` 完整输出，额外补充 `__module__` 和 `_ConfigFile`
- [x] 2.2 `_autoBuildFactorDB` 改为从 `serialize()` 格式解析：加载类 → `__QS_ArgClass__.deserialize()` 解密 → `cls(args=..., config_file=...)` → `connect()`
- [x] 2.3 在 `_autoBuildFactorDB` 中加入旧格式兼容逻辑：检测 `__type__` 字段区分新旧格式，旧格式走原路径

## 3. RiskDB — 对齐 FactorDB 的存储与重建

- [x] 3.1 `registerRiskDB` 的 `ConnectionJSON` 改为与 FactorDB 一致的完整 `serialize()` 输出（`__type__`、`__class__`、`__module__`、`__qsargs__`、`_ConfigFile`）
- [x] 3.2 新增 `_autoBuildRiskDB` 方法或在现有重建路径中支持 RiskDB 自动重建，复用与 FactorDB 相同的 `deserialize()` 逻辑

## 4. 因子和算子节点 — QSArgs/model_args 加密存储

- [x] 4.1 `_serializeFactor` 中 `QSArgsJSON` 走 `serializeFactorArgs`（已由 1.1 覆盖，此处确认调用路径正确）
- [x] 4.2 `_serializeOperatorNode` 中 `ModelArgsJSON` 走 `serializeOperatorArgs`（已由 1.2 覆盖，此处确认调用路径正确）

## 5. Factor/Operator 重建 — deserialize() 解密

- [x] 5.1 `_reconstructDataFactor` 在 `_desanitizeFromJSON(args)` 后增加 `DataFactor.__QS_ArgClass__.deserialize(args).model_dump()` 解密步骤
- [x] 5.2 `_reconstructDerivativeFactor` 在 args 反序列化后增加对应 `__QS_ArgClass__.deserialize()` 解密步骤
- [x] 5.3 `_reconstructFactorTableFactor` 在 args 反序列化后增加对应 `__QS_ArgClass__.deserialize()` 解密步骤
- [x] 5.4 `reconstructOperator` 在 `ModelArgsJSON` 反序列化后增加算子 `__QS_ArgClass__.deserialize()` 解密 ModelArgs

## 6. 其他节点类型 — QSArgsJSON 加密存储

- [x] 6.1 `storeFactorTable` 中 `QSArgsJSON` 改用 `_sanitizeForJSON(ft._QSArgs.serialize())`
- [x] 6.2 `storeBacktest` 中 `QSArgsJSON` 改用 `_sanitizeForJSON(bt_node._QSArgs.serialize())`
- [x] 6.3 `storeRiskTable` 中 `QSArgsJSON` 改用 `_sanitizeForJSON(rt._QSArgs.serialize())`
- [x] 6.4 `storeOptimizer`（组合优化器）中 `QSArgsJSON` 改用 `_sanitizeForJSON(pc._QSArgs.serialize())`

## 7. 测试验证

- [x] 7.1 补充或更新单元测试：验证 `serializeFactorArgs` 产出加密字段
- [x] 7.2 补充或更新单元测试：验证 `serializeOperatorArgs` 产出加密字段（如有 secret 字段）
- [x] 7.3 补充或更新单元测试：验证 FactorDB 存储-重建完整闭环（含加密字段）
- [x] 7.4 补充或更新单元测试：验证旧格式兼容性（无 `ENC:` 前缀的数据正常反序列化）
- [x] 7.5 补充或更新单元测试：验证 RiskDB 存储-重建闭环
- [x] 7.6 补充或更新单元测试：验证 Factor/Operator 重建路径的 deserialize 解密

## 8. 集成验证

- [x] 8.1 运行现有测试套件确保无回归：`python -m pytest tests/test_QSGraphDB.py -v`
- [x] 8.2 手动验证：注册含 secret 字段的 FactorDB → 检查 Neo4j 中 ConnectionJSON 含 `ENC:` 前缀 → 重建 FactorDB 并 connect 成功
