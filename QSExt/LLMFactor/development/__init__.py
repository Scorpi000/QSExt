# -*- coding: utf-8 -*-
"""因子开发模块。

将假设生成阶段的假设文档转化为 QuantStudio 框架下可执行、可验证的因子代码，
并完成超参数搜索。

三步流水线：
    1. 代码生成（LLM Agent）— code_generator.py
    2. 五 Agent 验证 — verifier.py + validators/
    3. 参数搜索（Optuna）— param_searcher.py

两种运行模式：
    - Skill 模式（Claude Agent SDK）— skill/
    - LangGraph 模式 — graph/
"""
from QSExt.LLMFactor.development.config import DevelopmentConfig
from QSExt.LLMFactor.development.models import (
    DevelopmentResult,
    EvalMetrics,
    ExecutionReport,
    FixAttempt,
    GeneratedCode,
    LeakTestReport,
    SearchResult,
    SemanticReviewReport,
    SyntaxReport,
    UnitCheckReport,
    ValidationReport,
)
from QSExt.LLMFactor.development.workspace import WorkspaceManager

__all__ = [
    "DevelopmentConfig",
    "DevelopmentResult",
    "EvalMetrics",
    "ExecutionReport",
    "FixAttempt",
    "GeneratedCode",
    "LeakTestReport",
    "SearchResult",
    "SemanticReviewReport",
    "SyntaxReport",
    "UnitCheckReport",
    "ValidationReport",
    "WorkspaceManager",
]
