# ai-session-store

## Purpose

基于本地 JSON 文件的轻量 AI 会话持久化存储，管理会话元数据（标题/时间/context）和消息历史。存储位于 `~/.qsweb/ai_sessions/` 目录。

## ADDED Requirements

### Requirement: 存储结构

系统 SHALL 以本地 JSON 文件存储 AI 会话数据。

#### Scenario: 目录结构

- **WHEN** 系统首次创建 AI 会话
- **THEN** 在 `~/.qsweb/ai_sessions/` 创建目录（如不存在），结构为：
  - `index.json`：会话索引数组，每项为 `{id, title, context, created_at, updated_at, message_count}`
  - `{session_id}.json`：单会话文件，内容为 `{id, context, messages: [{role, content, timestamp, blocks?}], created_at, updated_at}`

#### Scenario: 消息数量限制

- **WHEN** 会话消息数量超过 200 条
- **THEN** 保留最近 200 条消息，丢弃更早的消息

### Requirement: 会话 CRUD

系统 SHALL 通过 REST API 提供会话的创建、读取、列表、删除操作。

#### Scenario: 列出所有会话

- **WHEN** 前端调用 `GET /api/ai/sessions`
- **THEN** 返回 `index.json` 中的会话列表，按 `updated_at` 降序排列

#### Scenario: 获取单个会话

- **WHEN** 前端调用 `GET /api/ai/sessions/{session_id}`
- **THEN** 返回 `{session_id}.json` 的完整内容（含消息历史）

#### Scenario: 删除会话

- **WHEN** 前端调用 `DELETE /api/ai/sessions/{session_id}`
- **THEN** 删除 `{session_id}.json` 文件并从 `index.json` 中移除该条目，返回 204

#### Scenario: 删除不存在的会话

- **WHEN** 前端调用 `DELETE /api/ai/sessions/{session_id}` 且该 ID 不在 `index.json` 中
- **THEN** 返回 404

### Requirement: 自动保存

系统 SHALL 在新会话产生 AI 回复时自动持久化会话和消息。

#### Scenario: 首次自动保存

- **WHEN** 新会话（`session_id` 不在 `index.json` 中）中 AI 首次返回 `assistant` 消息
- **THEN** 后端将用户问题和 AI 回复写入 `{session_id}.json`，并在 `index.json` 中注册条目（title 取自用户第一条消息的前 50 字符）

#### Scenario: 后续消息追加

- **WHEN** 已有会话产生新消息
- **THEN** 后端将新消息追加到 `{session_id}.json` 的 `messages` 数组，更新 `index.json` 中的 `updated_at` 和 `message_count`

### Requirement: 文件写入安全

系统 SHALL 使用原子写入策略避免 JSON 文件损坏。

#### Scenario: 原子写入

- **WHEN** 需要更新 `index.json` 或 `{session_id}.json`
- **THEN** 先写入临时文件 `{filename}.tmp`，写入成功后 `os.replace()` 原子替换目标文件

#### Scenario: 并发保护

- **WHEN** 多个请求可能并发写入同一会话文件
- **THEN** 使用文件锁（Windows: `msvcrt.locking`，Linux: `fcntl.flock`）或在异步单进程环境下（FastAPI）使用 `asyncio.Lock` 按 session_id 粒度加锁

### Requirement: 存储后端接口

SessionStore SHALL 定义为 Python 抽象接口，便于未来替换存储后端。

#### Scenario: 接口定义

- **WHEN** 实现 SessionStore
- **THEN** 必须实现以下方法：
  - `list_sessions() -> List[SessionMeta]`
  - `get_session(session_id: str) -> Optional[SessionData]`
  - `save_message(session_id: str, message: dict) -> None`
  - `delete_session(session_id: str) -> bool`
  - `update_title(session_id: str, title: str) -> None`

#### Scenario: 默认实现

- **WHEN** 系统启动
- **THEN** 使用 `JsonFileSessionStore`（基于 JSON 文件的实现）作为默认后端

### Requirement: 会话重命名

系统 SHALL 支持通过 REST API 重命名会话。

#### Scenario: 重命名会话

- **WHEN** 前端调用 `PUT /api/ai/sessions/{session_id}/title`，body 为 `{"title": "新标题"}`
- **THEN** 更新 `index.json` 中对应条目的 `title` 字段，返回 `{"status": "ok"}`
- **WHEN** 会话不存在于索引中
- **THEN** 静默忽略（不影响用户体验）

### Requirement: 索引容错

系统 SHALL 在索引操作失败时不影响核心对话功能。

#### Scenario: 锁超时保护

- **WHEN** `_global_lock` 被持有超过 3 秒
- **THEN** 索引读/写操作超时后记录错误日志并跳过，不抛出异常阻塞 API

#### Scenario: 索引条目缺失恢复

- **WHEN** `_safe_update_index` 找不到目标条目（首次 `_upsert_index` 被跳过）
- **THEN** 自动从 session 文件重建索引条目（含 title、context、时间戳、消息数）

#### Scenario: 删除容错

- **WHEN** 删除时 session 文件已不存在但索引条目仍在
- **THEN** 清理索引条目并返回成功，不报 404 错误

### Requirement: 会话恢复

系统 SHALL 支持从持久化存储恢复完整会话历史。

#### Scenario: 恢复消息内容

- **WHEN** 前端从 `GET /api/ai/sessions/{id}` 获取会话数据
- **THEN** AI 消息的文本从 `data.blocks` 中 `kind === 'text'` 的 block 提取
- **AND** 思考过程从 `kind === 'thinking'` 的 block 提取
- **AND** 用户消息从 `data.content` 读取
