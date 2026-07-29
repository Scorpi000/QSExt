# qsregistry-factor-db-integration

## Purpose

将因子库连接管理统一到 QSGraphDB 图数据库，以 QSID 为唯一标识，支持完整的 CRUD 和自动重建，替代 QSWebConfig.json 的 factor_dbs 节作为连接配置的存储后端。

## ADDED Requirements

### Requirement: 因子库连接以 QSID 唯一标识

系统 SHALL 在 QSGraphDB 中以 `因子库` 节点的 QSID 属性作为唯一标识，QSID 由 FactorDB 实例的类路径和参数自动生成，相同类型和参数的因子库产生相同 QSID。

#### Scenario: 创建连接生成 QSID
- **WHEN** 用户创建新的因子库连接
- **THEN** 系统先 connect 生成 FactorDB 实例，将其 QSID 作为连接的唯一标识，写入 `因子库` 节点的 QSID 属性

#### Scenario: 阻止创建重复连接
- **WHEN** 用户尝试创建的新连接产生的 QSID 与图中已有 `因子库` 节点的 QSID 相同
- **THEN** 系统拒绝创建，返回错误 "已存在相同配置的因子库连接"，前端弹出消息阻止用户操作，不写入图数据库

### Requirement: 因子库连接 CRUD 通过 QSGraphDB

系统 SHALL 通过 QSGraphDB 的 `因子库` 节点实现因子库连接的完整 CRUD 操作。

#### Scenario: 列出所有因子库
- **WHEN** 前端请求连接列表
- **THEN** 系统调用 QSGraphDB.listFactorDBs() 返回所有 `因子库` 节点的 QSID、Name、DBType、UpdatedAt 等信息

#### Scenario: 获取单个因子库详情
- **WHEN** 前端请求特定因子库详情
- **THEN** 系统调用 QSGraphDB.getFactorDB(qsid) 返回节点属性和连接状态

#### Scenario: 更新因子库连接
- **WHEN** 用户修改因子库的连接参数
- **THEN** 系统用新参数重新 connect；若新 QSID 与旧 QSID 相同则直接更新节点属性；若 QSID 变化则先检查新 QSID 是否冲突、再查询影响范围并要求用户确认，确认后迁移因子表和因子关系到新节点、删除旧节点、更新池中引用

#### Scenario: QSID 变更时检测冲突
- **WHEN** 更新因子库参数导致 QSID 变化，且新 QSID 与图中已有 `因子库` 节点 QSID 相同
- **THEN** 系统拒绝更新，返回错误 "新参数与已有因子库连接（Name: xxx, QSID: yyy）冲突"，用户需调整参数避免冲突

#### Scenario: 删除因子库连接（级联）
- **WHEN** 用户确认级联删除某因子库连接
- **THEN** 系统沿 `(因子表)-[:属于因子库]->(因子库)` 和 `(因子)-[:属于因子表]->(因子表)` 链路级联删除所有依赖节点，再删除 `因子库` 节点自身，断开对应的 FactorDB 实例，清理内存缓存

### Requirement: 删除影响分析

系统 SHALL 在删除因子库前提供受影响的因子和因子表清单。

#### Scenario: 查询影响范围
- **WHEN** 用户请求删除因子库
- **THEN** 系统先查找直接属于该库因子表的因子（`(因子)-[:属于因子表]->(因子表)-[:属于因子库]->(因子库)`），再沿 `[:依赖]` 关系递归查找所有间接依赖这些因子的衍生因子，返回完整的直接+间接受影响因子列表，按因子表分组展示

#### Scenario: 无依赖时直接删除
- **WHEN** 因子库下没有任何因子表或因子
- **THEN** 系统直接删除因子库节点，不弹出影响确认对话框

### Requirement: 从图元数据重建 FactorDB 实例

系统 SHALL 支持从 `因子库` 节点的 ConnectionJSON 属性自动重建并连接 FactorDB 实例。

#### Scenario: 自动重建 FactorDB
- **WHEN** 系统需要访问已注册的因子库（如重建因子时）
- **THEN** 系统从 ConnectionJSON 中提取类路径和 `__qsargs__`，动态 import 类，解密参数，调用 connect()，返回可用的 FactorDB 实例

#### Scenario: 重建时连接不可用
- **WHEN** 从图元数据重建 FactorDB 但物理数据库不可达
- **THEN** 系统返回错误信息指明连接失败原因，不阻塞其他操作

### Requirement: 测试连接不依赖图数据库

系统 SHALL 支持在不存储连接的情况下测试数据库连接可用性。

#### Scenario: 瞬时连接测试
- **WHEN** 用户填写连接参数后点击"测试连接"
- **THEN** 系统创建瞬时数据库连接进行测试，返回成功/失败及详情，不写入图数据库

### Requirement: 连接配置迁移

系统 SHALL 提供 CLI 脚本将 QSWebConfig.json 中的 `factor_dbs` 节迁移到 QSGraphDB。

#### Scenario: 执行迁移
- **WHEN** 用户运行 `python -m QSWeb.scripts.migrate_connections`
- **THEN** 系统遍历 QSWebConfig.json 中的所有连接，逐一创建 FactorDB 实例并注册到 QSGraphDB，完成后备份原 JSON 文件

#### Scenario: 预览迁移
- **WHEN** 用户运行迁移脚本并指定 --dry-run
- **THEN** 系统输出将要迁移的连接列表和对应的 QSID 预览，不执行实际写入
