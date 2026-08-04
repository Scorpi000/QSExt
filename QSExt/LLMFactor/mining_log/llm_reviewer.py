# -*- coding: utf-8 -*-
"""LLM 组件审查器 — 基于大语言模型审查因子代码组件的金融逻辑和代码质量。

替代 experience_refiner.py 中的 NoOpReviewer，通过 LangChain 统一接口
调用不同 LLM 后端（Ollama 本地模型、OpenAI 兼容外部模型等）。

用法:
    from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer

    # 使用默认配置（.env 中的 LLM_PROVIDER）
    reviewer = LLMReviewer()

    # 指定 LangChain ChatModel
    from langchain_ollama import ChatOllama
    reviewer = LLMReviewer(llm=ChatOllama(model="qwen3"))

    # 使用工厂函数
    from QSExt.LLMFactor.mining_log.llm_client import create_llm
    reviewer = LLMReviewer(llm=create_llm("openai", model="deepseek-chat"))

    result = reviewer.review_component(code_snippet, name, description)
    failure = reviewer.classify_failure(run)
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from QSExt.LLMFactor.mining_log.models import MiningRun

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 输出中提取 JSON 对象。

    LLM 常在 JSON 外包裹 markdown 代码块或附加说明文字，
    此函数尝试多种策略提取第一个合法 JSON 对象。
    """
    # 策略 1: 直接解析
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 策略 2: 提取 ```json ... ``` 代码块
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 策略 3: 提取第一个 { ... } 块
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    start = None

    raise ValueError(f"无法从 LLM 输出中提取 JSON: {text[:200]}")


class LLMReviewer:
    """基于 LLM 的组件审查器。

    实现 ComponentReviewer 协议，通过 LangChain 统一接口调用不同 LLM 后端
    对因子代码组件进行金融逻辑审查和失败原因分析。

    Args:
        llm: LangChain BaseChatModel 实例。为 None 时通过 create_llm() 按 .env 配置创建。
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        if llm is not None:
            self._llm = llm
        else:
            from QSExt.LLMFactor.mining_log.llm_client import create_llm

            self._llm = create_llm()

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM。"""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        result = self._llm.invoke(messages)
        return result.content

    def review_component(
        self, code_snippet: str, name: str, description: str
    ) -> dict[str, Any]:
        """审查单个逻辑组件。

        评估金融逻辑正确性、代码质量和复用潜力。

        Returns:
            {
                "approved": bool,
                "financial_rationale": str,
                "issues": list[str],
                "suggestions": str,
                "quality_score": float,
            }
        """
        system_prompt = (
            "你是一位资深量化研究员，擅长审查因子代码的金融逻辑和实现质量。"
            "请严格按照要求的 JSON 格式返回审查结果，不要附加其他文字。"
        )
        user_prompt = f"""审查以下量化因子逻辑组件：

组件名称: {name}
描述: {description}
代码:
```python
{code_snippet}
```

请评估：
1. 金融逻辑是否成立？是否有理论依据？
2. 代码实现是否正确？有边界条件问题吗？
3. 是否具备跨因子复用的潜力？

返回 JSON（不要附加其他文字）:
{{"approved": true/false, "financial_rationale": "金融逻辑评估", "issues": ["问题1", "问题2"], "suggestions": "改进建议", "quality_score": 0.0-1.0}}
"""
        try:
            raw = self._chat(system_prompt, user_prompt)
            result = _extract_json(raw)
            # 确保必要字段存在且类型正确
            return {
                "approved": bool(result.get("approved", False)),
                "financial_rationale": str(result.get("financial_rationale", "")),
                "issues": list(result.get("issues", [])),
                "suggestions": str(result.get("suggestions", "")),
                "quality_score": float(result.get("quality_score", 0.5)),
            }
        except Exception as e:
            logger.warning("LLM review_component 调用失败，回退到默认值: %s", e)
            return {
                "approved": True,
                "financial_rationale": f"LLM 审查失败({e})，默认通过",
                "issues": [],
                "suggestions": "",
                "quality_score": 0.5,
            }

    def classify_failure(self, run: MiningRun) -> dict[str, Any]:
        """分析失败运行的原因，生成教训和恢复策略。

        Returns:
            {
                "failure_type": str,
                "lesson_learned": str,
                "recovery_strategy": str,
            }
        """
        factor_name = run.metadata.get("factor_name", "")
        decision_reason = run.metadata.get("decision_reason", "")
        rankic = run.metadata.get("rankic_mean") or 0
        inc_ic_t = run.metadata.get("incremental_ic_t") or 0
        composite_score = run.metadata.get("composite_score") or 0
        direction_tag = run.metadata.get("direction_tag", "")

        # 提取代码片段
        code = run.metadata.get("development", {}).get("code", "")
        if not code:
            code = run.metadata.get("hypothesis", {}).get("calculation_pseudo", "")
        code_section = f"\n代码:\n```python\n{code[:2000]}\n```" if code else ""

        system_prompt = (
            "你是一位资深量化研究员，擅长分析因子挖掘失败的原因并提出改进建议。"
            "请严格按照要求的 JSON 格式返回分析结果，不要附加其他文字。"
        )
        user_prompt = f"""分析以下因子挖掘失败案例：

因子名称: {factor_name}
研究方向: {direction_tag}
决策原因: {decision_reason}
RankIC: {rankic:.4f}
增量IC_t: {inc_ic_t:.2f}
综合评分: {composite_score:.4f}
{code_section}

请分析失败原因并给出改进建议。

返回 JSON（不要附加其他文字）:
{{"failure_type": "low_ic/no_incremental_ic/overfitting/data_leakage/logic_flaw", "lesson_learned": "核心教训", "recovery_strategy": "改进策略"}}
"""
        try:
            raw = self._chat(system_prompt, user_prompt)
            result = _extract_json(raw)
            return {
                "failure_type": str(result.get("failure_type", "logic_flaw")),
                "lesson_learned": str(result.get("lesson_learned", "")),
                "recovery_strategy": str(result.get("recovery_strategy", "")),
            }
        except Exception as e:
            logger.warning("LLM classify_failure 调用失败，回退到规则判断: %s", e)
            # 回退到与 NoOpReviewer 相同的规则判断
            if abs(rankic) < 0.01:
                failure_type = "low_ic"
            elif inc_ic_t < 1.0:
                failure_type = "no_incremental_ic"
            else:
                failure_type = "logic_flaw"
            return {
                "failure_type": failure_type,
                "lesson_learned": f"LLM 分析失败({e})，规则判断: RankIC={rankic:.4f}, 增量IC_t={inc_ic_t:.2f}",
                "recovery_strategy": "",
            }
