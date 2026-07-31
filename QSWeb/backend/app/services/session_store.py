"""
AI 会话持久化存储 — 基于本地 JSON 文件

存储结构:
    ~/.qsweb/ai_sessions/
    ├── index.json            # [{ id, title, context, created_at, updated_at, message_count }]
    ├── {session_id}.json     # { id, context, messages: [...], created_at, updated_at }

并发安全：asyncio.Lock 按 session_id 粒度加锁，原子写入（tmp + rename）。
"""

import json
import os
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from app.core.config import settings

logger = __import__("logging").getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class SessionMeta:
    """会话索引条目"""
    id: str
    title: str
    context: str
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0


@dataclass
class SessionData:
    """完整会话数据"""
    id: str
    context: str
    messages: list = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    MAX_MESSAGES: int = 200


# ---------------------------------------------------------------------------
# 抽象接口
# ---------------------------------------------------------------------------

class SessionStore(ABC):
    """会话存储抽象接口"""

    @abstractmethod
    async def list_sessions(self) -> list: ...
    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[dict]: ...
    @abstractmethod
    async def save_message(self, session_id: str, message: dict, context: str = "general") -> None: ...
    @abstractmethod
    async def delete_session(self, session_id: str) -> bool: ...
    @abstractmethod
    async def update_title(self, session_id: str, title: str) -> None: ...


# ---------------------------------------------------------------------------
# JSON 文件实现
# ---------------------------------------------------------------------------

class JsonFileSessionStore(SessionStore):
    """基于 JSON 文件的会话存储实现"""

    def __init__(self, base_dir: Optional[str] = None):
        self._base_dir = base_dir or settings.ai_workbench.get(
            "sessions_dir",
            os.path.expanduser("~/.qsweb/ai_sessions"),
        )
        self._index_path = os.path.join(self._base_dir, "index.json")
        self._locks: dict = {}
        self._global_lock = asyncio.Lock()
        os.makedirs(self._base_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def list_sessions(self) -> list:
        """列出所有会话（按 updated_at 降序）"""
        entries = await self._read_index()
        entries.sort(key=lambda e: e.get("updated_at", ""), reverse=True)
        return entries

    async def get_session(self, session_id: str) -> Optional[dict]:
        """获取单个会话的完整数据"""
        session_path = self._session_path(session_id)
        lock = await self._get_lock(session_id)
        async with lock:
            if not os.path.exists(session_path):
                return None
            try:
                with open(session_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return None

    async def save_message(
        self, session_id: str, message: dict, context: str = "general"
    ) -> None:
        """保存一条消息到会话"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session_path = self._session_path(session_id)
        lock = await self._get_lock(session_id)

        is_new = False
        msg_count = 1
        created_at = now

        async with lock:
            if os.path.exists(session_path):
                try:
                    with open(session_path, "r", encoding="utf-8") as f:
                        session = json.load(f)
                    created_at = session.get("created_at", now)
                except (json.JSONDecodeError, OSError):
                    session = {
                        "id": session_id, "context": context,
                        "messages": [], "created_at": now, "updated_at": now,
                    }
                    is_new = True
            else:
                session = {
                    "id": session_id, "context": context,
                    "messages": [], "created_at": now, "updated_at": now,
                }
                is_new = True

            session["messages"].append(message)
            session["updated_at"] = now
            if len(session["messages"]) > SessionData.MAX_MESSAGES:
                session["messages"] = session["messages"][-SessionData.MAX_MESSAGES:]
            msg_count = len(session["messages"])
            await self._atomic_write(session_path, session)

        # 索引更新在 per-session 锁外
        if is_new:
            title = self._derive_title(message)
            await self._safe_upsert_index(
                session_id, title, context, created_at, now, msg_count,
            )
        else:
            await self._safe_update_index(
                session_id, updated_at=now, message_count=msg_count,
            )

    async def delete_session(self, session_id: str) -> bool:
        """删除会话（始终清理索引）"""
        session_path = self._session_path(session_id)
        lock = await self._get_lock(session_id)
        file_existed = False

        async with lock:
            if os.path.exists(session_path):
                file_existed = True
                try:
                    os.remove(session_path)
                except OSError:
                    pass

        await self._safe_remove_from_index(session_id)
        return file_existed

    async def update_title(self, session_id: str, title: str) -> None:
        """更新会话标题"""
        await self._safe_update_index(session_id, title=title)

    # ------------------------------------------------------------------
    # 内部：索引读写
    # ------------------------------------------------------------------

    def _session_path(self, session_id: str) -> str:
        safe_id = os.path.basename(session_id)
        return os.path.join(self._base_dir, f"{safe_id}.json")

    async def _get_lock(self, session_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
            return self._locks[session_id]

    def _read_index_nolock(self) -> list:
        """同步读取索引（调用方持有 _global_lock）"""
        if not os.path.exists(self._index_path):
            return []
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    async def _read_index(self) -> list:
        """读取索引（public，带超时）"""
        if not os.path.exists(self._index_path):
            return []
        try:
            async with asyncio.timeout(3):
                async with self._global_lock:
                    return self._read_index_nolock()
        except asyncio.TimeoutError:
            logger.error("_read_index 获取 _global_lock 超时")
            if os.path.exists(self._index_path):
                return self._read_index_nolock()
            return []

    async def _safe_upsert_index(
        self, session_id, title, context, created_at, updated_at, message_count,
    ) -> None:
        """插入索引条目（容错）"""
        try:
            async with asyncio.timeout(3):
                async with self._global_lock:
                    entries = self._read_index_nolock()
                    for entry in entries:
                        if entry.get("id") == session_id:
                            entry.update({
                                "title": title, "context": context,
                                "created_at": created_at, "updated_at": updated_at,
                                "message_count": message_count,
                            })
                            break
                    else:
                        entries.append({
                            "id": session_id, "title": title, "context": context,
                            "created_at": created_at, "updated_at": updated_at,
                            "message_count": message_count,
                        })
                    await self._atomic_write(self._index_path, entries)
        except asyncio.TimeoutError:
            logger.error("_safe_upsert_index 超时，索引写入失败")
        except Exception as e:
            logger.error("_safe_upsert_index 异常: %s", e)

    async def _safe_update_index(self, session_id: str, **kwargs) -> None:
        """更新索引条目（容错，条目不存在时从文件重建）"""
        try:
            async with asyncio.timeout(3):
                async with self._global_lock:
                    entries = self._read_index_nolock()
                    for entry in entries:
                        if entry.get("id") == session_id:
                            entry.update(kwargs)
                            break
                    else:
                        session_path = self._session_path(session_id)
                        if os.path.exists(session_path):
                            try:
                                with open(session_path, "r", encoding="utf-8") as f:
                                    sess = json.load(f)
                                entries.append({
                                    "id": session_id,
                                    "title": sess.get("title", "新会话"),
                                    "context": sess.get("context", "general"),
                                    "created_at": sess.get("created_at", ""),
                                    "updated_at": sess.get("updated_at", ""),
                                    "message_count": len(sess.get("messages", [])),
                                })
                            except Exception:
                                pass
                    await self._atomic_write(self._index_path, entries)
        except asyncio.TimeoutError:
            logger.error("_safe_update_index 超时，索引更新失败")
        except Exception as e:
            logger.error("_safe_update_index 异常: %s", e)

    async def _safe_remove_from_index(self, session_id: str) -> None:
        """从索引中移除条目（容错）"""
        try:
            async with asyncio.timeout(3):
                async with self._global_lock:
                    entries = self._read_index_nolock()
                    entries = [e for e in entries if e.get("id") != session_id]
                    await self._atomic_write(self._index_path, entries)
        except asyncio.TimeoutError:
            logger.error("_safe_remove_from_index 超时")
        except Exception as e:
            logger.error("_safe_remove_from_index 异常: %s", e)

    @staticmethod
    async def _atomic_write(filepath: str, data) -> None:
        """原子写入：tmp + rename"""
        tmp_path = filepath + ".tmp"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_json_write, tmp_path, data)
        os.replace(tmp_path, filepath)

    @staticmethod
    def _derive_title(message: dict) -> str:
        """从消息中提取标题（前 50 字符）"""
        content = message.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            content = " ".join(text_parts)
        if not content:
            content = str(message.get("role", ""))
        title = content[:50].replace("\n", " ").strip()
        return title if title else "新会话"


def _sync_json_write(filepath: str, data) -> None:
    """同步 JSON 写入"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


# 全局单例
_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """获取 SessionStore 单例"""
    global _session_store
    if _session_store is None:
        _session_store = JsonFileSessionStore()
    return _session_store
