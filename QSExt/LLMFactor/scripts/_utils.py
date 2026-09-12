# -*- coding: utf-8 -*-
"""LLMFactor 流水线脚本的共享工具模块。

为假设生成（run_hypothesis.py）、因子开发（run_development.py）、
因子评测（run_evaluation.py）提供公共函数。

注意：本模块是内部模块，不作为公开 API 使用。
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from QSExt import __QS_MainPath__

__QS_Logger__ = logging.getLogger("QSR.pipeline.utils")


# ============================================================
# 公共常量
# ============================================================

# Skill 源目录（相对于项目根目录）
SKILL_SOURCES = {
    "generate-factor-def-code": "QSExt/DefModule/skills/generate-factor-def-code",
    "hypothesis": "QSExt/LLMFactor/hypothesis/skill/hypothesis",
    "develop-factor": "QSExt/LLMFactor/development/skill/develop-factor",
}


# ============================================================
# 日志配置
# ============================================================

def setup_logging(workspace_dir: Path, log_level: str = "INFO") -> None:
    """配置日志：同时输出到控制台和文件。

    Args:
        workspace_dir: 工作区目录
        log_level: 日志级别
    """
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(logging.StreamHandler(sys.stdout))
    log_file = workspace_dir / "pipeline.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)
    __QS_Logger__.info("日志文件: %s", log_file)


# ============================================================
# Agent 消息格式化
# ============================================================

def format_agent_message(message) -> list[str]:
    """将 Claude Agent 消息格式化为可读文本。

    Args:
        message: Claude Agent SDK 消息对象

    Returns:
        格式化后的文本行列表
    """
    lines = []
    role = getattr(message, "role", "")
    if role:
        lines.append(f"[{role}]")

    content = getattr(message, "content", None)
    if content is None:
        return lines

    if isinstance(content, str):
        if content.strip():
            lines.append(content)
        return lines

    if isinstance(content, list):
        for block in content:
            block_type = getattr(block, "type", None) or type(block).__name__

            if block_type in ("text", "TextBlock"):
                text = getattr(block, "text", "")
                if text.strip():
                    lines.append(text)

            elif block_type in ("tool_use", "ToolUseBlock"):
                tool_name = getattr(block, "name", "unknown")
                tool_input = getattr(block, "input", {})
                lines.append(f"[tool_use] {tool_name}")
                try:
                    input_str = json.dumps(tool_input, ensure_ascii=False, indent=2)
                    if len(input_str) > 2000:
                        input_str = input_str[:2000] + "\n... (truncated)"
                    lines.append(input_str)
                except Exception:
                    lines.append(str(tool_input))

            elif block_type in ("tool_result", "ToolResultBlock"):
                tool_id = getattr(block, "tool_use_id", "")
                result_content = getattr(block, "content", "")
                if isinstance(result_content, list):
                    result_text = "\n".join(getattr(r, "text", str(r)) for r in result_content)
                else:
                    result_text = str(result_content)
                if len(result_text) > 3000:
                    result_text = result_text[:3000] + "\n... (truncated)"
                lines.append(f"[tool_result] id={tool_id[:16]}...")
                lines.append(result_text)

            elif block_type in ("thinking", "ThinkingBlock"):
                thinking = getattr(block, "thinking", "")
                if thinking.strip():
                    lines.append(f"[thinking] {thinking[:500]}")

            else:
                lines.append(f"[{block_type}] {str(block)[:500]}")

    return lines


# ============================================================
# YAML 提取
# ============================================================

def extract_yaml_from_output(output: str) -> str | None:
    """从 Claude 输出中提取 YAML 内容。

    Args:
        output: Claude Agent 输出文本

    Returns:
        提取到的 YAML 字符串，失败返回 None
    """
    pattern = r"```yaml\s*\n(.*?)```"
    match = re.search(pattern, output, re.DOTALL)
    if match:
        return match.group(1).strip()
    pattern = r"(hypothesis_id:.*?)(?=\n---|\n##|\Z)"
    match = re.search(pattern, output, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


# ============================================================
# 因子名称提取
# ============================================================

def extract_factor_name_from_code(code_path: Path) -> str:
    """从因子代码中提取因子名称。

    尝试从 FactorDef 对象的 Name 字段或 TargetTable 字段读取，
    回退到目录名称。

    Args:
        code_path: factor_def.py 的路径

    Returns:
        因子名称
    """
    try:
        content = code_path.read_text(encoding="utf-8")
        match = re.search(r"""Name\s*[:=]\s*['"]([^'"]+)['"]""", content)
        if match:
            return match.group(1)
        match = re.search(r"""TargetTable\s*[:=]\s*['"]([^'"]+)['"]""", content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return code_path.parent.name


def extract_factor_name_from_output(output: str) -> str:
    """从 Claude 输出中提取因子名称。

    Args:
        output: Claude Agent 输出文本

    Returns:
        因子名称
    """
    patterns = [
        r"factor_name[:\s]+['\"]?(\w+)['\"]?",
        r"因子名称[:\s]+(\w+)",
        r"Generated factor[:\s]+(\w+)",
    ]
    for p in patterns:
        match = re.search(p, output, re.IGNORECASE)
        if match:
            return match.group(1)
    return "unknown_factor"


# ============================================================
# Skill 环境准备
# ============================================================

def ensure_skills(project_root: Path) -> None:
    """确保项目根目录：git 仓库 + .claude/skills/ + skill 目录链接。

    幂等——每次流水线启动前调用，已有正确链接时跳过。

    Args:
        project_root: 项目根目录
    """
    claude_dir = project_root / ".claude"
    skills_dir = claude_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    if not (project_root / ".git").exists():
        subprocess.run(
            ["git", "init"], cwd=str(project_root),
            check=False, capture_output=True,
        )

    for skill_name, skill_rel_path in SKILL_SOURCES.items():
        source = project_root / skill_rel_path
        if not source.is_dir():
            __QS_Logger__.warning("skill 源目录不存在，跳过: %s", source)
            continue
        _link_skill(skills_dir, skill_name, source)


def _link_skill(skills_dir: Path, skill_name: str, source: Path) -> None:
    """创建 skill 目录链接（Windows: mklink /J, Unix: symlink）。幂等。

    Args:
        skills_dir: .claude/skills/ 目录
        skill_name: skill 名称
        source: skill 源目录路径
    """
    target = skills_dir / skill_name

    if target.exists():
        if os.path.normcase(str(target.resolve())) == os.path.normcase(str(source.resolve())):
            return
        _rmpath(target)

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(target), str(source)],
                check=False, capture_output=True, text=True,
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "").strip()
                __QS_Logger__.warning("mklink 失败 [%s -> %s]: %s", target, source, err)
            else:
                __QS_Logger__.info("skill 链接已创建: %s -> %s", target, source)
        else:
            os.symlink(str(source), str(target), target_is_directory=True)
            __QS_Logger__.info("skill 链接已创建: %s -> %s", target, source)
    except Exception as e:
        __QS_Logger__.warning("创建 skill 链接失败: %s", e)


def _rmpath(path: Path) -> None:
    """删除 Junction / 符号链接 / 目录。

    Args:
        path: 要删除的路径
    """
    try:
        if os.name == "nt" and path.exists():
            subprocess.run(
                ["cmd", "/c", "rmdir", str(path)],
                check=False, capture_output=True,
            )
        elif path.is_symlink():
            path.unlink()
        elif path.is_dir():
            import shutil
            shutil.rmtree(str(path))
        elif path.is_file():
            path.unlink()
    except Exception as e:
        __QS_Logger__.warning("删除路径失败 [%s]: %s", path, e)


# ============================================================
# 阶段耗时
# ============================================================

def stage_elapsed(start, end):
    """计算阶段耗时。

    Args:
        start: 开始时间（ISO 格式字符串）
        end: 结束时间（ISO 格式字符串）

    Returns:
        耗时秒数，无法计算时返回 None
    """
    if start and end:
        return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 1)
    return None
