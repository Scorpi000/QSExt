# factor-script-import

## Purpose

因子脚本导入模块，支持用户将符合 FactorDef 框架规范的 Python 因子定义脚本导入到 QSWeb，经静态验证后存储到配置目录，可选注册到 Neo4j 图数据库。

## ADDED Requirements

### Requirement: 脚本上传与粘贴

系统 SHALL 支持用户通过上传 `.py` 文件或粘贴代码的方式提交因子定义脚本。

#### Scenario: 上传 .py 文件
- **WHEN** 用户在导入对话框中选择一个 `.py` 文件
- **THEN** 系统读取文件内容并展示在代码预览区域

#### Scenario: 粘贴代码
- **WHEN** 用户在导入对话框的文本框中粘贴 Python 代码
- **THEN** 系统将粘贴的内容展示在代码预览区域

#### Scenario: 非 Python 文件拒绝
- **WHEN** 用户上传非 `.py` 后缀的文件
- **THEN** 系统拒绝上传并提示"仅支持 .py 文件"

### Requirement: AST 静态验证

系统 SHALL 在导入前使用 `ast.parse` 静态解析脚本，提取元信息并验证结构。

#### Scenario: 提取 __FACTOR_META__
- **WHEN** 脚本包含有效的 `__FACTOR_META__` 字典
- **THEN** 系统解析并展示：`TargetTable`、`IDType`、`Description`、`Author`、`FactorDeps`、`DBDeps`、`Tags` 等字段

#### Scenario: 验证 defFactor 签名
- **WHEN** 脚本包含 `defFactor(fdi)` 函数定义
- **THEN** 系统确认签名有效，标记为"可导入"

#### Scenario: 缺少 __FACTOR_META__
- **WHEN** 脚本不包含 `__FACTOR_META__` 字典
- **THEN** 系统发出警告："脚本缺少 __FACTOR_META__ 声明"，但仍允许导入（兼容无元信息的简单脚本）

#### Scenario: AST 解析错误
- **WHEN** 脚本包含语法错误无法通过 `ast.parse`
- **THEN** 系统返回错误信息并拒绝导入，显示具体错误行号和消息

### Requirement: 脚本存储

系统 SHALL 将通过验证的脚本保存到 `QSWebConfig.json` 的 `factor_def.scripts_dir` 配置目录。

#### Scenario: 保存成功
- **WHEN** 用户确认导入，且 `scripts_dir` 目录存在
- **THEN** 系统将脚本以 `{factor_name}.py` 或原文件名保存，返回保存路径

#### Scenario: 文件名冲突
- **WHEN** 目标目录已存在同名文件
- **THEN** 系统提示用户选择覆盖或重命名

#### Scenario: 目录不存在
- **WHEN** 配置的 `scripts_dir` 目录不存在
- **THEN** 系统自动创建目录后保存

### Requirement: 可选注册到 Neo4j

系统 SHALL 支持在导入后将因子脚本注册到 Neo4j 图数据库（通过调用 `register_factors_to_graphdb.py` 或等效逻辑）。

#### Scenario: 自动注册
- **WHEN** `QSWebConfig.json` 的 `factor_def.register_to_graph` 为 `true`
- **THEN** 系统在脚本保存后自动将其注册到 Neo4j，创建因子节点和依赖关系

#### Scenario: 手动跳过注册
- **WHEN** 用户在导入对话框中取消勾选"注册到图数据库"
- **THEN** 系统仅保存脚本，不执行注册

### Requirement: 导入预览

系统 SHALL 在用户确认导入前展示脚本的元信息摘要。

#### Scenario: 展示元信息
- **WHEN** AST 解析成功
- **THEN** 预览面板显示：因子表名、ID 类型、作者、描述、依赖因子列表、依赖数据库列表、标签

#### Scenario: 展示依赖警告
- **WHEN** `FactorDeps` 中声明的依赖模块在已有因子列表中不存在
- **THEN** 预览面板显示黄色警告标记并列出缺失的依赖模块
