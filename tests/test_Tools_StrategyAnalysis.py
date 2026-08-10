import numpy as np
import pandas as pd

from QSExt.Tools.StrategyAnalysis import identify_drawdowns


class TestIdentifyDrawdowns:
    """identify_drawdowns 函数测试"""

    def test_basic_drawdowns(self):
        """基本回撤识别：两个回撤事件，均有完整恢复"""
        dates = pd.date_range('2020-01-01', periods=10, freq='D')
        nav = pd.Series(
            [1.00, 0.95, 0.90, 0.96, 1.01, 0.88, 0.92, 0.87, 0.98, 1.02],
            index=dates,
        )

        result = identify_drawdowns(nav, threshold=0.05)

        assert len(result) == 2

        # 回撤 1: D1(1.00) -> D3(0.90) -> D5(1.01)
        d1 = result[0]
        assert d1['start'] == pd.Timestamp('2020-01-01')
        assert d1['end'] == pd.Timestamp('2020-01-05')
        assert d1['trough'] == pd.Timestamp('2020-01-03')
        assert abs(d1['depth'] - 0.10) < 0.001
        assert d1['duration'] == 4
        assert d1['recovery_days'] == 2

        # 回撤 2: D5(1.01) -> D8(0.87) -> D10(1.02)
        d2 = result[1]
        assert d2['start'] == pd.Timestamp('2020-01-05')
        assert d2['end'] == pd.Timestamp('2020-01-10')
        assert d2['trough'] == pd.Timestamp('2020-01-08')
        assert abs(d2['depth'] - abs(0.87 / 1.01 - 1)) < 0.001
        assert d2['duration'] == 5
        assert d2['recovery_days'] == 2

    def test_threshold_filter(self):
        """阈值过滤：提高阈值后不返回任何回撤"""
        dates = pd.date_range('2020-01-01', periods=10, freq='D')
        nav = pd.Series(
            [1.00, 0.95, 0.90, 0.96, 1.01, 0.88, 0.92, 0.87, 0.98, 1.02],
            index=dates,
        )

        result = identify_drawdowns(nav, threshold=0.15)

        assert len(result) == 0

    def test_no_drawdown(self):
        """单调上涨净值：无回撤"""
        dates = pd.date_range('2020-01-01', periods=5, freq='D')
        nav = pd.Series([1.00, 1.02, 1.05, 1.08, 1.10], index=dates)

        result = identify_drawdowns(nav, threshold=0.05)

        assert len(result) == 0

    def test_ongoing_drawdown(self):
        """未恢复回撤：序列结束时仍处于回撤中"""
        dates = pd.date_range('2020-01-01', periods=5, freq='D')
        nav = pd.Series([1.00, 0.92, 0.88, 0.90, 0.85], index=dates)

        result = identify_drawdowns(nav, threshold=0.05)

        assert len(result) == 1
        d = result[0]
        assert d['start'] == pd.Timestamp('2020-01-01')
        assert d['end'] is None
        assert d['trough'] == pd.Timestamp('2020-01-05')
        assert abs(d['depth'] - 0.15) < 0.001
        assert d['duration'] == 4
        assert d['recovery_days'] is None

    def test_multiple_peaks_no_recovery(self):
        """多次新低但未恢复：只算一个回撤事件"""
        dates = pd.date_range('2020-01-01', periods=6, freq='D')
        # 1.00(peak) -> 0.95 -> 0.90 -> 0.85 -> 0.80 -> 0.82（仍未恢复）
        nav = pd.Series([1.00, 0.95, 0.90, 0.85, 0.80, 0.82], index=dates)

        result = identify_drawdowns(nav, threshold=0.05)

        assert len(result) == 1
        d = result[0]
        assert d['start'] == pd.Timestamp('2020-01-01')
        assert d['trough'] == pd.Timestamp('2020-01-05')
        assert d['end'] is None

    def test_sub_threshold_recovery_then_deeper(self):
        """未超阈值的反弹后继续下跌：仍属同一回撤"""
        dates = pd.date_range('2020-01-01', periods=5, freq='D')
        # 1.00 -> 0.97（未超阈值）-> 0.98 -> 0.85（加深）
        nav = pd.Series([1.00, 0.97, 0.98, 0.85, 1.01], index=dates)

        result = identify_drawdowns(nav, threshold=0.05)

        assert len(result) == 1
        d = result[0]
        assert d['start'] == pd.Timestamp('2020-01-01')
        assert d['trough'] == pd.Timestamp('2020-01-04')
        assert d['end'] == pd.Timestamp('2020-01-05')

    def test_empty_series(self):
        """空序列"""
        result = identify_drawdowns(pd.Series(dtype=float))
        assert result == []

    def test_single_point(self):
        """单点序列"""
        result = identify_drawdowns(pd.Series([1.0]))
        assert result == []

    def test_list_input(self):
        """纯 list 输入：返回索引位置，duration 为位置差"""
        nav_list = [1.00, 0.92, 0.88, 0.95, 1.01]

        result = identify_drawdowns(nav_list, threshold=0.05)

        assert len(result) == 1
        d = result[0]
        assert d['start'] == 0
        assert d['end'] == 4
        assert d['trough'] == 2
        assert abs(d['depth'] - 0.12) < 0.001
        assert d['duration'] == 4
        assert d['recovery_days'] == 2

    def test_ndarray_input(self):
        """numpy array 输入：返回索引位置"""
        nav_arr = np.array([1.00, 0.90, 0.95, 1.02, 1.05])

        result = identify_drawdowns(nav_arr, threshold=0.05)

        assert len(result) == 1
        d = result[0]
        assert d['start'] == 0
        assert d['end'] == 3
        assert d['trough'] == 1
        assert abs(d['depth'] - 0.10) < 0.001
        assert d['duration'] == 3
        assert d['recovery_days'] == 2

    def test_array_ongoing_drawdown(self):
        """array 未恢复回撤：end 和 recovery_days 为 None"""
        nav_list = [1.00, 0.93, 0.88, 0.85]

        result = identify_drawdowns(nav_list, threshold=0.05)

        assert len(result) == 1
        d = result[0]
        assert d['start'] == 0
        assert d['end'] is None
        assert d['trough'] == 3
        assert abs(d['depth'] - 0.15) < 0.001
        assert d['duration'] == 3
        assert d['recovery_days'] is None

    def test_custom_index(self):
        """自定义非日期索引：返回索引标签和标签差"""
        nav = pd.Series(
            [1.00, 0.92, 0.95, 1.01],
            index=[100, 200, 300, 400],
        )

        result = identify_drawdowns(nav, threshold=0.05)

        assert len(result) == 1
        d = result[0]
        assert d['start'] == 100
        assert d['end'] == 400
        assert d['trough'] == 200
        assert abs(d['depth'] - 0.08) < 0.001
        assert d['duration'] == 300
        assert d['recovery_days'] == 200
