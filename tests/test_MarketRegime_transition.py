# coding=utf-8
"""MarketRegime 第二期测试：状态转换检测 + 转换冲击分析。

覆盖:
    - CUSUMDetector: 标签序列转换点检测
    - KSTestDetector: 离散标签 / 连续信号的分布变化检测
    - StrategyRegimeAnalyzer.transition_impact_analysis()
"""
import sys

import numpy as np
import pandas as pd

from QSExt.MarketRegime.transition import CUSUMDetector, KSTestDetector
from QSExt.MarketRegime.strategy_analysis import StrategyRegimeAnalyzer


# ============================================================================
# CUSUMDetector
# ============================================================================

class TestCUSUMDetector:
    """CUSUMDetector 测试"""

    def test_basic_detection(self):
        """基本转换点检测：标签发生变化的时点"""
        dates = pd.date_range('2020-01-01', periods=10, freq='D')
        labels = pd.Series(
            ["牛市", "牛市", "牛市", "熊市", "熊市",
             "熊市", "牛市", "牛市", "牛市", "牛市"],
            index=dates,
        )

        detector = CUSUMDetector(threshold=1.5)
        result = detector.detect(labels)

        assert len(result) == 2
        # 第一次转换: 牛市 → 熊市 (D4)
        assert result.iloc[0]["from_regime"] == "牛市"
        assert result.iloc[0]["to_regime"] == "熊市"
        assert result.iloc[0]["date"] == dates[3]
        # 第二次转换: 熊市 → 牛市 (D7)
        assert result.iloc[1]["from_regime"] == "熊市"
        assert result.iloc[1]["to_regime"] == "牛市"
        assert result.iloc[1]["date"] == dates[6]

    def test_no_transition(self):
        """恒定标签：无转换点"""
        dates = pd.date_range('2020-01-01', periods=5, freq='D')
        labels = pd.Series(["牛市"] * 5, index=dates)

        detector = CUSUMDetector()
        result = detector.detect(labels)

        assert len(result) == 0

    def test_single_transition(self):
        """单一转换"""
        dates = pd.date_range('2020-01-01', periods=5, freq='D')
        labels = pd.Series(["牛市", "牛市", "熊市", "熊市", "熊市"],
                           index=dates)

        result = CUSUMDetector().detect(labels)

        assert len(result) == 1
        assert result.iloc[0]["from_regime"] == "牛市"
        assert result.iloc[0]["to_regime"] == "熊市"

    def test_empty_series(self):
        """空序列"""
        labels = pd.Series(dtype=object)
        result = CUSUMDetector().detect(labels)
        assert len(result) == 0

    def test_nan_handling(self):
        """NaN 值应被跳过"""
        dates = pd.date_range('2020-01-01', periods=5, freq='D')
        labels = pd.Series(["牛市", None, "熊市", "熊市", None],
                           index=dates)

        result = CUSUMDetector().detect(labels)
        # NaN 被 dropna 去掉后：牛市(0) → 熊市(2)
        assert len(result) == 1
        assert result.iloc[0]["from_regime"] == "牛市"
        assert result.iloc[0]["to_regime"] == "熊市"


# ============================================================================
# KSTestDetector
# ============================================================================

class TestKSTestDetector:
    """KSTestDetector 测试"""

    def test_discrete_labels(self):
        """离散标签输入：退化为标签变化检测"""
        dates = pd.date_range('2020-01-01', periods=8, freq='D')
        labels = pd.Series(
            ["牛市", "牛市", "牛市", "熊市", "熊市", "熊市", "牛市", "牛市"],
            index=dates,
        )

        detector = KSTestDetector(window=3)
        result = detector.detect(labels)

        assert len(result) == 2
        assert result.iloc[0]["from_regime"] == "牛市"
        assert result.iloc[0]["to_regime"] == "熊市"
        assert result.iloc[1]["from_regime"] == "熊市"
        assert result.iloc[1]["to_regime"] == "牛市"

    def test_continuous_signal(self):
        """连续信号输入：检测分布变化"""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=200, freq='D')
        # 前 100 天 N(0, 1)，后 100 天 N(2, 1) — 均值偏移
        values = np.concatenate([
            np.random.randn(100),
            np.random.randn(100) + 2,
        ])
        signal = pd.Series(values, index=dates)

        detector = KSTestDetector(p_threshold=0.001, window=40)
        result = detector.detect(signal)

        # 应在 ~D100 附近检测到转换
        assert len(result) > 0
        # 转换点应在 80~120 之间（窗口效应导致边界模糊）
        transition_dates = result["date"].values
        mid_point = dates[100]
        nearby = [abs((d - mid_point).days) < 30 for d in transition_dates]
        assert any(nearby), f"转换点应发生在均值偏移点附近，实际: {transition_dates}"

    def test_no_change(self):
        """恒定信号：无分布变化"""
        dates = pd.date_range('2020-01-01', periods=150, freq='D')
        signal = pd.Series(np.ones(150) * 0.5, index=dates)

        result = KSTestDetector(window=40).detect(signal)
        assert len(result) == 0

    def test_too_short_series(self):
        """序列长度不足 2*window：返回空"""
        dates = pd.date_range('2020-01-01', periods=10, freq='D')
        signal = pd.Series(np.random.randn(10), index=dates)

        result = KSTestDetector(window=60).detect(signal)
        assert len(result) == 0


# ============================================================================
# StrategyRegimeAnalyzer.transition_impact_analysis
# ============================================================================

class TestTransitionImpactAnalysis:
    """transition_impact_analysis 测试"""

    @staticmethod
    def _make_data():
        """构造测试数据。"""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', '2022-12-31', freq='B')
        n = len(dates)

        # 构造策略收益
        returns = pd.Series(np.random.randn(n) * 0.01, index=dates)

        # 构造标签：2020 牛市，2021 震荡，2022 熊市
        regime = pd.Series(index=dates, dtype=object)
        regime[dates.year == 2020] = "牛市"
        regime[dates.year == 2021] = "震荡"
        regime[dates.year == 2022] = "熊市"

        return returns, regime

    def test_default_detector(self):
        """默认检测器（相邻标签变化）"""
        returns, regime = self._make_data()
        analyzer = StrategyRegimeAnalyzer(returns, regime)

        result = analyzer.transition_impact_analysis()

        # 验证返回键
        assert "transitions" in result
        assert "window_returns" in result
        assert "direction_impact" in result
        assert "transition_loss_ratio" in result

        # 应有 2 次转换: 牛市→震荡, 震荡→熊市
        transitions = result["transitions"]
        assert len(transitions) == 2
        assert transitions.iloc[0]["from_regime"] == "牛市"
        assert transitions.iloc[0]["to_regime"] == "震荡"
        assert transitions.iloc[1]["from_regime"] == "震荡"
        assert transitions.iloc[1]["to_regime"] == "熊市"

        # 窗口收益 DataFrame 应有 3 行（±5, ±10, ±20）
        window_df = result["window_returns"]
        assert len(window_df) == 3
        assert "转换前收益" in window_df.columns
        assert "转换后收益" in window_df.columns

        # 方向敏感性应有 2 行
        direction_df = result["direction_impact"]
        assert len(direction_df) == 2

        # 亏损比例应在 [0, 1] 之间
        lr = result["transition_loss_ratio"]
        assert 0 <= lr <= 1

    def test_with_cusum_detector(self):
        """使用 CUSUMDetector"""
        returns, regime = self._make_data()
        analyzer = StrategyRegimeAnalyzer(returns, regime)

        result = analyzer.transition_impact_analysis(
            detector=CUSUMDetector(threshold=1.5))

        assert len(result["transitions"]) == 2

    def test_custom_windows(self):
        """自定义窗口列表"""
        returns, regime = self._make_data()
        analyzer = StrategyRegimeAnalyzer(returns, regime)

        result = analyzer.transition_impact_analysis(windows=[3, 7])

        window_df = result["window_returns"]
        assert len(window_df) == 2
        assert "±3日" in window_df.index
        assert "±7日" in window_df.index

    def test_no_transitions(self):
        """恒定标签：无转换"""
        dates = pd.date_range('2020-01-01', periods=100, freq='B')
        returns = pd.Series(np.random.randn(100) * 0.01, index=dates)
        regime = pd.Series(["牛市"] * 100, index=dates)

        analyzer = StrategyRegimeAnalyzer(returns, regime)
        result = analyzer.transition_impact_analysis()

        assert len(result["transitions"]) == 0
        assert result["window_returns"].empty
        assert result["direction_impact"].empty


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
