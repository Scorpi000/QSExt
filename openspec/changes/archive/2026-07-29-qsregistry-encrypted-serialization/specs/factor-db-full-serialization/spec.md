## ADDED Requirements

### Requirement: FactorDB 存储使用完整的 serialize() 输出

`_extractFDBConnection` SHALL 使用 `fdb.serialize()` 的完整输出替代手动挑选字段，仅额外补充 `__module__`（用于 import）。`config_file` 不在 ConnectionJSON 中存储，由 `__QS_Object__.__init__` 按默认路径自动查找配置文件。

`serialize()` 产出的标准结构包含 `__type__`、`__class__`、以及加密后的 `__qsargs__`。

#### Scenario: 存储 JYDB 因子库

- **WHEN** 调用 `registerFactorDB(jydb_instance)` 注册一个 QuantStudio JYDB 因子库
- **THEN** `ConnectionJSON` 包含 `__type__: "__QS_Object__"`、`__class__: "JYDB"`、`__module__: "QuantStudio.Factor.JYDB"`
- **AND** `__qsargs__` 中的敏感字段（如数据库密码）已加密
- **AND** 不包含 `_ConfigFile` 字段

#### Scenario: 存储 SQLite3DB 因子库

- **WHEN** 调用 `registerFactorDB(sqlite3db_instance)` 注册一个 SQLite3DB 因子库
- **THEN** `ConnectionJSON` 包含完整的 `serialize()` 输出 + `__module__`
- **AND** 不再依赖旧的 `{"ClassName": ..., "ModulePath": ..., "ConfigFile": ..., "QSArgs": ...}` 自维护格式

### Requirement: FactorDB 重建使用标准 deserialize()

`_autoBuildFactorDB` SHALL 从 `ConnectionJSON` 解析 `serialize()` 输出，使用 `__QS_ArgClass__.deserialize()` 解密 args（此处有完整 args，可安全校验），再调用构造函数和 `connect()`。

#### Scenario: 自动重建 JYDB 因子库

- **WHEN** 图中有 JYDB 因子库节点且 `ConnectionJSON` 包含完整 `serialize()` 输出
- **THEN** 通过 `__module__` 和 `__class__` 加载类
- **AND** 通过 `__QS_ArgClass__.deserialize(data["__qsargs__"])` 解密并校验 args
- **AND** 调用 `cls(args=decrypted_args)` 构造实例（不传 `config_file`，由 `__init__` 自动查找）
- **AND** 调用 `fdb.connect()` 建立连接

#### Scenario: 旧格式 ConnectionJSON 兼容

- **WHEN** 图中的 `ConnectionJSON` 是旧格式（`{"ClassName": ..., "ModulePath": ..., "ConfigFile": ..., "QSArgs": ...}`）
- **THEN** 自动检测格式：若存在 `__type__` 字段则走新路径，否则走旧路径
- **AND** 两种格式都能正常重建
