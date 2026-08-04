# -*- coding: utf-8 -*-
"""条件边逻辑。

定义 LangGraph 图中的条件路由：
  - after_verify: 验证后路由（通过/修复/需人工介入）
  - after_fix: 修复后路由（回到验证）
"""
from __future__ import annotations

import logging
from typing import Literal

from QSExt.LLMFactor.development.graph.state import DevelopmentState

logger = logging.getLogger(__name__)


def after_verify(state: DevelopmentState) -> Literal["search", "fix", "end"]:
    """验证后路由。

    验证全部通过 → search（参数搜索）
    未通过且未超过最大修复次数 → fix（自动修复）
    超过最大修复次数 → end（需人工介入）

    Returns:
        "search" / "fix" / "end"
    """
    report = state.get("validation_report", {})
    all_passed = report.get("all_passed", False)
    attempt = state.get("attempt", 0)

    # 从 config 读取最大修复次数
    config = state.get("config", {})
    max_auto_fixes = config.get("max_auto_fixes", 3)

    if all_passed:
        logger.info("验证全部通过，进入参数搜索")
        return "search"

    if attempt <= max_auto_fixes:
        logger.info(
            "验证未通过 (attempt %d/%d)，尝试自动修复",
            attempt, max_auto_fixes,
        )
        return "fix"

    logger.warning(
        "超过最大修复次数 (%d)，需人工介入",
        max_auto_fixes,
    )
    return "end"
