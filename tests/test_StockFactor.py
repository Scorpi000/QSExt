"""股票因子统计的只读结果兼容性与样本过滤回归。"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from QuantStudio.BackTest.SectionFactor.Correlation import CalcFactorTurnover
from QSExt.BackTest.StockFactor import StockCalcStability


class StockFactorTests(unittest.TestCase):
    def test_stability_filters_read_only_parent_result_without_modifying_it(self):
        dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(5)]
        data = np.array([[1., 2., 3.], [2., 3., 4.], [1., np.nan, 5.], [6., 7., 8.], [4., 5., 9.]])
        parent_result = np.array([[.2], [.4], [.6], [.8]])
        parent_result.setflags(write=False)
        factor = SimpleNamespace(Args=SimpleNamespace(CalcDTRuler=dates))
        operator = StockCalcStability(descriptor_ids=["A", "B", "C"], lookback=1)
        with patch.object(CalcFactorTurnover, "calculate", return_value=parent_result):
            result = operator.calculate(factor, dates, ["alpha"], [data],
                {"period_lookback": 1, "min_samples": 3})
        np.testing.assert_allclose(result, [[.2], [np.nan], [np.nan], [.8]], equal_nan=True)
        np.testing.assert_array_equal(parent_result, [[.2], [.4], [.6], [.8]])
        self.assertFalse(np.shares_memory(result, parent_result))


if __name__ == "__main__":
    unittest.main()
