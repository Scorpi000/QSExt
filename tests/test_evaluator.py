# -*- coding: utf-8 -*-
"""因子评测入口（evaluator）测试。

测试覆盖：
  - 辅助函数（_parse_dt_range, _find_output_key, _safe_float 等）
  - 统计提取函数（_extract_ic_stats, _extract_portfolio_stats 等）
  - FactorEvaluator 初始化与配置
  - EvalReport 数据类

运行方式：
    pytest tests/test_evaluator.py -v
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from QSExt.LLMFactor.evaluation.config import EvalConfig
from QSExt.LLMFactor.evaluation.scoring import FiveDimScore
from QSExt.LLMFactor.evaluation.decision import DecisionResult
from QSExt.LLMFactor.evaluation.evaluator import (
    EvalReport,
    FactorEvaluator,
    _extract_ic_stats,
    _extract_incremental_ic_stats,
    _extract_portfolio_stats,
    _extract_turnover_stats,
    _find_col,
    _find_output_key,
    _parse_dt_range,
    _safe_float,
    _collect_node_reports,
)


# ============================================================
# 辅助函数测试
# ============================================================


class TestSafeFloat:
    """_safe_float 测试。"""

    def test_normal_float(self):
        assert _safe_float(3.14) == 3.14

    def test_int(self):
        assert _safe_float(42) == 42.0

    def test_nan(self):
        assert _safe_float(float("nan")) == 0.0

    def test_none(self):
        assert _safe_float(None) == 0.0

    def test_none_with_default(self):
        assert _safe_float(None, -1.0) == -1.0

    def test_string(self):
        assert _safe_float("abc") == 0.0

    def test_string_with_default(self):
        assert _safe_float("abc", 99.0) == 99.0


class TestParseDtRange:
    """_parse_dt_range 测试。"""

    def test_normal(self):
        start, end = _parse_dt_range("2015-01", "2022-12")
        assert start == dt.datetime(2015, 1, 1)
        assert end == dt.datetime(2022, 12, 28)

    def test_same_month(self):
        start, end = _parse_dt_range("2023-06", "2023-06")
        assert start.year == 2023 and start.month == 6
        assert end.year == 2023 and end.month == 6


class TestFindOutputKey:
    """_find_output_key 测试。"""

    def test_exact_match(self):
        output = {"0-IC": {}, "1-IC衰减": {}, "2-分位数组合": {}}
        assert _find_output_key(output, "IC") == "0-IC"

    def test_fragment_match(self):
        output = {"0-IC": {}, "1-IC衰减": {}, "2-bp_lr-分位数组合": {}}
        assert _find_output_key(output, "分位数组合") == "2-bp_lr-分位数组合"

    def test_no_match(self):
        output = {"0-IC": {}, "1-IC衰减": {}}
        assert _find_output_key(output, "增量") is None

    def test_empty_output(self):
        assert _find_output_key({}, "IC") is None


class TestFindCol:
    """_find_col 测试。"""

    def test_found(self):
        df = pd.DataFrame(columns=["平均值", "标准差", "IC_IR"])
        assert _find_col(df, ["IC_IR", "ICIR"]) == "IC_IR"

    def test_first_match(self):
        df = pd.DataFrame(columns=["Mean", "平均值"])
        assert _find_col(df, ["平均值", "Mean"]) == "平均值"

    def test_not_found(self):
        df = pd.DataFrame(columns=["A", "B"])
        assert _find_col(df, ["C", "D"]) is None

    def test_empty_candidates(self):
        df = pd.DataFrame(columns=["A"])
        assert _find_col(df, []) is None


# ============================================================
# 统计提取函数测试
# ============================================================


class TestExtractIcStats:
    """_extract_ic_stats 测试。"""

    def test_normal(self):
        output = {
            "0-IC": {
                "IC": pd.DataFrame({"f1": [0.05, 0.03, 0.04]}),
                "统计数据": pd.DataFrame({
                    "平均值": [0.04],
                    "标准差": [0.01],
                    "IC_IR": [4.0],
                    "t统计量": [3.5],
                    "胜率": [0.65],
                }),
            }
        }
        stats = _extract_ic_stats(output, "0-IC")
        assert stats["rankic_mean"] == pytest.approx(0.04)
        assert stats["icir"] == pytest.approx(4.0)
        assert stats["t_stat"] == pytest.approx(3.5)
        assert stats["win_rate"] == pytest.approx(0.65)
        assert stats["ic_series"] is not None

    def test_missing_node(self):
        stats = _extract_ic_stats({}, "0-IC")
        assert stats == {}

    def test_empty_stats_df(self):
        output = {"0-IC": {"统计数据": pd.DataFrame()}}
        stats = _extract_ic_stats(output, "0-IC")
        assert stats == {}

    def test_alternative_column_names(self):
        """支持英文列名。"""
        output = {
            "0-IC": {
                "统计数据": pd.DataFrame({
                    "IC_mean": [0.03],
                    "ICIR": [2.5],
                    "t_stat": [3.0],
                    "win_rate": [0.60],
                }),
            }
        }
        stats = _extract_ic_stats(output, "0-IC")
        assert stats["rankic_mean"] == pytest.approx(0.03)
        assert stats["icir"] == pytest.approx(2.5)


class TestExtractPortfolioStats:
    """_extract_portfolio_stats 测试。"""

    def test_normal(self):
        output = {
            "2-分位数组合": {
                "统计数据": pd.DataFrame({
                    "年化收益率": [0.15, 0.08, 0.02, -0.03, -0.08, 0.23],
                    "波动率": [0.25, 0.23, 0.22, 0.21, 0.20, 0.12],
                    "Sharpe比率": [0.60, 0.35, 0.09, -0.14, -0.40, 1.92],
                    "最大回撤": [-0.15, -0.12, -0.10, -0.11, -0.18, -0.05],
                }, index=["P0", "P1", "P2", "P3", "P4", "P0-P4"]),
                "净值": pd.DataFrame(),
                "超额净值": pd.DataFrame(),
            }
        }
        stats = _extract_portfolio_stats(output, "2-分位数组合")
        assert stats["annual_return"] == pytest.approx(0.15)
        assert stats["sharpe"] == pytest.approx(0.60)
        assert stats["max_drawdown"] == pytest.approx(-0.15)
        assert stats["long_short_return"] == pytest.approx(0.23)
        assert stats["long_short_sharpe"] == pytest.approx(1.92)

    def test_missing_node(self):
        stats = _extract_portfolio_stats({}, "2-分位数组合")
        assert stats == {}


class TestExtractTurnoverStats:
    """_extract_turnover_stats 测试。"""

    def test_normal(self):
        output = {
            "3-因子换手率": {
                "统计数据": pd.DataFrame({
                    "平均值": [0.72],
                    "标准差": [0.10],
                    "最小值": [0.50],
                    "最大值": [0.90],
                }),
            }
        }
        stats = _extract_turnover_stats(output, "3-因子换手率")
        # avg_turnover = 1 - 0.72 = 0.28
        assert stats["avg_turnover"] == pytest.approx(0.28)


class TestExtractIncrementalIcStats:
    """_extract_incremental_ic_stats 测试。"""

    def test_normal(self):
        output = {
            "4-增量 IC 检验": {
                "统计数据": pd.DataFrame({
                    "增量IC均值": [0.018],
                    "标准差": [0.008],
                    "IC_IR": [2.25],
                    "增量IC t统计量": [2.8],
                    "最大相关性均值": [0.45],
                    "有效期数": [60],
                }),
            }
        }
        stats = _extract_incremental_ic_stats(output, "4-增量 IC 检验")
        assert stats["mean_ic"] == pytest.approx(0.018)
        assert stats["t_stat"] == pytest.approx(2.8)
        assert stats["max_correlation"] == pytest.approx(0.45)


# ============================================================
# FactorEvaluator 测试
# ============================================================


class TestFactorEvaluatorInit:
    """FactorEvaluator 初始化测试。"""

    def test_default_config(self):
        evaluator = FactorEvaluator()
        assert evaluator.config is not None
        assert evaluator.config.min_alpha_t == 3.0

    def test_custom_config(self):
        config = EvalConfig(min_alpha_t=2.5)
        evaluator = FactorEvaluator(config)
        assert evaluator.config.min_alpha_t == 2.5


# ============================================================
# EvalReport 测试
# ============================================================


class TestEvalReport:
    """EvalReport 数据类测试。"""

    def _make_report(self) -> EvalReport:
        return EvalReport(
            factor_name="test_factor",
            qsid="QSID_001",
            category="动量",
            scores=FiveDimScore(
                effectiveness=0.8, stability=0.7,
                turnover=0.6, diversity=0.5, overfitting_risk=0.9,
            ),
            decision=DecisionResult(
                decision="accepted",
                reason="测试通过",
                checks={},
            ),
            report_html="<html>test</html>",
            is_output={},
            oos_output={},
            is_stats={"ic": {"rankic_mean": 0.045, "icir": 0.72}},
            oos_stats={"ic": {"rankic_mean": 0.041}},
        )

    def test_summary(self):
        report = self._make_report()
        s = report.summary
        assert s["factor_name"] == "test_factor"
        assert s["decision"] == "accepted"
        assert s["rankic_mean"] == pytest.approx(0.045)
        assert s["oos_rankic"] == pytest.approx(0.041)


# ============================================================
# _collect_node_reports 测试
# ============================================================


class TestCollectNodeReports:
    """_collect_node_reports 测试。"""

    def test_with_reports(self):
        output = {
            "0-IC": {"统计数据": pd.DataFrame(), "Report": "<p>IC 报告</p>"},
            "1-IC衰减": {"统计数据": pd.DataFrame()},
            "2-分位数组合": {"Report": "<p>组合报告</p>"},
        }
        html = _collect_node_reports(output)
        assert "IC 报告" in html
        assert "组合报告" in html
        # 1-IC衰减 没有 Report，不应出现
        assert "IC衰减" not in html

    def test_empty_output(self):
        assert _collect_node_reports({}) == ""


# ============================================================
# EvalConfig 新字段测试
# ============================================================


class TestEvalConfigNewFields:
    """EvalConfig 新增字段测试。"""

    def test_ic_decay_periods_default(self):
        config = EvalConfig()
        assert config.ic_decay_periods == [1, 2, 3, 6, 12]

    def test_ic_decay_periods_custom(self):
        config = EvalConfig(ic_decay_periods=[1, 3, 6])
        assert config.ic_decay_periods == [1, 3, 6]
