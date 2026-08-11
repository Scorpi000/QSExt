# coding=utf-8
"""MarketRegime 模块端到端测试。

验证完整链路:

1. 合成行情数据 → DataFactor
2. 滚动均值信号
3. 阈值状态划分 → ThresholdClassify(PointOperator)
4. 滚动分位数划分 → QuantileClassify(TimeOperator)
5. 策略适应性分析 → StrategyRegimeAnalyzer
"""
import sys
import os

import numpy as np
import pandas as pd

from QuantStudio.Factor.Factor import DataFactor
from QuantStudio.Factor.FactorOperation import PointOperator, makeFactorOperator

from QSExt.MarketRegime.operators import ThresholdClassify, QuantileClassify
from QSExt.MarketRegime.strategy_analysis import StrategyRegimeAnalyzer


# ============================================================================
# 辅助: 滚动均值算子（简化版，避免依赖 BasicOperator 中的复杂实现）
# ============================================================================

class RollingMean(PointOperator):
    """简化的滚动均值算子，用于测试。

    对每个 ID 的时序信号做滚动均值平滑。
    """

    def __init__(self, window=20, args={}, config_file=None, **kwargs):
        self._window = window
        Args = (
            {"Name": "rolling_mean", "DataType": "double"}
            | args
            | {"Arity": 1, "DTMode": "单时点", "IDMode": "多ID"}
        )
        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(self, f, idt, iid, x, args):
        """x[0]: array(shape=(len(iid),)) — 各 ID 在 idt 时点的信号值。

        PointOperator 的 calculate 只拿到当前时点的值，无法做真正的滚动均值。
        但在测试场景中，我们可以预先计算好滚动均值后直接放入 DataFactor。
        因此此算子仅用于验证算子链路的类型正确性。
        """
        return x[0].astype(float)


# ============================================================================
# 测试类
# ============================================================================

class TestThresholdClassify:
    """ThresholdClassify 算子测试"""

    @staticmethod
    def _make_signal_factor(series: pd.Series, factor_name="signal"):
        """将 pd.Series 包装为 DataFactor。"""
        return DataFactor(series, factor_name=factor_name)

    def test_basic_classification(self):
        """基本三状态划分：熊市 / 震荡 / 牛市"""
        dates = pd.date_range('2024-01-01', periods=10, freq='D')
        # 信号: 负→零→正的序列
        signal = pd.Series(
            [-0.05, -0.03, -0.01, 0.00, 0.01, 0.03, 0.05, 0.02, -0.01, -0.04],
            index=dates,
        )

        f_signal = self._make_signal_factor(signal)
        f_regime = ThresholdClassify(
            thresholds=[-0.02, 0.02],
            labels=["熊市", "震荡", "牛市"],
        )(f_signal, factor_name="牛熊状态")

        labels = f_regime.readData(ids=["000001"], dts=dates)
        # labels 是 DataFrame, index=dates, columns=ids
        result = labels["000001"].values

        # 逐日验证
        expected = [
            "熊市",  # -0.05 <= -0.02
            "熊市",  # -0.03 <= -0.02
            "震荡",  # -0.01 in (-0.02, 0.02]
            "震荡",  # 0.00 in (-0.02, 0.02]
            "震荡",  # 0.01 in (-0.02, 0.02]
            "牛市",  # 0.03 > 0.02
            "牛市",  # 0.05 > 0.02
            "震荡",  # 0.02 in (-0.02, 0.02]
            "震荡",  # -0.01 in (-0.02, 0.02]
            "熊市",  # -0.04 <= -0.02
        ]
        assert list(result) == expected, f"预期: {expected}\n实际: {list(result)}"

    def test_binary_classification(self):
        """二分类（单一阈值）"""
        dates = pd.date_range('2024-01-01', periods=5, freq='D')
        signal = pd.Series([0.01, -0.01, 0.03, -0.03, 0.00], index=dates)

        f_signal = self._make_signal_factor(signal)
        f_regime = ThresholdClassify(
            thresholds=[0.0],
            labels=["下跌", "上涨"],
        )(f_signal, factor_name="涨跌状态")

        labels = f_regime.readData(ids=["000001"], dts=dates)
        result = labels["000001"].values

        expected = ["上涨", "下跌", "上涨", "下跌", "下跌"]  # 0.0 <= 0 → "下跌"
        assert list(result) == expected, f"预期: {expected}\n实际: {list(result)}"

    def test_multi_id(self):
        """多 ID 同时分类"""
        dates = pd.date_range('2024-01-01', periods=3, freq='D')
        # 2 IDs, 3 天
        data = pd.DataFrame({
            "A": [0.05, -0.03, 0.01],
            "B": [-0.05, 0.02, 0.03],
        }, index=dates)

        f_signal = DataFactor(data, factor_name="multi_signal")
        f_regime = ThresholdClassify(
            thresholds=[-0.02, 0.02],
            labels=["熊市", "震荡", "牛市"],
        )(f_signal, factor_name="牛熊状态")

        labels = f_regime.readData(ids=["A", "B"], dts=dates)

        assert labels.loc[dates[0], "A"] == "牛市"   # 0.05 > 0.02
        assert labels.loc[dates[0], "B"] == "熊市"   # -0.05 <= -0.02
        assert labels.loc[dates[1], "A"] == "熊市"   # -0.03 <= -0.02
        assert labels.loc[dates[1], "B"] == "震荡"   # 0.02 in (-0.02, 0.02]
        assert labels.loc[dates[2], "A"] == "震荡"   # 0.01 in (-0.02, 0.02]
        assert labels.loc[dates[2], "B"] == "牛市"   # 0.03 > 0.02

    def test_default_labels(self):
        """默认标签（三重阈值）"""
        dates = pd.date_range('2024-01-01', periods=5, freq='D')
        signal = pd.Series([-0.05, 0.01, 0.03, 0.05, -0.01], index=dates)

        f_signal = self._make_signal_factor(signal)
        f_regime = ThresholdClassify(
            thresholds=[-0.02, 0.02],
            # 不传 labels，使用默认 ['低位', '中位', '高位']
        )(f_signal, factor_name="状态")

        labels = f_regime.readData(ids=["000001"], dts=dates)
        result = labels["000001"].values

        assert result[0] == "低位"   # -0.05
        assert result[1] == "中位"   # 0.01
        assert result[2] == "高位"   # 0.03
        assert result[3] == "高位"   # 0.05
        assert result[4] == "中位"   # -0.01


class TestQuantileClassify:
    """QuantileClassify 算子测试"""

    def test_basic_quantile(self):
        """基本滚动分位数分类：低波 / 中波 / 高波"""
        np.random.seed(42)
        n_total = 400  # 需要足够长以确保 LookBack=252 有充分历史
        dates = pd.date_range('2023-01-01', periods=n_total, freq='D')

        # 初始 300 天低波（建立历史分布），最后 100 天高波
        vol = np.ones(n_total) * 0.15
        vol[-100:] = 0.30   # 尾部高波
        noise = np.random.randn(n_total) * 0.02
        signal = pd.Series(vol + noise, index=dates)

        f_signal = DataFactor(signal, factor_name="波动率")
        f_regime = QuantileClassify(
            lookback=252, low_pct=0.2, high_pct=0.8,
            labels=["低波", "中波", "高波"],
        )(f_signal, factor_name="波动率状态")

        # 读取尾部高波区域，需传入完整 dt_ruler 使 LookBack 有足够历史
        test_dates = dates[-50:]
        labels = f_regime.readData(ids=["000001"], dts=test_dates, dt_ruler=dates)
        result = labels["000001"].values

        # 尾部高波值（0.30），在历史分布（多为 0.15）中应多为 "高波"
        high_count = (result == "高波").sum()
        low_count = (result == "低波").sum()
        assert high_count > low_count, (
            f"高波区域应更多被划为高波，高波:{high_count} 低波:{low_count}"
        )

    def test_middle_range_labels(self):
        """波动率恒定区间：当前值与历史分布一致时应多为 '中波'"""
        np.random.seed(123)
        n_total = 350
        dates = pd.date_range('2023-01-01', periods=n_total, freq='D')

        vol = np.ones(n_total) * 0.25
        noise = np.random.randn(n_total) * 0.02
        signal = pd.Series(vol + noise, index=dates)

        f_signal = DataFactor(signal, factor_name="波动率")
        f_regime = QuantileClassify(
            lookback=252, low_pct=0.2, high_pct=0.8,
            labels=["低波", "中波", "高波"],
        )(f_signal, factor_name="波动率状态")

        test_dates = dates[-50:]
        labels = f_regime.readData(ids=["000001"], dts=test_dates, dt_ruler=dates)
        result = labels["000001"].values

        # 中段区域的波动值 ~0.25，在历史 (也 ~0.25) 中应多为中波
        mid_count = (result == "中波").sum()
        assert mid_count > 0, "应有中波状态出现"


class TestStrategyRegimeAnalyzer:
    """StrategyRegimeAnalyzer 端到端测试"""

    def test_regime_performance(self):
        """状态条件表现：牛市收益应高于熊市"""
        np.random.seed(2024)
        dates = pd.date_range('2020-01-01', '2022-12-31', freq='B')
        n = len(dates)

        # 构造策略收益：牛市中高收益，熊市中低收益，震荡在中间
        regime = np.full(n, "震荡", dtype=object)

        returns = np.random.randn(n) * 0.01  # 基准噪声

        bull_mask = dates.year == 2020
        bear_mask = dates.year == 2022
        # 2021 保持 "震荡"

        regime[bull_mask] = "牛市"
        returns[bull_mask] = np.random.randn(bull_mask.sum()) * 0.008 + 0.0015

        regime[bear_mask] = "熊市"
        returns[bear_mask] = np.random.randn(bear_mask.sum()) * 0.015 - 0.0015

        regime_idx = pd.Series(regime, index=dates)
        strategy_returns = pd.Series(returns, index=dates)

        analyzer = StrategyRegimeAnalyzer(strategy_returns, regime_idx)
        perf = analyzer.compute_regime_performance()

        assert "牛市" in perf.index
        assert "熊市" in perf.index
        assert "震荡" in perf.index

        bull_ret = perf.loc["牛市", "年化收益"]
        bear_ret = perf.loc["熊市", "年化收益"]
        assert bull_ret > bear_ret, (
            f"牛市年化收益({bull_ret:.4f})应 > 熊市年化收益({bear_ret:.4f})"
        )

    def test_adaptation_heatmap(self):
        """适应性热力图：输出矩阵形状正确"""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', '2022-12-31', freq='B')

        regime = pd.Series(
            np.random.choice(["牛市", "震荡", "熊市"], size=len(dates)),
            index=dates,
        )
        returns = pd.Series(np.random.randn(len(dates)) * 0.01, index=dates)

        analyzer = StrategyRegimeAnalyzer(returns, regime)
        heatmap = analyzer.compute_adaptation_heatmap(freq='Q')

        assert len(heatmap.index) == 3  # 三个状态
        assert len(heatmap.columns) > 0  # 至少一个季度

    def test_mrp(self):
        """MRP 计算：返回完整字段"""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', '2022-12-31', freq='B')

        regime = pd.Series(
            np.random.choice(["牛市", "震荡", "熊市"], size=len(dates)),
            index=dates,
        )
        returns = pd.Series(np.random.randn(len(dates)) * 0.01, index=dates)

        analyzer = StrategyRegimeAnalyzer(returns, regime)
        mrp = analyzer.compute_mrp()

        assert "mrp" in mrp
        assert "worst_regime" in mrp
        assert "worst_sharpe" in mrp
        assert "regime_sharpes" in mrp
        assert "mrp_vs_total" in mrp

        # 验证最差夏普就是各状态夏普中的最小值
        sharpes = [v for v in mrp["regime_sharpes"].values() if not np.isnan(v)]
        if sharpes:
            assert abs(mrp["worst_sharpe"] - min(sharpes)) < 1e-10


class TestEndToEndPipeline:
    """完整链路端到端测试"""

    def test_full_pipeline(self):
        """ThresholdClassify → StrategyRegimeAnalyzer 完整链路"""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', '2022-12-31', freq='B')
        n = len(dates)

        # ---- Step 1: 合成市场数据 ----
        # 构造有牛熊特征的市场收益序列
        base_returns = np.random.randn(n) * 0.01
        # 2020 牛市: 正漂移
        base_returns[dates.year == 2020] += 0.002
        # 2022 熊市: 负漂移
        base_returns[dates.year == 2022] -= 0.002

        market_returns = pd.Series(base_returns, index=dates)
        strategy_returns = market_returns + np.random.randn(n) * 0.005  # 策略 = 市场 + 噪音

        # ---- Step 2: DataFactor ----
        f_market = DataFactor(market_returns, factor_name="market_return")

        # ---- Step 3: 计算滚动均值信号 ----
        # 直接使用 DataFactor 包装预计算的滚动均值
        rolling_mean = market_returns.rolling(60, min_periods=1).mean()
        f_signal = DataFactor(rolling_mean, factor_name="signal")

        # ---- Step 4: ThresholdClassify ----
        f_regime = ThresholdClassify(
            thresholds=[-0.001, 0.001],
            labels=["熊市", "震荡", "牛市"],
        )(f_signal, factor_name="牛熊状态")

        # ---- Step 5: readData 获取标签 ----
        labels = f_regime.readData(ids=["000001"], dts=dates)
        regime_series = labels["000001"]

        # ---- Step 6: 验证标签含义 ----
        bull_count = (regime_series == "牛市").sum()
        bear_count = (regime_series == "熊市").sum()
        assert bull_count > 0, "应有牛市标签"
        assert bear_count > 0, "应有熊市标签"

        # 2020 年（正漂移）牛市应多于熊市
        mask_2020 = dates.year == 2020
        assert (regime_series[mask_2020] == "牛市").sum() > (
            regime_series[mask_2020] == "熊市"
        ).sum(), "2020年牛市应多于熊市"

        # 2022 年（负漂移）熊市应多于牛市
        mask_2022 = dates.year == 2022
        assert (regime_series[mask_2022] == "熊市").sum() > (
            regime_series[mask_2022] == "牛市"
        ).sum(), "2022年熊市应多于牛市"

        # ---- Step 7: StrategyRegimeAnalyzer ----
        analyzer = StrategyRegimeAnalyzer(strategy_returns, regime_series)

        # 状态表现
        perf = analyzer.compute_regime_performance()
        print("\n===== 状态条件表现 =====")
        print(perf.to_string())

        # 热力图
        heatmap = analyzer.compute_adaptation_heatmap(freq='Y')
        print("\n===== 适应性热力图 (年度) =====")
        print(heatmap.to_string())

        # MRP
        mrp = analyzer.compute_mrp()
        print("\n===== MRP (Minimum Regime Performance) =====")
        print(f"  最差状态: {mrp['worst_regime']}")
        print(f"  最差夏普: {mrp['worst_sharpe']:.4f}")
        print(f"  整体夏普: {mrp.get('mrp_vs_total', 'N/A')}")
        print(f"  各状态夏普: {mrp['regime_sharpes']}")

        print("\n✓ 完整链路验证通过")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
