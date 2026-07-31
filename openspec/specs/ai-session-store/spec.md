# ai-session-store

## Purpose

基于本地 JSON 文件的轻量 AI 会话持久化存储，管理会话元数据（标题/时间/context）和消息历史。存储位于 `~/.qsweb/ai_sessions/` 目录。

## Requirements

### Requirement: 存储结构

系统 SHALL 以本地 JSON 文件存储 AI 会话数据。`index.json` 为会话索引数组，`{session_id}.json` 为单会话文件。消息数量超过 200 条时保留最近 200 条。使用原子写入（tmp + rename）和 `asyncio.Lock` 按 session_id 粒度加锁。

### Requirement: 会话 CRUD

系统 SHALL 通过 REST API 提供会话的创建（由 WebSocket 消息处理自动完成）、读取、列表、删除、重命名操作。

- `GET /api/ai/sessions` — 列出所有会话（按 `updated_at` 降序）
- `GET /api/ai/sessions/{id}` — 获取单个会话的完整内容（含消息历史）
- `DELETE /api/ai/sessions/{id}` — 删除文件并清理索引，文件不存在时仍清理索引不报 404
- `PUT /api/ai/sessions/{id}/title` — 重命名会话

### Requirement: 自动保存

系统 SHALL 通过 fire-and-forget 模式自动持久化消息：WS handler 的 `start`/`query` 动作和 forward 循环中，先推送消息到前端，再 `asyncio.create_task(_safe_save_message(...))` 异步保存。文件写入在 per-session 锁内完成，索引更新在锁外由 `_global_lock` 保护。

### Requirement: 索引容错

系统 SHALL 保证索引操作失败不影响核心对话功能。所有索引操作加 3 秒 `asyncio.timeout` 超时保护，超时后记录日志并跳过。`_safe_update_index` 条目不存在时自动从 session 文件重建索引。

### Requirement: 存储后端接口

`SessionStore` 定义为 Python 抽象接口（`list_sessions`、`get_session`、`save_message`、`delete_session`、`update_title`），默认使用 `JsonFileSessionStore` 实现。

### Requirement: 会话恢复

前端从 `GET /api/ai/sessions/{id}` 获取会话数据时，AI 消息的文本从 `data.blocks` 中 `kind === 'text'` 提取，思考过程从 `kind === 'thinking'` 提取，用户消息从 `data.content` 读取。
