"""
AI 因子助手服务

通过 claude-agent-sdk 的 ClaudeSDKClient 调用 Claude，加载 develop-factor 技能和
MCP 工具，流式生成 FactorDef 因子定义脚本。

ClaudeSDKClient 在独立线程中运行（避免 anyio 与 FastAPI/uvicorn asyncio 事件循环
冲突），主线程通过 asyncio.run_coroutine_threadsafe() 发送命令，通过 queue.Queue
接收消息。

所有 Claude Code 配置从 QSWebConfig.json 的 factor_def.claude 段读取。
"""

import asyncio
import json
import queue
import threading
from typing import Optional

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.client import ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from app.core.config import settings


class AiService:
    """AI 因子助手服务 — 基于 ClaudeSDKClient 的双向交互"""

    def __init__(self):
        self._client: Optional[ClaudeSDKClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._msg_queue: Optional[queue.Queue] = None
        self._ready = threading.Event()

    # ------------------------------------------------------------------
    # 公开 API（主线程调用）
    # ------------------------------------------------------------------

    def start(self, prompt: str, scripts_dir: str) -> None:
        """启动 Claude 会话（在后台线程中）

        若已有会话运行中，先断开旧会话再启动新会话。
        调用后可通过 msg_queue 属性读取 AI 消息。
        """
        # 断开旧会话
        if self._ready.is_set():
            self.disconnect()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)

        self._ready.clear()
        self._msg_queue = queue.Queue()

        # 在 daemon 线程中创建独立的事件循环
        self._loop = asyncio.new_event_loop()

        def _run() -> None:
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._run_client(prompt, scripts_dir))
            except Exception as e:
                detail = str(e) or type(e).__name__
                self._msg_queue.put(("error", detail))
            finally:
                self._ready.clear()
                self._loop.close()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def query(self, prompt: str) -> None:
        """发送后续消息（主线程安全）"""
        self._send_command({"action": "query", "prompt": prompt})

    def interrupt(self) -> None:
        """中断 Claude 当前操作（主线程安全）"""
        self._send_command({"action": "interrupt"})

    def disconnect(self) -> None:
        """断开 Claude 连接（主线程安全）"""
        self._send_command({"action": "disconnect"})

    def _send_command(self, cmd: dict) -> None:
        """线程安全地发送命令到 ClaudeSDKClient 的事件循环"""
        if not self._ready.is_set() or self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._cmd_queue.put(cmd), self._loop
            )
        except Exception:
            pass

    @property
    def msg_queue(self) -> Optional[queue.Queue]:
        """消息队列 — 主事件循环通过 loop.run_in_executor 轮询"""
        return self._msg_queue

    # ------------------------------------------------------------------
    # 后台线程中的异步逻辑
    # ------------------------------------------------------------------

    async def _run_client(self, prompt: str, scripts_dir: str) -> None:
        """在后台线程的事件循环中运行 ClaudeSDKClient"""
        options = self._build_options(scripts_dir)
        self._client = ClaudeSDKClient(options=options)

        # 1) 连接并发送初始提示
        full_prompt = self._build_prompt(prompt, scripts_dir)
        await self._client.connect(prompt=full_prompt)

        # 2) 命令队列（属于当前事件循环）
        self._cmd_queue: asyncio.Queue = asyncio.Queue()
        self._ready.set()

        # 3) 并发运行：接收消息 + 处理命令
        async def recv_loop() -> None:
            try:
                async for msg in self._client.receive_messages():
                    self._msg_queue.put(("msg", msg))
            except asyncio.CancelledError:
                pass  # 正常取消，由 cmd_loop 的 disconnect 触发
            except Exception as e:
                detail = str(e) or type(e).__name__
                self._msg_queue.put(("error", detail))

        async def cmd_loop() -> None:
            while True:
                cmd = await self._cmd_queue.get()
                action = cmd.get("action")
                try:
                    if action == "query":
                        await self._client.query(cmd["prompt"])
                    elif action == "interrupt":
                        await self._client.interrupt()
                    elif action == "disconnect":
                        break
                except Exception as e:
                    self._msg_queue.put(
                        ("error", f"{action} 失败: {e}")
                    )

        recv_task = asyncio.create_task(recv_loop())
        cmd_task = asyncio.create_task(cmd_loop())

        # 等待任一任务完成（正常情况是 cmd_loop 因 disconnect 退出）
        done, pending = await asyncio.wait(
            [recv_task, cmd_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        # 4) 通知前端连接已关闭
        self._msg_queue.put(("done", None))

        # 5) 清理
        try:
            await self._client.disconnect()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _build_options(self, scripts_dir: str) -> ClaudeAgentOptions:
        """从配置构建 ClaudeAgentOptions"""
        claude_cfg = settings.factor_def.get("claude", {})

        repo_root = claude_cfg.get("repo_root", "D:/HST/QSExt")
        add_dirs = [scripts_dir]
        if skill_dir := settings.factor_def.get("skill_dir"):
            add_dirs.append(skill_dir)

        kwargs = {
            "skills": claude_cfg.get("skills", ["develop-factor"]),
            "mcp_servers": claude_cfg.get("mcp_servers", {}),
            "allowed_tools": claude_cfg.get("allowed_tools", [
                "mcp__jy_base_doc__*",
                "mcp__qs-registry__*",
                "Read", "Write", "Bash",
            ]),
            "cwd": repo_root,
            "permission_mode": claude_cfg.get("permission_mode", "acceptEdits"),
            "max_budget_usd": claude_cfg.get("max_budget_usd", 1.0),
            "add_dirs": add_dirs,
            "env": claude_cfg.get("env", {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1"}),
        }
        if cli_path := claude_cfg.get("cli_path"):
            kwargs["cli_path"] = cli_path

        return ClaudeAgentOptions(**kwargs)

    def _build_prompt(self, user_prompt: str, scripts_dir: str) -> str:
        """从配置模板构造发送给 Claude 的完整提示词

        模板从 QSWebConfig.json 的 factor_def.claude.system_prompt 读取，
        支持 {user_prompt} 和 {scripts_dir} 占位符。
        """
        claude_cfg = settings.factor_def.get("claude", {})
        template = claude_cfg.get("system_prompt", "")
        if not template:
            # fallback: 极简模式，仅透传用户输入
            return user_prompt
        return template.format(user_prompt=user_prompt, scripts_dir=scripts_dir)

    @staticmethod
    def format_message(msg) -> Optional[dict]:
        """将 SDK 消息类型转换为统一的 JSON 格式（静态方法，主线程安全）"""
        if isinstance(msg, SystemMessage):
            return {
                "type": "system",
                "data": {"content": getattr(msg, "content", str(msg))},
            }
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
                    # 思考过程，前端默认折叠
                    blocks.append({
                        "kind": "thinking",
                        "content": block.thinking,
                    })
                else:
                    text = getattr(block, "text", "") or str(block)
                    if text:
                        blocks.append({"kind": "text", "content": text})
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
