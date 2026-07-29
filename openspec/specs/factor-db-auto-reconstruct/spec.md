# factor-db-auto-reconstruct

## Purpose

允许 `QSGraphDB.reconstructFactor` 在重建 `FactorTableFactor` 时，从未注册的 FactorDB 图节点元数据自动构建并连接 FactorDB 实例，消除对调用方显式 `registerFactorDB` 的硬依赖。

## Requirements

### Requirement: 因子库节点存储完整重建信息

`registerFactorDB` 写入因子库节点时，SHALL 存储足以重建 FactorDB 实例的元信息，包括类名、模块路径、配置文件路径和完整的非敏感构造参数。

存储信息：
- `ClassName`: FactorDB 子类的类名
- `ModulePath`: 类所在模块的完整路径
- `ConfigFile`: `FactorDB.ConfigFile` 属性值，即该实例关联的配置文件绝对路径
- `QSArgs`: `_QSArgs.model_dump()` 的输出，经过 `_sanitizeForJSON` 处理。利用 Pydantic 原生机制，`Field(exclude=True)` 的字段 MUST NOT 出现在序列化结果中。

#### Scenario: JYDB 注册存储完整信息
- **WHEN** 调用 `registerFactorDB(jydb_instance)`
- **THEN** Neo4j 中对应的 `因子库` 节点的 `ConnectionJSON` 字段包含 `ClassName: "JYDB"`, `ModulePath: "QuantStudio.Factor.JYDB"`, `ConfigFile` 指向 JYDB 配置文件路径, 以及 `QSArgs` 中 `Name`, `DBName` 等非敏感参数
- **AND** `ConnectionJSON` 中不包含 `exclude=True` 的字段（如密码）

#### Scenario: HDF5DB 注册存储 MainDir
- **WHEN** 调用 `registerFactorDB(hdf5db_instance)`
- **THEN** `ConnectionJSON.QSArgs` 中包含 `MainDir` 字段

#### Scenario: exclude=True 字段被排除
- **WHEN** 某 FactorDB 的 `__QS_ArgClass__` 中某字段定义了 `Field(exclude=True)`
- **AND** 调用 `registerFactorDB` 注册该 FactorDB
- **THEN** `ConnectionJSON.QSArgs` 中不包含该字段

### Requirement: reconstructFactor 自动重建未注册的 FactorDB

`_reconstructFactorTableFactor` 在 `_FactorDBRegistry` 中未找到对应 FactorDB 时，SHALL 从图节点的 `ConnectionJSON` 自动构建 FactorDB 实例，调用 `connect()`，并缓存到 `_FactorDBRegistry`。

重建步骤：
1. 从 `ConnectionJSON` 解析 `ClassName`、`ModulePath`、`ConfigFile`、`QSArgs`
2. 通过 `importlib.import_module(ModulePath)` 和 `getattr(module, ClassName)` 获取类
3. 以 `QSArgs` 作为 `args` 参数、`ConfigFile` 作为 `config_file` 参数构造实例
4. 调用 `fdb.connect()`
5. 以 `fdb.Name` 为 key 存入 `_FactorDBRegistry`

#### Scenario: 未注册 JYDB 自动重建成功
- **WHEN** 调用 `reconstructFactor(qsid)` 且目标因子为 FactorTableFactor
- **AND** 因子表关联的 JYDB 因子库未在 `_FactorDBRegistry` 中
- **AND** `ConnectionJSON` 中的 `ConfigFile` 指向有效的 JYDB 配置文件
- **THEN** 系统自动构建 JYDB 实例（传入 `config_file=ConfigFile`）、连接数据库
- **AND** 将实例缓存到 `_FactorDBRegistry`
- **AND** 继续完成因子重建，返回有效的 Factor 对象

#### Scenario: ConfigFile 路径无效时重建失败
- **WHEN** `ConnectionJSON` 中的 `ConfigFile` 指向的文件不存在
- **THEN** 抛出包含明确错误信息的异常，指出缺失的配置文件路径

### Requirement: registerFactorDB 保留显式注入能力

调用方 SHALL 仍可通过 `registerFactorDB` 显式注册 FactorDB 实例。显式注册的实例优先生效：重建时若 `_FactorDBRegistry` 中已存在，MUST 直接使用注册表中的实例，不触发自动构建。

#### Scenario: 显式注册优先于自动构建
- **WHEN** QSWeb 通过 `registerFactorDB` 预先注册了 `"JYDB"` 实例
- **AND** 后续调用 `reconstructFactor` 需要 JYDB
- **THEN** 使用预先注册的实例，不触发自动构建

#### Scenario: 自动构建后再次重建命中缓存
- **WHEN** 首次 `reconstructFactor` 触发了 JYDB 的自动构建并缓存
- **AND** 再次调用 `reconstructFactor` 需要同一 JYDB
- **THEN** 直接使用缓存实例，不重复创建连接
