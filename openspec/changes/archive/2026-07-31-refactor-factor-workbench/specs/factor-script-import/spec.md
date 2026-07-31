# factor-script-import

## Purpose

因子脚本导入模块，支持用户将符合 FactorDef 框架规范的 Python 因子定义脚本导入到 QSWeb，经 `importlib` 动态加载验证后存储到配置目录，可选注册到 Neo4j 图数据库。

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

### Requirement: importlib 动态验证

系统 SHALL 在导入前使用 `importlib` 动态加载脚本模块，提取元信息并验证结构。

#### Scenario: 提取 __FACTOR_META__
- **WHEN** 脚本包含有效的 `__FACTOR_META__` 字典
- **THEN** 系统通过 `importlib` 加载模块后读取并展示：`TargetTable`、`IDType`、`Description`、`Author`、`MaxLookBack`、`FactorDeps`、`DBDeps`、`Tags` 等字段

#### Scenario: 验证 defFactor 签名
- **WHEN** 脚本包含 `defFactor(fdi)` 函数定义
- **THEN** 系统确认其为 callable，标记为"可导入"

#### Scenario: 缺少 __FACTOR_META__
- **WHEN** 脚本不包含 `__FACTOR_META__` 字典
- **THEN** 系统发出警告："脚本缺少 __FACTOR_META__ 声明"，但仍允许导入

#### Scenario: 导入错误
- **WHEN** 脚本包含语法错误或 `ImportError` 无法通过 `importlib` 加载
- **THEN** 系统返回错误信息并拒绝导入，显示具体错误消息

### Requirement: 脚本存储

系统 SHALL 将通过验证的脚本保存到 `QSWebConfig.json` 的 `factor_def.scripts_dir` 配置目录。

#### Scenario: 保存成功
- **WHEN** 用户确认导入，且 `scripts_dir` 目录存在
- **THEN** 系统将脚本以 `{factor_name}.py` 或原文件名保存，返回保存路径

#### Scenario: 文件名冲突
- **WHEN** 目标目录已存在同名文件
- **THEN** 系统自动添加 `_1`、`_2` 等后缀重命名后保存，并在返回结果中标记 `was_renamed`

#### Scenario: 目录不存在
- **WHEN** 配置的 `scripts_dir` 目录不存在
- **THEN** 系统自动创建目录后保存

### Requirement: 可选注册到 Neo4j

系统 SHALL 支持在导入后将因子脚本注册到 Neo4j 图数据库（通过后台任务调用 `register_factors_to_graphdb.py`）。

#### Scenario: 自动注册（后台任务）
- **WHEN** `QSWebConfig.json` 的 `factor_def.settings_path` 已配置且用户未取消注册
- **THEN** 系统在脚本保存后提交后台任务执行注册，返回 `task_id`，前端通过 `GET /api/tasks/{task_id}` 轮询进度

#### Scenario: 注册失败不自动关闭
- **WHEN** 注册失败
- **THEN** 前端在对话框中显示错误 Alert，用户手动关闭，不自动消失

#### Scenario: 未配置 settings_path
- **WHEN** `settings_path` 未配置
- **THEN** 系统跳过注册，返回 `register_hint` 提示信息

### Requirement: 导入预览

系统 SHALL 在用户确认导入前展示脚本的元信息摘要。

#### Scenario: 展示元信息
- **WHEN** AST 解析成功
- **THEN** 预览面板显示：因子表名、ID 类型、作者、描述、依赖因子列表、依赖数据库列表、标签

#### Scenario: 展示依赖警告
- **WHEN** `FactorDeps` 中声明的依赖模块在已有因子列表中不存在
- **THEN** 预览面板显示黄色警告标记并列出缺失的依赖模块
