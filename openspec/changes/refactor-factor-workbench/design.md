## Context

当前 QSWeb 因子工作台的衍生因子创建功能（`CreateFactorWizard`）仅向 Neo4j 写入元数据节点和关系，不生成任何可执行的因子定义代码。QSExt 已有 FactorDef 框架（`__FACTOR_META__` + `defFactor(fdi) -> List[Factor]` 契约、自动依赖解析、参数透传、批量执行）和 `develop-factor` AI 技能，但两者均未接入 Web 端。

此次重构需要：
- 前端框架：React 18 + TypeScript + Vite + Ant Design 5 + Zustand
- 后端框架：Python FastAPI + WebSocket
- AI 调用：`claude-agent-sdk` (v0.2.112)，进程内异步调用
- MCP 工具：`jy_base_doc`（查询聚源数据表）、`qs-registry`（搜索因子/算子）
- 因子脚本存储路径通过 `QSWebConfig.json` 配置

## Goals / Non-Goals

**Goals:**
- 移除现有的衍生因子创建向导（前端 + 后端）
- 提供因子脚本导入功能：上传文件或粘贴代码 → ast 静态验证 → 存储 → 可选注册到 Neo4j
- 提供 AI 因子助手：Chat 面板 → WebSocket → claude-agent-sdk → develop-factor skill → 生成的脚本走导入管道
- AI 生成和手动导入共享同一条后端导入管道

**Non-Goals:**
- 不考虑代码安全性（沙箱执行、代码注入扫描）
- 不修改 `develop-factor` 技能内容
- 不修改 `jy_base_doc` / `qs-registry` MCP 服务器
- 不修改 FactorDef 框架本身
- 不修改 QSWeb 现有的搜索、DAG、详情、连接管理功能
- 不在 Web 端提供因子脚本的在线编辑功能（仅导入和 AI 生成）

## Decisions

### Decision 1: AI 调用使用 claude-agent-sdk 的 `query()` 而非 CLI 子进程

**选择**: `claude_agent_sdk.query()`

**理由**:
- 进程内异步调用，无需管理子进程生命周期
- 原生支持 `AsyncIterator` 流式输出，直接映射到 WebSocket
- 参数化配置（`mcp_servers`, `allowed_tools`, `skills`, `cwd`），避免 CLI 字符串拼接
- 已安装 v0.2.112，Python 版本匹配 QS312 环境

**备选方案**: CLI 子进程 (`claude -p "..." --output-format stream-json`)
- 优点：零依赖，CLI 已有
- 缺点：子进程管理复杂，流式输出需要逐行解析 JSON，参数传递靠字符串拼接易出错

### Decision 2: AI 使用 `query()` 而非 `ClaudeSDKClient`

**选择**: `query()`（单向流式）

**理由**:
- `develop-factor` 技能是完整的自主工作流（理解需求 → 调研数据 → 生成脚本 → 保存），不需要人在中间多次干预
- `query()` 更简单：一个 `async for` 完成所有消息接收
- 若后续发现需要多轮交互，可升级到 `ClaudeSDKClient`，前端 WebSocket 架构无需变动

### Decision 3: AI 生成和手动导入走同一条导入管道

**选择**: `POST /api/factors/import` 统一处理所有来源

**理由**:
- 避免验证、存储、注册逻辑重复
- AI 生成的脚本在 Claude 写入磁盘后，前端调用同一个导入 API 获取验证结果和元信息
- 用户手动上传的脚本也走同一 API

**数据流**:
```
手动上传/粘贴 ──┐
                 ├──→ POST /api/factors/import ──→ ast.parse → 验证 → 存储 → 返回元信息
AI Write 后 ────┘
```

### Decision 4: 脚本存放路径通过 QSWebConfig.json 配置

**选择**: 在 `QSWebConfig.json` 中新增 `factor_def` 配置段

```jsonc
{
  "factor_def": {
    "scripts_dir": "D:/Data/FactorDef/Scripts",  // 因子脚本存放目录
    "register_to_graph": true,                    // 导入后自动注册到 Neo4j
    "auto_execute": false                         // 导入后是否自动执行
  }
}
```

**理由**:
- 与现有 QSWebConfig.json 配置模式一致（backtest、risk_dbs、portfolio、reports 均在此文件）
- 避免硬编码路径
- `scripts_dir` 同时作为 `query()` 的 `cwd` 参数，Claude 的 Write 工具自然写入正确位置

### Decision 5: ast 静态解析而非 import 动态执行

**选择**: 使用 `ast.parse` 提取 `__FACTOR_META__` 字典和验证 `defFactor` 函数签名

**理由**:
- 安全：不执行用户代码
- 足够：只需要提取元信息和验证结构，不需要实际运行
- 快速：无需连接数据库、解析依赖

**提取内容**:
- `__FACTOR_META__` 字典的键值（TargetTable、IDType、Description、FactorDeps、DBDeps 等）
- `defFactor(fdi)` 函数签名存在性

### Decision 6: WebSocket 流式推送 AI 消息

**选择**: 前端通过 WebSocket 连接 `/ws/ai/chat`，后端逐条推送 `claude-agent-sdk` 的 `query()` 产生的消息类型

**消息类型映射**:
| SDK 消息类型 | 前端展示 |
|-------------|---------|
| `SystemMessage` | 系统初始化信息（隐藏或显示为状态栏） |
| `AssistantMessage` | Claude 的思考过程和回复（Markdown 渲染） |
| `ToolUseBlock` + `ToolResultBlock` | 工具调用卡片（如"正在查询 JYDB..."） |
| `ResultMessage` | 最终结果（提取生成的脚本路径/content） |
| `StreamEvent` | 流式内容增量 |

## Risks / Trade-offs

1. **[风险] `query()` 单轮交互可能不足以处理需求澄清场景**
   → **缓解**: `develop-factor` 技能设计了"信息不足时主动询问"的流程。若实践中发现体验不佳，可升级到 `ClaudeSDKClient`，前端 WebSocket 架构无需变动。

2. **[风险] Claude 生成的脚本可能引用不存在的表名或字段**
   → **缓解**: `develop-factor` 技能强制要求通过 `jy_base_doc` MCP 工具验证所有表名和字段名后才生成代码。这是技能的核心约束之一。

3. **[风险] 因子脚本的 `FactorDeps` 依赖模块可能不存在**
   → **缓解**: ast 解析时提取 `FactorDeps` 声明，在导入预览中向用户展示缺失的依赖。这不阻断导入，但给出警告。

4. **[权衡] ast 静态解析无法捕获所有运行时错误**
   → 这是有意为之（安全优先）。完整的运行时验证留给 FactorDef 框架的执行阶段。

## Open Questions

- `QSWebConfig.json` 的 `factor_def.scripts_dir` 默认值？建议 `D:/Data/FactorDef/Scripts`
- 是否需要导入后自动触发 `register_factors_to_graphdb.py`？当前设计为可选（`register_to_graph` 配置项），默认 true
