# global-factor-pool

## Purpose

提供跨页面共享的全局因子池，用户可以从 FactorDB 或 QSRegistry 双源添加因子到池中，在回测、组合优化、报告中心等页面间复用已选因子。池子可选持久化到 QSGraphDB 图数据库。

## ADDED Requirements

### Requirement: 全局因子池跨页面共享

系统 SHALL 在前端维护一个全局因子池 Zustand store，所有页面读取同一个池子实例，池中因子的增删在所有页面间即时同步。

#### Scenario: 在回测页面向池中添加因子
- **WHEN** 用户在回测工作台打开 FactorDiscover，从因子库浏览并添加因子到池中
- **THEN** 该因子立即出现在所有页面的 FactorPoolPanel 中

#### Scenario: 在其他页面使用池中因子
- **WHEN** 用户导航到组合优化页面
- **THEN** FactorPoolPanel 展示与回测工作台相同池中因子列表，用户可直接选择使用

### Requirement: 双源因子添加

系统 SHALL 支持从 FactorDB（因子库直接连接）和 QSRegistry（图数据库搜索）两个来源添加因子到池中。

#### Scenario: 从 FactorDB 添加因子
- **WHEN** 用户在 FactorDiscover 中选择 FactorDB Tab，依次选择连接、因子表、因子
- **THEN** 系统将因子加入池中，PoolItem 的 source 标记为 "db"，包含 conn_id、table_name、factor_name 引用信息

#### Scenario: 从 QSRegistry 添加因子
- **WHEN** 用户在 FactorDiscover 中切换到 QSRegistry Tab，搜索并选择因子
- **THEN** 系统将因子加入池中，PoolItem 的 source 标记为 "registry"，以 QSID 作为标识

#### Scenario: 去重检查
- **WHEN** 用户尝试添加一个已存在于池中的因子（相同 source + qsid）
- **THEN** 系统提示"该因子已在池中"，不重复添加

### Requirement: 因子池管理

系统 SHALL 支持用户查看池中因子、选中/取消选中、移除因子。

#### Scenario: 选中因子用于当前页面功能
- **WHEN** 用户在 FactorPoolPanel 中勾选因子
- **THEN** 被选中的因子关联到当前页面的功能（如回测模块配置、优化输入等）

#### Scenario: 从池中移除因子
- **WHEN** 用户点击池中某因子的删除按钮
- **THEN** 该因子从池中移除，所有页面的 FactorPoolPanel 同步更新

### Requirement: 因子池持久化到图数据库

系统 SHALL 支持用户将当前因子池保存到 QSGraphDB 图数据库，通过 `因子池` 节点与 `因子` 节点的 `[包含]` 关系持久化。

#### Scenario: 保存因子池
- **WHEN** 用户点击"保存池子"按钮并输入名称
- **THEN** 系统在图数据库中 MERGE `因子池` 节点（Name 为输入名称），对池中每个因子建立 `[:包含]->(:因子 {QSID})` 关系

#### Scenario: 加载已保存的因子池
- **WHEN** 用户选择加载一个已保存的池子
- **THEN** 系统从图中读取该池子的 `[:包含]` 关系，获取所有关联因子的 QSID，在池中恢复这些因子

#### Scenario: 恢复时因子库不可用
- **WHEN** 加载因子池时，池中某因子的源 FactorDB 连接不可用
- **THEN** 系统将该因子显示为 "stale" 状态（灰色），标注原因，不阻塞其他因子的正常加载

#### Scenario: 覆盖保存
- **WHEN** 用户以相同名称再次保存池子
- **THEN** 系统删除旧的 `[:包含]` 关系，写入新的关系集合

#### Scenario: 因子库删除时清理池子
- **WHEN** 用户确认级联删除某因子库连接
- **THEN** 系统自动从全局因子池中移除两类受影响因子：(1) source 为 "db" 且 conn_id 匹配被删因子库 QSID 的 PoolItem；(2) source 为 "registry" 且 QSID 在图数据库中属于被级联删除的因子节点。所有页面的 FactorPoolPanel 同步更新

#### Scenario: 池中因子来自已删除因子库但未在图库中
- **WHEN** 池中存在 source="db" 的因子，其 conn_id 指向被删除的因子库，但这些因子从未被写入图数据库
- **THEN** 系统通过 conn_id 匹配将其从池中移除，无需查询图数据库

### Requirement: 因子元数据预览

系统 SHALL 支持对池中因子懒加载元数据（ID 数量、日期范围等统计信息）。

#### Scenario: 查看因子统计
- **WHEN** 用户悬停或点击池中因子的信息图标
- **THEN** 系统异步加载因子的统计信息（id_count、dt_count、first_dt、last_dt）并展示
