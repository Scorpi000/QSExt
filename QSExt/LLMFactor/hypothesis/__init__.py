# -*- coding: utf-8 -*-
"""假设生成模块。

提供因子研究假设的结构化生成能力，包括：
  - 数据模型：HypothesisDoc、ResearchContext、DirectionCandidate 等
  - 配置管理：ResearchConfig（从 YAML 加载）
  - 辅助工具：多样化模式选择、搜索预算分配
  - Prompt 模板：Step 1/3/4 的提示词（供 Skill 和 LangGraph 复用）
  - Skill 定义：Claude Code 第一阶段的 Skill 文件
"""
from QSExt.LLMFactor.hypothesis.config import ResearchConfig
from QSExt.LLMFactor.hypothesis.models import (
    DirectionCandidate,
    ResearchContext,
    HypothesisDoc,
    WikiResearchResult,
    FactorCodeSnippet,
    DataFieldSpec,
    ReflectionRecord,
    InspiredBy,
    ExpectedCharacteristics,
    NoveltyCheckResult,
    DirectionStats,
)
from QSExt.LLMFactor.hypothesis.divmode import (
    DiversityMode,
    DiversityModeSelector,
)
from QSExt.LLMFactor.hypothesis.budget import BudgetAllocator
from QSExt.LLMFactor.hypothesis.graph import (
    HypothesisState,
    build_hypothesis_graph,
    compile_graph,
    run_hypothesis_generation,
    arun_hypothesis_generation,
)

__all__ = [
    "ResearchConfig",
    "DirectionCandidate",
    "ResearchContext",
    "HypothesisDoc",
    "WikiResearchResult",
    "FactorCodeSnippet",
    "DataFieldSpec",
    "ReflectionRecord",
    "InspiredBy",
    "ExpectedCharacteristics",
    "NoveltyCheckResult",
    "DirectionStats",
    "DiversityMode",
    "DiversityModeSelector",
    "BudgetAllocator",
    # LangGraph
    "HypothesisState",
    "build_hypothesis_graph",
    "compile_graph",
    "run_hypothesis_generation",
    "arun_hypothesis_generation",
]
