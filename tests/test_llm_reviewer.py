# -*- coding: utf-8 -*-
"""LLM 审查器测试。

测试覆盖：
  - _extract_json: JSON 提取工具函数
  - create_llm: LLM 工厂函数（Ollama / OpenAI）
  - LLMReviewer.review_component: 组件审查（mock LLM）
  - LLMReviewer.classify_failure: 失败分类（mock LLM）
  - 错误回退: LLM 调用失败时的降级行为

运行方式：
    # 仅运行单元测试（不需要 Ollama）
    pytest tests/test_llm_reviewer.py -v -k "not integration"

    # 运行全部测试（需要 Ollama）
    pytest tests/test_llm_reviewer.py -v

环境要求：
    - QSExt/config/.env 中配置 OLLAMA_BASE_URL
    - Ollama 服务运行中（qwen3 或其他 LLM 模型可用）
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from dotenv import load_dotenv

from QSExt import __QS_MainPath__

load_dotenv(__QS_MainPath__ + "/config/.env")

from QSExt.LLMFactor.mining_log.models import MiningRun


# ============================================================
# 辅助：创建 mock LLM
# ============================================================


def _make_mock_llm(content: str):
    """创建一个 mock 的 LangChain BaseChatModel，返回指定 content。"""
    from langchain_core.messages import AIMessage

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content=content)
    return mock_llm


# ============================================================
# _extract_json 单元测试
# ============================================================


class TestExtractJson:
    """_extract_json JSON 提取测试。"""

    def test_plain_json(self):
        """纯 JSON 字符串应直接解析。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import _extract_json

        result = _extract_json('{"approved": true, "quality_score": 0.8}')
        assert result["approved"] is True
        assert result["quality_score"] == 0.8

    def test_json_in_code_block(self):
        """markdown 代码块中的 JSON 应被提取。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import _extract_json

        text = '''以下是审查结果：
```json
{"approved": false, "issues": ["逻辑错误"], "quality_score": 0.3}
```
请参考以上结果。'''
        result = _extract_json(text)
        assert result["approved"] is False
        assert "逻辑错误" in result["issues"]

    def test_json_in_code_block_no_lang(self):
        """无语言标记的代码块中的 JSON 应被提取。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import _extract_json

        text = '''```
{"failure_type": "low_ic", "lesson_learned": "IC 过低"}
```'''
        result = _extract_json(text)
        assert result["failure_type"] == "low_ic"

    def test_json_with_surrounding_text(self):
        """JSON 周围有文字时应被提取。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import _extract_json

        text = '根据分析，结果如下：{"approved": true, "quality_score": 0.75} 以上为审查结论。'
        result = _extract_json(text)
        assert result["approved"] is True
        assert result["quality_score"] == 0.75

    def test_nested_json(self):
        """嵌套 JSON 对象应正确解析。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import _extract_json

        text = '{"result": {"approved": true}, "issues": ["a", "b"]}'
        result = _extract_json(text)
        assert result["result"]["approved"] is True
        assert len(result["issues"]) == 2

    def test_invalid_json_raises(self):
        """无合法 JSON 时应抛出 ValueError。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import _extract_json

        with pytest.raises(ValueError, match="无法从 LLM 输出中提取"):
            _extract_json("这段文字没有任何 JSON 内容")

    def test_json_with_think_tags(self):
        """LLM 输出中包含 <think> 标签时应跳过提取 JSON。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import _extract_json

        text = '''<think>
让我分析一下这个组件...
</think>

{"approved": true, "financial_rationale": "逻辑合理", "quality_score": 0.8}'''
        result = _extract_json(text)
        assert result["approved"] is True


# ============================================================
# create_llm 工厂测试
# ============================================================


class TestCreateLlm:
    """create_llm 工厂函数测试。"""

    def test_create_ollama(self):
        """创建 Ollama LLM。"""
        from QSExt.LLMFactor.mining_log.llm_client import create_llm

        llm = create_llm("ollama", model="qwen3")
        assert type(llm).__name__ == "ChatOllama"

    def test_create_openai(self):
        """创建 OpenAI 兼容 LLM。"""
        from QSExt.LLMFactor.mining_log.llm_client import create_llm

        llm = create_llm("openai", model="test", base_url="http://localhost", api_key="test")
        assert type(llm).__name__ == "ChatOpenAI"

    def test_create_unknown_provider(self):
        """未知 provider 应抛出 ValueError。"""
        from QSExt.LLMFactor.mining_log.llm_client import create_llm

        with pytest.raises(ValueError, match="不支持的 LLM provider"):
            create_llm("unknown_provider")

    def test_default_provider_is_ollama(self):
        """默认 provider 应为 ollama。"""
        from QSExt.LLMFactor.mining_log.llm_client import create_llm

        llm = create_llm()
        assert type(llm).__name__ == "ChatOllama"


# ============================================================
# LLMReviewer 单元测试（mock LangChain LLM）
# ============================================================


class TestLLMReviewerComponentReview:
    """LLMReviewer.review_component 测试。"""

    def test_review_approved(self):
        """正常审查结果应正确返回。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer

        mock_llm = _make_mock_llm(json.dumps({
            "approved": True,
            "financial_rationale": "日内动量分解逻辑合理，有学术支撑",
            "issues": [],
            "suggestions": "可考虑加入波动率调整",
            "quality_score": 0.85,
        }, ensure_ascii=False))

        reviewer = LLMReviewer(llm=mock_llm)
        result = reviewer.review_component(
            code_snippet="overnight = open / close.shift(1) - 1",
            name="隔夜收益",
            description="计算隔夜跳空收益",
        )

        assert result["approved"] is True
        assert "日内动量" in result["financial_rationale"]
        assert result["quality_score"] == 0.85
        assert isinstance(result["issues"], list)

    def test_review_rejected(self):
        """审查不通过应返回 approved=False。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer

        mock_llm = _make_mock_llm(json.dumps({
            "approved": False,
            "financial_rationale": "逻辑存在缺陷",
            "issues": ["未处理除零错误", "缺少空值检查"],
            "suggestions": "添加 np.where 保护",
            "quality_score": 0.3,
        }, ensure_ascii=False))

        reviewer = LLMReviewer(llm=mock_llm)
        result = reviewer.review_component("x = a / b", "除法组件", "简单除法")

        assert result["approved"] is False
        assert len(result["issues"]) == 2
        assert result["quality_score"] == 0.3

    def test_review_json_in_code_block(self):
        """LLM 返回 markdown 代码块包裹的 JSON 应正确提取。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer

        mock_llm = _make_mock_llm(
            '以下是审查结果：\n```json\n{"approved": true, "financial_rationale": "OK", "issues": [], "suggestions": "", "quality_score": 0.7}\n```'
        )

        reviewer = LLMReviewer(llm=mock_llm)
        result = reviewer.review_component("code", "name", "desc")

        assert result["approved"] is True
        assert result["quality_score"] == 0.7

    def test_review_llm_error_fallback(self):
        """LLM 调用失败时应回退到默认值。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("连接超时")

        reviewer = LLMReviewer(llm=mock_llm)
        result = reviewer.review_component("code", "name", "desc")

        # 回退：默认通过
        assert result["approved"] is True
        assert result["quality_score"] == 0.5
        assert "连接超时" in result["financial_rationale"]

    def test_review_calls_llm_with_messages(self):
        """应通过 LangChain messages 调用 LLM。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer
        from langchain_core.messages import SystemMessage, HumanMessage

        mock_llm = _make_mock_llm('{"approved": true, "financial_rationale": "", "issues": [], "suggestions": "", "quality_score": 0.5}')

        reviewer = LLMReviewer(llm=mock_llm)
        reviewer.review_component("code", "test_name", "test_desc")

        # 验证调用了 invoke 且参数是 messages 列表
        mock_llm.invoke.assert_called_once()
        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 2
        assert isinstance(call_args[0], SystemMessage)
        assert isinstance(call_args[1], HumanMessage)
        assert "test_name" in call_args[1].content


class TestLLMReviewerClassifyFailure:
    """LLMReviewer.classify_failure 测试。"""

    def test_classify_low_ic(self):
        """低 IC 失败分类。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer

        mock_llm = _make_mock_llm(json.dumps({
            "failure_type": "low_ic",
            "lesson_learned": "纯动量因子在 A 股 IC 偏低，需叠加其他信号",
            "recovery_strategy": "加入成交量或波动率过滤",
        }, ensure_ascii=False))

        run = MiningRun(
            id="FM_test",
            metadata={
                "factor_name": "pure_momentum",
                "direction_tag": "动量/日间",
                "decision_reason": "IC 不显著",
                "rankic_mean": 0.008,
                "incremental_ic_t": 0.5,
            },
        )

        reviewer = LLMReviewer(llm=mock_llm)
        result = reviewer.classify_failure(run)

        assert result["failure_type"] == "low_ic"
        assert "动量" in result["lesson_learned"]
        assert len(result["recovery_strategy"]) > 0

    def test_classify_with_code(self):
        """有代码时应传入 LLM 分析。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer

        mock_llm = _make_mock_llm(json.dumps({
            "failure_type": "logic_flaw",
            "lesson_learned": "使用了未来数据",
            "recovery_strategy": "用 shift(1) 避免前视偏差",
        }, ensure_ascii=False))

        run = MiningRun(
            id="FM_test_code",
            metadata={
                "factor_name": "bad_factor",
                "rankic_mean": 0.05,
                "incremental_ic_t": 2.0,
                "development": {"code": "factor = future_data / past_data"},
            },
        )

        reviewer = LLMReviewer(llm=mock_llm)
        result = reviewer.classify_failure(run)

        assert result["failure_type"] == "logic_flaw"

        # 验证 LLM 收到了代码
        call_args = mock_llm.invoke.call_args[0][0]
        user_msg = [m for m in call_args if hasattr(m, "content") and "future_data" in m.content]
        assert len(user_msg) > 0

    def test_classify_llm_error_fallback(self):
        """LLM 调用失败时应回退到规则判断。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("服务不可用")

        run = MiningRun(
            id="FM_test_fallback",
            metadata={
                "factor_name": "test_factor",
                "rankic_mean": 0.005,
                "incremental_ic_t": 0.3,
            },
        )

        reviewer = LLMReviewer(llm=mock_llm)
        result = reviewer.classify_failure(run)

        # rankic < 0.01 → low_ic
        assert result["failure_type"] == "low_ic"
        assert "服务不可用" in result["lesson_learned"]


# ============================================================
# 与 ExperienceRefiner 集成测试（mock LLM）
# ============================================================


class TestLLMReviewerIntegration:
    """LLMReviewer 与 ExperienceRefiner 的集成测试。"""

    def test_refiner_with_llm_reviewer(self):
        """ExperienceRefiner 使用 LLMReviewer 应正常工作。"""
        from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer
        from QSExt.LLMFactor.mining_log.experience_refiner import ExperienceRefiner

        mock_llm = _make_mock_llm(json.dumps({
            "approved": True,
            "financial_rationale": "逻辑合理",
            "issues": [],
            "suggestions": "",
            "quality_score": 0.8,
        }, ensure_ascii=False))

        mock_repo = MagicMock()
        mock_repo.insert_experience = MagicMock(return_value="EXP_test")

        reviewer = LLMReviewer(llm=mock_llm)
        refiner = ExperienceRefiner(mock_repo, reviewer=reviewer)

        run = MiningRun(
            id="FM_integration_test",
            content="集成测试",
            metadata={
                "status": "completed",
                "decision": "accepted",
                "factor_name": "integration_factor",
                "direction_tag": "测试/集成",
                "development": {
                    "code": "# ---- 收益计算 ----\nret = close / close.shift(1) - 1",
                },
            },
        )

        experiences = refiner.refine(run)
        assert isinstance(experiences, list)
        if experiences:
            mock_repo.insert_experience.assert_called()


# ============================================================
# 集成测试（需要 Ollama）
# ============================================================


@pytest.fixture(scope="module")
def llm():
    """创建 Ollama LLM 实例（需要 Ollama 运行）。"""
    from QSExt.LLMFactor.mining_log.llm_client import create_llm
    import requests as req

    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    try:
        resp = req.get(f"{base_url}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pytest.skip("Ollama 服务不可用，跳过 LLM 集成测试")

    if not models:
        pytest.skip("Ollama 无可用模型，跳过 LLM 集成测试")

    try:
        llm = create_llm("ollama", model=models[0])
        from langchain_core.messages import HumanMessage

        llm.invoke([HumanMessage(content="hi")])
        return llm
    except Exception:
        pytest.skip("Ollama LLM 调用失败，跳过 LLM 集成测试")


@pytest.fixture(scope="module")
def llm_reviewer(llm):
    """创建 LLMReviewer 实例。"""
    from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer

    return LLMReviewer(llm=llm)


@pytest.mark.integration
class TestLLMReviewerLive:
    """LLMReviewer 真实 LLM 集成测试。"""

    def test_review_component_live(self, llm_reviewer):
        """真实 LLM 审查组件。"""
        code = """# ---- 隔夜收益 ----
overnight = open / close.shift(1) - 1
# ---- 日内收益 ----
intraday = close / open - 1
"""
        result = llm_reviewer.review_component(
            code_snippet=code,
            name="隔夜日内收益分解",
            description="将日收益率拆分为隔夜跳空和日内趋势两个独立信号",
        )
        assert "approved" in result
        assert "quality_score" in result
        assert 0.0 <= result["quality_score"] <= 1.0
        assert isinstance(result["issues"], list)

    def test_classify_failure_live(self, llm_reviewer):
        """真实 LLM 分析失败原因。"""
        run = MiningRun(
            id="FM_LIVE_TEST",
            metadata={
                "factor_name": "test_pure_momentum",
                "direction_tag": "动量/日间方向预测",
                "decision": "rejected",
                "decision_reason": "RankIC 仅 0.008，不显著",
                "rankic_mean": 0.008,
                "incremental_ic_t": 0.5,
                "composite_score": 0.2,
            },
        )
        result = llm_reviewer.classify_failure(run)
        assert "failure_type" in result
        assert result["failure_type"] in [
            "low_ic", "no_incremental_ic", "overfitting",
            "data_leakage", "logic_flaw",
        ]
        assert len(result["lesson_learned"]) > 0


@pytest.mark.integration
class TestCreateLlmLive:
    """create_llm 真实集成测试。"""

    def test_ollama_provider(self):
        """通过 create_llm 创建 Ollama LLM 并调用。"""
        from QSExt.LLMFactor.mining_log.llm_client import create_llm
        from langchain_core.messages import HumanMessage
        import requests as req

        # 获取 Ollama 实际可用的模型名
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        try:
            resp = req.get(f"{base_url}/api/tags", timeout=5)
            models = [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            pytest.skip("Ollama 服务不可用")

        if not models:
            pytest.skip("Ollama 无可用模型")

        llm = create_llm("ollama", model=models[0])
        result = llm.invoke([HumanMessage(content="回复 OK")])
        assert len(result.content) > 0
