# -*- coding: utf-8 -*-
"""报告数据准备模块测试。"""
import numpy as np
import pandas as pd
import pytest

from QSExt.LLMFactor.evaluation.decision import DecisionResult
from QSExt.LLMFactor.evaluation.report import (
    generate_eval_report,
    prepare_report_data,
)
from QSExt.LLMFactor.evaluation.scoring import FiveDimScore


# ============================================================
# 测试数据构造
# ============================================================

def _make_ic_output(factor_name="test_factor", n_months=24):
    """构造 IC 节点 output。"""
    dates = pd.date_range("2020-01-01", periods=n_months, freq="ME")
    ic_df = pd.DataFrame(
        np.random.randn(n_months, 1) * 0.02 + 0.04,
        index=dates,
        columns=[factor_name],
    )
    stats_df = pd.DataFrame({
        "平均值": [0.045],
        "IC_IR": [0.72],
        "t统计量": [3.5],
        "胜率": [0.65],
    }, index=[factor_name])
    return {
        "IC": ic_df,
        "统计数据": stats_df,
    }


def _make_portfolio_output(factor_name="test_factor", n_months=24):
    """构造分位数组合节点 output。"""
    dates = pd.date_range("2020-01-01", periods=n_months, freq="ME")
    groups = [f"P{i}" for i in range(5)]
    nv_df = pd.DataFrame(
        np.random.randn(n_months, 5).cumsum(axis=0) * 0.01 + 1,
        index=dates,
        columns=groups,
    )
    excess_nv_df = pd.DataFrame(
        np.random.randn(n_months, 5).cumsum(axis=0) * 0.005,
        index=dates,
        columns=groups,
    )
    stats_df = pd.DataFrame({
        "年化收益率": [0.15, 0.10, 0.08, 0.05, 0.02],
        "Sharpe比率": [1.5, 1.0, 0.8, 0.5, 0.2],
        "最大回撤率": [-0.10, -0.12, -0.15, -0.18, -0.25],
    }, index=groups)
    return {
        "净值": nv_df,
        "超额净值": excess_nv_df,
        "统计数据": stats_df,
    }


def _make_turnover_output(factor_name="test_factor", n_months=24):
    """构造换手率节点 output。"""
    dates = pd.date_range("2020-01-01", periods=n_months, freq="ME")
    turnover_df = pd.DataFrame(
        np.random.rand(n_months, 1) * 0.3 + 0.2,
        index=dates,
        columns=[factor_name],
    )
    stats_df = pd.DataFrame({
        "平均值": [0.35],
    }, index=[factor_name])
    return {
        "换手率": turnover_df,
        "统计数据": stats_df,
    }


def _make_incremental_ic_output(factor_name="test_factor", n_months=24):
    """构造增量 IC 节点 output。"""
    dates = pd.date_range("2020-01-01", periods=n_months, freq="ME")
    ic_df = pd.DataFrame(
        np.random.randn(n_months, 1) * 0.015 + 0.02,
        index=dates,
        columns=[factor_name],
    )
    corr_df = pd.DataFrame(
        np.random.rand(n_months, 1) * 0.3 + 0.2,
        index=dates,
        columns=[factor_name],
    )
    stats_df = pd.DataFrame({
        "增量IC均值": [0.018],
        "标准差": [0.015],
        "IC_IR": [1.2],
        "增量IC t统计量": [2.8],
        "最大相关性均值": [0.35],
        "有效期数": [24],
    }, index=[factor_name])
    return {
        "IC": ic_df,
        "最大相关性": corr_df,
        "统计数据": stats_df,
    }


def _make_size_stratified_output(factor_name="test_factor"):
    """构造规模分层节点 output。"""
    groups = [f"G{i}" for i in range(5)]
    data = []
    for i, g in enumerate(groups):
        data.append({
            f"{g} 年化收益": 0.15 - i * 0.03,
            f"{g} Alpha": 0.10 - i * 0.02,
            f"{g} t统计量": 4.0 - i * 0.5,
        })
    row = {}
    for d in data:
        row.update(d)
    stats_df = pd.DataFrame(row, index=[factor_name])
    return {"统计数据": stats_df}


def _make_sub_period_output(factor_name="test_factor"):
    """构造子期稳健性节点 output。"""
    periods = ["2020", "2021", "2022", "2023"]
    stats_df = pd.DataFrame({
        "period": periods,
        "IC均值": [0.04, 0.05, 0.03, 0.04],
        "ICIR": [0.7, 0.8, 0.5, 0.6],
        "t统计量": [3.0, 3.5, 2.5, 2.8],
        "胜率": [0.65, 0.70, 0.60, 0.62],
        "因子": [factor_name] * 4,
    })
    summary_df = pd.DataFrame({
        "因子": [factor_name],
        "全期IC均值": [0.04],
        "子期ICIR": [1.8],
        "正IC子期比例": [1.0],
        "子期数": [4],
    })
    return {"统计数据": stats_df, "汇总": summary_df}


def _make_full_output(factor_name="test_factor"):
    """构造完整的 BTReport output。"""
    return {
        "0-Rank IC 分析": _make_ic_output(factor_name),
        "1-IC 衰减分析": {"IC衰减": pd.DataFrame(), "统计数据": pd.DataFrame()},
        "2-分位数组合": _make_portfolio_output(factor_name),
        "3-因子换手率": _make_turnover_output(factor_name),
        "增量 IC 检验": _make_incremental_ic_output(factor_name),
        "规模分层 Alpha": _make_size_stratified_output(factor_name),
        "子期稳健性": _make_sub_period_output(factor_name),
    }


def _make_scores():
    """构造五维度评分。"""
    return FiveDimScore(
        effectiveness=0.77,
        stability=0.83,
        turnover=0.75,
        diversity=0.52,
        overfitting_risk=1.0,
    )


def _make_decision():
    """构造入库决策。"""
    return DecisionResult(
        decision="accepted",
        reason="入库通过：Alpha t=3.80 > 3.0",
        checks={
            "alpha_t": {"passed": True, "value": 3.8, "threshold": 3.0},
            "composite_score": {"passed": True, "value": 0.78, "threshold": 0.60},
            "incremental_ic_t": {"passed": True, "value": 2.8, "threshold": 2.0},
            "oos_rankic": {"passed": True, "value": 0.041, "threshold": 0.02},
        },
    )


# ============================================================
# 测试用例
# ============================================================

class TestPrepareReportData:
    """prepare_report_data 函数测试。"""

    def test_basic(self):
        """基本功能：返回 DataContext，包含评分和决策。"""
        output = _make_full_output()
        scores = _make_scores()
        decision = _make_decision()

        ctx = prepare_report_data(
            is_output=output,
            oos_output={},
            scores=scores,
            decision=decision,
            factor_name="test_factor",
        )

        # 评分数据
        scores_df = ctx.get("custom", "scores")
        assert scores_df is not None
        assert isinstance(scores_df, pd.DataFrame)
        assert "综合评分" in scores_df.columns

        # 决策数据
        decision_df = ctx.get("custom", "decision")
        assert decision_df is not None
        assert "决策" in decision_df.columns
        assert decision_df["决策"].iloc[0] == "accepted"

        # 检查详情
        checks_df = ctx.get("custom", "decision_checks")
        assert checks_df is not None
        assert "检查项" in checks_df.columns

    def test_data_sources_accessible(self):
        """各数据源可通过 DataContext 访问。"""
        output = _make_full_output()
        ctx = prepare_report_data(
            is_output=output,
            oos_output={},
            scores=_make_scores(),
            decision=_make_decision(),
            factor_name="test_factor",
        )

        # IC 数据
        ic_df = ctx.get("0-Rank IC 分析", "IC")
        assert ic_df is not None
        assert not ic_df.empty

        # 增量 IC 数据
        inc_stats = ctx.get("增量 IC 检验", "统计数据")
        assert inc_stats is not None

        # 规模分层数据
        size_stats = ctx.get("规模分层 Alpha", "统计数据")
        assert size_stats is not None

        # 子期数据
        sub_stats = ctx.get("子期稳健性", "统计数据")
        assert sub_stats is not None

    def test_oos_output_prefixed(self):
        """样本外 output 以 OOS- 前缀存储。"""
        is_output = {"0-Rank IC 分析": _make_ic_output()}
        oos_output = {"0-Rank IC 分析": _make_ic_output()}

        ctx = prepare_report_data(
            is_output=is_output,
            oos_output=oos_output,
            scores=_make_scores(),
            decision=_make_decision(),
            factor_name="test",
        )

        # 样本内数据存在
        assert ctx.get("0-Rank IC 分析", "IC") is not None
        # 样本外数据以 OOS- 前缀存在
        assert ctx.get("OOS-0-Rank IC 分析", "IC") is not None

    def test_empty_output(self):
        """空 output 不报错。"""
        ctx = prepare_report_data(
            is_output={},
            oos_output={},
            scores=_make_scores(),
            decision=_make_decision(),
            factor_name="empty",
        )
        assert ctx.get("custom", "scores") is not None


class TestGenerateEvalReport:
    """generate_eval_report 函数测试。"""

    def test_html_output(self):
        """生成 HTML 报告。"""
        output = _make_full_output()
        html = generate_eval_report(
            is_output=output,
            oos_output={},
            scores=_make_scores(),
            decision=_make_decision(),
            factor_name="test_factor",
            fmt="html",
        )
        assert isinstance(html, str)
        assert len(html) > 0
        assert "<html" in html.lower()

    def test_markdown_output(self):
        """生成 Markdown 报告。"""
        output = _make_full_output()
        md = generate_eval_report(
            is_output=output,
            oos_output={},
            scores=_make_scores(),
            decision=_make_decision(),
            factor_name="test_factor",
            fmt="markdown",
        )
        assert isinstance(md, str)
        assert len(md) > 0

    def test_report_contains_sections(self):
        """报告包含关键章节。"""
        output = _make_full_output()
        html = generate_eval_report(
            is_output=output,
            oos_output={},
            scores=_make_scores(),
            decision=_make_decision(),
            factor_name="test_factor",
        )
        # 检查关键章节标题
        assert "Rank IC" in html or "IC 分析" in html
        assert "增量 IC" in html
        assert "规模分层" in html
        assert "子期" in html
        assert "评分" in html
        assert "决策" in html

    def test_report_contains_factor_name(self):
        """报告包含因子名称。"""
        html = generate_eval_report(
            is_output=_make_full_output(),
            oos_output={},
            scores=_make_scores(),
            decision=_make_decision(),
            factor_name="my_special_factor",
        )
        assert "my_special_factor" in html

    def test_partial_output(self):
        """部分 output 时跳过缺失章节。"""
        partial_output = {
            "0-Rank IC 分析": _make_ic_output(),
        }
        html = generate_eval_report(
            is_output=partial_output,
            oos_output={},
            scores=_make_scores(),
            decision=_make_decision(),
            factor_name="partial",
        )
        assert isinstance(html, str)
        assert len(html) > 0
