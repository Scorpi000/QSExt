# yaml-config-format

## Purpose

QSWeb 配置文件从 JSON 切换到 YAML 格式，支持注释、多行字符串和 anchor/alias 引用，提升可读性和可维护性。

## Requirements

### Requirement: 配置文件格式

系统 SHALL 从 `~/QuantStudioConfig/QSWebConfig.yaml` 读取配置，替代原有的 `QSWebConfig.json`。

#### Scenario: 配置文件存在

- **WHEN** `QSWebConfig.yaml` 存在于 `~/QuantStudioConfig/` 目录
- **THEN** 系统使用 YAML 解析器读取配置，所有配置节点可用且行为与原有 JSON 配置一致

#### Scenario: 配置文件不存在

- **WHEN** `QSWebConfig.yaml` 不存在
- **THEN** 系统使用内置默认配置，功能正常运行

### Requirement: 注释支持

配置文件的任意位置 SHALL 支持 `#` 开头的行注释，注释文本在解析时被忽略。

#### Scenario: 含注释的配置文件

- **WHEN** 配置文件中包含 `# 这是注释` 行
- **THEN** 系统正常解析，注释不影响配置值

### Requirement: 多行字符串

`system_prompt` 等长文本字段 SHALL 支持 YAML 多行字符串语法（`|` 或 `>`），在 JSON 中只能写成单行字符串的内容迁移后以多行形式呈现。

#### Scenario: system_prompt 多行书写

- **WHEN** `system_prompt` 使用 `|` 多行字符串语法书写
- **THEN** 解析后的字符串保留换行符，内容与原 JSON 中的单行 `\n` 字符串等价

### Requirement: Anchor/Alias 继承

配置中 SHALL 支持 YAML anchor（`&name`）和 alias（`*name`）引用，以及 `<<:` merge key 用于合并继承。

#### Scenario: Context 继承 base 配置

- **WHEN** `general` context 定义为 `&base` anchor，其他 context 使用 `<<: *base` 合并
- **THEN** 子 context 继承 base 的所有字段，自身定义的同名字段覆盖继承值

#### Scenario: MCP 服务器配置复用

- **WHEN** 多个 context 引用同一个 `&qs_registry` anchor
- **THEN** 所有引用该 anchor 的 context 获得相同的 MCP 服务器配置

### Requirement: 配置写入

系统 SHALL 支持将修改写回 `QSWebConfig.yaml`，写入时保留文件中已有的注释、格式和 anchor 结构。

#### Scenario: 保存 portfolio 任务

- **WHEN** 用户保存 portfolio 优化任务
- **THEN** 新任务数据写入 `QSWebConfig.yaml` 的 `portfolio.saved_tasks` 节点，文件中其他部分的注释和 anchor 保持不变

#### Scenario: 保存风险库配置

- **WHEN** 用户保存风险库配置
- **THEN** 新风险库信息写入 `QSWebConfig.yaml` 的 `risk_dbs` 节点，文件中其他部分不变

### Requirement: 路径常量统一

`QS_CONFIG_PATH` SHALL 在 `core/config.py` 的 `Settings` 中统一定义，所有服务模块通过 `settings.QS_CONFIG_PATH` 获取配置文件路径。

#### Scenario: 服务模块获取配置路径

- **WHEN** 任何后端模块需要读取或写入配置
- **THEN** 通过 `from app.core.config import settings` 后使用 `settings.QS_CONFIG_PATH` 获取路径，无需自行拼接
