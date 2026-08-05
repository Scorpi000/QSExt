# -*- coding: utf-8 -*-
"""MiningLogWriter 和 validator 测试。

使用 mock 测试写入逻辑，不依赖数据库。
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from QSExt.LLMFactor.mining_log.writer import MiningLogWriter
from QSExt.LLMFactor.mining_log.validator import validate_run
from QSExt.LLMFactor.mining_log.models import MiningRun, RunStatus


# ============================================================
# Mock fixtures
# ============================================================

@pytest.fixture
def mock_repo():
    """创建 mock 的 MiningLogRepository。"""
    repo = MagicMock()
    # 默认 get_run 返回 None（新记录）
    repo.get_run.return_value = None
    return repo


@pytest.fixture
def writer(mock_repo):
    """创建 MiningLogWriter 实例。"""
    return MiningLogWriter(mock_repo)


# ============================================================
# MiningLogWriter 测试
# ============================================================

class TestWriterStartRun:
    """start_run 方法测试。"""

    def test_basic(self, writer, mock_repo):
        """基本功能：创建运行记录。"""
        run = writer.start_run(
            run_id="FM_20260701_001",
            factor_name="test_factor",
            category="动量",
            direction_tag="动量/日内",
            hypothesis={"economic_rationale": "测试逻辑"},
        )

        assert run.id == "FM_20260701_001"
        assert run.metadata["factor_name"] == "test_factor"
        assert run.metadata["category"] == "动量"
        assert run.metadata["status"] == RunStatus.IN_DEVELOPMENT.value
        assert "hypothesis" in run.metadata
        assert "timing" in run.metadata
        mock_repo.insert_run.assert_called_once()

    def test_with_optional_fields(self, writer, mock_repo):
        """可选字段正确写入。"""
        run = writer.start_run(
            run_id="FM_20260701_002",
            factor_name="f2",
            category="估值",
            direction_tag="估值/PE",
            hypothesis={"economic_rationale": "逻辑"},
            tags=["估值", "PE"],
            parent_run_id="FM_20260615_001",
            hypothesis_id="hyp_001",
            inspired_by={"wiki_pages": ["page1"]},
            exploration_trail=[{"source": "wiki"}],
            reflection={"critique_notes": "批判"},
        )

        assert run.metadata["parent_run_id"] == "FM_20260615_001"
        assert run.metadata["hypothesis_id"] == "hyp_001"
        assert run.metadata["inspired_by"] == {"wiki_pages": ["page1"]}
        assert run.tags == ["估值", "PE"]

    def test_content_generated(self, writer, mock_repo):
        """content 字段自动生成。"""
        run = writer.start_run(
            run_id="FM_20260701_003",
            factor_name="momentum_v2",
            category="动量",
            direction_tag="动量/方向",
            hypothesis={"economic_rationale": "动量逻辑描述"},
        )

        assert "momentum_v2" in run.content
        assert "动量" in run.content


class TestWriterRecordDevelopment:
    """record_development 方法测试。"""

    def test_basic(self, writer, mock_repo):
        """基本功能：记录开发阶段。"""
        # 模拟已有记录
        existing = MiningRun(id="FM_20260701_001")
        existing.metadata = {
            "factor_name": "test",
            "status": RunStatus.IN_DEVELOPMENT.value,
            "timing": {},
        }
        mock_repo.get_run.return_value = existing

        writer.record_development(
            run_id="FM_20260701_001",
            code_path="workspace/FM_001/factor.py",
            best_params={"LookBack": 120},
            auto_fix_count=1,
        )

        # 验证 insert_run 被调用
        mock_repo.insert_run.assert_called_once()
        call_args = mock_repo.insert_run.call_args[0][0]
        assert call_args.metadata["status"] == RunStatus.EVALUATING.value
        assert call_args.metadata["development"]["code_path"] == "workspace/FM_001/factor.py"
        assert call_args.metadata["development"]["best_params"] == {"LookBack": 120}

    def test_run_not_found(self, writer, mock_repo):
        """运行记录不存在时抛出异常。"""
        mock_repo.get_run.return_value = None
        with pytest.raises(ValueError, match="不存在"):
            writer.record_development(run_id="FM_xxx", code_path="path")


class TestWriterRecordEvaluation:
    """record_evaluation 方法测试。"""

    def test_basic(self, writer, mock_repo):
        """基本功能：记录评测结果。"""
        existing = MiningRun(id="FM_20260701_001")
        existing.metadata = {
            "factor_name": "test",
            "status": RunStatus.EVALUATING.value,
            "timing": {},
        }
        mock_repo.get_run.return_value = existing

        writer.record_evaluation(
            run_id="FM_20260701_001",
            rankic_mean=0.045,
            rankicir=0.72,
            oos_rankic=0.041,
            incremental_ic_t=2.8,
            composite_score=0.67,
        )

        call_args = mock_repo.insert_run.call_args[0][0]
        assert call_args.metadata["rankic_mean"] == 0.045
        assert call_args.metadata["rankicir"] == 0.72
        assert call_args.metadata["evaluation"]["rankic_mean"] == 0.045

    def test_required_field(self, writer, mock_repo):
        """rankic_mean 是必填字段。"""
        existing = MiningRun(id="FM_001")
        existing.metadata = {"status": "evaluating", "timing": {}}
        mock_repo.get_run.return_value = existing

        # rankic_mean 必须提供
        writer.record_evaluation(run_id="FM_001", rankic_mean=0.05)
        mock_repo.insert_run.assert_called_once()


class TestWriterSetDecision:
    """set_decision 方法测试。"""

    def test_accepted(self, writer, mock_repo):
        """设置 accepted 决策。"""
        existing = MiningRun(id="FM_001")
        existing.metadata = {"status": "evaluating", "timing": {}}
        mock_repo.get_run.return_value = existing

        writer.set_decision(
            run_id="FM_001",
            decision="accepted",
            reason="增量 IC 显著",
        )

        call_args = mock_repo.insert_run.call_args[0][0]
        assert call_args.metadata["decision"] == "accepted"
        assert call_args.metadata["status"] == RunStatus.COMPLETED.value

    def test_rejected(self, writer, mock_repo):
        """设置 rejected 决策。"""
        existing = MiningRun(id="FM_001")
        existing.metadata = {"status": "evaluating", "timing": {}}
        mock_repo.get_run.return_value = existing

        writer.set_decision(
            run_id="FM_001",
            decision="rejected",
            reason="IC 不显著",
        )

        call_args = mock_repo.insert_run.call_args[0][0]
        assert call_args.metadata["decision"] == "rejected"


class TestWriterMarkFailed:
    """mark_failed 方法测试。"""

    def test_basic(self, writer, mock_repo):
        """标记运行失败。"""
        existing = MiningRun(id="FM_001")
        existing.metadata = {"status": "in_development", "timing": {}}
        mock_repo.get_run.return_value = existing

        writer.mark_failed(run_id="FM_001", reason="语法错误")

        call_args = mock_repo.insert_run.call_args[0][0]
        assert call_args.metadata["status"] == RunStatus.FAILED.value
        assert call_args.metadata["failure_reason"] == "语法错误"


class TestWriterUpdateMethods:
    """update_field / update_tags 测试。"""

    def test_update_field(self, writer, mock_repo):
        """更新单个字段。"""
        existing = MiningRun(id="FM_001")
        existing.metadata = {"factor_name": "test"}
        mock_repo.get_run.return_value = existing

        writer.update_field("FM_001", "category", "动量")

        call_args = mock_repo.insert_run.call_args[0][0]
        assert call_args.metadata["category"] == "动量"

    def test_update_tags(self, writer, mock_repo):
        """更新标签。"""
        existing = MiningRun(id="FM_001")
        existing.metadata = {}
        existing.tags = ["old"]
        mock_repo.get_run.return_value = existing

        writer.update_tags("FM_001", ["新标签", "动量"])

        call_args = mock_repo.insert_run.call_args[0][0]
        assert call_args.tags == ["新标签", "动量"]


# ============================================================
# Validator 测试
# ============================================================

class TestValidateRun:
    """validate_run 函数测试。"""

    def test_complete_record(self):
        """完整记录校验通过。"""
        metadata = {
            "factor_name": "test",
            "category": "动量",
            "direction_tag": "动量/日内",
            "status": RunStatus.COMPLETED.value,
            "hypothesis": {"economic_rationale": "逻辑"},
            "development": {"code_path": "path"},
            "evaluation": {"rankic_mean": 0.04},
            "decision": "accepted",
            "decision_reason": "通过",
            "rankic_mean": 0.04,
            "rankicir": 0.72,
            "composite_score": 0.67,
            "timing": {},
        }
        result = validate_run(metadata)
        assert result["is_complete"] is True
        assert result["missing_required"] == []

    def test_missing_required(self):
        """缺失必填字段。"""
        metadata = {"status": "completed"}
        result = validate_run(metadata)
        assert result["is_complete"] is False
        assert "factor_name" in result["missing_required"]

    def test_missing_recommended(self):
        """缺失推荐字段。"""
        metadata = {
            "factor_name": "test",
            "category": "动量",
            "direction_tag": "动量/日内",
            "status": RunStatus.COMPLETED.value,
        }
        result = validate_run(metadata)
        assert "hypothesis" in result["missing_recommended"]
        assert "decision" in result["missing_recommended"]

    def test_in_development_status(self):
        """in_development 状态的校验。"""
        metadata = {
            "factor_name": "test",
            "category": "动量",
            "direction_tag": "动量/日内",
            "status": RunStatus.IN_DEVELOPMENT.value,
            "hypothesis": {"economic_rationale": "逻辑"},
            "timing": {},
        }
        result = validate_run(metadata)
        assert result["is_complete"] is True

    def test_empty_metadata(self):
        """空 metadata。"""
        result = validate_run({})
        assert result["is_complete"] is False
        assert len(result["missing_required"]) > 0
