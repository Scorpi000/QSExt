# -*- coding: utf-8 -*-
"""LangGraph 图编译与运行。

构建假设生成的完整 LangGraph 图，支持：
  - 单方向假设生成
  - 多方向批量假设生成
  - 可选跳过 Step 1（指定方向）
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langgraph.graph import END, StateGraph

from QSExt.LLMFactor.hypothesis.graph.state import HypothesisState
from QSExt.LLMFactor.hypothesis.graph.nodes import (
    explore_node,
    research_node,
    generate_node,
    reflect_node,
    refine_node,
    check_node,
    log_node,
    advance_candidate_node,
    skip_direction_node,
)
from QSExt.LLMFactor.hypothesis.graph.edges import (
    should_continue_reflect,
    novelty_gate,
    has_more_candidates,
)

logger = logging.getLogger(__name__)


def build_hypothesis_graph() -> StateGraph:
    """构建假设生成 LangGraph 图。

    图结构：
        START → explore → [循环: research → generate → reflect → (refine)? → check → (skip/log)] → END

    Returns:
        编译好的 LangGraph 图
    """
    # 创建图
    graph = StateGraph(HypothesisState)

    # 添加节点
    graph.add_node("explore", explore_node)
    graph.add_node("research", research_node)
    graph.add_node("generate", generate_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("refine", refine_node)
    graph.add_node("check", check_node)
    graph.add_node("log", log_node)
    graph.add_node("skip", skip_direction_node)
    graph.add_node("advance", advance_candidate_node)

    # 设置入口
    graph.set_entry_point("explore")

    # Step 1 → 循环开始
    graph.add_conditional_edges(
        "explore",
        has_more_candidates,
        {
            "next_candidate": "research",
            "end": END,
        },
    )

    # Step 2 → Step 3
    graph.add_edge("research", "generate")

    # Step 3 → Step 4a
    graph.add_edge("generate", "reflect")

    # Step 4a → 条件: 精炼 or 直接校验
    graph.add_conditional_edges(
        "reflect",
        should_continue_reflect,
        {
            "refine": "refine",
            "check": "check",
        },
    )

    # Step 4b → Step 4c
    graph.add_edge("refine", "check")

    # Step 4c → 条件: 跳过 / 记录预警 / 记录
    graph.add_conditional_edges(
        "check",
        novelty_gate,
        {
            "skip": "skip",
            "warn_and_log": "log",
            "log": "log",
        },
    )

    # 跳过 → 推进
    graph.add_edge("skip", "advance")

    # 记录 → 推进
    graph.add_edge("log", "advance")

    # 推进 → 条件: 继续 or 结束
    graph.add_conditional_edges(
        "advance",
        has_more_candidates,
        {
            "next_candidate": "research",
            "end": END,
        },
    )

    return graph


def compile_graph(checkpointer: Any = None):
    """编译图。

    Args:
        checkpointer: 可选的检查点保存器（用于持久化状态）

    Returns:
        编译好的可执行图
    """
    graph = build_hypothesis_graph()
    kwargs = {}
    if checkpointer:
        kwargs["checkpointer"] = checkpointer
    return graph.compile(**kwargs)


def run_hypothesis_generation(
    config: dict,
    target_direction: Optional[str] = None,
    max_directions: int = 5,
    checkpointer: Any = None,
) -> dict:
    """运行假设生成流程（同步包装）。

    Args:
        config: ResearchConfig 序列化后的配置字典
        target_direction: 可选的指定方向（跳过 Step 1）
        max_directions: 最大处理方向数
        checkpointer: 可选的检查点保存器

    Returns:
        包含 completed_hypotheses 和 skipped_directions 的结果字典
    """
    import asyncio
    return asyncio.run(arun_hypothesis_generation(
        config=config,
        target_direction=target_direction,
        max_directions=max_directions,
        checkpointer=checkpointer,
    ))


async def arun_hypothesis_generation(
    config: dict,
    target_direction: Optional[str] = None,
    max_directions: int = 5,
    checkpointer: Any = None,
) -> dict:
    """异步运行假设生成流程。

    Args:
        config: ResearchConfig 序列化后的配置字典
        target_direction: 可选的指定方向（跳过 Step 1）
        max_directions: 最大处理方向数
        checkpointer: 可选的检查点保存器

    Returns:
        包含 completed_hypotheses 和 skipped_directions 的结果字典
    """
    logger.info("=" * 60)
    logger.info("假设生成 (LangGraph 异步)")
    logger.info("=" * 60)

    initial_state = HypothesisState.create_initial(
        config=config,
        target_direction=target_direction,
    )

    app = compile_graph(checkpointer=checkpointer)
    final_state = await app.ainvoke(initial_state)

    completed = final_state.get("completed_hypotheses", [])
    skipped = final_state.get("skipped_directions", [])

    logger.info("=" * 60)
    logger.info("假设生成完成: %d 完成, %d 跳过", len(completed), len(skipped))
    logger.info("=" * 60)

    return {
        "completed_hypotheses": completed,
        "skipped_directions": skipped,
    }
