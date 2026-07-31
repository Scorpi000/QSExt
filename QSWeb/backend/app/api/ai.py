"""
AI 因子助手 WebSocket API

通过 WebSocket 提供基于 ClaudeSDKClient 的双向交互式 AI 因子创建辅助。
后端通过 ClaudeSDKClient 管理持久 CLI 进程，前端可发送后续消息和中断。

协议（前端 → 后端）:
  {"action": "start", "prompt": "..."}      — 启动 Claude 会话
  {"action": "query", "prompt": "..."}      — 发送后续消息
  {"action": "interrupt"}                   — 中断 Claude 当前操作
  {"action": "disconnect"}                  — 断开 Claude 连接

协议（后端 → 前端）:
  {"type": "assistant", "data": {"blocks": [...]}}   — Claude 回复
  {"type": "tool_use" / "tool_result", ...}          — 工具调用
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

# 根据配置选择 AI 服务实现
_claude_mode = settings.factor_def.get("claude", {}).get("mode", "cli")
if _claude_mode == "sdk":
    from app.services.ai_service import AiService  # noqa: E402
else:
    from app.services.ai_service_cli import AiServiceCLI as AiService  # noqa: E402

router = APIRouter()


@router.websocket("/ws/ai/chat")
async def ai_chat(websocket: WebSocket):
    """AI 因子助手 WebSocket 端点 — 双向交互模式

    生命周期:
      1. 客户端连接 → 服务端 accept
      2. 客户端发送 {"action": "start", "prompt": "..."}
      3. 服务端创建 AiService，后台线程启动 ClaudeSDKClient
      4. 启动 forward 任务：轮询 msg_queue → 格式化 → WebSocket 推送
      5. 客户端可随时发送 query / interrupt / disconnect
      6. Claude 完成或任一端断开 → 清理
    """
    await websocket.accept()

    scripts_dir = settings.factor_def["scripts_dir"]
    service = AiService()
    forward_task: asyncio.Task | None = None

    async def forward_ai_messages() -> None:
        """从 msg_queue 读取 AI 消息并推送到 WebSocket"""
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
            elif kind == "msg_sent":
                # 消息已发送确认（前端可用作输入反馈）
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
                if not prompt.strip():
                    await _safe_send(websocket, {
                        "type": "error",
                        "data": {"message": "prompt 不能为空"},
                    })
                    continue

                # 启动 Claude 会话
                service.start(prompt, scripts_dir)
                # 启动消息转发
                if forward_task:
                    forward_task.cancel()
                forward_task = asyncio.create_task(forward_ai_messages())

            elif action == "query":
                prompt = data.get("prompt", "")
                if not prompt.strip():
                    continue
                # 在线程中执行 query，避免 wait 阻塞事件循环
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, service.query, prompt)
                # 重新启动 forward 以接收新一轮回复
                if forward_task:
                    forward_task.cancel()
                forward_task = asyncio.create_task(forward_ai_messages())

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
