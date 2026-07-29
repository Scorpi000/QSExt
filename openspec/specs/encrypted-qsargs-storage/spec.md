# encrypted-qsargs-storage

## Purpose

QSRegistry 中所有存储到 Neo4j 的 `__QS_Args__` 参数使用 QuantStudio 核心的 `serialize()`/`_decryptArgs()` 进行加密存储和解密重建，替代原有的明文 `model_dump()`。

## Requirements

### Requirement: 存储时对 QSArgs 敏感字段加密

QSRegistry 在将 `__QS_Args__` 存储到 Neo4j 时，SHALL 使用 `__QS_Args__.serialize()` 方法替代直接 `model_dump()`。该方法对标记 `secret=True` 的 Field 值使用 Fernet 加密，输出 `"ENC:<base64>"` 格式的密文字符串。

加密后的值在 `_sanitizeForJSON` 中作为普通字符串透传，不产生额外的包装。

#### Scenario: 因子库 QSArgs 包含数据库密码

- **WHEN** FactorDB 的 `__QS_ArgClass__` 中某个 Field 标记了 `json_schema_extra={"secret": True}`（例如数据库连接密码）
- **THEN** 存储到 Neo4j 时，该字段的值呈现为 `"ENC:gAAAAAB..."` 格式
- **AND** 非 secret 字段保持原值不变

#### Scenario: 算子 ModelArgs 不含敏感字段

- **WHEN** FactorOperator 的 `ModelArgs` 中没有任何 secret 字段
- **THEN** `serialize()` 对所有字段原样透传
- **AND** 存储格式与旧版一致（无 `ENC:` 前缀出现）

### Requirement: 重建时自动解密 QSArgs

QSRegistry 在从 Neo4j 重建对象时，SHALL 在 `_desanitizeFromJSON` 后对参数进行解密：

- **Factor 和 FactorOperator 重建**：使用 `_decryptArgs()` 逐字段调用 `decrypt_value()` 解密，不构造 ArgClass 实例（因存储时排除了 `Operator` 等字段，ArgClass 的 pydantic 校验会失败）
- **FactorDB 和 RiskDB 重建**：使用 `__QS_ArgClass__.deserialize()` 完整解密并校验（因存储了完整的 args）

#### Scenario: 解密包含加密字段的 args

- **WHEN** 从 Neo4j 读取的 QSArgsJSON 包含 `"ENC:gAAAAAB..."` 格式的值
- **THEN** `_decryptArgs()` 使用 `decrypt_value()` 解密该字段
- **AND** 解密后的明文正确传入对象构造函数

#### Scenario: 旧数据不含加密字段

- **WHEN** 从 Neo4j 读取的 QSArgsJSON 中所有值都是明文（无 `ENC:` 前缀）
- **THEN** `decrypt_value()` 对所有字段透传
- **AND** 对象正常重建，行为与升级前一致

### Requirement: Factor 节点存储时使用 serialize()

`serializeFactorArgs` SHALL 使用 `factor._QSArgs.serialize()` 替代 `factor._QSArgs.model_dump()`，在 sanitize 前完成加密。

#### Scenario: DataFactor 存储

- **WHEN** 调用 `serializeFactorArgs(data_factor)` 序列化一个 DataFactor
- **THEN** 返回的 JSON 字符串中 `QSArgsJSON` 包含加密后的敏感字段
- **AND** `Operator` 和 `Meta` 字段照常排除（它们通过图关系单独存储）

#### Scenario: DerivativeFactor 存储

- **WHEN** 调用 `serializeFactorArgs(derivative_factor)` 序列化一个 DerivativeFactor
- **THEN** 返回的 JSON 字符串中 `QSArgsJSON` 包含加密后的敏感字段
- **AND** `Operator` 被排除（通过 `USES_OPERATOR` 关系存储）

### Requirement: Operator 节点存储时使用 serialize()

`serializeOperatorArgs` SHALL 对 `operator._QSArgs.serialize()` 结果提取 `ModelArgs` 子集，在 sanitize 前完成加密。

#### Scenario: 算子 ModelArgs 存储

- **WHEN** 调用 `serializeOperatorArgs(operator)` 序列化一个 FactorOperator
- **THEN** 返回的 JSON 字符串中 `ModelArgsJSON` 包含加密后的敏感字段
- **AND** 非敏感字段保持原样

### Requirement: Factor 重建时解密 QSArgs

所有 Factor 重建方法（`_reconstructDataFactor`、`_reconstructDerivativeFactor`、`_reconstructFactorTableFactor`）SHALL 在反序列化 args 后使用 `_decryptArgs()` 解密。

#### Scenario: 重建 DataFactor

- **WHEN** 调用 `_reconstructDataFactor` 从图数据重建 DataFactor
- **THEN** 从 `QSArgsJSON` 反序列化后调用 `_decryptArgs()` 解密
- **AND** 解密后的 args 传入 `DataFactor(data=..., args=decrypted_args)`

#### Scenario: 重建 DerivativeFactor

- **WHEN** 调用 `_reconstructDerivativeFactor` 重建衍生因子
- **THEN** 算子先于因子重建（维持拓扑顺序）
- **AND** args 经由 `_decryptArgs()` 解密
- **AND** 解密后的 args 合并 `Operator` 后传入算子调用

### Requirement: Operator 重建时解密 ModelArgs

`reconstructOperator` SHALL 在反序列化 `ModelArgsJSON` 后使用 `_decryptArgs()` 解密 ModelArgs。

#### Scenario: 重建算子

- **WHEN** 调用 `reconstructOperator(qsid)` 从图数据重建算子
- **THEN** `ModelArgsJSON` 经 `_desanitizeFromJSON` 还原后
- **AND** 调用 `_decryptArgs()` 解密
- **AND** 解密后的 ModelArgs 与 `Name`、`DataType`、`Arity` 等组装为完整 args 传入 `op_class(args=...)`
