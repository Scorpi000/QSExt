# -*- coding: utf-8 -*-
"""LangGraph 图状态定义。

定义因子开发流程中各节点共享的状态结构。
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

from langgraph.graph import add_messages


class DevelopmentState(dict):
    """LangGraph 图状态。

    Attributes:
        hypothesis: 假设生成阶段输出的假设文档（HypothesisDoc.to_development_input()）
        config: DevelopmentConfig 序列化后的配置字典
        workspace_dir: 工作区目录路径
        generated_code: Step 1 代码生成产出
        validation_report: Step 2 验证报告
        attempt: 当前修复尝试次数
        search_result: Step 3 参数搜索结果
        development_result: 最终产出
        error: 错误信息（流程中断时设置）
        messages: LangGraph 内部消息列表
    """

    # 输入
    hypothesis: dict
    config: dict

    # Step 1 产出
    generated_code: Optional[dict]

    # Step 2 产出
    validation_report: Optional[dict]
    attempt: int

    # Step 3 产出
    search_result: Optional[dict]

    # 工作区
    workspace_dir: Optional[str]

    # 最终产出
    development_result: Optional[dict]

    # 错误
    error: Optional[str]

    # 消息
    messages: Annotated[list, add_messages]

    @classmethod
    def create_initial(
        cls,
        hypothesis: dict,
        config: dict,
        workspace_dir: Optional[str] = None,
    ) -> "DevelopmentState":
        """创建初始状态。

        Args:
            hypothesis: 假设文档字典
            config: DevelopmentConfig 序列化后的配置字典
            workspace_dir: 可选的工作区目录

        Returns:
            初始化的 DevelopmentState
        """
        return cls(
            hypothesis=hypothesis,
            config=config,
            generated_code=None,
            validation_report=None,
            attempt=0,
            search_result=None,
            workspace_dir=workspace_dir,
            development_result=None,
            error=None,
            messages=[],
        )
