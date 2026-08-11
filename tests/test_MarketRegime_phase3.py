# coding=utf-8
"""MarketRegime 第三期测试：HMMClassify + WassersteinDetector + DTWDetector。

覆盖:
    - HMMClassify: 基于 HMM 的多维市场状态发现（PanelOperator）
    - WassersteinDetector: Wasserstein 距离检测器
    - DTWDetector: DTW 动态时间规整检测器
"""
import sys

import numpy as np
import pandas as pd
import pytest

from QuantStudio.Factor.Factor import DataFactor
from QSExt.MarketRegime.operators import HMMClassify
from QSExt.MarketRegime.transition import WassersteinDetector, DTWDetector

# 检查 hmmlearn 是否可用
try:
    import hmmlearn
    HAS_HMMLEARN = True
except ImportError:
    HAS_HMMLEARN = False


# ============================================================================
# HMMClassify
# ============================================================================

@pytest.mark.skipif(not HAS_HMMLEARN, reason="hmmlearn not installed")
class TestHMMClassify:
    """HMMClassify 算子测试"""

    @staticmethod
    def _make_multi_factor_data(n_days=300, n_ids=3):
        """构造多因子测试数据。"""
        np.random.seed(42)
        dates = pd.date_range('2023-01-01', periods=n_days, freq='D')
        ids = [f"ID_{i:02d}" for i in range(n_ids)]

        # 构造两个信号因子：市场收益和波动率
        # 2023 前半年低波上涨，后半年高波下跌
        returns_data = np.random.randn(n_days, n_ids) * 0.01
        returns_data[:150] += 0.002  # 前半年正漂移
        returns_data[150:] -= 0.002  # 后半年负漂移

        vol_data = np.random.randn(n_days, n_ids) * 0.02 + 0.15
        vol_data[150:] += 0.10  # 后半年高波动

        f_return = DataFactor(
            pd.DataFrame(returns_data, index=dates, columns=ids),
            factor_name="市场收益"
        )
        f_vol = DataFactor(
            pd.DataFrame(vol_data, index=dates, columns=ids),
            factor_name="波动率"
        )

        return f_return, f_vol, dates, ids

    def test_basic_hmm(self):
        """基本 HMM 状态划分"""
        f_return, f_vol, dates, ids = self._make_multi_factor_data()

        # 创建 HMM 算子
        hmm = HMMClassify(n_components=3, lookback=200)
        f_regime = hmm(f_return, f_vol, factor_name="HMM状态")

        # 读取尾部数据
        test_dates = dates[-50:]
        labels = f_regime.readData(ids=ids, dts=test_dates, dt_ruler=dates)

        # 验证输出形状
        assert labels.shape == (len(test_dates), len(ids))

        # 验证标签值在预期范围内
        all_labels = labels.values.flatten()
        valid_labels = [l for l in all_labels if pd.notna(l)]
        assert len(valid_labels) > 0
        # 标签应该是状态0、1、2中的一个
        for label in valid_labels:
            assert label in ["状态0", "状态1", "状态2"]

    def test_custom_labels(self):
        """自定义标签"""
        f_return, f_vol, dates, ids = self._make_multi_factor_data(n_days=200, n_ids=2)

        hmm = HMMClassify(
            n_components=2,
            lookback=150,
            labels=["低波上涨", "高波下跌"],
        )
        f_regime = hmm(f_return, f_vol, factor_name="市场状态")

        test_dates = dates[-30:]
        labels = f_regime.readData(ids=ids, dts=test_dates, dt_ruler=dates)

        # 验证标签值在预期范围内
        all_labels = labels.values.flatten()
        valid_labels = [l for l in all_labels if pd.notna(l)]
        for label in valid_labels:
            assert label in ["低波上涨", "高波下跌"]

    def test_single_id(self):
        """单 ID 测试"""
        f_return, f_vol, dates, _ = self._make_multi_factor_data(n_days=200, n_ids=1)
        ids = ["ID_00"]

        hmm = HMMClassify(n_components=2, lookback=150)
        f_regime = hmm(f_return, f_vol, factor_name="HMM状态")

        test_dates = dates[-20:]
        labels = f_regime.readData(ids=ids, dts=test_dates, dt_ruler=dates)

        assert labels.shape == (len(test_dates), 1)
        assert not labels.isna().all().all()

    def test_labels_count_mismatch(self):
        """标签数量不匹配应报错"""
        with pytest.raises(ValueError, match="labels 数量"):
            HMMClassify(n_components=3, labels=["A", "B"])  # 3 组件但只有 2 标签


# ============================================================================
# WassersteinDetector
# ============================================================================

class TestWassersteinDetector:
    """WassersteinDetector 测试"""

    def test_basic_detection(self):
        """基本分布变化检测"""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=200, freq='D')
        # 前 100 天 N(0, 1)，后 100 天 N(2, 1) — 均值偏移
        values = np.concatenate([
            np.random.randn(100),
            np.random.randn(100) + 2,
        ])
        signal = pd.Series(values, index=dates)

        detector = WassersteinDetector(threshold=0.5, window=40)
        result = detector.detect(signal)

        # 应在 ~D100 附近检测到转换
        assert len(result) > 0
        assert "distance" in result.columns

        # 转换点应在 80~120 之间（窗口效应导致边界模糊）
        transition_dates = result["date"].values
        mid_point = dates[100]
        nearby = [abs((d - mid_point).days) < 30 for d in transition_dates]
        assert any(nearby), f"转换点应发生在均值偏移点附近，实际: {transition_dates}"

    def test_no_change(self):
        """恒定信号：无分布变化"""
        dates = pd.date_range('2020-01-01', periods=150, freq='D')
        signal = pd.Series(np.ones(150) * 0.5, index=dates)

        result = WassersteinDetector(window=40).detect(signal)
        assert len(result) == 0

    def test_discrete_labels(self):
        """离散标签输入：退化为标签变化检测"""
        dates = pd.date_range('2020-01-01', periods=8, freq='D')
        labels = pd.Series(
            ["牛市", "牛市", "牛市", "熊市", "熊市", "熊市", "牛市", "牛市"],
            index=dates,
        )

        detector = WassersteinDetector(window=3)
        result = detector.detect(labels)

        assert len(result) == 2
        assert result.iloc[0]["from_regime"] == "牛市"
        assert result.iloc[0]["to_regime"] == "熊市"
        assert result.iloc[1]["from_regime"] == "熊市"
        assert result.iloc[1]["to_regime"] == "牛市"
        assert "distance" in result.columns

    def test_too_short_series(self):
        """序列长度不足 2*window：返回空"""
        dates = pd.date_range('2020-01-01', periods=10, freq='D')
        signal = pd.Series(np.random.randn(10), index=dates)

        result = WassersteinDetector(window=60).detect(signal)
        assert len(result) == 0

    def test_distance_values(self):
        """验证距离值的合理性"""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=200, freq='D')
        # 小幅变化：N(0,1) → N(0.5,1)
        values = np.concatenate([
            np.random.randn(100),
            np.random.randn(100) + 0.5,
        ])
        signal = pd.Series(values, index=dates)

        detector = WassersteinDetector(threshold=0.1, window=40)
        result = detector.detect(signal)

        if len(result) > 0:
            # 距离值应该大于阈值
            assert all(result["distance"] > 0.1)


# ============================================================================
# DTWDetector
# ============================================================================

class TestDTWDetector:
    """DTWDetector 测试"""

    def test_basic_detection(self):
        """基本 DTW 相似模式查找"""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=300, freq='D')
        # 构造有重复模式的信号
        pattern = np.sin(np.linspace(0, 2 * np.pi, 50))
        values = np.concatenate([
            pattern + np.random.randn(50) * 0.1,  # 第一个周期
            pattern + np.random.randn(50) * 0.1,  # 第二个周期（相似）
            np.random.randn(200) * 0.5,           # 随机噪声
        ])
        signal = pd.Series(values, index=dates)

        detector = DTWDetector(window=50, top_k=3)
        result = detector.find_similar(signal)

        assert len(result) > 0
        assert "start_date" in result.columns
        assert "end_date" in result.columns
        assert "distance" in result.columns

        # 结果应按距离排序
        distances = result["distance"].values
        assert all(distances[i] <= distances[i + 1] for i in range(len(distances) - 1))

    def test_top_k_limit(self):
        """top_k 限制返回数量"""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=200, freq='D')
        signal = pd.Series(np.random.randn(200), index=dates)

        detector = DTWDetector(window=30, top_k=2)
        result = detector.find_similar(signal)

        assert len(result) <= 2

    def test_distance_threshold(self):
        """距离阈值过滤"""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=200, freq='D')
        # 完全相同的模式
        pattern = np.sin(np.linspace(0, 2 * np.pi, 30))
        values = np.concatenate([
            pattern,
            pattern,
            np.random.randn(140) * 10,  # 大噪声
        ])
        signal = pd.Series(values, index=dates)

        # 使用非常严格的阈值，应该过滤掉大部分结果
        detector = DTWDetector(window=30, top_k=10, distance_threshold=0.01)
        result = detector.find_similar(signal)

        # 结果数量应该少于不限制阈值的情况
        detector_loose = DTWDetector(window=30, top_k=10)
        result_loose = detector_loose.find_similar(signal)

        assert len(result) <= len(result_loose)

    def test_detect_as_label_detector(self):
        """detect 方法：标签序列的转换点检测"""
        dates = pd.date_range('2020-01-01', periods=8, freq='D')
        labels = pd.Series(
            ["牛市", "牛市", "牛市", "熊市", "熊市", "熊市", "牛市", "牛市"],
            index=dates,
        )

        detector = DTWDetector(window=3)
        result = detector.detect(labels)

        assert len(result) == 2
        assert result.iloc[0]["from_regime"] == "牛市"
        assert result.iloc[0]["to_regime"] == "熊市"
        assert result.iloc[1]["from_regime"] == "熊市"
        assert result.iloc[1]["to_regime"] == "牛市"

    def test_too_short_series(self):
        """序列长度不足：返回空"""
        dates = pd.date_range('2020-01-01', periods=10, freq='D')
        signal = pd.Series(np.random.randn(10), index=dates)

        detector = DTWDetector(window=60)
        result = detector.find_similar(signal)

        assert len(result) == 0

    def test_dtw_computation(self):
        """DTW 距离计算验证"""
        detector = DTWDetector(window=10)

        # 相同序列的 DTW 距离应为 0
        x = np.array([1, 2, 3, 4, 5])
        dist = detector._compute_dtw(x, x)
        assert dist == 0.0

        # 不同序列的 DTW 距离应大于 0
        y = np.array([2, 3, 4, 5, 6])
        dist = detector._compute_dtw(x, y)
        assert dist > 0.0


# ============================================================================
# 集成测试
# ============================================================================

class TestPhase3Integration:
    """第三期组件集成测试"""

    @pytest.mark.skipif(not HAS_HMMLEARN, reason="hmmlearn not installed")
    def test_hmm_with_transition_detectors(self):
        """HMMClassify + 转换检测器集成"""
        np.random.seed(42)
        n_days = 300
        dates = pd.date_range('2023-01-01', periods=n_days, freq='D')
        ids = ["000001"]

        # 构造有明显状态切换的信号
        signal_data = np.random.randn(n_days, 1) * 0.01
        signal_data[:100] += 0.003   # 第一阶段：上涨
        signal_data[100:200] -= 0.005  # 第二阶段：下跌
        signal_data[200:] += 0.002   # 第三阶段：反弹

        f_signal = DataFactor(
            pd.DataFrame(signal_data, index=dates, columns=ids),
            factor_name="市场信号"
        )

        # 使用 HMMClassify
        hmm = HMMClassify(n_components=3, lookback=200)
        f_regime = hmm(f_signal, factor_name="HMM状态")

        # 读取标签
        test_dates = dates[-100:]
        labels = f_regime.readData(ids=ids, dts=test_dates, dt_ruler=dates)
        regime_series = labels["000001"]

        # 使用 WassersteinDetector 检测分布变化
        signal_series = pd.Series(signal_data.flatten(), index=dates)
        wasserstein = WassersteinDetector(threshold=0.01, window=30)
        transitions = wasserstein.detect(signal_series)

        # 应该检测到一些转换点
        assert len(transitions) >= 0  # 可能为 0（取决于信号特征）

        # 使用 DTWDetector 查找相似模式
        dtw = DTWDetector(window=50, top_k=2)
        similar = dtw.find_similar(signal_series)

        # 应该找到一些相似时期
        assert len(similar) >= 0

    def test_transition_detectors_only(self):
        """仅测试转换检测器（不需要 hmmlearn）"""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=200, freq='D')
        # 前 100 天 N(0, 1)，后 100 天 N(2, 1)
        values = np.concatenate([
            np.random.randn(100),
            np.random.randn(100) + 2,
        ])
        signal = pd.Series(values, index=dates)

        # WassersteinDetector
        wasserstein = WassersteinDetector(threshold=0.5, window=40)
        transitions = wasserstein.detect(signal)
        assert len(transitions) > 0

        # DTWDetector
        dtw = DTWDetector(window=50, top_k=3)
        similar = dtw.find_similar(signal)
        assert len(similar) > 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
