## Context

当前 QSWeb 配置存储在 `~/QuantStudioConfig/QSWebConfig.json`，由多个后端服务模块直接读写。代码中 `QS_CONFIG_PATH` 常量散落在 4 个文件中，各模块自行 `json.load`/`json.dump`。配置文件约 200 行，`ai_workbench` 段占大部分，其中 `system_prompt` 是内嵌在 JSON 字符串中的多段文本，且 4 个 context（`general`/`backtest`/`risk`/`portfolio`）的 `mcp_servers` 配置高度重复。

## Goals / Non-Goals

**Goals:**
- 配置文件从 JSON 切换为 YAML，支持 `#` 注释、`|` 多行字符串、`&anchor`/`*alias` 引用
- 使用 YAML anchor/alias 消除 `ai_workbench.contexts` 中的重复配置
- 统一所有模块的配置路径常量到 `core/config.py`，消除重复定义
- 写入配置时保留注释和格式（使用 `ruamel.yaml`）
- 现有功能不受影响，所有读取配置的后端服务正常工作

**Non-Goals:**
- 不改变配置结构的语义（节的名称、层级关系不变）
- 不重构各服务模块的业务逻辑
- 不改变前端代码（除一处 Tooltip 文字外）

## Decisions

### Decision 1: YAML 作为唯一格式，直接切换

**选择**: 将 `QSWebConfig.json` 替换为 `QSWebConfig.yaml`，所有读写代码直接改为 YAML。

**备选**: 保留 JSON 为"编译产物"，编辑 YAML 后生成 JSON。此方案无需改代码但增加构建步骤和两种格式的同步问题。

**理由**: 直接切换最简单，Python `yaml` 库生态成熟，读取 API 几乎一对一对应 `json` 模块。

### Decision 2: `pyyaml` 读取 + `ruamel.yaml` 写入

**选择**: 读取使用 `yaml.safe_load()`（`pyyaml`），写入使用 `ruamel.yaml`。

**备选**: 全部使用 `pyyaml`。但 `pyyaml` 的 `dump` 会丢失所有注释和 anchor 别名，将 YAML 展平为无格式输出。

**理由**: `ruamel.yaml` 的 `round_trip_load`/`round_trip_dump` 能保留注释、格式和 anchor，适合需要读写配置的场景。读取侧不关心格式保留，`pyyaml` 更轻量、API 更简洁。

### Decision 3: 路径常量统一到 `Settings.QS_CONFIG_PATH`

**选择**: 在 `core/config.py` 的 `Settings` 类中新增 `QS_CONFIG_PATH` 属性，其他模块统一引用 `settings.QS_CONFIG_PATH`。

**现状**:
```
config.py:         os.path.join(self.QS_CONFIG_PATH, "QSWebConfig.json")
risk_service.py:   Path(settings.QS_CONFIG_PATH) / "QSWebConfig.json"
qs_bridge.py:      os.path.expanduser("~/QuantStudioConfig/QSWebConfig.json")
report_service.py: os.path.expanduser("~/QuantStudioConfig/QSWebConfig.json")
portfolio_service.py: Path(os.path.expanduser("~/QuantStudioConfig/QSWebConfig.json"))
```

**理由**: 消除 5 处重复的路径拼接，未来修改路径只需改一处。

### Decision 4: YAML anchor/alias 结构

**选择**: 
- `general` context 作为 `&base` anchor，包含共享字段（`repo_root`、`cli_path`、`env`）
- 各 context 通过 `<<: *base` 合并继承
- `qs-registry` MCP 服务器配置提取为 `&qs_registry` anchor，各 context 引用

**不选择**: 更深层的继承（如 `factor` 继承 `general`，`backtest` 继承 `general`）。因为各 context 的差异主要在 `tools` 和 `system_prompt`，`<<: *base` 已足够。

## Risks / Trade-offs

- [风险] `ruamel.yaml` 写入时可能改变用户手写的 anchor 结构 → 首次迁移后的 YAML 文件已包含正确的 anchor 结构，后续增量写入（如保存 portfolio 任务）只修改局部子树，`ruamel.yaml` 会保留其他部分的格式
- [风险] 用户在不知情的情况下手动编辑了 JSON 文件 → 切换后旧 JSON 文件不再被读取，需通过文档和注释告知用户
- [风险] YAML 缩进敏感，用户手动编辑时可能引入格式错误 → VS Code 有原生 YAML 校验，且 `yaml.safe_load` 会抛出清晰的解析错误信息

## Migration Plan

1. 创建 `QSWebConfig.yaml`，内容从原 JSON 手动转换为带 anchor/alias 的 YAML
2. 更新所有 Python 代码的读写逻辑
3. 更新文档和前端 Tooltip 文字
4. 手动测试各功能模块确认配置读取正常
5. 旧 `QSWebConfig.json` 保留不删除，用户在确认一切正常后手动删除

## Open Questions

无。
