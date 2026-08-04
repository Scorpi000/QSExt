# -*- coding: utf-8 -*-
"""假设生成模块 Prompt 模板。

包含 Step 1/3/4 的提示词模板，供 Skill 文件和第二阶段 LangGraph 复用。
"""
from QSExt.LLMFactor.hypothesis.prompts.step1_direction import (
    STEP1_SYSTEM,
    STEP1_USER_TEMPLATE,
)
from QSExt.LLMFactor.hypothesis.prompts.step3_hypothesis import (
    STEP3_SYSTEM,
    STEP3_USER_TEMPLATE,
)
from QSExt.LLMFactor.hypothesis.prompts.step4_reflection import (
    STEP4_CRITIQUE_SYSTEM,
    STEP4_CRITIQUE_TEMPLATE,
    STEP4_REFINE_SYSTEM,
    STEP4_REFINE_TEMPLATE,
)

__all__ = [
    "STEP1_SYSTEM",
    "STEP1_USER_TEMPLATE",
    "STEP3_SYSTEM",
    "STEP3_USER_TEMPLATE",
    "STEP4_CRITIQUE_SYSTEM",
    "STEP4_CRITIQUE_TEMPLATE",
    "STEP4_REFINE_SYSTEM",
    "STEP4_REFINE_TEMPLATE",
]
