# -*- coding: utf-8 -*-
"""因子开发 — 独立脚本。

从假设文档生成可执行的因子代码，支持自动验证与修复。

支持两种运行模式：
  - skill — Claude Agent SDK 自主决策，更灵活但成本更高
  - graph — LangGraph 节点驱动，可复现性更高

用法::

    # Skill 模式（默认，含自动验证与修复）
    python -m QSExt.LLMFactor.scripts.run_development --hypothesis workspace/hypothesis/hypothesis.yaml

    # Graph 模式
    python -m QSExt.LLMFactor.scripts.run_development --mode graph --hypothesis workspace/hypothesis/hypothesis.yaml

    # 指定工作区目录
    python -m QSExt.LLMFactor.scripts.run_development --hypothesis hypothesis.yaml --workspace workspace/dev

    # 禁用参数搜索
    python -m QSExt.LLMFactor.scripts.run_development --hypothesis hypothesis.yaml --no-param-search

    # 调试模式（更多输出）
    python -m QSExt.LLMFactor.scripts.run_development --hypothesis hypothesis.yaml --log-level DEBUG

输出:
    - development/factor_def.py : 生成的因子代码
    - development/claude_output.txt : Claude Agent 完整输出（Skill 模式）
    - development/fix_attempt_*.txt : 自动修复日志（Skill 模式，如有）
    - development.log : 运行日志

环境要求:
    - LLM 服务可用（假设生成和因子开发需要）
    - Skill 模式额外需要: claude-agent-sdk, Claude Code CLI
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Windows 环境设置
if sys.platform == "win32":
    os.environ["CLAUDE_CODE_USE_POWERSHELL_TOOL"] = "1"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from QSExt import __QS_MainPath__

load_dotenv(__QS_MainPath__ + "/config/.env")

from QSExt.LLMFactor.scripts._utils import (
    ensure_skills,
    extract_factor_name_from_code,
    extract_factor_name_from_output,
    format_agent_message,
    setup_logging,
)

__QS_Logger__ = logging.getLogger("QSR.pipeline.development")


# ============================================================
# 因子代码验证
# ============================================================

def validate_factor_code(factor_dir: str) -> tuple[bool, str]:
    """验证因子代码的基础正确性。

    检查项：
    1. factor_def.py 是否存在
    2. 模块能否正常导入（触发 @FactorOperatorized 装饰器执行）
    3. 是否包含 defFactor 函数

    Args:
        factor_dir: 因子目录路径

    Returns:
        (passed, error_message) — passed=True 时 error_message 为空
    """
    factor_path = Path(factor_dir)
    code_path = factor_path / "factor_def.py"

    if not code_path.exists():
        return False, "factor_def.py 不存在"

    try:
        module_name = f"_validate_factor_{code_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(code_path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        error_type = type(e).__name__
        return False, f"模块导入失败: {error_type}: {e}"

    if not hasattr(module, "defFactor"):
        return False, "模块中缺少 defFactor 函数"

    return True, ""


# ============================================================
# Graph 模式
# ============================================================

def run_development_graph(hypothesis: dict, workspace_dir: Path, dev_config=None) -> dict | None:
    """使用 LangGraph 执行因子开发。

    Args:
        hypothesis: HypothesisDoc.to_development_input() 的输出
        workspace_dir: 工作区目录
        dev_config: DevelopmentConfig 实例

    Returns:
        包含 factor_dir, factor_code_path, factor_name, status 字段的 dict，失败返回 None
    """
    from QSExt.LLMFactor.development.config import DevelopmentConfig
    from QSExt.LLMFactor.development.graph import run_development

    __QS_Logger__.info("=" * 60)
    __QS_Logger__.info("因子开发（Graph 模式）")
    __QS_Logger__.info("  因子: %s", hypothesis.get("factor_name", "unknown"))
    __QS_Logger__.info("=" * 60)

    config = dev_config or DevelopmentConfig()
    development_dir = workspace_dir / "development"
    development_dir.mkdir(parents=True, exist_ok=True)

    result = run_development(
        hypothesis=hypothesis,
        config=config.to_dict(),
        workspace_dir=str(development_dir),
    )

    if not result:
        __QS_Logger__.error("因子开发: 开发返回空结果")
        return None

    __QS_Logger__.info("因子开发完成: status=%s", result.get("status"))
    return result


# ============================================================
# Skill 模式
# ============================================================

async def run_development_skill(
    hypothesis_yaml_path: str,
    workspace_dir: Path,
    max_turns: int = 80,
    cli_path: str = "claude",
    project_root: Path | None = None,
    permission_mode: str = "bypassPermissions",
    dev_config=None,
) -> dict | None:
    """使用 Claude Agent SDK 执行因子开发。

    Args:
        hypothesis_yaml_path: 假设 YAML 文件路径
        workspace_dir: 工作区目录
        max_turns: 最大 Agent 轮次
        cli_path: Claude CLI 路径
        project_root: 项目根目录
        permission_mode: 权限模式
        dev_config: DevelopmentConfig 实例

    Returns:
        包含 factor_dir, factor_code_path, factor_name, status, claude_output 字段的 dict
    """
    from claude_agent_sdk import query, ClaudeAgentOptions
    from QSExt.LLMFactor.development.config import DevelopmentConfig

    __QS_Logger__.info("=" * 60)
    __QS_Logger__.info("因子开发（Skill 模式）")
    __QS_Logger__.info("=" * 60)

    root = project_root or Path.cwd()
    mcp_config = root / ".mcp.json"
    development_dir = workspace_dir / "development"
    development_dir.mkdir(parents=True, exist_ok=True)

    dc = dev_config or DevelopmentConfig()
    param_search_step = (
        "3. 参数搜索：使用 Optuna 搜索最优超参数"
        if dc.enable_param_search
        else "3. 参数搜索：已跳过（配置中 enable_param_search=false）"
    )

    prompt = f"""请执行因子开发任务。

假设文档路径：{hypothesis_yaml_path}

请严格按照 /develop-factor skill 的指令执行流程：
1. 代码生成：读取假设文档，检索经验组件和参考代码，生成 factor_def.py
2. 自动验证：运行语法检查、执行验证、泄漏检测、单位检查、语义审查
   **重要：执行验证必须用 Bash 工具运行 Python 命令，实际导入 factor_def.py 并执行 defFactor()。**
   **不要只做静态分析！必须通过 python -c "import ..." 确认代码在运行时没有错误。**
{param_search_step}
4. 结果汇总：保存所有产出物

请将所有产出物保存到：{development_dir.as_posix()}/

请开始执行。"""

    options = ClaudeAgentOptions(
        cli_path=cli_path,
        skills=["develop-factor"],
        mcp_servers=str(mcp_config) if mcp_config.exists() else None,
        cwd=str(root),
        permission_mode=permission_mode,
        max_turns=max_turns,
    )

    __QS_Logger__.info("启动 Claude Agent（develop-factor skill）...")
    output_messages = []

    async for message in query(prompt=prompt, options=options):
        output_messages.extend(format_agent_message(message))

    full_output = "\n".join(output_messages)
    __QS_Logger__.info("Claude Agent 输出长度: %d 字符", len(full_output))

    factor_def = development_dir / "factor_def.py"
    if not factor_def.exists():
        for py_file in development_dir.glob("**/*.py"):
            if "defFactor" in py_file.read_text(encoding="utf-8"):
                factor_def = py_file
                break

    if not factor_def.exists():
        __QS_Logger__.error("因子开发阶段未生成 factor_def.py")
        return None

    return {
        "factor_dir": str(development_dir),
        "factor_code_path": str(factor_def),
        "factor_name": extract_factor_name_from_output(full_output),
        "status": "completed",
        "claude_output": full_output,
    }


async def run_development_skill_with_fix(
    hypothesis_yaml_path: str,
    workspace_dir: Path,
    max_turns: int = 80,
    cli_path: str = "claude",
    project_root: Path | None = None,
    dev_config=None,
    max_fix_attempts: int = 3,
    permission_mode: str = "bypassPermissions",
) -> dict | None:
    """使用 Claude Agent SDK 执行因子开发，带本地验证和自动修复循环。

    流程：
    1. 调用 run_development_skill 生成因子代码
    2. 本地验证（import + defFactor 检查）
    3. 如果失败，将错误信息发回 Claude Agent 修复
    4. 重复直到通过或达到最大修复次数

    Args:
        hypothesis_yaml_path: 假设 YAML 文件路径
        workspace_dir: 工作区目录
        max_turns: 初始生成的最大 Agent 轮次
        cli_path: Claude CLI 路径
        project_root: 项目根目录
        dev_config: DevelopmentConfig 实例
        max_fix_attempts: 最大修复尝试次数
        permission_mode: 权限模式

    Returns:
        包含 factor_dir 等字段的 dict，失败返回 None
    """
    from claude_agent_sdk import query, ClaudeAgentOptions

    # 第一次生成
    result = await run_development_skill(
        hypothesis_yaml_path=hypothesis_yaml_path,
        workspace_dir=workspace_dir, max_turns=max_turns,
        cli_path=cli_path, project_root=project_root, dev_config=dev_config,
    )

    if not result or result.get("status") != "completed":
        return result

    factor_dir = result.get("factor_dir", "")

    # 验证-修复循环
    for attempt in range(1, max_fix_attempts + 1):
        passed, error_msg = validate_factor_code(factor_dir)
        if passed:
            __QS_Logger__.info("因子代码验证通过（第 %d 次检查）", attempt)
            return result

        __QS_Logger__.warning("因子代码验证失败（第 %d 次）: %s", attempt, error_msg)

        __QS_Logger__.info("请求 Claude Agent 修复代码...")
        fix_prompt = f"""factor_def.py 存在以下错误，请修复：

错误信息：
{error_msg}

请读取 {factor_dir}/factor_def.py，修复错误后重新保存到同一位置。
只修复上述错误，不要改变因子的核心计算逻辑。

常见修复指南：
- 如果是 @FactorOperatorized 参数错误，args 只允许以下键：Arity, DTMode, IDMode, DataType, ModelArgs, LookBack
- IDMode 只能是 "单ID" 或 "多ID"，不能是 "全ID" 等其他值
- DTMode 只能是 "单时点" 或 "多时点"
- DataType 只能是 "double"、"object" 或 "string"

修复完成后，请确认 factor_def.py 已保存。"""

        root = project_root or Path.cwd()
        mcp_config = root / ".mcp.json"
        options = ClaudeAgentOptions(
            cli_path=cli_path,
            skills=["develop-factor"],
            mcp_servers=str(mcp_config) if mcp_config.exists() else None,
            cwd=str(root),
            permission_mode=permission_mode,
            max_turns=20,
        )

        fix_messages = []
        async for message in query(prompt=fix_prompt, options=options):
            fix_messages.extend(format_agent_message(message))

        fix_output = "\n".join(fix_messages)
        __QS_Logger__.info("修复 Agent 输出长度: %d 字符", len(fix_output))

        fix_log_path = Path(factor_dir) / f"fix_attempt_{attempt}.txt"
        fix_log_path.write_text(fix_output, encoding="utf-8")

        result["claude_output"] = result.get("claude_output", "") + f"\n\n--- Fix Attempt {attempt} ---\n" + fix_output

    # 最后一次验证
    passed, error_msg = validate_factor_code(factor_dir)
    if not passed:
        __QS_Logger__.error("因子代码验证仍未通过（%d 次修复后）: %s", max_fix_attempts, error_msg)
        result["status"] = "validation_failed"
        result["validation_error"] = error_msg

    return result


# ============================================================
# 辅助函数
# ============================================================

def _parse_hypothesis_yaml(yaml_str: str, target: str, direction: str | None) -> dict | None:
    """解析假设 YAML 为因子开发阶段输入格式。"""
    try:
        from QSExt.LLMFactor.hypothesis.models import (
            DirectionCandidate, HypothesisDoc, ResearchContext,
        )
        dummy_dir = DirectionCandidate(
            direction_tag=direction or target,
            category=target.replace("因子", ""),
            description="", rationale="",
        )
        context = ResearchContext(direction=dummy_dir)
        doc = HypothesisDoc.from_llm_yaml(yaml_str, context)
        development_input = doc.to_development_input()
        return {
            "hypothesis": development_input,
            "yaml": yaml_str,
            "direction": direction or "from_file",
        }
    except Exception as e:
        __QS_Logger__.error("解析假设 YAML 失败: %s", e, exc_info=True)
        return None


# ============================================================
# 主入口
# ============================================================

def _default_config_path() -> str:
    """获取默认配置文件路径。"""
    return str(Path(__QS_MainPath__) / "LLMFactor" / "config" / "pipeline.yaml")


def main():
    parser = argparse.ArgumentParser(
        description="因子开发 — 从假设文档生成因子代码",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--config", default=None, help="流水线配置文件路径")
    parser.add_argument("--mode", choices=["skill", "graph"], default="skill", help="运行模式（默认：skill）")
    parser.add_argument("--hypothesis", required=True, help="假设 YAML 文件路径")
    parser.add_argument("--workspace", default=None, help="工作区目录（默认自动生成 FM_<时间戳>）")
    parser.add_argument("--max-turns", type=int, default=80, help="最大 Agent 轮次（Skill 模式）")
    parser.add_argument("--max-fix-attempts", type=int, default=3, help="最大自动修复次数（Skill 模式）")
    parser.add_argument("--no-param-search", action="store_true", help="禁用参数搜索")
    parser.add_argument("--log-level", default="INFO", help="日志级别")

    args = parser.parse_args()

    # 验证假设文件
    hypothesis_path = Path(args.hypothesis)
    if not hypothesis_path.exists():
        print(f"错误: 假设文件不存在: {args.hypothesis}", file=sys.stderr)
        sys.exit(1)

    # 加载配置
    from QSExt.LLMFactor.pipeline_config import PipelineConfig
    config_path = args.config or _default_config_path()
    pipeline_config = PipelineConfig.from_yaml(config_path)
    __QS_Logger__.info("已加载配置: %s", config_path)

    # 确定工作区
    if args.workspace:
        workspace_dir = Path(args.workspace).resolve()
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = pipeline_config.resolve_workspace_dir().parent
        workspace_dir = base_dir / f"FM_{timestamp}"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # 配置日志
    setup_logging(workspace_dir, args.log_level)

    # 加载配置
    cli_path = pipeline_config.resolve_claude_cli()
    project_root = pipeline_config.resolve_project_root()
    dev_config = pipeline_config.load_development_config()

    if args.no_param_search:
        dev_config.enable_param_search = False

    # 准备 Skill 环境
    if args.mode == "skill":
        ensure_skills(project_root)

    # 解析假设
    yaml_str = hypothesis_path.read_text(encoding="utf-8")
    hypothesis_result = _parse_hypothesis_yaml(yaml_str, "factor", None)
    if not hypothesis_result:
        __QS_Logger__.error("解析假设 YAML 失败")
        sys.exit(1)

    # 复制假设文件到工作区
    hypothesis_dir = workspace_dir / "hypothesis"
    hypothesis_dir.mkdir(parents=True, exist_ok=True)
    (hypothesis_dir / "hypothesis.yaml").write_text(yaml_str, encoding="utf-8")

    # 运行因子开发
    try:
        if args.mode == "skill":
            result = asyncio.run(run_development_skill_with_fix(
                hypothesis_yaml_path=str(hypothesis_path),
                workspace_dir=workspace_dir,
                max_turns=args.max_turns,
                cli_path=cli_path,
                project_root=project_root,
                dev_config=dev_config,
                max_fix_attempts=args.max_fix_attempts,
                permission_mode=dev_config.permission_mode,
            ))
        else:
            result = run_development_graph(
                hypothesis_result["hypothesis"], workspace_dir, dev_config=dev_config,
            )
    except Exception as e:
        __QS_Logger__.error("因子开发异常: %s", e, exc_info=True)
        sys.exit(1)

    if not result:
        __QS_Logger__.error("因子开发失败")
        sys.exit(1)

    # 保存输出
    if result.get("claude_output"):
        (workspace_dir / "development" / "claude_output.txt").write_text(
            result["claude_output"], encoding="utf-8",
        )

    # 汇总
    factor_name = None
    code_path = result.get("factor_code_path")
    if code_path:
        factor_name = extract_factor_name_from_code(Path(code_path))

    summary = {
        "run_at": datetime.now().isoformat(),
        "mode": args.mode,
        "hypothesis_file": str(hypothesis_path),
        "factor_name": factor_name or result.get("factor_name"),
        "status": result.get("status"),
        "factor_dir": result.get("factor_dir"),
        "factor_code_path": result.get("factor_code_path"),
        "validation_error": result.get("validation_error"),
        "workspace": str(workspace_dir),
    }
    summary_path = workspace_dir / "development_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    __QS_Logger__.info("=" * 60)
    __QS_Logger__.info("因子开发完成")
    __QS_Logger__.info("  因子名称: %s", summary["factor_name"])
    __QS_Logger__.info("  状态: %s", summary["status"])
    __QS_Logger__.info("  代码路径: %s", summary["factor_code_path"])
    __QS_Logger__.info("  工作区: %s", workspace_dir)
    __QS_Logger__.info("=" * 60)


if __name__ == "__main__":
    main()
