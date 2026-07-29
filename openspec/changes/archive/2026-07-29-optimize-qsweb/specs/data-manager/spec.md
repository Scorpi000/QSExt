# data-manager (delta)

## MODIFIED Requirements

### Requirement: 因子库连接管理

系统 SHALL 支持用户添加、编辑、删除因子库连接配置，并测试连接可用性。连接配置持久化到 QSGraphDB 图数据库的 `因子库` 节点。

#### Scenario: 添加连接
- **WHEN** 用户填写连接名称、数据库类型（HDF5/ClickHouse/MongoDB/Neo4j/SQL）和参数，点击保存
- **THEN** 系统创建 FactorDB 实例并 connect，将连接元数据写入 QSGraphDB 的 `因子库` 节点，以 FactorDB 实例的 QSID 作为唯一标识，连接列表中显示新连接及其 QSID

#### Scenario: 测试连接
- **WHEN** 用户点击某连接的"测试连接"按钮
- **THEN** 系统根据 `db_type` 创建瞬时数据库连接进行测试，返回成功/失败及详情，不写入图数据库

#### Scenario: 更新连接（QSID 不变）
- **WHEN** 用户修改连接的非关键参数（如 Name、Description），新参数生成的 QSID 与旧 QSID 相同
- **THEN** 系统直接更新图数据库中对应 `因子库` 节点的属性，不弹确认对话框

#### Scenario: 更新连接（QSID 变更需确认）
- **WHEN** 用户修改连接的参数（如 IP、Port、DBName 等影响 QSID 的参数）后点击保存，新参数生成的 QSID 与旧 QSID 不同
- **THEN** 系统先检查新 QSID 是否与已有因子库冲突（冲突则阻止），再查询旧 QSID 的影响范围（与删除时相同的级联分析），弹出确认对话框告知用户"QSID 将从 xxx 变更为 yyy，此操作将影响 N 个因子表、M 个因子"，用户确认后执行变更

#### Scenario: 更新连接（QSID 变更确认后执行）
- **WHEN** 用户在 QSID 变更确认对话框中点击确认
- **THEN** 系统用新参数重新 connect，在图中创建新 `因子库` 节点（新 QSID），将旧节点下的因子表和因子关系迁移到新节点，删除旧 `因子库` 节点，更新全局因子池中所有引用旧 QSID 的 PoolItem 的 conn_id 为新 QSID

#### Scenario: 创建重复连接被阻止
- **WHEN** 用户填写的连接参数与已有因子库产生相同 QSID
- **THEN** 系统返回错误，前端弹出消息提示"已存在相同配置的因子库连接（QSID: xxx），请勿重复创建"，不写入图数据库

#### Scenario: 删除连接
- **WHEN** 用户点击删除某因子库连接
- **THEN** 系统查询图中受该因子库影响的所有因子（通过 `因子表`-[`属于因子库`]->`因子库` 链路），弹出确认对话框列出影响范围（N 个因子表、M 个因子），用户确认后执行级联删除

### Requirement: 因子库删除级联

系统 SHALL 在删除因子库连接时，检测并级联删除图中所有依赖该因子库的因子及相关关系，同时清理全局因子池中的对应项。

#### Scenario: 检测删除影响范围
- **WHEN** 用户请求删除某因子库连接
- **THEN** 系统通过 Cypher 查询该因子库下所有直接因子（`(因子)-[:属于因子表]->(因子表)-[:属于因子库]->(因子库)`），再沿 `(因子)-[:依赖*1..]->` 递归查找所有间接依赖这些因子的衍生因子，返回完整的影响范围（直接因子 + 间接因子），按因子表分组展示

#### Scenario: 用户确认级联删除
- **WHEN** 用户在影响范围确认对话框中点击确认
- **THEN** 系统执行级联删除：移除图中所有受影响因子的 `[:包含]` 关系（从因子池中移除）、删除因子节点、删除因子表节点、删除因子库节点，同时清理全局因子池中的对应 PoolItem 和后端 FactorDB 内存缓存

#### Scenario: 用户取消删除
- **WHEN** 用户在影响范围确认对话框中点击取消
- **THEN** 系统不执行任何删除操作，因子库连接和所有依赖节点保持原状

## ADDED Requirements

### Requirement: 连接 QSID 展示

系统 SHALL 在连接列表中展示每个连接的 QSID 标识。

#### Scenario: 查看连接 QSID
- **WHEN** 用户在连接列表中查看某个连接
- **THEN** 连接卡片显示其 QSID（可复制），用于跨系统引用

## REMOVED Requirements

### Requirement: QSWebConfig.json 持久化

**Reason**: 因子库连接管理已迁移到 QSGraphDB 图数据库作为单一真相源，QSWebConfig.json 的 `factor_dbs` 节不再使用。

**Migration**: 运行 `python -m QSWeb.scripts.migrate_connections` 将已有连接写入 Neo4j。QSWebConfig.json 文件保留用于其他配置节（backtest、reports 等）。
