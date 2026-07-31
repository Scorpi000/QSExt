"""
通用 AI 助手 WebSocket API

通过 WebSocket 提供基于 Claude CLI 的多场景 AI 对话能力（支持 factor/backtest/risk
等上下文配置）。后端通过 ClaudeSDKClient 管理持久 CLI 进程，前端可发送后续消息和中断。

协议（前端 → 后端）:
  {"action": "start", "context": "factor", "prompt": "..."}  — 启动 Claude 会话
  {"action": "query", "prompt": "..."}                        — 发送后续消息
  {"action": "interrupt"}                                     — 中断 Claude 当前操作
  {"action": "disconnect"}                                    — 断开 Claude 连接

协议（后端 → 前端）:
  {"type": "assistant", "data": {"blocks": [...]}}   — Claude 回复
  {"type": "action_card", "data": {...}}             — 结构化操作卡片
  {"type": "stream", "data": {"content": "..."}}     — 流式增量
  {"type": "result", "data": {...}}                  — 任务完成
  {"type": "error", "data": {"message": "..."}}      — 错误
  {"type": "interrupted"}                            — 已中断
  {"type": "done"}                                   — Claude 本轮完成
"""

import asyncio
import json
import queue
import traceback

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.services.session_store import get_session_store

# 根据 ai_workbench.mode 选择 AI 服务实现
# sdk: ClaudeSDKClient（原生多轮对话 query，推荐）
# cli: 子进程 + stream-json（-p 模式不保存 session，query 需重启进程）
_claude_mode = settings.ai_workbench.get("mode", "cli")
if _claude_mode == "sdk":
    from app.services.ai_service import AiService  # noqa: E402
else:
    from app.services.ai_service_cli import AiServiceCLI as AiService  # noqa: E402

router = APIRouter()


def _resolve_context_config(context: str) -> dict:
    """从 ai_workbench 配置解析指定 context 的完整配置

    未找到时回退到 general context，general 也不存在时返回空字典。
    """
    aw = settings.ai_workbench
    contexts = aw.get("contexts", {})
    general = contexts.get("general", {})
    ctx = contexts.get(context, general)
    # 合并 general 作为默认值
    return {**general, **ctx}


@router.get("/api/ai/contexts")
async def get_ai_contexts():
    """返回可用 AI context 列表（不含完整 system_prompt）"""
    aw = settings.ai_workbench
    contexts = []
    for key, ctx in aw.get("contexts", {}).items():
        contexts.append({
            "key": key,
            "description": ctx.get("description", ""),
            "placeholder": ctx.get("placeholder", ""),
        })
    return {
        "contexts": contexts,
        "default_context": aw.get("default_context", "general"),
        "route_context_map": aw.get("route_context_map", {}),
    }


@router.websocket("/ws/ai/chat")
async def ai_chat(websocket: WebSocket):
    """通用 AI 助手 WebSocket 端点 — 双向交互模式

    生命周期:
      1. 客户端连接 → 服务端 accept
      2. 客户端发送 {"action": "start", "context": "...", "prompt": "..."}
      3. 服务端解析 context_config，创建 AiService，后台线程启动 Claude CLI
      4. 启动 forward 任务：轮询 msg_queue → 格式化 → WebSocket 推送
      5. 消息自动持久化到 SessionStore
      6. Claude 完成或任一端断开 → 清理
    """
    await websocket.accept()

    service = AiService()
    forward_task: asyncio.Task | None = None
    session_store = get_session_store()
    current_session_id: str | None = None
    current_context: str = "general"

    async def forward_ai_messages() -> None:
        """从 msg_queue 读取 AI 消息并推送到 WebSocket"""
        nonlocal current_session_id
        loop = asyncio.get_event_loop()
        while True:
            try:
                kind, payload = await loop.run_in_executor(
                    None, service.msg_queue.get, True, 0.3
                )
            except queue.Empty:
                continue

            if kind == "done":
                await _safe_send(websocket, {"type": "done"})
                break
            elif kind == "error":
                await _safe_send(websocket, {
                    "type": "error",
                    "data": {"message": payload},
                })
                break
            elif kind == "msg":
                formatted = AiService.format_message(payload)
                if formatted:
                    await _safe_send(websocket, formatted)
                    # 后台异步持久化（失败不影响消息推送）
                    if (current_session_id
                            and formatted.get("type") in ("assistant", "action_card")):
                        asyncio.create_task(
                            _safe_save_message(
                                session_store, current_session_id,
                                formatted, current_context,
                            )
                        )
            elif kind == "msg_sent":
                # 消息已发送确认
                pass

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await _safe_send(websocket, {
                    "type": "error",
                    "data": {"message": "无效的 JSON 格式"},
                })
                continue

            action = data.get("action", "")

            if action == "start":
                prompt = data.get("prompt", "")
                requested_context = data.get("context", "general")
                session_id = data.get("session_id")

                if not prompt.strip():
                    await _safe_send(websocket, {
                        "type": "error",
                        "data": {"message": "prompt 不能为空"},
                    })
                    continue

                # 解析 context 配置
                current_context = requested_context
                context_config = _resolve_context_config(current_context)

                # 启动 Claude 会话（同步，快速返回）
                service.start(prompt, context_config)
                current_session_id = session_id or service._session_id

                # 先启动消息转发，确保消息能及时推送到前端
                if forward_task:
                    forward_task.cancel()
                forward_task = asyncio.create_task(forward_ai_messages())

                # 异步持久化用户消息（不阻塞消息转发）
                asyncio.create_task(
                    _safe_save_message(
                        session_store, current_session_id,
                        {"type": "user", "data": {"content": prompt}},
                        current_context,
                    )
                )

            elif action == "query":
                prompt = data.get("prompt", "")
                if not prompt.strip():
                    continue

                # 异步持久化用户追问
                if current_session_id:
                    asyncio.create_task(
                        _safe_save_message(
                            session_store, current_session_id,
                            {"type": "user", "data": {"content": prompt}},
                            current_context,
                        )
                    )

                # 流式模式：直接推送消息到输入队列，forward_task 自动接收回复
                service.query(prompt)

            elif action == "answer":
                answers = data.get("answers", {})
                service.answer(answers)

            elif action == "interrupt":
                service.interrupt()
                await _safe_send(websocket, {"type": "interrupted"})

            elif action == "disconnect":
                service.disconnect()
                break

            else:
                await _safe_send(websocket, {
                    "type": "error",
                    "data": {"message": f"未知 action: {action}"},
                })

    except WebSocketDisconnect:
        pass
    except Exception:
        traceback.print_exc()
        await _safe_send(websocket, {
            "type": "error",
            "data": {"message": f"服务端异常: {traceback.format_exc()[-2000:]}"},
        })
    finally:
        if forward_task:
            forward_task.cancel()
        service.disconnect()
        try:
            await websocket.close()
        except Exception:
            pass


async def _safe_send(websocket: WebSocket, msg: dict) -> None:
    """安全发送 WebSocket 消息，忽略连接已关闭的错误"""
    try:
        await websocket.send_text(
            json.dumps(msg, ensure_ascii=False, default=str)
        )
    except Exception:
        pass


async def _safe_save_message(session_store, session_id, message, context) -> None:
    """异步保存消息，失败不阻塞主流程"""
    try:
        await session_store.save_message(session_id, message, context=context)
    except Exception:
        pass
