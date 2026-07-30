"""
AI 因子助手服务

通过 claude-agent-sdk 的 query() 调用 Claude，加载 develop-factor 技能和
MCP 工具，流式生成 FactorDef 因子定义脚本。

所有 Claude Code 配置从 QSWebConfig.json 的 factor_def.claude 段读取。
query() 在独立线程中运行以避免与 FastAPI 事件循环冲突。
"""

import asyncio
import queue
import threading
from typing import AsyncIterator, Optional

from claude_agent_sdk import query, ClaudeAgentOptions, StreamEvent, ResultMessage
from claude_agent_sdk.types import (
    AssistantMessage,
    UserMessage,
    SystemMessage,
    ToolUseBlock,
    ToolResultBlock,
)

from app.core.config import settings


class AiService:
    """AI 因子助手服务"""

    async def chat(
        self,
        user_prompt: str,
        scripts_dir: str,
    ) -> AsyncIterator[dict]:
        """与 Claude 对话，流式返回消息

        query() 在独立线程中运行，通过队列将消息传回主事件循环。
        """
        claude_cfg = settings.factor_def.get("claude", {})
        prompt = self._build_prompt(user_prompt, scripts_dir)

        repo_root = claude_cfg.get("repo_root", "D:/HST/QSExt")
        add_dirs = [scripts_dir]
        if skill_dir := settings.factor_def.get("skill_dir"):
            add_dirs.append(skill_dir)

        stderr_lines = []

        opts = {
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
            opts["cli_path"] = cli_path
        opts["stderr"] = lambda line: stderr_lines.append(line)

        options = ClaudeAgentOptions(**opts)

        # 在独立线程中运行 query()，通过队列传递消息
        msg_queue: queue.Queue = queue.Queue()

        def _run_in_thread():
            async def _run():
                try:
                    async for msg in query(prompt=prompt, options=options):
                        msg_queue.put(("msg", msg))
                    msg_queue.put(("done", None))
                except Exception as e:
                    detail = f"{e}"
                    if stderr_lines:
                        detail += f"\nstderr: {''.join(stderr_lines[-50:])}"
                    msg_queue.put(("error", detail))

            asyncio.run(_run())

        thread = threading.Thread(target=_run_in_thread, daemon=True)
        thread.start()

        # 主事件循环中消费队列
        loop = asyncio.get_event_loop()
        while True:
            try:
                kind, payload = await loop.run_in_executor(None, msg_queue.get, True, 0.5)
            except queue.Empty:
                continue

            if kind == "done":
                break
            elif kind == "error":
                yield {
                    "type": "error",
                    "data": {"message": payload},
                }
                break
            elif kind == "msg":
                formatted = self._format_message(payload)
                if formatted:
                    yield formatted

    def _build_prompt(self, user_prompt: str, scripts_dir: str) -> str:
        """构造发送给 Claude 的完整提示词"""
        return (
            f"使用 develop-factor 技能，根据以下需求创建因子定义脚本：\n\n"
            f"{user_prompt}\n\n"
            f"请遵循 develop-factor 技能的所有步骤：\n"
            f"1. 理解需求并澄清不明确的部分\n"
            f"2. 通过 jy_base_doc 工具验证数据表和字段\n"
            f"3. 生成符合 FactorDef 框架规范的因子定义脚本\n"
            f"4. 将脚本保存到 {scripts_dir} 目录下\n\n"
            f"脚本必须包含 __FACTOR_META__ 和 defFactor(fdi) -> List[Factor]。\n"
            f"如果用户需求不明确，先使用 AskUserQuestion 工具询问缺失的关键信息。"
        )

    def _format_message(self, msg) -> Optional[dict]:
        """将 SDK 消息类型转换为统一的 JSON 格式"""
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
                    "content": getattr(msg, "content", str(msg)),
                    "is_error": getattr(msg, "is_error", False),
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
