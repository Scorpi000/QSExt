"""
AI 因子助手服务 — CLI 子进程方案

直接 spawn Claude Code CLI 子进程（`--output-format stream-json --input-format
stream-json`），通过 stdin/stdout JSON 行协议通信。完整保留 Claude Code 的所有能力
（skills、MCP 工具、hooks 等），无 SDK 依赖，无线程/事件循环冲突。

与 ai_service.py (SDK 方案) 接口一致，通过 QSWebConfig.json 的
factor_def.claude.mode 切换（"cli" | "sdk"）。
"""

import json
import logging
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import uuid
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_junction(path: str) -> bool:
    """判断 Windows 目录是否为 junction（非管理员可创建的目录链接）

    Linux/macOS 上 junction 概念不存在，退化为 os.path.islink。
    """
    if os.name != "nt":
        return os.path.islink(path)
    try:
        import ctypes
        FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        return attrs != -1 and bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except Exception:
        return False


def _remove_path(path: str) -> None:
    """跨平台删除目录/链接

    Windows: cmd /c rmdir（兼容 junction 和普通目录）
    Linux/macOS: shutil.rmtree（目录）或 os.unlink（符号链接）
    """
    try:
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "rmdir", "/S", "/Q", path],
                check=False, capture_output=True,
            )
        elif os.path.islink(path):
            os.unlink(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
    except Exception:
        pass


class AiServiceCLI:
    """AI 助手服务 — CLI 子进程方案

    通过 Claude CLI stream-json 协议提供 AI 对话能力。
    配置由 context_config（来自 QSWebConfig.json ai_workbench）驱动。
    """

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_lines: list = []
        self._msg_queue: Optional[queue.Queue] = None
        self._session_id: str = "default"
        self._context_config: dict = {}

    # ------------------------------------------------------------------
    # 公开 API（主线程调用）
    # ------------------------------------------------------------------

    def start(self, prompt: str, context_config: dict) -> None:
        """启动 Claude CLI 子进程（新会话）并发送初始提示

        Args:
            prompt: 用户输入的需求描述
            context_config: 来自 ai_workbench.contexts.<context> 的完整配置字典
        """
        if self._process and self._process.poll() is None:
            self.disconnect()

        self._msg_queue = queue.Queue()
        self._session_id = str(uuid.uuid4())
        self._context_config = context_config
        self._launch(prompt, resume=False)

    def query(self, prompt: str, history: list = None) -> None:
        """发送后续消息

        - 进程还在运行：直接 stdin 发送后续消息
        - 进程已退出（-p 模式正常结束）：重新创建会话。
          -p 模式下 Claude Code 不持久化 session，无法使用 --resume。
          如需上下文连续性，通过 history 参数传入历史消息。
        """
        if self._process and self._process.poll() is None:
            self._send_json({
                "type": "user",
                "message": {"role": "user", "content": prompt},
                "parent_tool_use_id": None,
                "session_id": self._session_id,
            })
            return

        # -p 模式下进程已退出，session 未持久化，启动新会话
        self._msg_queue = queue.Queue()
        self._session_id = str(uuid.uuid4())
        self._launch(prompt, resume=False)

    def interrupt(self) -> None:
        """中断 Claude（终止子进程）"""
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._process = None

    def disconnect(self) -> None:
        """清理子进程和线程"""
        self.interrupt()
        self._process = None

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _launch(self, prompt: str, resume: bool) -> None:
        """启动 Claude CLI 子进程并发送提示

        resume=False: 新会话（--session-id <uuid>）
        resume=True:  恢复会话（--resume <uuid>）
        """
        self._stderr_lines = []
        ctx = self._context_config

        cli_path = ctx.get("cli_path", "claude")
        repo_root = ctx.get("repo_root", "D:/HST/QSExt")

        # 确保工作目录就绪（按 skills 列表动态链接）
        skills = ctx.get("skills", [])
        skill_dir = ctx.get("skill_dir", "")
        self._ensure_workspace(repo_root, skills, skill_dir)

        cmd = [
            cli_path,
            "-p",
            "--verbose",
            "--output-format", "stream-json",
            "--input-format", "stream-json",
            "--permission-mode", ctx.get("permission_mode", "acceptEdits"),
            "--max-budget-usd", str(ctx.get("max_budget_usd", 1.0)),
        ]

        # 附加目录（确保 Claude 至少有一个工作目录）
        if scripts_dir := ctx.get("scripts_dir"):
            cmd.extend(["--add-dir", scripts_dir])
        else:
            cmd.extend(["--add-dir", repo_root])
        if skill_dir:
            cmd.extend(["--add-dir", skill_dir])

        # 会话管理：新会话用 --session-id，后续用 --resume
        if resume:
            cmd.extend(["--resume", self._session_id])
        else:
            cmd.extend(["--session-id", self._session_id])

        # MCP 配置
        mcp_servers = ctx.get("mcp_servers", {})
        tools = ctx.get("tools", [])
        if mcp_servers or tools:
            mcp_config_path = self._write_mcp_config(mcp_servers, tools)
            cmd.extend(["--mcp-config", mcp_config_path])
            cmd.append("--strict-mcp-config")

        # 环境变量
        env = os.environ.copy()
        env.update(ctx.get("env", {}))
        for server_cfg in mcp_servers.values():
            if isinstance(server_cfg, dict):
                server_env = server_cfg.get("env", {})
                if isinstance(server_env, dict):
                    env.update(server_env)

        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=repo_root,
                env=env,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except FileNotFoundError:
            self._msg_queue.put(("error", f"找不到 Claude CLI: {cli_path}"))
            return
        except Exception as e:
            self._msg_queue.put(("error", f"启动 Claude CLI 失败: {e}"))
            return

        # 后台读取 stdout / stderr（捕获局部引用，避免线程间竞态）
        proc = self._process
        self._stdout_thread = threading.Thread(
            target=self._read_stdout, args=(proc,), daemon=True
        )
        self._stdout_thread.start()
        threading.Thread(
            target=self._read_stderr, args=(proc,), daemon=True
        ).start()

        # 发送提示
        scripts_dir_val = ctx.get("scripts_dir", "")
        self._send_json({
            "type": "user",
            "message": {
                "role": "user",
                "content": (
                    self._build_prompt(prompt, scripts_dir_val)
                    if not resume else prompt
                ),
            },
            "parent_tool_use_id": None,
            "session_id": self._session_id,
        })

    @property
    def msg_queue(self) -> Optional[queue.Queue]:
        return self._msg_queue

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _send_json(self, data: dict) -> None:
        """向子进程 stdin 写入一行 JSON"""
        if not self._process:
            return
        if self._process.poll() is not None:
            stderr_tail = "".join(self._stderr_lines[-20:])
            self._msg_queue.put(("error", f"Claude 进程已退出 (code={self._process.returncode}): {stderr_tail[:500]}"))
            return
        try:
            line = json.dumps(data, ensure_ascii=False) + "\n"
            self._process.stdin.write(line)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError):
            self._msg_queue.put(("error", "无法向 Claude 发送消息（连接已断开）"))

    def _read_stdout(self, proc: subprocess.Popen) -> None:
        """后台线程：读取 stdout 的 JSON 行"""
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = self._parse_cli_message(data)
                if msg is not None:
                    self._msg_queue.put(("msg", msg))
                if data.get("type") == "result" and not data.get("is_error"):
                    self._msg_queue.put(("done", None))
            # CLI 在 -p 模式下完成后退出，这是正常行为
            exit_code = proc.wait()
            if exit_code != 0:
                stderr_tail = "".join(self._stderr_lines[-20:])
                logger.warning("Claude CLI 退出 (code=%d): %s", exit_code, stderr_tail)
                # 通知前端进程异常退出
                if self._msg_queue:
                    self._msg_queue.put(("error", f"Claude 异常退出 (code={exit_code}): {stderr_tail[:500]}"))
        except Exception as e:
            logger.warning("读取 Claude 输出失败: %s", e)
            if self._msg_queue:
                self._msg_queue.put(("error", f"读取 Claude 输出失败: {e}"))

    def _read_stderr(self, proc: subprocess.Popen) -> None:
        """后台线程：收集 stderr 用于错误诊断"""
        try:
            for line in proc.stderr:
                self._stderr_lines.append(line)
        except Exception:
            pass

    def _parse_cli_message(self, data: dict) -> Optional[dict]:
        """将 CLI stream-json 消息转为前端统一格式

        CLI 输出格式与 SDK 消息类型的对应关系:
          {"type":"system","subtype":"init",...}       → SystemMessage
          {"type":"assistant","message":{...},...}     → AssistantMessage
          {"type":"user","message":{...},...}          → UserMessage (echo)
          {"type":"result","subtype":"success",...}    → ResultMessage
          {"type":"stream",...}                        → StreamEvent

        我们用 SDK 同样的消息类型名，方便前端复用。
        """
        msg_type = data.get("type", "")

        if msg_type == "system":
            subtype = data.get("subtype", "")
            if subtype == "init":
                # 初始化消息，前端可忽略
                return {
                    "type": "system",
                    "data": {"content": f"session: {data.get('session_id', '?')}"},
                }
            return None  # 隐藏其他系统消息（thinking_tokens 等）

        elif msg_type == "assistant":
            message = data.get("message", {})
            content = message.get("content", [])
            blocks = []
            for block in content:
                block_type = block.get("type", "")
                if block_type == "text":
                    blocks.append({
                        "kind": "text",
                        "content": block.get("text", ""),
                    })
                elif block_type == "tool_use":
                    blocks.append({
                        "kind": "tool_use",
                        "tool_name": block.get("name", ""),
                        "tool_input": block.get("input", {}),
                        "id": block.get("id", ""),
                    })
                elif block_type == "tool_result":
                    blocks.append({
                        "kind": "tool_result",
                        "content": block.get("content", ""),
                        "tool_use_id": block.get("tool_use_id", ""),
                    })
                elif block_type == "thinking":
                    blocks.append({
                        "kind": "thinking",
                        "content": block.get("thinking", ""),
                    })
                elif block_type == "server_tool_use":
                    blocks.append({
                        "kind": "tool_use",
                        "tool_name": block.get("name", ""),
                        "tool_input": block.get("input", {}),
                        "id": block.get("id", ""),
                    })

            # 检测 action_card 嵌入
            for blk in blocks:
                if blk.get("kind") == "text":
                    action_card = self._extract_action_card(blk.get("content", ""))
                    if action_card:
                        # 将 action_card 作为独立消息入队
                        self._msg_queue.put(("msg", {
                            "type": "action_card",
                            "data": action_card,
                        }))
                        # 从文本中移除 action_card 内容
                        blk["content"] = self._strip_action_card(
                            blk.get("content", "")
                        )

            return {"type": "assistant", "data": {"blocks": blocks}}

        elif msg_type == "user":
            # --replay-user-messages 回显，跳过
            return None

        elif msg_type == "result":
            subtype = data.get("subtype", "")
            is_error = data.get("is_error", False) or subtype == "error"
            # 文本内容已在 assistant 消息中展示，这里只发完成信号
            # is_error 时保留错误信息
            if is_error:
                return {
                    "type": "result",
                    "data": {
                        "content": data.get("result", ""),
                        "is_error": True,
                    },
                }
            # 正常完成：不发可见消息，由 _read_stdout 发送 done 信号
            return None

        elif msg_type == "stream_event":
            # 流式增量，content 在顶层
            return {
                "type": "stream",
                "data": {"content": data.get("content", "")},
            }

        elif msg_type == "error":
            return {
                "type": "error",
                "data": {"message": data.get("message", str(data))},
            }

        # 未识别的消息类型
        return None

    def _write_mcp_config(self, mcp_servers: dict, tools: list = None) -> str:
        """将 MCP 服务器配置写入临时 JSON 文件，返回文件路径"""
        config = {"mcpServers": {}}
        for name, server in mcp_servers.items():
            if isinstance(server, dict) and server.get("type") != "sdk":
                entry = {
                    "command": server.get("command", ""),
                    "args": server.get("args", []),
                }
                if server.get("env"):
                    entry["env"] = server["env"]
                config["mcpServers"][name] = entry

        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="mcp_config_",
            delete=False,
            encoding="utf-8",
        )
        json.dump(config, tmp, indent=2)
        tmp.close()
        return tmp.name

    def _ensure_workspace(
        self, repo_root: str, skills: list, skill_dir: str
    ) -> None:
        """确保工作目录就绪：git 仓库 + .claude/ + 动态链接技能"""
        logger.info("检查工作目录: %s", repo_root)
        claude_dir = os.path.join(repo_root, ".claude")
        skills_dir = os.path.join(claude_dir, "skills")

        # 1) 确保 .claude/skills/ 目录存在
        os.makedirs(skills_dir, exist_ok=True)

        # 2) 确保是 git 仓库（Claude Code 需要）
        git_dir = os.path.join(repo_root, ".git")
        if not os.path.exists(git_dir):
            subprocess.run(
                ["git", "init"],
                cwd=repo_root,
                check=False, capture_output=True,
            )

        # 3) 根据 context_config.skills 列表动态链接技能
        if skill_dir and skills:
            for skill_name in skills:
                self._link_skill(skills_dir, skill_name, skill_dir)

    @staticmethod
    def _link_skill(skills_dir: str, skill_name: str, skill_source_parent: str) -> None:
        """在 .claude/skills/ 下创建技能的目录链接

        每次启动时检查——若旧链接指向错误位置则删除重建。
        Windows: 用 mklink /J 创建 junction（无需管理员权限）
        Linux/macOS: 用 os.symlink 创建符号链接
        """
        target = os.path.join(skills_dir, skill_name)
        source = os.path.join(skill_source_parent, skill_name)

        if not os.path.isdir(source):
            return

        # 检查已有链接/目录是否正确
        if os.path.exists(target):
            is_link = os.path.islink(target) or _is_junction(target)
            if is_link:
                # 检查是否指向正确位置
                if os.path.normcase(os.path.realpath(target)) == \
                   os.path.normcase(os.path.realpath(source)):
                    return  # 已正确，跳过
            # 指向不对或不是链接，删除后重建
            logger.info("移除旧的技能链接/目录: %s", target)
            _remove_path(target)

        # 创建链接
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", target, source],
                    check=False, capture_output=True, text=True,
                )
                if result.returncode != 0:
                    logger.warning(
                        "mklink 失败 [%s -> %s]: %s",
                        target, source, result.stderr.strip(),
                    )
            else:
                os.symlink(source, target, target_is_directory=True)
            logger.info("技能链接已创建: %s -> %s", target, source)
        except Exception as e:
            logger.warning("创建技能链接失败 [%s -> %s]: %s", target, source, e)

    def _build_prompt(self, user_prompt: str, scripts_dir: str) -> str:
        """构造发送给 Claude 的初始提示

        system_prompt 作为系统指令通过 --system-prompt 传递，
        用户消息保持原文。保留 {user_prompt}/{scripts_dir} 兼容旧模板。
        """
        template = self._context_config.get("system_prompt", "")
        if not template:
            return user_prompt
        if "{user_prompt}" in template:
            # 旧模板格式（兼容）
            return template.format(user_prompt=user_prompt, scripts_dir=scripts_dir)
        # 新格式：system_prompt 不含占位符，单独传递
        return user_prompt

    @staticmethod
    def _extract_action_card(text: str) -> Optional[dict]:
        """从文本中提取 action_card JSON

        支持两种格式：
        1. 代码块内: ```json\n{ "type": "action_card", ... }\n```
        2. 纯 JSON 行
        """
        import re

        # 匹配 action_card JSON 模式（在代码块中或独立出现）
        # 查找 JSON 对象包含 "type": "action_card"
        pattern = r'\{[^{}]*"type"\s*:\s*"action_card"[^{}]*\}'
        match = re.search(pattern, text)
        if not match:
            return None

        try:
            obj = json.loads(match.group())
            if obj.get("type") == "action_card":
                return obj.get("data", obj)
        except json.JSONDecodeError:
            pass

        # 尝试更宽松的匹配：提取完整 JSON 对象（可能跨多行且有嵌套）
        start = text.find('"type": "action_card"')
        if start == -1:
            return None
        # 向前找到第一个 {
        brace_start = text.rfind('{', 0, start)
        if brace_start == -1:
            return None
        # 从 { 开始找匹配的 }
        depth = 0
        i = brace_start
        while i < len(text):
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
            i += 1
        return None

    @staticmethod
    def _strip_action_card(text: str) -> str:
        """从文本中移除 action_card JSON 内容"""
        import re
        # 移除 JSON 代码块中的 action_card
        # 匹配完整的 ```json ... ``` 块中包含 action_card
        text = re.sub(
            r'```json\s*\n?\{[^`]*"type"\s*:\s*"action_card"[^`]*\}\s*\n?```',
            '', text,
        )
        # 移除独立 action_card JSON 行
        text = re.sub(
            r'\n?\{[^{}]*"type"\s*:\s*"action_card"[^{}]*\}\n?',
            '', text,
        )
        return text.strip()

    # format_message 复用 SDK 版本（消息格式一致）
    @staticmethod
    def format_message(msg) -> Optional[dict]:
        """消息已由 _parse_cli_message 转为统一格式，此方法为兼容保留"""
        if isinstance(msg, dict) and "type" in msg:
            return msg
        return {"type": "unknown", "data": {"raw": str(msg)}}
