# risk-db-full-connection

## Purpose

RiskDB 的 ConnectionJSON 从 `{"type": "..."}` 最小存根补齐为与 FactorDB 一致的完整 `serialize()` 输出，支持自动重建。

## Requirements

### Requirement: RiskDB 存储完整的重建元信息

`registerRiskDB` SHALL 存储与 FactorDB 一致的完整连接信息（`__type__`、`__class__`、`__module__`、加密后的 `__qsargs__`），替代当前的 `{"type": "..."}` 最小存根。

#### Scenario: 存储风险库

- **WHEN** 调用 `registerRiskDB(risk_db_instance)` 注册一个 RiskDB 实例
- **THEN** `ConnectionJSON` 包含 `__type__: "__QS_Object__"`、`__class__`、`__module__`
- **AND** `__qsargs__` 中的敏感字段已加密
- **AND** 格式与 FactorDB 的 ConnectionJSON 一致
- **AND** 不包含 `_ConfigFile` 字段

#### Scenario: 旧格式兼容

- **WHEN** 图中的风险库节点 `ConnectionJSON` 是旧格式 `{"type": "..."}`
- **THEN** 重建时如果缺少必要字段（`ModulePath`、`ClassName`），跳过自动重建
- **AND** 记录警告日志提示用户重新注册该风险库

### Requirement: RiskDB 支持自动重建

RiskDB 的自动重建 SHALL 复用 FactorDB 的重建逻辑：从 `ConnectionJSON` 解析 `serialize()` 输出，使用 `__QS_ArgClass__.deserialize()` 解密 args，再调用构造函数和 `connect()`。

#### Scenario: 自动重建风险库

- **WHEN** 图中有风险库节点且 `ConnectionJSON` 包含完整 `serialize()` 输出
- **THEN** 通过 `__module__` 和 `__class__` 加载类
- **AND** 通过 `__QS_ArgClass__.deserialize(data["__qsargs__"])` 解密 args
- **AND** 调用 `cls(args=decrypted_args)` 构造实例（不传 `config_file`）
- **AND** 调用 `risk_db.connect()` 建立连接
