# -*- coding: utf-8 -*-
"""单轮挖掘执行器 — 封装假设生成→因子开发→因子评测的完整流程。

使用示例::

    from QSExt.LLMFactor.loop.round_runner import RoundRunner

    runner = RoundRunner(mode="skill", base_dir=Path("workspace/"))
    result = runner.run_round(direction="动量/短期反转", round_num=1)
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from QSExt import __QS_MainPath__
from QSExt.LLMFactor.loop.models import RoundResult

__QS_Logger__ = logging.getLogger("QSR.loop.round_runner")


class RoundRunner:
    """单轮挖掘执行器。

    Attributes:
        mode: 运行模式（"skill" 或 "graph"）
        base_dir: 工作区根目录
        target: 研究目标（如 "动量因子"）
        max_turns_hypothesis: 假设生成阶段最大轮次
        max_turns_development: 因子开发阶段最大轮次
        eval_config: 评测配置（含缓存设置）
    """

    def __init__(
        self,
        mode: str = "skill",
        base_dir: Path | str | None = None,
        target: str = "动量因子",
        max_turns_hypothesis: int = 50,
        max_turns_development: int = 80,
        eval_config=None,
    ):
        self.mode = mode
        self.base_dir = Path(base_dir) if base_dir else Path(__QS_MainPath__).parent / "workspace"
        self.target = target
        self.max_turns_hypothesis = max_turns_hypothesis
        self.max_turns_development = max_turns_development
        self.eval_config = eval_config
        self._cache_manager = None  # 跨轮次持久化 Cache 管理器

    def run_round(self, direction: str, round_num: int) -> RoundResult:
        """执行单轮挖掘。

        Args:
            direction: 研究方向标签（如 "动量/短期反转"）
            round_num: 轮次编号

        Returns:
            RoundResult
        """
        start_time = datetime.now()
        round_dir = self.base_dir / f"FM_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        round_dir.mkdir(parents=True, exist_ok=True)

        __QS_Logger__.info("=" * 60)
        __QS_Logger__.info("第 %d 轮挖掘开始: %s", round_num, direction)
        __QS_Logger__.info("工作区: %s", round_dir)
        __QS_Logger__.info("=" * 60)

        try:
            if self.mode == "skill":
                result = self._run_skill_mode(direction, round_num, round_dir)
            else:
                result = self._run_graph_mode(direction, round_num, round_dir)
        except Exception as e:
            __QS_Logger__.error("第 %d 轮异常: %s", round_num, e, exc_info=True)
            result = RoundResult(
                round_num=round_num,
                direction=direction,
                decision="error",
                error=str(e),
            )

        result.elapsed_seconds = (datetime.now() - start_time).total_seconds()
        result.workspace_dir = str(round_dir)

        __QS_Logger__.info(
            "第 %d 轮完成: decision=%s, factor=%s, 耗时=%.1f秒",
            round_num, result.decision, result.factor_name, result.elapsed_seconds,
        )

        return result

    def _get_cache(self, dt_ruler):
        """获取或创建跨轮次复用的 Cache 实例。

        Args:
            dt_ruler: 交易日序列

        Returns:
            FeatherFactorCache 实例，若缓存未启用则返回 None
        """
        if self._cache_manager is None:
            from QSExt.LLMFactor.evaluation.cache_manager import EvalCacheManager
            ec = self.eval_config
            self._cache_manager = EvalCacheManager(
                cache_dir=ec.cache_dir if ec else None,
                start_mode=ec.cache_start_mode if ec else "continue",
                enabled=ec.cache_enabled if ec else True,
            )
        return self._cache_manager.get_or_create(dt_ruler)

    def _run_skill_mode(self, direction: str, round_num: int, round_dir: Path) -> RoundResult:
        """使用 Skill 模式运行单轮。"""
        from QSExt.LLMFactor.scripts.run_pipeline import (
            run_hypothesis_skill,
            run_development_skill_with_fix,
            build_evaluation_context,
            run_evaluation,
        )

        # 假设生成
        __QS_Logger__.info("假设生成（Skill 模式）")
        hypothesis_dir = round_dir / "hypothesis"
        hypothesis_dir.mkdir(exist_ok=True)

        hypothesis_result = asyncio.run(run_hypothesis_skill(
            target=self.target,
            direction=direction,
            market="A股",
            frequency="日频",
            workspace_dir=round_dir,
            max_turns=self.max_turns_hypothesis,
        ))

        if not hypothesis_result:
            return RoundResult(
                round_num=round_num,
                direction=direction,
                decision="error",
                error="假设生成阶段未生成假设",
            )

        # 保存 Claude 输出
        if hypothesis_result.get("claude_output"):
            (hypothesis_dir / "claude_output.txt").write_text(
                hypothesis_result["claude_output"], encoding="utf-8"
            )

        factor_name = hypothesis_result["hypothesis"].get("factor_name", "unknown")

        # 因子开发
        __QS_Logger__.info("因子开发（Skill 模式）")
        development_result = asyncio.run(run_development_skill_with_fix(
            hypothesis_yaml_path=str(hypothesis_dir / "hypothesis.yaml"),
            workspace_dir=round_dir,
            max_turns=self.max_turns_development,
        ))

        if not development_result or development_result.get("status") not in ("completed",):
            error_msg = development_result.get("validation_error", "因子开发阶段未完成") if development_result else "因子开发阶段未完成"
            return RoundResult(
                round_num=round_num,
                direction=direction,
                factor_name=factor_name,
                decision="error",
                error=error_msg,
            )

        # 保存 Claude 输出
        if development_result.get("claude_output"):
            (round_dir / "development" / "claude_output.txt").write_text(
                development_result["claude_output"], encoding="utf-8"
            )

        # 因子评测
        __QS_Logger__.info("因子评测")
        try:
            ctx = build_evaluation_context(development_result, round_dir)
            if ctx:
                factor, price, ids, dtruler, balance_dts, factor_name = ctx
                category = hypothesis_result["hypothesis"].get("category", "")
                cache = self._get_cache(dtruler)
                evaluation_summary = run_evaluation(
                    factor, price, ids, dtruler, balance_dts,
                    factor_name, category, round_dir,
                    cache=cache,
                )
                if evaluation_summary:
                    return RoundResult(
                        round_num=round_num,
                        direction=direction,
                        factor_name=factor_name,
                        decision=evaluation_summary.get("decision", "unknown"),
                        composite_score=evaluation_summary.get("composite_score", 0.0),
                    )
        except Exception as e:
            __QS_Logger__.error("因子评测异常: %s", e, exc_info=True)

        return RoundResult(
            round_num=round_num,
            direction=direction,
            factor_name=factor_name,
            decision="error",
            error="因子评测阶段未完成",
        )

    def _run_graph_mode(self, direction: str, round_num: int, round_dir: Path) -> RoundResult:
        """使用 Graph 模式运行单轮。"""
        from QSExt.LLMFactor.scripts.run_pipeline import (
            run_hypothesis_graph,
            run_development_graph,
            build_evaluation_context,
            run_evaluation,
        )

        # 假设生成
        __QS_Logger__.info("假设生成（Graph 模式）")
        hypothesis_result = run_hypothesis_graph(
            target=self.target,
            direction=direction,
            max_directions=1,
        )

        if not hypothesis_result:
            return RoundResult(
                round_num=round_num,
                direction=direction,
                decision="error",
                error="假设生成阶段未生成假设",
            )

        # 保存假设
        hypothesis_dir = round_dir / "hypothesis"
        hypothesis_dir.mkdir(exist_ok=True)
        (hypothesis_dir / "hypothesis.yaml").write_text(hypothesis_result["yaml"], encoding="utf-8")

        factor_name = hypothesis_result["hypothesis"].get("factor_name", "unknown")

        # 因子开发
        __QS_Logger__.info("因子开发（Graph 模式）")
        development_result = run_development_graph(hypothesis_result["hypothesis"], round_dir)

        if not development_result or development_result.get("status") != "completed":
            return RoundResult(
                round_num=round_num,
                direction=direction,
                factor_name=factor_name,
                decision="error",
                error="因子开发阶段未完成",
            )

        # 因子评测
        __QS_Logger__.info("因子评测")
        try:
            ctx = build_evaluation_context(development_result, round_dir)
            if ctx:
                factor, price, ids, dtruler, balance_dts, factor_name = ctx
                category = hypothesis_result["hypothesis"].get("category", "")
                cache = self._get_cache(dtruler)
                evaluation_summary = run_evaluation(
                    factor, price, ids, dtruler, balance_dts,
                    factor_name, category, round_dir,
                    cache=cache,
                )
                if evaluation_summary:
                    return RoundResult(
                        round_num=round_num,
                        direction=direction,
                        factor_name=factor_name,
                        decision=evaluation_summary.get("decision", "unknown"),
                        composite_score=evaluation_summary.get("composite_score", 0.0),
                    )
        except Exception as e:
            __QS_Logger__.error("因子评测异常: %s", e, exc_info=True)

        return RoundResult(
            round_num=round_num,
            direction=direction,
            factor_name=factor_name,
            decision="error",
            error="因子评测阶段未完成",
        )
