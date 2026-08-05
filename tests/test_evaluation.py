# -*- coding: utf-8 -*-
"""因子评测模块测试。

测试覆盖：
  - 评分算法（scoring）
  - 决策规则（decision）
  - 配置（config）

运行方式：
    pytest tests/test_evaluation.py -v
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from QSExt.LLMFactor.evaluation.config import EvalConfig
from QSExt.LLMFactor.evaluation.scoring import (
    FiveDimScore,
    calc_effectiveness,
    calc_stability,
    calc_turnover,
    calc_diversity,
    calc_overfitting_risk,
    calc_scores,
)
from QSExt.LLMFactor.evaluation.decision import (
    DecisionResult,
    make_decision,
    check_correlation_warning,
)


# ============================================================
# 配置测试
# ============================================================


class TestEvalConfig:
    """评测配置测试。"""

    def test_default_config(self):
        """默认配置应有合理的默认值。"""
        config = EvalConfig()
        assert config.in_sample_start == "2015-01"
        assert config.in_sample_end == "2022-12"
        assert config.oos_start == "2023-01"
        assert config.oos_end == "2025-12"
        assert config.corr_method == "spearman"
        assert config.group_num == 5
        assert config.min_alpha_t == 3.0
        assert config.min_composite_score == 0.60
        assert config.min_incremental_ic_t == 2.0
        assert config.min_oos_rankic == 0.02
        assert config.corr_warning_threshold == 0.7

    def test_custom_config(self):
        """自定义配置应正确覆盖默认值。"""
        config = EvalConfig(
            min_alpha_t=2.5,
            min_composite_score=0.55,
            group_num=10,
        )
        assert config.min_alpha_t == 2.5
        assert config.min_composite_score == 0.55
        assert config.group_num == 10
        # 未覆盖的值应保持默认
        assert config.min_incremental_ic_t == 2.0

    def test_score_weights(self):
        """评分权重应总和为 1。"""
        config = EvalConfig()
        weights = config.score_weights
        assert abs(sum(weights.values()) - 1.0) < 1e-6


# ============================================================
# 评分测试
# ============================================================


class TestScoring:
    """评分算法测试。"""

    def test_effectiveness_high(self):
        """高 RankIC 和 ICIR 应得到高有效性评分。"""
        score = calc_effectiveness(0.06, 0.8)
        assert score > 0.9

    def test_effectiveness_low(self):
        """低 RankIC 和 ICIR 应得到低有效性评分。"""
        score = calc_effectiveness(0.005, 0.1)
        assert score < 0.3

    def test_effectiveness_medium(self):
        """中等 RankIC 和 ICIR 应得到中等有效性评分。"""
        score = calc_effectiveness(0.03, 0.5)
        assert 0.3 < score < 0.8

    def test_stability_high(self):
        """高胜率和自相关应得到高稳定性评分。"""
        # 使用更长的序列，确保胜率和自相关都高
        ic_series = pd.Series([0.05, 0.03, 0.04, 0.06, 0.02, 0.04, 0.05, 0.03,
                               0.04, 0.05, 0.03, 0.06, 0.04, 0.05, 0.03, 0.04])
        score = calc_stability(ic_series)
        assert score > 0.5  # 胜率 100%，应得到高分

    def test_stability_low(self):
        """低胜率应得到低稳定性评分。"""
        ic_series = pd.Series([-0.02, 0.01, -0.03, 0.02, -0.01, -0.04, 0.01, -0.02])
        score = calc_stability(ic_series)
        assert score < 0.5

    def test_stability_short_series(self):
        """短序列应返回默认值。"""
        ic_series = pd.Series([0.01, 0.02])
        score = calc_stability(ic_series)
        assert score == 0.5

    def test_turnover_low(self):
        """低换手率应得到高评分。"""
        score = calc_turnover(0.2)
        assert score > 0.9

    def test_turnover_high(self):
        """高换手率应得到低评分。"""
        score = calc_turnover(0.8)
        assert score < 0.3

    def test_turnover_medium(self):
        """中等换手率应得到中等评分。"""
        score = calc_turnover(0.5)
        assert 0.3 < score < 0.8

    def test_diversity_high(self):
        """高增量 IC t 应得到高多样性评分。"""
        score = calc_diversity(3.5, 0.3)
        assert score > 0.7

    def test_diversity_low(self):
        """低增量 IC t 应得到低多样性评分。"""
        score = calc_diversity(0.5, 0.3)
        assert score < 0.3

    def test_diversity_with_high_correlation(self):
        """高相关性应降低多样性评分。"""
        score_low_corr = calc_diversity(3.0, 0.2)
        score_high_corr = calc_diversity(3.0, 0.8)
        assert score_low_corr > score_high_corr

    def test_overfitting_low_risk(self):
        """IS/OOS 衰减比高应得到高评分（低过拟合风险）。"""
        score = calc_overfitting_risk(0.05, 0.045, 0.7, 0.65)
        assert score > 0.7

    def test_overfitting_high_risk(self):
        """IS/OOS 衰减比低应得到低评分（高过拟合风险）。"""
        score = calc_overfitting_risk(0.05, 0.01, 0.7, 0.2)
        assert score < 0.4

    def test_calc_scores_integration(self):
        """完整评分流程测试。"""
        scores = calc_scores(
            ic_stats={"rankic_mean": 0.045, "icir": 0.72, "win_rate": 0.65},
            oos_ic_stats={"rankic_mean": 0.041, "icir": 0.68},
            incremental_ic_stats={"t_stat": 2.8, "max_correlation": 0.45},
            turnover_stats={"avg_turnover": 0.4},
        )
        assert isinstance(scores, FiveDimScore)
        assert 0 <= scores.effectiveness <= 1
        assert 0 <= scores.stability <= 1
        assert 0 <= scores.turnover <= 1
        assert 0 <= scores.diversity <= 1
        assert 0 <= scores.overfitting_risk <= 1
        assert 0 <= scores.composite <= 1

    def test_calc_scores_with_defaults(self):
        """缺失数据时应使用默认值。"""
        scores = calc_scores(
            ic_stats={"rankic_mean": 0.045, "icir": 0.72},
        )
        assert isinstance(scores, FiveDimScore)
        assert scores.diversity == 0.5  # 默认值
        assert scores.overfitting_risk == 0.5  # 默认值

    def test_five_dim_score_to_dict(self):
        """to_dict 应返回正确格式。"""
        scores = FiveDimScore(0.8, 0.7, 0.6, 0.5, 0.4)
        d = scores.to_dict()
        assert "有效性" in d
        assert "稳定性" in d
        assert "换手率" in d
        assert "多样性" in d
        assert "过拟合风险" in d
        assert "综合评分" in d

    def test_five_dim_score_to_dataframe(self):
        """to_dataframe 应返回 DataFrame。"""
        scores = FiveDimScore(0.8, 0.7, 0.6, 0.5, 0.4)
        df = scores.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert "有效性" in df.columns


# ============================================================
# 决策测试
# ============================================================


class TestDecision:
    """决策规则测试。"""

    def test_accept_all_passed(self):
        """所有检查通过应返回 accepted。"""
        config = EvalConfig()
        scores = FiveDimScore(0.8, 0.7, 0.6, 0.7, 0.6)
        decision = make_decision(
            ic_stats={"rankic_mean": 0.05, "icir": 0.8, "t_stat": 4.0},
            oos_ic_stats={"rankic_mean": 0.04},
            incremental_ic_stats={"t_stat": 2.5, "max_correlation": 0.4},
            scores=scores,
            alpha_stats={"capm_t": 3.5, "ff3_t": 3.2},
            config=config,
        )
        assert decision.decision == "accepted"
        assert decision.factor_type == "standard"

    def test_accept_synergistic(self):
        """单独不达标但增量 IC 显著应返回 accepted + synergistic。"""
        config = EvalConfig()
        scores = FiveDimScore(0.8, 0.7, 0.6, 0.7, 0.6)
        decision = make_decision(
            ic_stats={"rankic_mean": 0.05, "icir": 0.8, "t_stat": 4.0},
            oos_ic_stats={"rankic_mean": 0.01},  # 低于阈值
            incremental_ic_stats={"t_stat": 2.5, "max_correlation": 0.4},
            scores=scores,
            alpha_stats={"capm_t": 3.5, "ff3_t": 3.2},
            config=config,
        )
        assert decision.decision == "accepted"
        assert decision.factor_type == "synergistic"

    def test_refine_partial_pass(self):
        """部分检查通过应返回 refining。"""
        config = EvalConfig()
        scores = FiveDimScore(0.5, 0.7, 0.6, 0.5, 0.6)  # 综合评分低于阈值
        decision = make_decision(
            ic_stats={"rankic_mean": 0.03, "icir": 0.5, "t_stat": 3.5},
            oos_ic_stats={"rankic_mean": 0.025},
            incremental_ic_stats={"t_stat": 1.5, "max_correlation": 0.4},
            scores=scores,
            alpha_stats={"capm_t": 3.5, "ff3_t": 3.2},  # Alpha 通过
            config=config,
        )
        assert decision.decision == "refining"

    def test_reject_all_failed(self):
        """所有检查失败应返回 rejected。"""
        config = EvalConfig()
        scores = FiveDimScore(0.3, 0.4, 0.5, 0.3, 0.4)  # 低分
        decision = make_decision(
            ic_stats={"rankic_mean": 0.01, "icir": 0.2, "t_stat": 1.0},
            oos_ic_stats={"rankic_mean": 0.005},
            incremental_ic_stats={"t_stat": 0.5, "max_correlation": 0.4},
            scores=scores,
            alpha_stats={"capm_t": 1.5, "ff3_t": 1.2},
            config=config,
        )
        assert decision.decision == "rejected"

    def test_decision_to_dict(self):
        """to_dict 应返回正确格式。"""
        decision = DecisionResult("accepted", "测试原因", {"check1": {"passed": True}})
        d = decision.to_dict()
        assert d["决策"] == "accepted"
        assert d["决策原因"] == "测试原因"
        assert d["因子类型"] == "standard"

    def test_decision_to_dataframe(self):
        """to_dataframe 应返回 DataFrame。"""
        checks = {
            "alpha_t": {"passed": True, "value": 3.5, "threshold": 3.0},
            "composite_score": {"passed": False, "value": 0.55, "threshold": 0.60},
        }
        decision = DecisionResult("refining", "测试", checks)
        df = decision.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "检查项" in df.columns
        assert "通过" in df.columns

    def test_correlation_warning(self):
        """高相关性应触发预警。"""
        config = EvalConfig(corr_warning_threshold=0.7)
        result = check_correlation_warning(0.8, config)
        assert result["warning"] is True
        assert "预警" in result["message"]

    def test_no_correlation_warning(self):
        """低相关性不应触发预警。"""
        config = EvalConfig(corr_warning_threshold=0.7)
        result = check_correlation_warning(0.5, config)
        assert result["warning"] is False
