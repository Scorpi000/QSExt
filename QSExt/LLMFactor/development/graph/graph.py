# -*- coding: utf-8 -*-
"""LangGraph 图编译与运行。

构建因子开发的完整 LangGraph 图，支持：
  - 代码生成 → 五 Agent 验证 → (自动修复循环) → 参数搜索 → 结果汇总
  - 可配置的验证和搜索选项

图结构：
    START → generate → verify → [条件路由] → search → log → END
                              ├─ all_passed → search
                              ├─ can_fix → fix → verify (循环)
                              └─ max_exceeded → END (needs_manual)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langgraph.graph import END, StateGraph

from QSExt.LLMFactor.development.graph.state import DevelopmentState
from QSExt.LLMFactor.development.graph.nodes import (
    generate_node,
    verify_node,
    fix_node,
    search_node,
    log_node,
)
from QSExt.LLMFactor.development.graph.edges import after_verify

logger = logging.getLogger(__name__)


def build_development_graph() -> StateGraph:
    """构建因子开发 LangGraph 图。

    图结构：
        START → generate → verify → [条件路由] → search → log → END

    Returns:
        未编译的 StateGraph
    """
    graph = StateGraph(DevelopmentState)

    # 添加节点
    graph.add_node("generate", generate_node)
    graph.add_node("verify", verify_node)
    graph.add_node("fix", fix_node)
    graph.add_node("search", search_node)
    graph.add_node("log", log_node)

    # 设置入口
    graph.set_entry_point("generate")

    # Step 1 → Step 2
    graph.add_edge("generate", "verify")

    # Step 2 → 条件路由
    graph.add_conditional_edges(
        "verify",
        after_verify,
        {
            "search": "search",
            "fix": "fix",
            "end": END,
        },
    )

    # 修复 → 回到验证（循环）
    graph.add_edge("fix", "verify")

    # 参数搜索 → 结果汇总
    graph.add_edge("search", "log")

    # 结果汇总 → END
    graph.add_edge("log", END)

    return graph


def compile_graph(checkpointer: Any = None):
    """编译图。

    Args:
        checkpointer: 可选的检查点保存器（用于持久化状态）

    Returns:
        编译好的可执行图
    """
    graph = build_development_graph()
    kwargs = {}
    if checkpointer:
        kwargs["checkpointer"] = checkpointer
    return graph.compile(**kwargs)


def run_development(
    hypothesis: dict,
    config: dict,
    workspace_dir: Optional[str] = None,
    checkpointer: Any = None,
) -> dict:
    """运行因子开发流程（同步包装）。

    Args:
        hypothesis: 假设文档字典（假设生成阶段输出）
        config: DevelopmentConfig 序列化后的配置字典
        workspace_dir: 可选的工作区目录
        checkpointer: 可选的检查点保存器

    Returns:
        DevelopmentResult 字典
    """
    import asyncio
    return asyncio.run(arun_development(
        hypothesis=hypothesis,
        config=config,
        workspace_dir=workspace_dir,
        checkpointer=checkpointer,
    ))


async def arun_development(
    hypothesis: dict,
    config: dict,
    workspace_dir: Optional[str] = None,
    checkpointer: Any = None,
) -> dict:
    """异步运行因子开发流程。

    Args:
        hypothesis: 假设文档字典（假设生成阶段输出）
        config: DevelopmentConfig 序列化后的配置字典
        workspace_dir: 可选的工作区目录
        checkpointer: 可选的检查点保存器

    Returns:
        DevelopmentResult 字典
    """
    factor_name = hypothesis.get("factor_name", "unknown")

    logger.info("=" * 60)
    logger.info("因子开发 (LangGraph)")
    logger.info("因子: %s", factor_name)
    logger.info("=" * 60)

    initial_state = DevelopmentState.create_initial(
        hypothesis=hypothesis,
        config=config,
        workspace_dir=workspace_dir,
    )

    app = compile_graph(checkpointer=checkpointer)
    final_state = await app.ainvoke(initial_state)

    result = final_state.get("development_result") or {}
    if not result:
        # 验证失败且未到达 log_node，构造失败结果
        result = {
            "factor_dir": final_state.get("workspace_dir", ""),
            "factor_code_path": "",
            "status": "validation_failed",
            "validation": final_state.get("validation_report"),
            "factor_name": factor_name,
        }
    status = result.get("status", "unknown")

    logger.info("=" * 60)
    logger.info("因子开发完成: %s, status=%s", factor_name, status)
    logger.info("=" * 60)

    return result
