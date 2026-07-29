# global-factor-pool

## Purpose

提供跨页面共享的全局因子池，用户可以从 FactorDB 或 QSRegistry 双源添加因子到池中，在回测、组合优化、报告中心等页面间复用已选因子。池子位于 MainLayout 右侧滑出面板，支持持久化到 QSGraphDB 图数据库。

## Requirements

### Requirement: 全局因子池跨页面共享

系统 SHALL 在前端维护一个全局因子池 Zustand store，所有页面读取同一个池子实例，池中因子的增删在所有页面间即时同步。因子池面板位于 MainLayout 右侧，hover 展开或点击固定。

#### Scenario: 在任意页面向池中添加因子
- **WHEN** 用户从右侧因子池面板打开 FactorDiscover Drawer，从因子库浏览或 QSRegistry 搜索并添加因子到池中
- **THEN** 该因子立即出现在所有页面的池中

#### Scenario: 在其他页面使用池中因子
- **WHEN** 用户导航到回测工作台、组合优化、报告中心等页面
- **THEN** 各页面通过 store 读取池中因子，ModulePicker/PoolFactorPicker/PoolRefPicker 等组件自动展示最新列表

### Requirement: 双源因子添加

系统 SHALL 支持从 FactorDB（因子库直接连接）和 QSRegistry（图数据库搜索）两个来源添加因子到池中。QSRegistry Tab 支持关键词搜索和语义搜索切换。

#### Scenario: 从 FactorDB 添加因子
- **WHEN** 用户在 FactorDiscover 中选择 FactorDB Tab，依次选择连接、因子表、因子
- **THEN** 系统将因子加入池中，PoolItem 的 source 标记为 "db"，包含 conn_id、table_name、factor_name 引用信息

#### Scenario: 从 QSRegistry 添加因子
- **WHEN** 用户在 FactorDiscover 中切换到 QSRegistry Tab，选择关键词或语义搜索模式，搜索并选择因子
- **THEN** 系统将因子加入池中，PoolItem 的 source 标记为 "registry"，以 QSID 作为标识

#### Scenario: 去重检查
- **WHEN** 用户尝试添加一个已存在于池中的因子（相同 source + 标识）
- **THEN** 系统提示"该因子已在池中"，不重复添加

### Requirement: 因子池管理

系统 SHALL 支持用户查看池中因子、选中/取消选中、移除因子。

#### Scenario: 选中因子用于当前页面功能
- **WHEN** 用户在 FactorPoolPanel 中勾选因子
- **THEN** 被选中的因子关联到当前页面的功能（如回测模块配置、报告被测因子列表等）

#### Scenario: 从池中移除因子
- **WHEN** 用户点击池中某因子的删除按钮
- **THEN** 该因子从池中移除，所有页面的 FactorPoolPanel 同步更新

### Requirement: 因子池持久化到图数据库

系统 SHALL 支持用户将当前因子池保存到 QSGraphDB 图数据库。保存时通过 `storeFactors` 将因子完整注册为 `因子` 节点（含 DAG、算子、因子表关系），再通过 `因子池` 节点与 `因子` 节点的 `[:包含]` 关系持久化。

#### Scenario: 保存因子池
- **WHEN** 用户点击右侧面板的保存按钮并输入名称
- **THEN** 系统解析所有因子为 Factor 对象，调用 storeFactors 写入完整因子节点，再 MERGE `因子池` 节点建立 `[:包含]` 关系

#### Scenario: 加载已保存的因子池
- **WHEN** 用户在右侧面板下拉中选择加载一个已保存的池子
- **THEN** 系统从图中读取 `[:包含]` 关系，遍历因子节点还原 PoolItem 列表（含 source、ref 等），恢复池中因子

#### Scenario: 覆盖保存
- **WHEN** 用户以相同名称再次保存池子
- **THEN** 系统删除旧的 `[:包含]` 关系，写入新的关系集合

### Requirement: 因子元数据预览

系统 SHALL 支持对池中因子懒加载元数据（ID 数量、日期范围等统计信息）。

#### Scenario: 查看因子统计
- **WHEN** 用户悬停或点击池中因子的信息图标
- **THEN** 系统异步加载因子的统计信息（id_count、dt_count、first_dt、last_dt）并展示
