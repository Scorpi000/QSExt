# factor-workbench

本文件为 `factor-workbench` 能力的增量变更规格（delta spec）。

## REMOVED Requirements

### Requirement: 衍生因子创建

**Reason**: 替换为更强大的 FactorDef 脚本导入和 AI 辅助创建功能。原衍生因子创建仅向 Neo4j 写入元数据节点，无法生成可执行的因子定义代码。

**Migration**: 使用新的"导入因子脚本"或"AI 辅助创建"功能。已通过旧向导创建的衍生因子节点仍保留在 Neo4j 中，可正常查看。

## MODIFIED Requirements

### Requirement: 因子元信息管理

系统 SHALL 支持用户查看因子的描述、标签等元信息，以及因子的脚本来源（脚本路径或 AI 生成标记）。

#### Scenario: 查看因子详情
- **WHEN** 用户在搜索结果或 DAG 中点击因子
- **THEN** 显示因子详情面板：名称、描述、算子类型、依赖因子列表、数据统计。若因子有对应的 FactorDef 脚本，额外显示脚本路径和导入时间。

#### Scenario: 编辑因子描述
- **WHEN** 用户修改因子描述并保存
- **THEN** 系统更新 QSRegistry 中的因子元数据

## ADDED Requirements

### Requirement: 因子创建入口

系统 SHALL 在因子工作台提供两个新的因子创建入口，替代原有的"创建衍生因子"按钮。

#### Scenario: 导入因子脚本入口
- **WHEN** 用户在因子工作台点击"导入因子脚本"按钮
- **THEN** 系统打开导入对话框，支持上传 .py 文件或粘贴代码

#### Scenario: AI 辅助创建入口
- **WHEN** 用户在因子工作台点击"AI 辅助创建"按钮
- **THEN** 系统打开 AI 因子助手 Chat 面板
