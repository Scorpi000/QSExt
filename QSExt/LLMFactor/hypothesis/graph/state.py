# -*- coding: utf-8 -*-
"""LangGraph 图状态定义。

定义假设生成流程中各节点共享的状态结构。
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

from langgraph.graph import add_messages


class HypothesisState(dict):
    """LangGraph 图状态。

    Attributes:
        config: ResearchConfig 序列化后的配置字典
        target_direction: 可选的指定方向（跳过 Step 1 时使用）
        candidates: Step 1 产出的候选方向列表
        current_candidate_idx: 当前处理的方向索引
        research_context: Step 2 产出的调研上下文
        draft_hypothesis: Step 3 产出的假设草稿
        critique: Step 4a 的批判结果
        refined_hypothesis: Step 4b 精炼后的假设
        novelty_result: Step 4c 新颖性校验结果
        completed_hypotheses: 所有完成的假设列表
        skipped_directions: 被跳过的方向及原因
        messages: LangGraph 内部消息列表
    """

    # 输入
    config: dict
    target_direction: Optional[str]

    # Step 1 产出
    candidates: list[dict]
    current_candidate_idx: int

    # Step 2 产出
    research_context: Optional[dict]

    # Step 3 产出
    draft_hypothesis: Optional[dict]

    # Step 4 产出
    critique: Optional[dict]
    refined_hypothesis: Optional[dict]
    novelty_result: Optional[dict]

    # 最终产出
    completed_hypotheses: list[dict]
    skipped_directions: list[dict]

    # 消息
    messages: Annotated[list, add_messages]

    @classmethod
    def create_initial(cls, config: dict, target_direction: Optional[str] = None) -> "HypothesisState":
        """创建初始状态。

        Args:
            config: ResearchConfig 序列化后的配置字典
            target_direction: 可选的指定方向

        Returns:
            初始化的 HypothesisState
        """
        return cls(
            config=config,
            target_direction=target_direction,
            candidates=[],
            current_candidate_idx=0,
            research_context=None,
            draft_hypothesis=None,
            critique=None,
            refined_hypothesis=None,
            novelty_result=None,
            completed_hypotheses=[],
            skipped_directions=[],
            messages=[],
        )
