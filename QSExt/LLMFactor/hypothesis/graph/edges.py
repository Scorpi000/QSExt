# -*- coding: utf-8 -*-
"""条件边逻辑。

定义 LangGraph 图中的条件路由：
  - should_continue_reflect: 批判后是否需要精炼
  - novelty_gate: 新颖性校验结果路由
  - has_more_candidates: 是否还有候选方向需要处理
"""
from __future__ import annotations

import logging
from typing import Literal

from QSExt.LLMFactor.hypothesis.graph.state import HypothesisState

logger = logging.getLogger(__name__)


def should_continue_reflect(state: HypothesisState) -> Literal["refine", "check"]:
    """批判后是否需要精炼。

    risk_level=high → 需要精炼
    risk_level=low/medium → 直接进入新颖性校验

    Returns:
        "refine" 或 "check"
    """
    critique = state.get("critique", {})
    risk_level = critique.get("risk_level", "low")

    if risk_level == "high":
        logger.info("批判风险等级 high，进入精炼阶段")
        return "refine"

    logger.info("批判风险等级 %s，跳过精炼直接校验", risk_level)
    return "check"


def novelty_gate(state: HypothesisState) -> Literal["skip", "warn_and_log", "log"]:
    """新颖性校验结果路由。

    Returns:
        "skip" - 被阻断，跳过该方向
        "warn_and_log" - 有预警，记录后继续
        "log" - 通过，记录日志
    """
    novelty = state.get("novelty_result", {})
    passed = novelty.get("passed", True)
    block_reason = novelty.get("block_reason")

    if block_reason:
        logger.info("新颖性校验阻断: %s", block_reason)
        return "skip"

    if not passed:
        warnings = novelty.get("warnings", [])
        logger.info("新颖性校验有 %d 条预警", len(warnings))
        return "warn_and_log"

    logger.info("新颖性校验通过")
    return "log"


def has_more_candidates(state: HypothesisState) -> Literal["next_candidate", "end"]:
    """是否还有候选方向需要处理。

    Returns:
        "next_candidate" - 还有候选方向
        "end" - 所有方向已处理完毕
    """
    candidates = state.get("candidates", [])
    current_idx = state.get("current_candidate_idx", 0)

    if current_idx < len(candidates):
        logger.info("还有 %d 个候选方向待处理", len(candidates) - current_idx)
        return "next_candidate"

    logger.info("所有候选方向已处理完毕")
    return "end"
