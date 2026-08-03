"""
通用 AI 助手服务 — Claude Agent SDK

通过 claude-agent-sdk 的 ClaudeSDKClient 调用 Claude，原生支持多轮对话（query）
和会话管理。所有配置从 ai_workbench context_config 驱动。

ClaudeSDKClient 在独立线程中运行（避免 anyio 与 FastAPI/uvicorn asyncio 事件循环
冲突），主线程通过 asyncio.run_coroutine_threadsafe() 发送命令，通过 queue.Queue
接收消息。
"""

import asyncio
import json
import logging
import queue
import threading
from typing import Optional

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.client import ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage,
    PermissionResultAllow,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

logger = logging.getLogger(__name__)


class AiService:
    """通用 AI 助手服务 — 基于 ClaudeSDKClient 的双向交互，配置由 context_config 驱动"""

    def __init__(self):
        self._client: Optional[ClaudeSDKClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._msg_queue: Optional[queue.Queue] = None
        self._ready = threading.Event()
        self._context_config: dict = {}
        self._session_id: str = ""
        # AskUserQuestion 等待机制
        self._question_event: Optional[asyncio.Event] = None
        self._pending_answers: Optional[dict] = None

    # ------------------------------------------------------------------
    # 公开 API（主线程调用）
    # ------------------------------------------------------------------

    def start(self, prompt: str, context_config: dict) -> None:
        """启动 Claude 会话（在后台线程中）

        若已有会话运行中，先断开旧会话再启动新会话。
        """
        import uuid
        if self._ready.is_set():
            self.disconnect()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)

        self._ready.clear()
        self._msg_queue = queue.Queue()
        self._context_config = context_config
        self._session_id = str(uuid.uuid4())

        self._loop = asyncio.new_event_loop()

        def _run() -> None:
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._run_client(prompt))
            except Exception as e:
                detail = str(e) or type(e).__name__
                self._msg_queue.put(("error", detail))
            finally:
                self._ready.clear()
                self._loop.close()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def query(self, prompt: str) -> None:
        """发送后续消息 — client.query() 直接写 transport（主线程安全）"""
        if not self._ready.is_set() or self._loop is None or not self._client:
            logger.warning("query() 调用时服务未就绪")
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._client.query(prompt), self._loop
            )
        except Exception as e:
            logger.warning("query() 失败: %s", e)

    def interrupt(self) -> None:
        """中断 Claude 当前操作"""
        if not self._ready.is_set() or self._loop is None or not self._client:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._client.interrupt(), self._loop
            )
        except Exception as e:
            logger.warning("interrupt() 失败: %s", e)

    def disconnect(self) -> None:
        """断开 Claude 连接"""
        self._resolve_question(None)
        if self._client and self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._client.disconnect(), self._loop
                )
            except Exception as e:
                logger.warning("disconnect() 失败: %s", e)
        self._ready.clear()

    def answer(self, answers: dict) -> None:
        """接收前端返回的 AskUserQuestion 答案（主线程安全）"""
        self._resolve_question(answers)

    def _resolve_question(self, answers=None) -> None:
        """设置答案并唤醒 _can_use_tool 中的等待"""
        self._pending_answers = answers
        if self._question_event and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._question_event.set)

    @property
    def msg_queue(self) -> Optional[queue.Queue]:
        return self._msg_queue

    # ------------------------------------------------------------------
    # 后台线程中的异步逻辑
    # ------------------------------------------------------------------

    async def _run_client(self, prompt: str) -> None:
        """在后台线程的事件循环中运行 ClaudeSDKClient（流式输入）"""
        options = self._build_options()
        self._client = ClaudeSDKClient(options=options)

        async def input_stream():
            """发送初始提示后保持连接，后续消息通过 client.query() 投递"""
            yield {
                "type": "user",
                "message": {"role": "user", "content": prompt},
            }
            await asyncio.Event().wait()  # keep-alive，stdin 不关

        await self._client.connect(prompt=input_stream())
        self._ready.set()

        try:
            async for msg in self._client.receive_messages():
                self._msg_queue.put(("msg", msg))
        except Exception as e:
            self._msg_queue.put(("error", str(e) or type(e).__name__))
        finally:
            self._msg_queue.put(("done", None))
            try:
                await self._client.disconnect()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    async def _can_use_tool(self, tool_name: str, input_data: dict, context) -> object:
        """canUseTool 回调：拦截 AskUserQuestion，等待前端返回答案"""
        if tool_name == "AskUserQuestion":
            self._question_event = asyncio.Event()
            self._pending_answers = None
            self._msg_queue.put(("msg", {
                "type": "ask_user",
                "data": input_data,
            }))
            await self._question_event.wait()
            self._question_event = None
            answers = self._pending_answers or {}
            self._pending_answers = None
            return PermissionResultAllow(updated_input={
                "questions": input_data.get("questions", []),
                "answers": answers,
            })
        return None

    def _build_options(self) -> ClaudeAgentOptions:
        """从 context_config 构建 ClaudeAgentOptions"""
        ctx = self._context_config
        repo_root = ctx.get("repo_root", "D:/HST/QSExt")
        scripts_dir = ctx.get("scripts_dir", "")
        skill_dir = ctx.get("skill_dir", "")

        add_dirs = [repo_root]
        if scripts_dir:
            add_dirs.append(scripts_dir)
        if skill_dir:
            add_dirs.append(skill_dir)

        kwargs: dict = {
            "cwd": repo_root,
            "skills": ctx.get("skills", []),
            "mcp_servers": ctx.get("mcp_servers", {}),
            "allowed_tools": ctx.get("tools", ["Read"]),
            "add_dirs": add_dirs,
            "env": ctx.get("env", {}),
            "permission_mode": ctx.get("permission_mode", "acceptEdits"),
            "max_budget_usd": ctx.get("max_budget_usd", 1.0),
            "can_use_tool": self._can_use_tool,
        }

        # 将 system_prompt 作为系统指令传给 Claude（不含 {user_prompt} 占位符时）
        sp = ctx.get("system_prompt", "")
        if sp and "{user_prompt}" not in sp:
            kwargs["system_prompt"] = sp

        if cli_path := ctx.get("cli_path"):
            kwargs["cli_path"] = cli_path

        return ClaudeAgentOptions(**kwargs)

    @staticmethod
    def _extract_action_card(text: str) -> Optional[dict]:
        """从文本中提取 action_card JSON"""
        import re
        pattern = r'\{[^{}]*"type"\s*:\s*"action_card"[^{}]*\}'
        match = re.search(pattern, text)
        if not match:
            # 尝试宽松匹配：嵌套对象
            start = text.find('"type": "action_card"')
            if start == -1:
                return None
            brace_start = text.rfind('{', 0, start)
            if brace_start == -1:
                return None
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(text[brace_start:i + 1])
                            if obj.get("type") == "action_card":
                                return obj.get("data", obj)
                        except json.JSONDecodeError:
                            pass
                        break
            return None
        try:
            obj = json.loads(match.group())
            if obj.get("type") == "action_card":
                return obj.get("data", obj)
        except json.JSONDecodeError:
            pass
        return None

    @staticmethod
    def _strip_action_card(text: str) -> str:
        """从文本中移除 action_card JSON"""
        import re
        text = re.sub(
            r'```json\s*\n?\{[^`]*"type"\s*:\s*"action_card"[^`]*\}\s*\n?```',
            '', text,
        )
        text = re.sub(
            r'\n?\{[^{}]*"type"\s*:\s*"action_card"[^{}]*\}\n?',
            '', text,
        )
        return text.strip()

    @staticmethod
    def format_message(msg) -> Optional[dict]:
        """将 SDK 消息类型转换为统一的 JSON 格式（静态方法，主线程安全）"""
        # 原始 dict（如 ask_user）直接透传
        if isinstance(msg, dict) and "type" in msg:
            return msg
        if isinstance(msg, SystemMessage):
            if msg.subtype == "init":
                return {
                    "type": "init",
                    "data": {
                        "session_id": msg.data.get("session_id", ""),
                        "slash_commands": msg.data.get("slash_commands", []),
                        "model": msg.data.get("model", ""),
                    },
                }
            return None  # 隐藏其他系统消息（thinking_tokens 等）
        elif isinstance(msg, AssistantMessage):
            content_blocks = getattr(msg, "content", [])
            blocks = []
            for block in content_blocks:
                if isinstance(block, ToolUseBlock):
                    blocks.append({
                        "kind": "tool_use",
                        "tool_name": getattr(block, "name", ""),
                        "tool_input": getattr(block, "input", {}),
                        "id": getattr(block, "id", ""),
                    })
                elif isinstance(block, ToolResultBlock):
                    blocks.append({
                        "kind": "tool_result",
                        "content": getattr(block, "content", ""),
                        "tool_use_id": getattr(block, "tool_use_id", ""),
                    })
                elif isinstance(block, ThinkingBlock):
                    blocks.append({
                        "kind": "thinking",
                        "content": block.thinking,
                    })
                else:
                    text = getattr(block, "text", "") or str(block)
                    if text:
                        blocks.append({"kind": "text", "content": text})

            # 检测并提取 action_card
            for blk in blocks:
                if blk.get("kind") == "text":
                    card = AiService._extract_action_card(blk.get("content", ""))
                    if card:
                        blk["content"] = AiService._strip_action_card(blk.get("content", ""))

            return {"type": "assistant", "data": {"blocks": blocks}}
        elif isinstance(msg, UserMessage):
            blocks = []
            for block in getattr(msg, "content", []):
                if isinstance(block, ToolUseBlock):
                    blocks.append({
                        "kind": "tool_use",
                        "tool_name": getattr(block, "name", ""),
                        "tool_input": getattr(block, "input", {}),
                    })
                elif isinstance(block, ToolResultBlock):
                    blocks.append({
                        "kind": "tool_result",
                        "content": getattr(block, "content", ""),
                    })
                else:
                    text = str(block)
                    if text:
                        blocks.append({"kind": "text", "content": text})
            return {"type": "user", "data": {"blocks": blocks}}
        elif isinstance(msg, ResultMessage):
            return {
                "type": "result",
                "data": {
                    "content": msg.result,
                    "is_error": msg.is_error,
                },
            }
        elif isinstance(msg, StreamEvent):
            return {
                "type": "stream",
                "data": {"content": getattr(msg, "content", str(msg))},
            }
        else:
            return {
                "type": "unknown",
                "data": {"raw": str(msg)},
            }


# 全局实例
ai_service = AiService()
