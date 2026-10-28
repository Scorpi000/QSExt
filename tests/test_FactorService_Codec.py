"""远程控制值和标准数据封装的保真测试。"""

import datetime as dt
import unittest

import numpy as np
import pandas as pd

from QuantStudio.Core.QSObject import Panel
from QSExt.FactorService.codec import dumps_control, loads_control, pack, unpack


class TestCodec(unittest.TestCase):
    """验证类型、轴、缺失值和不完整传输。"""

    def test_control_types_and_reserved_keys(self):
        value = {"$type": "不是协议标记", 3: (dt.date(2026, 1, 1), np.int16(4)), "nested": [{"x": float("inf")}], "date": pd.Timestamp("2026-01-01", tz="Asia/Shanghai")}
        result = loads_control(dumps_control(value))
        self.assertEqual(value, result)
        self.assertIsInstance(result[3], tuple)
        self.assertIsInstance(result[3][1], np.int16)

    def test_frame_dtypes_and_object_missing(self):
        frame = pd.DataFrame({"a": pd.Series([1, pd.NA, 3], dtype="Int64"), "b": [1., np.nan, float("inf")], "c": pd.Series([None, pd.NA, {"$type": (2, "中文")}], dtype=object), "d": pd.date_range("2026-01-01", periods=3, tz="Asia/Shanghai")})
        frame.index.name = "序号"
        pd.testing.assert_frame_equal(unpack(pack(frame)), frame)

    def test_panel_axes_and_empty(self):
        dates = pd.DatetimeIndex(["2026-01-03", "2026-01-01"], name="日期")
        frame = pd.DataFrame([[np.nan, 2.], [np.nan, 4.]], index=dates, columns=pd.Index(["B", "A"], name="证券"))
        panel = Panel({"中文": frame}, items=pd.Index(["中文"], name="因子"), major_axis=dates, minor_axis=frame.columns)
        result = unpack(pack(panel))
        pd.testing.assert_index_equal(result.items, panel.items)
        pd.testing.assert_frame_equal(result.iloc[0], frame)
        empty = Panel(np.empty((0, 2, 2)), items=[], major_axis=dates, minor_axis=frame.columns)
        self.assertEqual(unpack(pack(empty)).shape, (0, 2, 2))

    def test_reject_unknown_type_corruption_and_limit(self):
        with self.assertRaises(TypeError):
            dumps_control(lambda: None)
        data = pack(pd.Series([1., 2.]))
        with self.assertRaises(ValueError):
            unpack(data[:-1])
        with self.assertRaises(ValueError):
            pack(pd.Series([1., 2.]), max_bytes=10)

    def test_nullable_float_mask_string_storage_and_frequency(self):
        """区分有效 NaN 与 NA，并保留字符串存储及日期频率。"""
        nullable = pd.arrays.FloatingArray(np.array([np.nan, np.nan, 1.]), np.array([False, True, False]))
        frame = pd.DataFrame({"float": nullable, "string": pd.array(["A", None, "B"], dtype="string[pyarrow]")}, index=pd.date_range("2026-01-01", periods=3))
        actual = unpack(pack(frame))
        pd.testing.assert_frame_equal(actual, frame)
        self.assertFalse(actual["float"].isna().iloc[0])
        self.assertTrue(actual["float"].isna().iloc[1])


if __name__ == "__main__":
    unittest.main()
