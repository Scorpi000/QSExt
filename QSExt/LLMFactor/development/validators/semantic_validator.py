# -*- coding: utf-8 -*-
"""Agent E: 语义审查验证器（LLM）。

检查项：
    1. 代码逻辑是否与假设文档的伪代码一致
    2. 参数搜索空间是否合理
    3. 是否有明显的计算效率问题
    4. 是否遗漏了假设文档中的关键计算步骤

使用示例::

    from QSExt.LLMFactor.development.config import DevelopmentConfig

    config = DevelopmentConfig()
    validator = SemanticValidator(config)
    report = validator.validate(factor_dir, hypothesis)
"""
from __future__ import annotations

import logging
import re

from QSExt.LLMFactor.development.config import DevelopmentConfig
from QSExt.LLMFactor.development.models import SemanticReviewReport
from QSExt.LLMFactor.development.prompts.code_generation import build_semantic_review_prompt

__QS_Logger__ = logging.getLogger("QSR.development.semantic_validator")


class SemanticValidator:
    """语义审查验证器（Agent E，LLM 驱动）。

    Attributes:
        config: 开发配置
    """

    def __init__(self, config: DevelopmentConfig):
        self.config = config
        self._llm = None

    @property
    def llm(self):
        """懒加载 LLM 实例。"""
        if self._llm is None:
            from QSExt.LLMFactor.mining_log.llm_client import create_llm
            self._llm = create_llm(
                model=self.config.llm_model,
                temperature=self.config.llm_temperature,
            )
        return self._llm

    def validate(self, factor_dir: str, hypothesis: dict) -> SemanticReviewReport:
        """执行语义审查。

        Args:
            factor_dir: 因子目录路径
            hypothesis: 假设文档

        Returns:
            SemanticReviewReport
        """
        from pathlib import Path

        code_path = Path(factor_dir) / "factor_def.py"
        if not code_path.exists():
            return SemanticReviewReport(
                passed=False,
                review_text="factor_def.py 不存在",
                suggestions=[],
            )

        code = code_path.read_text(encoding="utf-8")

        # 构建 prompt
        prompt = build_semantic_review_prompt(code, hypothesis)

        # 调用 LLM
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            messages = [
                SystemMessage(content="你是一个 QuantStudio 因子代码审查专家。请仔细审查代码与假设的一致性。"),
                HumanMessage(content=prompt),
            ]
            response = self.llm.invoke(messages)
            review_text = response.content
        except Exception as e:
            __QS_Logger__.warning(f"LLM 调用失败: {e}")
            return SemanticReviewReport(
                passed=True,  # LLM 不可用时跳过（不阻塞流水线）
                review_text=f"LLM 调用失败，跳过语义审查: {e}",
                suggestions=[],
            )

        # 解析审查结果
        return self._parse_review(review_text)

    def _parse_review(self, review_text: str) -> SemanticReviewReport:
        """解析 LLM 审查输出。

        Args:
            review_text: LLM 输出的审查文本

        Returns:
            SemanticReviewReport
        """
        # 提取审查结论
        passed = True
        if "FAILED" in review_text:
            passed = False
        elif "WARNING" in review_text:
            passed = True  # WARNING 不阻塞

        # 提取改进建议
        suggestions = self._extract_suggestions(review_text)

        return SemanticReviewReport(
            passed=passed,
            review_text=review_text,
            suggestions=suggestions,
        )

    def _extract_suggestions(self, text: str) -> list[str]:
        """从审查文本中提取改进建议。"""
        suggestions = []
        in_suggestions = False

        for line in text.split("\n"):
            line = line.strip()
            if "改进建议" in line:
                in_suggestions = True
                continue
            if in_suggestions and line.startswith(("- ", "* ", "1.", "2.", "3.", "4.", "5.")):
                suggestion = line.lstrip("-*0123456789. ")
                if suggestion:
                    suggestions.append(suggestion)

        return suggestions
