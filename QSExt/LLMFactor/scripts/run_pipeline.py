# -*- coding: utf-8 -*-
"""因子挖掘流水线 — 统一入口。

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
import importlib.util
import json
import logging
import os
import re
import subprocess
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
# 假设生成 — Graph 模式
# ============================================================

def run_hypothesis_graph(
    target: str,
    direction: str | None = None,
    max_directions: int = 1,
) -> dict | None:
    """使用 LangGraph 执行假设生成。"""
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
# 假设生成 — Skill 模式
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
    """使用 Claude Agent SDK 执行假设生成。"""
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
        output_messages.extend(_format_agent_message(message))

    full_output = "\n".join(output_messages)
    __QS_Logger__.info("Claude Agent 输出长度: %d 字符", len(full_output))

    yaml_str = None
    yaml_file = output_path / "hypothesis.yaml"
    if yaml_file.exists():
        yaml_str = yaml_file.read_text(encoding="utf-8")
    else:
        yaml_str = _extract_yaml_from_output(full_output)
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
# 因子开发 — Graph 模式
# ============================================================

def run_development_graph(hypothesis: dict, workspace_dir: Path, dev_config=None) -> dict | None:
    """使用 LangGraph 执行因子开发。"""
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
# 因子开发 — Skill 模式
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
    """使用 Claude Agent SDK 执行因子开发。"""
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
        output_messages.extend(_format_agent_message(message))

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
        "factor_name": _extract_factor_name_from_output(full_output),
        "status": "completed",
        "claude_output": full_output,
    }


# ============================================================
# 因子评测（两种模式共用）
# ============================================================

def build_evaluation_context(development_result: dict, workspace_dir: Path, pipeline_config=None):
    """从因子开发产出物构建评测所需的因子对象和参数。"""
    from QSExt.FactorDef.FactorDefContent import FactorDefInput
    from QuantStudio.Factor.JYDB import JYDB
    from QSExt.LLMFactor.pipeline_config import PipelineConfig

    pc = pipeline_config or PipelineConfig()
    data_ctx = pc.data

    factor_dir = development_result.get("factor_dir", "")
    code_path = Path(factor_dir) / "factor_def.py"

    if not code_path.exists():
        for py_file in Path(factor_dir).glob("**/*.py"):
            if "defFactor" in py_file.read_text(encoding="utf-8"):
                code_path = py_file
                break

    if not code_path.exists():
        __QS_Logger__.error("factor_def.py 不存在: %s", code_path)
        return None

    __QS_Logger__.info("加载因子代码: %s", code_path)
    module_name = f"_pipeline_factor_{code_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(code_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "defFactor"):
        __QS_Logger__.error("因子模块缺少 defFactor 函数")
        return None

    __QS_Logger__.info("连接 JYDB...")
    SDB = JYDB().connect()

    DTRuler = SDB.getTradeDay(
        start_date=data_ctx.get_trade_day_start(),
        end_date=data_ctx.get_trade_day_end(),
    )
    __QS_Logger__.info("  交易日数量: %d", len(DTRuler))

    IDs = SDB.getStockID(dt=data_ctx.get_stock_date())
    if len(IDs) > data_ctx.max_stocks:
        IDs = IDs[:data_ctx.max_stocks]
    __QS_Logger__.info("  股票数量: %d", len(IDs))

    fdi = FactorDefInput(
        Debug=False,
        FDB={"JYDB": SDB},
        DTs=DTRuler,
        IDs=IDs,
        SectionIDs=IDs,
        DTRuler=DTRuler,
    )

    __QS_Logger__.info("执行 defFactor()...")
    result = module.defFactor(fdi=fdi)
    if isinstance(result, list):
        factors = result
    elif hasattr(result, "FactorList"):
        factors = result.FactorList
    else:
        __QS_Logger__.error("defFactor 返回未知类型: %s", type(result).__name__)
        return None

    if not factors:
        __QS_Logger__.error("defFactor 返回空列表")
        return None

    factor = factors[0]
    __QS_Logger__.info("  因子名称: %s", factor.Name)

    __QS_Logger__.info("获取价格数据...")
    price_FT = SDB.getTable("股票行情表现", args={"LookBack": 0})
    price = price_FT.getFactor("收盘价")

    balance_dts = _get_month_end_dates(DTRuler)
    __QS_Logger__.info("  再平衡时点数量: %d", len(balance_dts))

    factor_name = development_result.get("factor_name", "unknown_factor")
    return factor, price, IDs, DTRuler, balance_dts, factor_name


def run_evaluation(
    factor, price, descriptor_ids, dt_ruler, balance_dts,
    factor_name: str, category: str, workspace_dir: Path,
    eval_config=None, cache=None,
) -> dict | None:
    """运行因子评测。"""
    from QSExt.LLMFactor.evaluation import FactorEvaluator, EvalConfig

    __QS_Logger__.info("=" * 60)
    __QS_Logger__.info("因子评测")
    __QS_Logger__.info("  因子: %s", factor_name)
    __QS_Logger__.info("=" * 60)

    config = eval_config or EvalConfig()
    evaluator = FactorEvaluator(config)
    report = evaluator.evaluate(
        factor=factor, price=price,
        descriptor_ids=descriptor_ids, dt_ruler=dt_ruler,
        balance_dts=balance_dts, factor_name=factor_name,
        category=category, cache=cache,
    )

    evaluation_dir = workspace_dir / "evaluation"
    evaluation_dir.mkdir(parents=True, exist_ok=True)

    report_html_path = evaluation_dir / "eval_report.html"
    report_html_path.write_text(report.report_html, encoding="utf-8")

    summary = report.summary
    summary["scores"] = {
        "effectiveness": report.scores.effectiveness,
        "stability": report.scores.stability,
        "turnover": report.scores.turnover,
        "diversity": report.scores.diversity,
        "overfitting_risk": report.scores.overfitting_risk,
        "composite": report.scores.composite,
    }
    summary["decision_reason"] = report.decision.reason

    summary_path = evaluation_dir / "eval_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    __QS_Logger__.info("因子评测完成: decision=%s, composite=%.3f",
                       report.decision.decision, report.scores.composite)
    return summary


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
# 因子代码验证与自动修复
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

    # 尝试导入模块（会触发装饰器执行，捕获参数错误等）
    try:
        import importlib.util
        module_name = f"_validate_factor_{code_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(code_path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        error_type = type(e).__name__
        return False, f"模块导入失败: {error_type}: {e}"

    # 检查 defFactor 函数
    if not hasattr(module, "defFactor"):
        return False, "模块中缺少 defFactor 函数"

    return True, ""


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

        # 发回 Claude Agent 修复
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
            max_turns=20,  # 修复用较少轮次
        )

        fix_messages = []
        async for message in query(prompt=fix_prompt, options=options):
            fix_messages.extend(_format_agent_message(message))

        fix_output = "\n".join(fix_messages)
        __QS_Logger__.info("修复 Agent 输出长度: %d 字符", len(fix_output))

        # 保存修复日志
        fix_log_path = Path(factor_dir) / f"fix_attempt_{attempt}.txt"
        fix_log_path.write_text(fix_output, encoding="utf-8")

        # 更新 result 中的 claude_output（追加修复日志）
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

def _get_month_end_dates(dtruler: list) -> list:
    """从交易日序列中提取月末日期。"""
    month_ends = []
    for i, d in enumerate(dtruler):
        if i == len(dtruler) - 1 or dtruler[i + 1].month != d.month:
            month_ends.append(d)
    return month_ends


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


def _extract_yaml_from_output(output: str) -> str | None:
    """从 Claude 输出中提取 YAML 内容。"""
    pattern = r"```yaml\s*\n(.*?)```"
    match = re.search(pattern, output, re.DOTALL)
    if match:
        return match.group(1).strip()
    pattern = r"(hypothesis_id:.*?)(?=\n---|\n##|\Z)"
    match = re.search(pattern, output, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _format_agent_message(message) -> list[str]:
    """将 Claude Agent 消息格式化为可读文本。"""
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


def _extract_factor_name_from_code(code_path: Path) -> str:
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
        # 尝试匹配 Name="xxx" 或 Name = "xxx"
        match = re.search(r"""Name\s*[:=]\s*['"]([^'"]+)['"]""", content)
        if match:
            return match.group(1)
        # 尝试匹配 TargetTable="xxx"
        match = re.search(r"""TargetTable\s*[:=]\s*['"]([^'"]+)['"]""", content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return code_path.parent.name


def _extract_factor_name_from_output(output: str) -> str:
    """从 Claude 输出中提取因子名称。"""
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


def _stage_elapsed(start, end):
    """计算阶段耗时。"""
    if start and end:
        return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 1)
    return None


def _default_config_path() -> str:
    """获取默认配置文件路径。"""
    return str(Path(__QS_MainPath__) / "LLMFactor" / "config" / "pipeline.yaml")


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
        _ensure_skills(project_root)

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

    _setup_logging(workspace_dir, args.log_level)
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
        # 提供了已有假设文件，直接加载
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
        # 运行假设生成
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
        # --factor-dir 模式：从已有因子目录构建 development_result
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
            factor_name = _extract_factor_name_from_code(code_path)
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
            "elapsed": _stage_elapsed(hypothesis_start, hypothesis_end),
        },
        "development": {
            "status": development_result.get("status", "skipped") if development_result else "skipped",
            "factor_dir": development_result.get("factor_dir") if development_result else None,
            "start": development_start, "end": development_end,
            "elapsed": _stage_elapsed(development_start, development_end),
        },
        "evaluation": {
            **(evaluation_summary or {"status": "skipped"}),
            "start": evaluation_start, "end": evaluation_end,
            "elapsed": _stage_elapsed(evaluation_start, evaluation_end),
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
# 日志配置
# ============================================================

def _setup_logging(workspace_dir: Path, log_level: str = "INFO"):
    """配置日志：同时输出到控制台和文件。"""
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
# Skill 工作空间准备
# ============================================================

# Skill 源目录（相对于项目根目录）
_SKILL_SOURCES = {
    "hypothesis": "QSExt/LLMFactor/hypothesis/skill/hypothesis",
    "develop-factor": "QSExt/LLMFactor/development/skill/develop-factor",
}


def _ensure_skills(project_root: Path) -> None:
    """确保项目根目录：git 仓库 + .claude/skills/ + skill 目录链接。

    幂等——每次流水线启动前调用，已有正确链接时跳过。
    """
    claude_dir = project_root / ".claude"
    skills_dir = claude_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    # 确保是 git 仓库（Claude Code 需要）
    if not (project_root / ".git").exists():
        subprocess.run(
            ["git", "init"], cwd=str(project_root),
            check=False, capture_output=True,
        )

    for skill_name, skill_rel_path in _SKILL_SOURCES.items():
        source = project_root / skill_rel_path
        if not source.is_dir():
            __QS_Logger__.warning("skill 源目录不存在，跳过: %s", source)
            continue
        _link_skill(skills_dir, skill_name, source)


def _link_skill(skills_dir: Path, skill_name: str, source: Path) -> None:
    """创建 skill 目录链接（Windows: mklink /J, Unix: symlink）。幂等。"""
    target = skills_dir / skill_name

    if target.exists():
        if os.path.normcase(str(target.resolve())) == os.path.normcase(str(source.resolve())):
            return  # 已正确
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
    """删除 Junction / 符号链接 / 目录"""
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
        # --factor-dir 自动覆盖为仅评测
        if args.stages != ["evaluation"]:
            __QS_Logger__.info("--factor-dir 指定，自动将阶段覆盖为 evaluation")
            args.stages = ["evaluation"]

    # 加载配置
    from QSExt.LLMFactor.pipeline_config import PipelineConfig
    config_path = args.config or _default_config_path()
    pipeline_config = PipelineConfig.from_yaml(config_path)
    __QS_Logger__.info("已加载配置: %s", config_path)

    # 统一使用 resolve_workspace_dir().parent 作为基础目录
    # 单次模式在此基础上创建 FM_<时间戳> 子目录，循环模式直接使用
    base_dir = pipeline_config.resolve_workspace_dir().parent
    base_dir.mkdir(parents=True, exist_ok=True)

    if args.max_rounds > 1:
        # ── 持续循环模式 ──
        _setup_logging(base_dir, args.log_level)

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
