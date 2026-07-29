## Why

QuantStudio 核心库新增了 `__QS_Object__` 和 `__QS_Args__` 的加密序列化功能（基于 Fernet 对称加密），对标记 `secret=True` 的敏感字段自动加密为 `"ENC:<base64>"` 格式。QSRegistry 当前维护着一套**完全独立**的序列化体系（`_sanitizeForJSON` / `_desanitizeFromJSON`），绕过 QuantStudio 的 `serialize()/deserialize()`，导致：
1. 敏感字段（如数据库密码）以明文存入 Neo4j
2. QSRegistry 与 QuantStudio 核心序列化协议割裂，各自维护重复逻辑
3. RiskDB 的 ConnectionJSON 不完整（仅存 `{"type": "..."}`），无法自动重建

## What Changes

- **存储端**：所有 `_QSArgs.model_dump()` 替换为 `_QSArgs.serialize()`，由 QuantStudio 核心统一处理加密和序列化。FactorDB 和 RiskDB 的连接信息存储从手动挑字段改为完整的 `fdb.serialize()` 输出
- **重建端**：所有 args 反序列化后增加 `__QS_ArgClass__.deserialize()` 解密步骤，统一使用 QuantStudio 标准协议
- **RiskDB**：`registerRiskDB` 的 ConnectionJSON 从 `{"type": "..."}` 补齐为与 FactorDB 一致的完整重建信息（`ModulePath`、`ClassName`、`ConfigFile`、加密后的 `QSArgs`）
- **`_serialization.py`**：`serializeFactorArgs` 和 `serializeOperatorArgs` 改用 `_QSArgs.serialize()`，不再直接 `model_dump()`

## Capabilities

### New Capabilities

- `encrypted-qsargs-storage`: QSRegistry 存储的 QSArgs 使用 QuantStudio 的 `serialize()` 进行加密，`secret=True` 的敏感字段以 `ENC:<base64>` 密文形式存储
- `factor-db-full-serialization`: FactorDB 存储时使用 `__QS_Object__.serialize()` 完整输出替代手动的 `ConnectionJSON`，重建时使用 `__QS_ArgClass__.deserialize()` 解密
- `risk-db-full-connection`: RiskDB 的 ConnectionJSON 补齐为与 FactorDB 一致的完整重建元信息，支持自动重建

### Modified Capabilities

（无现有 specs，不需要 delta spec）

## Impact

- **QSExt/QSRegistry/QSGraphDB.py**：~15 处存储/重建代码修改（因子库、风险库、因子表、回测、风险表、优化器的存储；因子、算子、因子库的反序列化重建）
- **QSExt/QSRegistry/_serialization.py**：`serializeFactorArgs` 和 `serializeOperatorArgs` 实现调整
- **不兼容变更**：无。`decrypt_value()` 对非 `ENC:` 前缀的值透传，旧 Neo4j 数据完全兼容
