# -*- coding: utf-8 -*-
"""因子假设生成 — 独立脚本。

支持两种运行模式：
  - skill — Claude Agent SDK 自主决策，更灵活但成本更高
  - graph — LangGraph 节点驱动，可复现性更高

用法::

    # Skill 模式（默认）
    python -m QSExt.LLMFactor.scripts.run_hypothesis --target "动量因子"

    # Graph 模式
    python -m QSExt.LLMFactor.scripts.run_hypothesis --mode graph --target "动量因子"

    # 指定方向（跳过方向探索）
    python -m QSExt.LLMFactor.scripts.run_hypothesis --target "动量因子" --direction "动量/短期反转"

    # 指定工作区目录
    python -m QSExt.LLMFactor.scripts.run_hypothesis --target "动量因子" --workspace workspace/hypothesis

    # 指定配置文件
    python -m QSExt.LLMFactor.scripts.run_hypothesis --config my_pipeline.yaml --target "估值因子"

输出:
    - hypothesis/hypothesis.yaml : 生成的假设文档
    - hypothesis/claude_output.txt : Claude Agent 完整输出（Skill 模式）
    - hypothesis.log : 运行日志

环境要求:
    - PostgreSQL (JYDB) 连接可用（Graph 模式）
    - MCP servers 已配置（.mcp.json）
    - LLM 服务可用
    - Skill 模式额外需要: claude-agent-sdk, Claude Code CLI
"""
from __future__ import annotations

import argparse
import asyncio
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
    extract_yaml_from_output,
    format_agent_message,
    setup_logging,
)

__QS_Logger__ = logging.getLogger("QSR.pipeline.hypothesis")


# ============================================================
# Graph 模式
# ============================================================

def run_hypothesis_graph(
    target: str,
    direction: str | None = None,
    max_directions: int = 1,
) -> dict | None:
    """使用 LangGraph 执行假设生成。

    Args:
        target: 研究目标（如 "动量因子"）
        direction: 指定研究方向（跳过方向探索），None 则自动探索
        max_directions: 最大方向数

    Returns:
        包含 hypothesis, yaml, direction 字段的 dict，失败返回 None
    """
    from QSExt.LLMFactor.hypothesis.graph import run_hypothesis_generation
    from QSExt.LLMFactor.hypothesis import ResearchConfig

    config = ResearchConfig(target=target, market="A股", frequency="日频")

    __QS_Logger__.info("=" * 60)
    __QS_Logger__.info("假设生成（Graph 模式）")
    __QS_Logger__.info("  目标: %s, 方向: %s", target, direction or "自动探索")
    __QS_Logger__.info("=" * 60)

    result = run_hypothesis_generation(
        config=config.to_dict(),
        target_direction=direction,
        max_directions=max_directions,
    )

    completed = result.get("completed_hypotheses", [])
    if not completed:
        __QS_Logger__.error("假设生成: 未生成任何假设")
        return None

    first = completed[0]
    yaml_str = first.get("yaml", "")
    if not yaml_str:
        __QS_Logger__.error("假设生成: 假设 YAML 为空")
        return None

    return _parse_hypothesis_yaml(yaml_str, target, direction)


# ============================================================
# Skill 模式
# ============================================================

async def run_hypothesis_skill(
    target: str,
    direction: str | None,
    market: str,
    frequency: str,
    workspace_dir: Path,
    max_turns: int = 50,
    cli_path: str = "claude",
    project_root: Path | None = None,
    permission_mode: str = "bypassPermissions",
) -> dict | None:
    """使用 Claude Agent SDK 执行假设生成。

    Args:
        target: 研究目标（如 "动量因子"）
        direction: 指定研究方向，None 则自动探索
        market: 目标市场
        frequency: 数据频率
        workspace_dir: 工作区目录
        max_turns: 最大 Agent 轮次
        cli_path: Claude CLI 路径
        project_root: 项目根目录
        permission_mode: 权限模式

    Returns:
        包含 hypothesis, yaml, direction, claude_output 字段的 dict，失败返回 None
    """
    from claude_agent_sdk import query, ClaudeAgentOptions

    __QS_Logger__.info("=" * 60)
    __QS_Logger__.info("假设生成（Skill 模式）")
    __QS_Logger__.info("  目标: %s, 方向: %s", target, direction or "自动探索")
    __QS_Logger__.info("=" * 60)

    root = project_root or Path.cwd()
    mcp_config = root / ".mcp.json"
    output_path = workspace_dir / "hypothesis"
    output_path.mkdir(parents=True, exist_ok=True)

    direction_instruction = ""
    if direction:
        direction_instruction = f"\n\n请直接聚焦于方向「{direction}」，跳过方向探索步骤。"

    prompt = f"""请执行因子假设生成任务。

参数：
- 目标因子类别: {target}
- 目标市场: {market}
- 数据频率: {frequency}
{direction_instruction}

请严格按照 /hypothesis skill 的指令执行完整的流程：
1. 方向探索：搜索知识库、已有因子库、历史挖掘记录，提出候选方向
2. 深度调研：选择最有潜力的方向进行深入调研
3. 假设生成：基于调研结果生成一个完整的因子研究假设
4. 反思校验：进行自我批判和新颖性校验

最终输出必须是一个完整的 YAML 格式假设文档，包含 hypothesis_id、factor_name、economic_rationale、calculation_pseudo 等所有必需字段。

请将生成的假设文档保存到：{output_path.as_posix()}/hypothesis.yaml

请开始执行。"""

    options = ClaudeAgentOptions(
        cli_path=cli_path,
        skills=["hypothesis"],
        mcp_servers=str(mcp_config) if mcp_config.exists() else None,
        cwd=str(root),
        permission_mode=permission_mode,
        max_turns=max_turns,
    )

    __QS_Logger__.info("启动 Claude Agent（hypothesis skill）...")
    output_messages = []

    async for message in query(prompt=prompt, options=options):
        output_messages.extend(format_agent_message(message))

    full_output = "\n".join(output_messages)
    __QS_Logger__.info("Claude Agent 输出长度: %d 字符", len(full_output))

    yaml_str = None
    yaml_file = output_path / "hypothesis.yaml"
    if yaml_file.exists():
        yaml_str = yaml_file.read_text(encoding="utf-8")
    else:
        yaml_str = extract_yaml_from_output(full_output)
        if yaml_str:
            yaml_file.write_text(yaml_str, encoding="utf-8")

    if not yaml_str:
        __QS_Logger__.error("未能获取假设 YAML")
        return None

    result = _parse_hypothesis_yaml(yaml_str, target, direction)
    if result:
        result["claude_output"] = full_output
    return result


# ============================================================
# 辅助函数
# ============================================================

def _parse_hypothesis_yaml(yaml_str: str, target: str, direction: str | None) -> dict | None:
    """解析假设 YAML 为因子开发阶段输入格式。

    Args:
        yaml_str: YAML 字符串
        target: 研究目标
        direction: 研究方向

    Returns:
        解析后的 dict，失败返回 None
    """
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
    import os as _os
    return str(Path(__QS_MainPath__) / "LLMFactor" / "config" / "pipeline.yaml")


def main():
    parser = argparse.ArgumentParser(
        description="因子假设生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--config", default=None, help="流水线配置文件路径")
    parser.add_argument("--mode", choices=["skill", "graph"], default="skill", help="运行模式（默认：skill）")
    parser.add_argument("--target", default="全部", help="研究目标（如：动量因子、全部）")
    parser.add_argument("--market", default="A股", help="目标市场")
    parser.add_argument("--frequency", default="日频", help="数据频率")
    parser.add_argument("--direction", default=None, help="指定方向（跳过方向探索）")
    parser.add_argument("--max-directions", type=int, default=1, help="最大方向数（Graph 模式）")
    parser.add_argument("--workspace", default=None, help="工作区目录（默认自动生成 FM_<时间戳>）")
    parser.add_argument("--max-turns", type=int, default=50, help="最大 Agent 轮次（Skill 模式）")
    parser.add_argument("--log-level", default="INFO", help="日志级别")

    args = parser.parse_args()

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
        workspace_dir = base_dir / f"H_{timestamp}"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # 配置日志
    setup_logging(workspace_dir, args.log_level)

    # 准备 Skill 环境
    cli_path = pipeline_config.resolve_claude_cli()
    project_root = pipeline_config.resolve_project_root()
    hypo_config = pipeline_config.load_hypothesis_config()

    if args.mode == "skill":
        ensure_skills(project_root)

    # 运行假设生成
    try:
        if args.mode == "skill":
            result = asyncio.run(run_hypothesis_skill(
                target=args.target,
                direction=args.direction,
                market=args.market,
                frequency=args.frequency,
                workspace_dir=workspace_dir,
                max_turns=args.max_turns,
                cli_path=cli_path,
                project_root=project_root,
                permission_mode=hypo_config.permission_mode,
            ))
        else:
            result = run_hypothesis_graph(
                target=args.target,
                direction=args.direction,
                max_directions=args.max_directions,
            )
    except Exception as e:
        __QS_Logger__.error("假设生成异常: %s", e, exc_info=True)
        sys.exit(1)

    if not result:
        __QS_Logger__.error("假设生成失败")
        sys.exit(1)

    # 保存输出
    hypothesis_dir = workspace_dir / "hypothesis"
    hypothesis_dir.mkdir(parents=True, exist_ok=True)
    (hypothesis_dir / "hypothesis.yaml").write_text(result["yaml"], encoding="utf-8")
    if result.get("claude_output"):
        (hypothesis_dir / "claude_output.txt").write_text(
            result["claude_output"], encoding="utf-8",
        )

    # 汇总
    summary = {
        "run_at": datetime.now().isoformat(),
        "mode": args.mode,
        "target": args.target,
        "direction": result.get("direction"),
        "factor_name": result["hypothesis"].get("factor_name"),
        "workspace": str(workspace_dir),
    }
    summary_path = workspace_dir / "hypothesis_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    __QS_Logger__.info("=" * 60)
    __QS_Logger__.info("假设生成完成")
    __QS_Logger__.info("  因子名称: %s", summary["factor_name"])
    __QS_Logger__.info("  方向: %s", summary["direction"])
    __QS_Logger__.info("  工作区: %s", workspace_dir)
    __QS_Logger__.info("=" * 60)


if __name__ == "__main__":
    main()
