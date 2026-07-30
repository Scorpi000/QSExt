"""
AI 因子助手 WebSocket API

通过 WebSocket 连接提供流式的 AI 因子创建辅助功能。
"""

import json
import traceback
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ai_service import ai_service
from app.core.config import settings

router = APIRouter()


@router.websocket("/ws/ai/chat")
async def ai_chat(websocket: WebSocket):
    """AI 因子助手 WebSocket 端点

    生命周期:
      1. 客户端连接 → 服务端 accept
      2. 客户端发送 JSON: {"prompt": "用户需求描述"}
      3. 服务端流式推送 AI 消息（assistant / tool_use / tool_result / result / stream / error）
      4. 客户端可发送 {"action": "stop"} 终止（当前实现等待自然结束）
      5. 任一端断开连接即结束

    消息格式:
      {"type": "assistant", "data": {"blocks": [{"kind": "text", "content": "..."}, ...]}}
      {"type": "tool_use", "data": {"tool_name": "...", "tool_input": {...}}}
      {"type": "tool_result", "data": {"content": "..."}}
      {"type": "result", "data": {"content": "...", "is_error": false}}
      {"type": "stream", "data": {"content": "..."}}
      {"type": "error", "data": {"message": "..."}}
      {"type": "done"}
    """
    await websocket.accept()

    scripts_dir = settings.factor_def["scripts_dir"]

    try:
        while True:
            # 接收用户消息
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": {"message": "无效的 JSON 格式"},
                }, ensure_ascii=False))
                continue

            action = data.get("action")
            if action == "stop":
                await websocket.send_text(json.dumps({"type": "stopped"}, ensure_ascii=False))
                break

            prompt = data.get("prompt", "")
            if not prompt.strip():
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": {"message": "prompt 不能为空"},
                }, ensure_ascii=False))
                continue

            # 流式调用 AI
            try:
                async for msg in ai_service.chat(user_prompt=prompt, scripts_dir=scripts_dir):
                    await websocket.send_text(json.dumps(msg, ensure_ascii=False, default=str))
            except Exception as e:
                import traceback as _tb
                detail = _tb.format_exc()
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": {"message": f"AI 调用异常: {e}", "traceback": detail[-3000:]},
                }, ensure_ascii=False))

            # 通知客户端本轮完成
            await websocket.send_text(json.dumps({"type": "done"}, ensure_ascii=False))

    except WebSocketDisconnect:
        pass
    except Exception:
        traceback.print_exc()
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "data": {"message": f"服务端异常: {traceback.format_exc()}"},
            }, ensure_ascii=False))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
