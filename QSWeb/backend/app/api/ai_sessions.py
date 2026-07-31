"""
AI 会话管理 REST API

提供会话的列表、读取、删除操作。
会话的创建和消息追加由 WebSocket 消息处理自动完成。
"""

from fastapi import APIRouter, HTTPException

from app.services.session_store import get_session_store

router = APIRouter()


@router.get("/api/ai/sessions")
async def list_sessions():
    """列出所有 AI 会话（按更新时间降序）"""
    store = get_session_store()
    sessions = await store.list_sessions()
    return {"sessions": sessions}


@router.get("/api/ai/sessions/{session_id}")
async def get_session(session_id: str):
    """获取单个会话的完整数据（含消息历史）"""
    store = get_session_store()
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.put("/api/ai/sessions/{session_id}/title")
async def rename_session(session_id: str, body: dict):
    """重命名会话"""
    title = body.get("title", "")
    store = get_session_store()
    await store.update_title(session_id, title)
    return {"status": "ok"}


@router.delete("/api/ai/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话（文件不存在时也清理索引，确保 UI 能正常移除）"""
    store = get_session_store()
    deleted = await store.delete_session(session_id)
    return {"status": "deleted", "file_deleted": deleted}
