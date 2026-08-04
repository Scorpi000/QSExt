# -*- coding: utf-8 -*-
"""因子挖掘流水线 — 统一入口（编排层）。

将假设生成、因子开发、因子评测三个阶段串联为完整流水线。
实际实现已拆分到以下独立脚本：
  - run_hypothesis.py — 假设生成
  - run_development.py — 因子开发
  - run_evaluation.py — 因子评测

支持两种运行模式（Skill / Graph）和两种运行方式（单次 / 持续循环）。

运行模式:
  - skill  — Claude Agent SDK 自主决策，更灵活但成本更高
  - graph  — LangGraph 节点驱动，可复现性更高

运行方式:
  - 单次（默认）: --max-rounds 1，跑一轮完整的 假设生成→因子开发→因子评测
  - 持续循环: --max-rounds N，由 DirectionScheduler 自动选方向，一轮一轮持续运行

用法::

    # 单次运行全部阶段（Skill 模式，默认）
    python -m QSExt.LLMFactor.scripts.run_pipeline --target "动量因子"

    # 单次运行（Graph 模式）
    python -m QSExt.LLMFactor.scripts.run_pipeline --mode graph --target "动量因子"

    # 指定方向（跳过方向探索）
    python -m QSExt.LLMFactor.scripts.run_pipeline --target "动量因子" --direction "动量/短期反转"

    # 仅运行假设生成
    python -m QSExt.LLMFactor.scripts.run_pipeline --target "动量因子" --stages hypothesis

    # 假设生成 + 因子开发（跳过评测）
    python -m QSExt.LLMFactor.scripts.run_pipeline --target "动量因子" --stages hypothesis,development

    # 仅运行因子开发（提供已有假设文件）
    python -m QSExt.LLMFactor.scripts.run_pipeline --stages development --hypothesis-yaml workspace/hypothesis/hypothesis.yaml

    # 持续循环（10 轮或 8 小时）
    python -m QSExt.LLMFactor.scripts.run_pipeline --target "动量因子" --max-rounds 10 --max-hours 8

    # 指定已有因子目录，直接评测
    python -m QSExt.LLMFactor.scripts.run_pipeline --factor-dir local/workspace/FM_xxx/development

    # 指定配置文件
    python -m QSExt.LLMFactor.scripts.run_pipeline --config my_pipeline.yaml --target "估值因子"

    # 复用已有评测缓存（不清空）
    python -m QSExt.LLMFactor.scripts.run_pipeline --target "动量因子" --no-clear-cache

环境要求:
    - PostgreSQL (JYDB) 连接可用
    - MCP servers 已配置（.mcp.json）
    - LLM 服务可用（假设生成和因子开发需要）
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

# ── 从独立脚本导入核心函数 ──
from QSExt.LLMFactor.scripts.run_hypothesis import (
    run_hypothesis_graph,
    run_hypothesis_skill,
)
from QSExt.LLMFactor.scripts.run_development import (
    run_development_graph,
    run_development_skill_with_fix,
)
from QSExt.LLMFactor.scripts.run_evaluation import (
    build_evaluation_context,
    run_evaluation,
)
from QSExt.LLMFactor.scripts._utils import (
    ensure_skills,
    extract_factor_name_from_code,
    setup_logging,
    stage_elapsed,
)

__QS_Logger__ = logging.getLogger("QSR.pipeline")


# ============================================================
# 方向目录（持续循环使用）
# ============================================================

DIRECTION_CATALOG = [
    "动量/短期反转", "动量/中期动量", "动量/动量因子",
    "估值/EP_TTM", "估值/BP_MRQ", "估值/SP_TTM",
    "波动率/低波动率", "波动率/特质波动率",
    "流动性/换手率", "流动性/非流动性",
    "质量/ROE", "质量/毛利率",
    "技术/量价背离", "技术/成交额分布",
]


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


def _default_config_path() -> str:
    """获取默认配置文件路径。"""
    return str(Path(__QS_MainPath__) / "LLMFactor" / "config" / "pipeline.yaml")


# ============================================================
# 持续循环
# ============================================================

def generate_candidates(target: str, scheduler) -> list:
    """生成候选方向列表。"""
    from QSExt.LLMFactor.hypothesis.models import DirectionCandidate

    coverage = scheduler.get_coverage()
    candidates = []
    for tag in DIRECTION_CATALOG:
        category = tag.split("/")[0]
        if target and category not in target and target not in tag:
            if target != "全部":
                continue
        stats = coverage.get(tag)
        candidate = DirectionCandidate(
            direction_tag=tag, category=category,
            description=f"研究方向: {tag}", rationale="", coverage=stats,
        )
        candidates.append(candidate)

    __QS_Logger__.info("生成 %d 个候选方向（目标: %s）", len(candidates), target)
    return candidates


def run_mining_loop(
    target: str, max_rounds: int, max_hours: float, mode: str,
    base_dir: Path, max_turns_hypothesis: int, max_turns_development: int,
    eval_config=None,
):
    """执行持续挖掘循环。"""
    from QSExt.LLMFactor.loop.models import LoopResult
    from QSExt.LLMFactor.loop.round_runner import RoundRunner
    from QSExt.LLMFactor.loop.scheduler import DirectionScheduler

    loop_id = f"loop_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    base_dir.mkdir(parents=True, exist_ok=True)

    loop_result = LoopResult(loop_id=loop_id, started_at=datetime.now().isoformat())
    scheduler = DirectionScheduler()
    runner = RoundRunner(
        mode=mode, base_dir=base_dir, target=target,
        max_turns_hypothesis=max_turns_hypothesis,
        max_turns_development=max_turns_development,
        eval_config=eval_config,
    )

    max_seconds = max_hours * 3600
    start_time = datetime.now()

    __QS_Logger__.info("=" * 60)
    __QS_Logger__.info("持续挖掘循环启动")
    __QS_Logger__.info("  循环 ID: %s", loop_id)
    __QS_Logger__.info("  目标: %s", target)
    __QS_Logger__.info("  最大轮次: %d", max_rounds)
    __QS_Logger__.info("  最大时间: %.1f 小时", max_hours)
    __QS_Logger__.info("  模式: %s", mode)
    __QS_Logger__.info("  工作区: %s", base_dir)
    __QS_Logger__.info("=" * 60)

    summary = scheduler.get_coverage_summary()
    __QS_Logger__.info("历史覆盖: %d 个方向, %d 次尝试, %d 次成功",
                       summary["total_directions"], summary["total_attempts"], summary["total_successes"])

    for round_num in range(1, max_rounds + 1):
        elapsed = (datetime.now() - start_time).total_seconds()
        if elapsed >= max_seconds:
            __QS_Logger__.info("达到时间上限 (%.1f 小时)，停止", max_hours)
            break

        __QS_Logger__.info("\n" + "=" * 60)
        __QS_Logger__.info("第 %d / %d 轮", round_num, max_rounds)
        __QS_Logger__.info("已用时间: %.1f / %.1f 分钟", elapsed / 60, max_seconds / 60)
        __QS_Logger__.info("=" * 60)

        candidates = generate_candidates(target, scheduler)
        selected = scheduler.select_next(candidates)
        if selected is None:
            __QS_Logger__.info("无可用方向，停止循环")
            break

        direction = selected.direction_tag
        __QS_Logger__.info("选定方向: %s", direction)

        round_result = runner.run_round(direction=direction, round_num=round_num)
        loop_result.add_round(round_result)
        _save_loop_summary(loop_result, base_dir)
        scheduler._coverage = None

        __QS_Logger__.info(
            "第 %d 轮结果: direction=%s, decision=%s, score=%.3f",
            round_num, direction, round_result.decision, round_result.composite_score,
        )

    loop_result.finished_at = datetime.now().isoformat()
    _save_loop_summary(loop_result, base_dir)

    __QS_Logger__.info("\n" + "=" * 60)
    __QS_Logger__.info("持续挖掘循环完成")
    __QS_Logger__.info("  总轮次: %d", loop_result.total_rounds)
    __QS_Logger__.info("  入库: %d", loop_result.accepted)
    __QS_Logger__.info("  拒绝: %d", loop_result.rejected)
    __QS_Logger__.info("  待精炼: %d", loop_result.refining)
    __QS_Logger__.info("  错误: %d", loop_result.errors)
    __QS_Logger__.info("  工作区: %s", base_dir)
    __QS_Logger__.info("=" * 60)

    return loop_result


def _save_loop_summary(loop_result, base_dir: Path):
    """保存循环汇总到 base_dir/loop_xxx.json。"""
    path = base_dir / f"{loop_result.loop_id}.json"
    path.write_text(
        json.dumps(loop_result.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


# ============================================================
# 单次流水线
# ============================================================

def run_single_pipeline(args, pipeline_config, base_dir: Path):
    """执行单次流水线（假设生成→因子开发→因子评测）。"""
    mode = args.mode
    cli_path = pipeline_config.resolve_claude_cli()
    project_root = pipeline_config.resolve_project_root()
    hypo_config = pipeline_config.load_hypothesis_config()
    dev_config = pipeline_config.load_development_config()
    eval_config = pipeline_config.load_evaluation_config()
    eval_config.cache_start_mode = "new" if args.clear_cache else "continue"
    max_turns_hypothesis = args.max_turns_hypothesis or pipeline_config.max_turns_hypothesis
    max_turns_development = args.max_turns_development or pipeline_config.max_turns_development

    stages = set(args.stages)

    # Skill 模式准备：确保 Claude Code 能找到 hypothesis / develop-factor 技能
    if mode == "skill" and ("hypothesis" in stages or "development" in stages):
        ensure_skills(project_root)

    # --factor-dir 模式：使用因子目录的上级作为工作区
    if args.factor_dir:
        factor_dir = Path(args.factor_dir).resolve()
        if not factor_dir.exists():
            __QS_Logger__.error("因子目录不存在: %s", factor_dir)
            sys.exit(1)
        workspace_dir = factor_dir.parent
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        workspace_dir = base_dir / f"FM_{timestamp}"
        workspace_dir.mkdir(parents=True, exist_ok=True)

    setup_logging(workspace_dir, args.log_level)
    __QS_Logger__.info("运行阶段: %s", ", ".join(args.stages))

    start_time = datetime.now()
    hypothesis_result = None
    development_result = None
    evaluation_summary = None
    hypothesis_start = hypothesis_end = None
    development_start = development_end = None
    evaluation_start = evaluation_end = None

    # ── 假设生成 ──
    if args.hypothesis_yaml:
        yaml_path = Path(args.hypothesis_yaml)
        if not yaml_path.exists():
            __QS_Logger__.error("假设文件不存在: %s", yaml_path)
            sys.exit(1)
        yaml_str = yaml_path.read_text(encoding="utf-8")
        hypothesis_result = _parse_hypothesis_yaml(yaml_str, args.target, args.direction)
        if hypothesis_result:
            hypothesis_dir = workspace_dir / "hypothesis"
            hypothesis_dir.mkdir(exist_ok=True)
            (hypothesis_dir / "hypothesis.yaml").write_text(yaml_str, encoding="utf-8")
    elif "hypothesis" in stages:
        hypothesis_start = datetime.now().isoformat()
        try:
            if mode == "skill":
                hypothesis_result = asyncio.run(run_hypothesis_skill(
                    target=args.target, direction=args.direction,
                    market=args.market, frequency=args.frequency,
                    workspace_dir=workspace_dir, max_turns=max_turns_hypothesis,
                    cli_path=cli_path, project_root=project_root,
                    permission_mode=hypo_config.permission_mode,
                ))
            else:
                hypothesis_result = run_hypothesis_graph(
                    target=args.target, direction=args.direction,
                    max_directions=args.max_directions,
                )
            hypothesis_end = datetime.now().isoformat()
            if hypothesis_result:
                hypothesis_dir = workspace_dir / "hypothesis"
                hypothesis_dir.mkdir(exist_ok=True)
                (hypothesis_dir / "hypothesis.yaml").write_text(hypothesis_result["yaml"], encoding="utf-8")
                if hypothesis_result.get("claude_output"):
                    (hypothesis_dir / "claude_output.txt").write_text(
                        hypothesis_result["claude_output"], encoding="utf-8",
                    )
        except Exception as e:
            __QS_Logger__.error("假设生成异常: %s", e, exc_info=True)
    else:
        __QS_Logger__.info("跳过假设生成阶段（未在 --stages 中指定）")

    # ── 因子开发 ──
    if "development" in stages:
        if hypothesis_result:
            development_start = datetime.now().isoformat()
            try:
                if mode == "skill":
                    hypothesis_yaml_path = str(workspace_dir / "hypothesis" / "hypothesis.yaml")
                    development_result = asyncio.run(run_development_skill_with_fix(
                        hypothesis_yaml_path=hypothesis_yaml_path,
                        workspace_dir=workspace_dir, max_turns=max_turns_development,
                        cli_path=cli_path, project_root=project_root, dev_config=dev_config,
                        permission_mode=dev_config.permission_mode,
                    ))
                    if development_result and development_result.get("claude_output"):
                        (workspace_dir / "development" / "claude_output.txt").write_text(
                            development_result["claude_output"], encoding="utf-8",
                        )
                else:
                    development_result = run_development_graph(
                        hypothesis_result["hypothesis"], workspace_dir, dev_config=dev_config,
                    )
            except Exception as e:
                __QS_Logger__.error("因子开发异常: %s", e, exc_info=True)
            development_end = datetime.now().isoformat()
        else:
            __QS_Logger__.info("跳过因子开发阶段（无假设数据）")
    else:
        __QS_Logger__.info("跳过因子开发阶段（未在 --stages 中指定）")

    # ── 因子评测 ──
    if "evaluation" in stages:
        if not development_result and args.factor_dir:
            factor_dir = Path(args.factor_dir).resolve()
            code_path = factor_dir / "factor_def.py"
            if not code_path.exists():
                for py_file in factor_dir.glob("**/*.py"):
                    if "defFactor" in py_file.read_text(encoding="utf-8"):
                        code_path = py_file
                        break
            if not code_path.exists():
                __QS_Logger__.error("因子目录中未找到包含 defFactor 的 Python 文件: %s", factor_dir)
                sys.exit(1)
            factor_name = extract_factor_name_from_code(code_path)
            development_result = {
                "factor_dir": str(factor_dir),
                "factor_code_path": str(code_path),
                "factor_name": factor_name,
                "status": "completed",
            }
            __QS_Logger__.info("使用已有因子目录: %s（%s）", factor_dir, factor_name)

        if development_result and development_result.get("status") == "completed":
            evaluation_start = datetime.now().isoformat()
            try:
                ctx = build_evaluation_context(development_result, workspace_dir, pipeline_config)
                if ctx:
                    factor, price, ids, dtruler, balance_dts, factor_name = ctx
                    category = hypothesis_result["hypothesis"].get("category", "") if hypothesis_result else ""
                    evaluation_summary = run_evaluation(
                        factor, price, ids, dtruler, balance_dts,
                        factor_name, category, workspace_dir,
                        eval_config=eval_config,
                    )
            except Exception as e:
                __QS_Logger__.error("因子评测异常: %s", e, exc_info=True)
            evaluation_end = datetime.now().isoformat()
        else:
            __QS_Logger__.info("跳过因子评测阶段（因子开发未完成）")
    else:
        __QS_Logger__.info("跳过因子评测阶段（未在 --stages 中指定）")

    # ── 汇总 ──
    elapsed = (datetime.now() - start_time).total_seconds()
    summary = {
        "pipeline_run_at": datetime.now().isoformat(),
        "mode": mode,
        "stages": args.stages,
        "elapsed_seconds": round(elapsed, 1),
        "hypothesis": {
            "status": "completed" if hypothesis_result else "skipped",
            "factor_name": hypothesis_result.get("hypothesis", {}).get("factor_name") if hypothesis_result else None,
            "direction": hypothesis_result.get("direction") if hypothesis_result else None,
            "start": hypothesis_start, "end": hypothesis_end,
            "elapsed": stage_elapsed(hypothesis_start, hypothesis_end),
        },
        "development": {
            "status": development_result.get("status", "skipped") if development_result else "skipped",
            "factor_dir": development_result.get("factor_dir") if development_result else None,
            "start": development_start, "end": development_end,
            "elapsed": stage_elapsed(development_start, development_end),
        },
        "evaluation": {
            **(evaluation_summary or {"status": "skipped"}),
            "start": evaluation_start, "end": evaluation_end,
            "elapsed": stage_elapsed(evaluation_start, evaluation_end),
        },
    }

    summary_path = workspace_dir / "pipeline_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    __QS_Logger__.info("=" * 60)
    __QS_Logger__.info("流水线执行完成（%s 模式）", mode.upper())
    __QS_Logger__.info("  耗时: %.1f 秒", elapsed)
    __QS_Logger__.info("  假设生成: %s", summary["hypothesis"]["status"])
    __QS_Logger__.info("  因子开发: %s", summary["development"]["status"])
    __QS_Logger__.info("  因子评测: %s", summary["evaluation"].get("decision", summary["evaluation"].get("status", "skipped")))
    __QS_Logger__.info("  工作区: %s", workspace_dir)
    __QS_Logger__.info("=" * 60)


# ============================================================
# 阶段解析
# ============================================================

_VALID_STAGES = {"hypothesis", "development", "evaluation"}


def _parse_stages(value: str) -> list[str]:
    """解析逗号分隔的阶段列表，返回合法的阶段名列表。"""
    stages = [s.strip().lower() for s in value.split(",") if s.strip()]
    invalid = set(stages) - _VALID_STAGES
    if invalid:
        raise argparse.ArgumentTypeError(
            f"无效的阶段: {', '.join(invalid)}。可选: {', '.join(sorted(_VALID_STAGES))}"
        )
    if not stages:
        raise argparse.ArgumentTypeError("至少指定一个阶段")
    return stages


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="因子挖掘流水线 — 统一入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 基本参数
    parser.add_argument("--config", default=None, help="流水线配置文件路径")
    parser.add_argument("--mode", choices=["skill", "graph"], default="skill", help="运行模式（默认：skill）")
    parser.add_argument("--target", default="全部", help="研究目标（如：动量因子、全部）")
    parser.add_argument("--market", default="A股", help="目标市场")
    parser.add_argument("--frequency", default="日频", help="数据频率")
    parser.add_argument("--log-level", default="INFO", help="日志级别")

    # 单次模式便捷参数
    single_group = parser.add_argument_group("单次模式参数（--max-rounds 1 时生效）")
    single_group.add_argument("--direction", default=None, help="指定方向（跳过方向探索）")
    single_group.add_argument("--max-directions", type=int, default=1, help="最大方向数（Graph 模式）")
    single_group.add_argument(
        "--stages", type=_parse_stages, default="hypothesis,development,evaluation",
        metavar="STAGE[,STAGE...]",
        help="指定运行的阶段（逗号分隔），可选: hypothesis, development, evaluation。默认全部运行",
    )
    single_group.add_argument("--hypothesis-yaml", default=None, help="加载已有的假设 YAML 文件")
    single_group.add_argument("--factor-dir", default=None, help="已有因子目录路径，直接进入评测阶段")

    # 循环模式参数
    loop_group = parser.add_argument_group("循环模式参数（--max-rounds > 1 时生效）")
    loop_group.add_argument("--max-rounds", type=int, default=1, help="最大轮次（默认：1 = 单次运行）")
    loop_group.add_argument("--max-hours", type=float, default=8.0, help="最大运行时间/小时（循环模式）")

    # 通用参数
    parser.add_argument("--max-turns-hypothesis", type=int, default=None, help="假设生成阶段最大轮次")
    parser.add_argument("--max-turns-development", type=int, default=None, help="因子开发阶段最大轮次")
    parser.add_argument(
        "--clear-cache", action=argparse.BooleanOptionalAction, default=True,
        help="挖掘前是否清空评测缓存（默认：True）。使用 --no-clear-cache 复用已有缓存",
    )

    args = parser.parse_args()

    # 参数校验
    if args.factor_dir:
        if args.hypothesis_yaml:
            parser.error("--factor-dir 与 --hypothesis-yaml 不能同时使用")
        if args.max_rounds > 1:
            parser.error("--factor-dir 不能与循环模式（--max-rounds > 1）同时使用")
        if args.stages != ["evaluation"]:
            __QS_Logger__.info("--factor-dir 指定，自动将阶段覆盖为 evaluation")
            args.stages = ["evaluation"]

    # 加载配置
    from QSExt.LLMFactor.pipeline_config import PipelineConfig
    config_path = args.config or _default_config_path()
    pipeline_config = PipelineConfig.from_yaml(config_path)
    __QS_Logger__.info("已加载配置: %s", config_path)

    # 统一使用 resolve_workspace_dir().parent 作为基础目录
    base_dir = pipeline_config.resolve_workspace_dir().parent
    base_dir.mkdir(parents=True, exist_ok=True)

    if args.max_rounds > 1:
        # ── 持续循环模式 ──
        setup_logging(base_dir, args.log_level)

        eval_config = pipeline_config.load_evaluation_config()
        eval_config.cache_start_mode = "new" if args.clear_cache else "continue"
        run_mining_loop(
            target=args.target,
            max_rounds=args.max_rounds,
            max_hours=args.max_hours,
            mode=args.mode,
            base_dir=base_dir,
            max_turns_hypothesis=args.max_turns_hypothesis or pipeline_config.max_turns_hypothesis,
            max_turns_development=args.max_turns_development or pipeline_config.max_turns_development,
            eval_config=eval_config,
        )
    else:
        # ── 单次流水线模式 ──
        run_single_pipeline(args, pipeline_config, base_dir)


if __name__ == "__main__":
    main()
