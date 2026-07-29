# data-manager

## Purpose

QSWeb 数据管理模块，支持用户管理因子库连接、浏览因子树形结构、预览数据以及编辑因子表和因子的元数据。

## Requirements

### Requirement: 因子库连接管理

系统 SHALL 支持用户添加、编辑、删除因子库连接配置，并测试连接可用性。

#### Scenario: 添加连接
- **WHEN** 用户填写连接名称、数据库类型（HDF5/ClickHouse/MongoDB/Neo4j/SQL）和参数，点击保存
- **THEN** 系统创建连接配置并持久化到 `QSWebConfig.json`，连接列表中显示新连接

#### Scenario: 测试连接
- **WHEN** 用户点击某连接的"测试连接"按钮
- **THEN** 系统根据 `db_type` 调用对应的驱动进行实际连接测试，返回成功/失败及详情

#### Scenario: 删除连接
- **WHEN** 用户确认删除某连接
- **THEN** 系统移除配置并断开对应的 FactorDB 实例

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
