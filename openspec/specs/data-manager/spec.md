# data-manager

## Purpose

QSWeb 数据管理模块，支持用户管理因子库连接（以 QSGraphDB 为存储后端、QSID 为标识）、浏览因子树形结构、预览数据以及编辑因子表和因子的元数据。

## Requirements

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
- **THEN** 系统直接更新图数据库中对应 `因子库` 节点的属性

#### Scenario: 更新连接（QSID 变更需确认）
- **WHEN** 用户修改连接的参数（如 IP、Port 等影响 QSID 的参数）后点击保存，新参数生成的 QSID 与旧 QSID 不同
- **THEN** 系统先检查新 QSID 是否与已有因子库冲突，再查询旧 QSID 的影响范围，弹出确认对话框告知影响范围，用户确认后执行变更

#### Scenario: 创建重复连接被阻止
- **WHEN** 用户填写的连接参数与已有因子库产生相同 QSID
- **THEN** 系统返回错误，前端弹出消息提示"已存在相同配置的因子库连接"，不写入图数据库

#### Scenario: 删除连接（级联确认）
- **WHEN** 用户点击删除某因子库连接
- **THEN** 系统调用 `getImpact` 查询受影响的因子表和因子，弹出确认对话框列出影响范围（因子表、直接因子、间接因子、影响总数），用户确认后执行级联删除

#### Scenario: 连接列表中展示 QSID
- **WHEN** 用户在连接列表中查看某个连接
- **THEN** 连接卡片显示其 QSID（可选中复制），用于跨系统引用

### Requirement: 因子库删除级联

系统 SHALL 在删除因子库连接时，检测并级联删除图中所有依赖该因子库的因子及相关关系。

#### Scenario: 检测删除影响范围
- **WHEN** 用户请求删除某因子库连接
- **THEN** 系统通过 Cypher 查询该因子库下所有直接因子，再沿 `[:依赖]` 关系递归查找间接依赖的衍生因子，返回完整影响范围

#### Scenario: 用户取消删除
- **WHEN** 用户在影响范围确认对话框中点击取消
- **THEN** 系统不执行任何删除操作，因子库连接和所有依赖节点保持原状

### Requirement: 因子树浏览

系统 SHALL 支持用户通过树形结构浏览 FactorDB → FactorTable → Factor 层级，并支持延迟加载。

#### Scenario: 展开因子库节点
- **WHEN** 用户点击因子库节点的展开箭头
- **THEN** 系统调用 `db.TableNames` 获取因子表列表，填充子节点

#### Scenario: 展开因子表节点
- **WHEN** 用户点击因子表节点的展开箭头
- **THEN** 系统调用 `ft.FactorNames` 获取因子列表，填充子节点

#### Scenario: 右键菜单操作
- **WHEN** 用户右键点击因子表或因子节点
- **THEN** 显示上下文菜单（重命名、删除、批量删除等操作）

### Requirement: 数据预览

系统 SHALL 支持用户选中因子后在右侧预览面板中查看因子数据。

#### Scenario: 查看因子数据
- **WHEN** 用户点击因子节点
- **THEN** 系统调用 `ft.readData()` 读取数据，在 DataGrid 表格中展示，支持分页

#### Scenario: 设置日期/ID 范围
- **WHEN** 用户设置起止日期和 ID 过滤条件后点击查询
- **THEN** 系统按条件过滤数据并刷新表格

### Requirement: 元数据编辑

系统 SHALL 支持用户查看和编辑因子表、因子的元数据。

#### Scenario: 编辑因子元数据
- **WHEN** 用户打开元数据编辑器，修改键值对后点击保存
- **THEN** 系统调用 `ft.setFactorMetaData()` 持久化变更

### Requirement: 因子表/因子管理

系统 SHALL 支持用户重命名、删除因子表和因子。

#### Scenario: 重命名因子表
- **WHEN** 用户右键因子表，选择重命名，输入新名称
- **THEN** 系统调用 `db.renameTable()` 完成重命名，树节点刷新
