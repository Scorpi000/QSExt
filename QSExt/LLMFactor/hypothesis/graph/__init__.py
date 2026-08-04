# -*- coding: utf-8 -*-
"""LangGraph 假设生成图模块。

提供基于 LangGraph 的假设生成流程，包括：
  - 图状态定义 (HypothesisState)
  - 图节点实现 (explore, research, generate, reflect, refine, check, log)
  - 条件边逻辑 (should_continue_reflect, novelty_gate, has_more_candidates)
  - 图编译与运行 (build_hypothesis_graph, run_hypothesis_generation)
"""
from QSExt.LLMFactor.hypothesis.graph.state import HypothesisState
from QSExt.LLMFactor.hypothesis.graph.graph import (
    build_hypothesis_graph,
    compile_graph,
    run_hypothesis_generation,
    arun_hypothesis_generation,
)
from QSExt.LLMFactor.hypothesis.graph.edges import (
    should_continue_reflect,
    novelty_gate,
    has_more_candidates,
)
from QSExt.LLMFactor.hypothesis.graph.nodes import (
    explore_node,
    research_node,
    generate_node,
    reflect_node,
    refine_node,
    check_node,
    log_node,
)

__all__ = [
    "HypothesisState",
    "build_hypothesis_graph",
    "compile_graph",
    "run_hypothesis_generation",
    "arun_hypothesis_generation",
    "should_continue_reflect",
    "novelty_gate",
    "has_more_candidates",
    "explore_node",
    "research_node",
    "generate_node",
    "reflect_node",
    "refine_node",
    "check_node",
    "log_node",
]
