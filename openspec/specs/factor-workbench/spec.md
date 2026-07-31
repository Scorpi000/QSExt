# factor-workbench

## Purpose

QSWeb 因子工作台模块，支持用户搜索 QSRegistry 中的因子、可视化因子依赖的 DAG、导入 FactorDef 脚本、AI 辅助创建因子以及管理因子元信息。

## Requirements

### Requirement: 因子搜索

系统 SHALL 支持用户通过关键词或语义搜索查找 QSRegistry 中注册的因子。

#### Scenario: 关键词搜索
- **WHEN** 用户输入关键词（如"动量"），点击搜索
- **THEN** 系统调用 QSRegistry 关键词匹配，返回因子列表（名称、类型、描述）

#### Scenario: 语义搜索
- **WHEN** 用户输入自然语言描述（如"市盈率变化率"），点击语义搜索
- **THEN** 系统调用 Ollama 嵌入向量检索，返回语义相关的因子列表

#### Scenario: 按类型/标签筛选
- **WHEN** 用户选择因子类型（原子/衍生）或标签筛选条件
- **THEN** 系统过滤搜索结果，仅显示匹配的因子

### Requirement: DAG 可视化

系统 SHALL 支持用户查看因子依赖关系的有向无环图。

#### Scenario: 查看因子 DAG
- **WHEN** 用户选中一个因子，点击"查看 DAG"
- **THEN** 系统获取因子的依赖链数据，使用 React Flow 渲染 DAG，节点按类型着色

#### Scenario: 点击高亮依赖链
- **WHEN** 用户点击 DAG 中的某个节点
- **THEN** 该节点的所有上游依赖和下游被依赖节点高亮显示

#### Scenario: 自动布局
- **WHEN** 用户点击"自动布局"按钮
- **THEN** 系统使用 dagre 算法重新计算节点位置

### Requirement: 因子创建入口

系统 SHALL 在因子工作台提供两个新的因子创建入口，替代原有的"创建衍生因子"按钮。

#### Scenario: 导入因子脚本入口
- **WHEN** 用户在因子工作台点击"导入因子脚本"按钮
- **THEN** 系统打开导入对话框，支持上传 .py 文件或粘贴代码

#### Scenario: AI 辅助创建入口
- **WHEN** 用户在因子工作台点击"AI 辅助创建"按钮
- **THEN** 系统打开 AI 因子助手 Chat 面板

### Requirement: 因子元信息管理

系统 SHALL 支持用户查看因子的描述、标签等元信息，以及因子的脚本来源（脚本路径或 AI 生成标记）。

#### Scenario: 查看因子详情
- **WHEN** 用户在搜索结果或 DAG 中点击因子
- **THEN** 显示因子详情面板：名称、描述、算子类型、依赖因子列表、数据统计。若因子有对应的 FactorDef 脚本，额外显示脚本路径和导入时间

#### Scenario: 编辑因子描述
- **WHEN** 用户修改因子描述并保存
- **THEN** 系统更新 QSRegistry 中的因子元数据
