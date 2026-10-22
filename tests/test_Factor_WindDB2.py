# -*- coding: utf-8 -*-
"""WindDB2 迁移回归测试，使用确定性数据且不连接实际数据库。"""
import datetime as dt
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Factor.Factor import FactorContext
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QSExt.Factor.WindDB2 import WindDB2


def _mean_rating(table, date, iid, data, args):
    """按机构最新记录求平均评级。"""
    return data["本次标准评级"].astype(float).mean()


def _mean_estimate(table, date, iid, data, args):
    """取 FY0 预测值均值。"""
    return data[0]["预测每股收益(摊薄)(元)"].astype(float).mean()


def _count_estimates(table, date, iid, data, args):
    """将无预测记录映射为零。"""
    return len(data[0])


class TestWindDB2(unittest.TestCase):
    """覆盖元数据、公共读取接口和 Wind 特有的数据口径。"""

    @classmethod
    def setUpClass(cls):
        cls.fdb = WindDB2(args={"TablePrefix": "wind."}, config_file="")
        cls.ids = ["000001.SZ"]

    def test_all_configured_tables_construct(self):
        names = self.fdb._TableInfo.index[self.fdb._TableInfo.TableClass.notna()]
        for name in names:
            with self.subTest(table=name):
                table = self.fdb.getTable(name)
                self.assertEqual(table.Name, name)
                self.assertEqual(table.Args.TablePrefix, "wind.")

    def test_metadata_normalization(self):
        self.assertTrue(self.fdb._TableInfo.index.is_unique)
        self.assertTrue(self.fdb._FactorInfo.index.is_unique)
        table = self.fdb.getTable("中国A股财务指标")
        self.assertEqual(table.Args.PublDTField, "公告日期")
        self.assertEqual(table.Args.DTField, "报告期")
        table = self.fdb.getTable("中国A股指数成份股")
        self.assertEqual(table.Args.DTField, "纳入日期")
        self.assertEqual(table.Args.EndDTField, "剔除日期")
        self.assertFalse(table.Args.EndDTIncluded)
        self.assertIn("Wind代码", self.fdb.getTable("中国LOF基金基本资料").FactorNames)

    def test_table_names_filter_database_case_insensitively(self):
        fdb = WindDB2(config_file="")
        with patch.object(fdb, "getDBTable", return_value=["ASHAREEODPRICES"]):
            self.assertEqual(fdb.TableNames, ["中国A股日行情"])

    def test_argument_precedence(self):
        fdb = WindDB2(args={"FTArgs": {"MultiMapping": True, "LookBack": 3}}, config_file="")
        table = fdb.getTable("中国A股日行情", args={"LookBack": 5})
        self.assertFalse(table.Args.MultiMapping)
        self.assertEqual(table.Args.LookBack, 5)
        table = fdb.getTable("中国A股日行情", args={"多重映射": True, "MultiMapping": False})
        self.assertFalse(table.Args.MultiMapping)
        self.assertIsInstance(table.PrepareID, str)
        self.assertEqual(table.getFactor("收盘价(元)").Name, "收盘价(元)")

    def test_explicit_config_and_info_file(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "wind.json"
            config.write_text(json.dumps({"Name": "测试Wind", "TablePrefix": "config.", "DBInfoFile": self.fdb._InfoResourcePath}), encoding="utf-8")
            fdb = WindDB2(args={"TablePrefix": "explicit."}, config_file=str(config))
            self.assertEqual(fdb.Name, "测试Wind")
            self.assertEqual(fdb.getTable("中国A股日行情").Args.TablePrefix, "explicit.")

    def test_unsupported_table(self):
        for name, args in (("不存在的表", {}), ("中国A股日行情", {"TableType": "__import__('os')"})):
            with self.subTest(table=name), self.assertRaises(__QS_Error__):
                self.fdb.getTable(name, args=args)

    def test_wide_table_public_read(self):
        table = self.fdb.getTable("中国A股日行情")
        dates = [dt.datetime(2024, 1, 2), dt.datetime(2024, 1, 3)]
        with patch.object(self.fdb, "fetchall", return_value=[("20240102", self.ids[0], 10), ("20240103", self.ids[0], 12)]) as fetch:
            data = table.readData(["收盘价(元)"], self.ids, dates)
        np.testing.assert_array_equal(data.iloc[0].to_numpy(), [[10], [12]])
        self.assertIn("wind.AShareEODPrices", fetch.call_args.args[0])
        self.assertIn("'20240102'", fetch.call_args.args[0])

    def test_financial_announcement_and_ttm(self):
        dates = [dt.datetime(2024, 4, 29), dt.datetime(2024, 4, 30)]
        rows = [(self.ids[0], "20230830", "20230630", "408001000", 30),
                (self.ids[0], "20240330", "20231231", "408001000", 100),
                (self.ids[0], "20240430", "20240331", "408001000", 20),
                (self.ids[0], "20230430", "20230331", "408001000", 10)]
        table = self.fdb.getTable("中国A股利润表", args={"CalcType": "TTM"})
        factor = table._FactorInfo.index[(table._FactorInfo.FieldType == "因子") & table._FactorInfo.DataType.str.contains("NUMBER")][0]
        with patch.object(self.fdb, "fetchall", return_value=rows) as fetch:
            data = table.readData([factor], self.ids, dates)
        np.testing.assert_allclose(data.iloc[0].to_numpy(), [[100], [110]])
        self.assertIn("wind.AShareIssuingDatePredict.s_stm_actual_issuingdate", fetch.call_args.args[0])
        self.assertIn("t.AnnDate<='20240430'", fetch.call_args.args[0])

    def test_financial_single_quarter_and_lookback(self):
        dates = [dt.datetime(2024, 9, 1)]
        rows = [(self.ids[0], "20240430", "20240331", None, 20),
                (self.ids[0], "20240830", "20240630", None, 50)]
        for args, expected in (({"CalcType": "单季度"}, 30), ({"PeriodLookBack": 1}, 20)):
            with self.subTest(args=args):
                table = self.fdb.getTable("中国A股财务指标", args=args)
                factor = table._FactorInfo.index[table._FactorInfo.FieldType == "因子"][0]
                with patch.object(self.fdb, "fetchall", return_value=rows):
                    data = table.readData([factor], self.ids, dates)
                self.assertEqual(data.iloc[0, 0, 0], expected)

    def test_financial_supplements(self):
        table = self.fdb.getTable("中国A股利润表")
        factor = table._FactorInfo.index[table._FactorInfo.FieldType == "因子"][0]
        # 使用真实元数据中的快报、预告字段。
        express = self.fdb._FactorInfo.loc["中国A股业绩快报"]
        notice = self.fdb._FactorInfo.loc["中国A股业绩预告"]
        expr_name = express.index[express.FieldType == "因子"][0]
        notice_name = notice.index[notice.FieldType == "因子"][0]
        table = self.fdb.getTable("中国A股利润表", args={"ExprFactor": expr_name, "NoticeFactor": notice_name})
        with patch.object(self.fdb, "fetchall", side_effect=[[], [(self.ids[0], "20240120", "20231231", 100)], [(self.ids[0], "20240110", "20231231", 20000)]]) as fetch:
            data = table.readData([factor], self.ids, [dt.datetime(2024, 1, 15), dt.datetime(2024, 1, 25)])
        np.testing.assert_allclose(data.iloc[0].to_numpy(), [[20000], [100]])
        self.assertIn("*10000", fetch.call_args_list[-1].args[0])

    def test_financial_date_query(self):
        table = self.fdb.getTable("中国A股财务指标")
        date = dt.datetime(2024, 4, 30)
        with patch.object(self.fdb, "fetchall", return_value=[("20240430",)]) as fetch:
            self.assertEqual(table.getDateTime(iid=self.ids[0], start_dt=date, end_dt=date), [date])
        sql = fetch.call_args.args[0]
        self.assertNotIn("20240430''", sql)
        with patch.object(self.fdb, "fetchall", return_value=[(self.ids[0],)]) as fetch:
            self.assertEqual(table.getID(idt=date), self.ids)
        self.assertIn("'20240430'", fetch.call_args.args[0])

    def test_consensus_fy_switch_and_intraday(self):
        table = self.fdb.getTable("中国A股盈利预测汇总")
        factor = table._FactorInfo.index[table._FactorInfo.FieldType == "因子"][0]
        rows = [("20240401", self.ids[0], "20231231", 1), ("20240401", self.ids[0], "20241231", 2)]
        announcements = [(self.ids[0], "20240415", "20231231")]
        dates = [dt.datetime(2024, 4, 14, 15), dt.datetime(2024, 4, 15, 10), dt.datetime(2024, 4, 15, 15)]
        with patch.object(self.fdb, "fetchall", side_effect=[rows, announcements]):
            data = table.readData([factor], self.ids, dates)
        np.testing.assert_array_equal(data.iloc[0].to_numpy(), [[1], [2], [2]])
        self.assertEqual(data.major_axis.tolist(), dates)

    def test_consensus_missing_ann_and_stale_prediction(self):
        table = self.fdb.getTable("中国A股盈利预测汇总", args={"LookBack": 5})
        factor = table._FactorInfo.index[table._FactorInfo.FieldType == "因子"][0]
        with patch.object(self.fdb, "fetchall", side_effect=[[("20240101", self.ids[0], "20231231", 3)], []]):
            data = table.readData([factor], self.ids, [dt.datetime(2024, 1, 2), dt.datetime(2024, 1, 6), dt.datetime(2024, 1, 7), dt.datetime(2024, 1, 10)])
        np.testing.assert_allclose(data.iloc[0].to_numpy(), [[3], [3], [np.nan], [np.nan]], equal_nan=True)

    def test_consensus_forward_twelve_months(self):
        table = self.fdb.getTable("中国A股盈利预测汇总", args={"CalcType": "Fwd12M"})
        factor = table._FactorInfo.index[table._FactorInfo.FieldType == "因子"][0]
        rows = [("20240229", self.ids[0], "20241231", 100), ("20240229", self.ids[0], "20251231", 200)]
        with patch.object(self.fdb, "fetchall", return_value=rows) as fetch:
            data = table.readData([factor], self.ids, [dt.datetime(2024, 2, 29)])
        expected = 100 * 306 / 366 + 200 * 60 / 366
        self.assertAlmostEqual(data.iloc[0, 0, 0], expected)
        self.assertEqual(fetch.call_count, 1)

    def test_rating_deduplication_and_window(self):
        table = self.fdb.getTable("中国A股投资评级明细", args={"Operator": _mean_rating, "Period": 5})
        rows = pd.DataFrame([("20240101", self.ids[0], "甲", 1), ("20240102", self.ids[0], "甲", 3), ("20240102", self.ids[0], "乙", 5)], columns=["日期", "QS_ID", "研究机构名称", "本次标准评级"])
        dates = [dt.datetime(2024, 1, 3, 10), dt.datetime(2024, 1, 3, 15), dt.datetime(2024, 1, 8)]
        data = table.__QS_calcData__(rows, ["本次标准评级"], self.ids, dates)
        np.testing.assert_allclose(data.iloc[0].to_numpy(), [[4], [4], [np.nan]], equal_nan=True)
        self.assertEqual(table.getFactorMetaData(["本次标准评级"], key="DataType").iloc[0], "double")

    def test_estimate_fy_switch(self):
        factor = "预测每股收益(摊薄)(元)"
        table = self.fdb.getTable("中国A股盈利预测明细", args={"Operator": _mean_estimate})
        rows = pd.DataFrame([("20240401", self.ids[0], "20231231", 100, "甲", 1), ("20240401", self.ids[0], "20241231", 100, "甲", 2)], columns=["日期", "QS_ID", table._ReportDateField, table._CapitalField, "研究机构名称", factor])
        ann = pd.DataFrame([(self.ids[0], "20240415", "20231231")], columns=["QS_ID", "公告日期", "报告期"])
        data = table.__QS_calcData__({"RawData": rows, "ReportANN": ann}, [factor], self.ids, [dt.datetime(2024, 4, 14), dt.datetime(2024, 4, 15)])
        np.testing.assert_array_equal(data.iloc[0].to_numpy(), [[1], [2]])

    def test_rating_public_read(self):
        table = self.fdb.getTable("中国A股投资评级明细", args={"Operator": _mean_rating})
        # 查询顺序为日期、ID、因子值、去重字段。
        rows = [("20240102", self.ids[0], 3, "甲"), ("20240102", self.ids[0], 5, "乙")]
        with patch.object(self.fdb, "fetchall", return_value=rows) as fetch:
            data = table.readData(["本次标准评级"], self.ids, [dt.datetime(2024, 1, 3)])
        self.assertEqual(data.iloc[0, 0, 0], 4)
        self.assertIn("wind.AShareStockRating", fetch.call_args.args[0])

    def test_estimate_public_read(self):
        table = self.fdb.getTable("中国A股盈利预测明细", args={"Operator": _mean_estimate})
        factor = "预测每股收益(摊薄)(元)"
        rows = [("20240401", self.ids[0], "20241231", 100, 2, "甲")]
        with patch.object(self.fdb, "fetchall", side_effect=[rows, [(self.ids[0], "20240415", "20231231")]]):
            data = table.readData([factor], self.ids, [dt.datetime(2024, 4, 15)])
        self.assertEqual(data.iloc[0, 0, 0], 2)

    def test_empty_estimate_calls_operator(self):
        table = self.fdb.getTable("中国A股盈利预测明细", args={"Operator": _count_estimates})
        with patch.object(self.fdb, "fetchall", return_value=[]):
            data = table.readData(["预测每股收益(摊薄)(元)"], self.ids, [dt.datetime(2024, 4, 15)])
        self.assertEqual(data.iloc[0, 0, 0], 0)

    def test_empty_queries(self):
        for name in ("中国A股利润表", "中国A股盈利预测汇总", "中国A股投资评级明细", "中国A股盈利预测明细"):
            with self.subTest(table=name):
                table = self.fdb.getTable(name)
                factor = table._FactorInfo.index[table._FactorInfo.FieldType == "因子"][0]
                with patch.object(self.fdb, "fetchall") as fetch:
                    result = table.readData([factor], [], [dt.datetime(2024, 1, 1)])
                    self.assertEqual(result.shape, (1, 1, 0))
                    fetch.assert_not_called()

    def test_report_ann_cache_roundtrip(self):
        table = self.fdb.getTable("中国A股盈利预测汇总")
        factor = table._FactorInfo.index[table._FactorInfo.FieldType == "因子"][0]
        raw = pd.DataFrame([("20240401", self.ids[0], "20241231", 2), ("20240401", "000002.SZ", "20241231", 9)], columns=["日期", "QS_ID", "报告期", factor])
        ann = pd.DataFrame([(self.ids[0], "20240415", "20231231"), ("000002.SZ", "20240415", "20231231")], columns=["QS_ID", "公告日期", "报告期"])
        with tempfile.TemporaryDirectory() as directory:
            cache = FeatherFactorCache(args={"CacheDir": directory, "PIDs": ["0", "1"], "DTRuler": [dt.datetime(2024, 4, 15)]})
            cache.start()
            context = SimpleNamespace(DataCache=cache)
            table.__QS_saveRawData__({"RawData": raw, "ReportANN": ann}, "wind", [factor], {"0": self.ids, "1": ["000002.SZ"]}, context)
            restored = cache.readRawData("wind-" + factor, pids=["0"])
            self.assertEqual(restored["ReportANN"].QS_ID.tolist(), self.ids)
            with patch.object(self.fdb, "fetchall") as fetch:
                data = table.__QS_calcData__(restored, [factor], self.ids, [dt.datetime(2024, 4, 15)])
                fetch.assert_not_called()
            self.assertEqual(data.iloc[0, 0, 0], 2)

    def test_consensus_read_with_engine(self):
        """计算图经过准备、缓存和计算三个阶段，公告数据无需再次查询。"""
        table = self.fdb.getTable("中国A股盈利预测汇总")
        factor = table._FactorInfo.index[table._FactorInfo.FieldType == "因子"][0]
        dates = [dt.datetime(2024, 4, 14), dt.datetime(2024, 4, 15)]
        rows = [("20240401", self.ids[0], "20231231", 1), ("20240401", self.ids[0], "20241231", 2)]
        with tempfile.TemporaryDirectory() as directory:
            cache = FeatherFactorCache(args={"CacheDir": directory, "DTRuler": dates, "PIDs": ["0"]})
            cache.start()
            context = FactorContext(DTRuler=dates, SectionIDs=self.ids, DataCache=cache)
            with patch.object(self.fdb, "fetchall", side_effect=[rows, [(self.ids[0], "20240415", "20231231")]]) as fetch:
                with context, Engine(args={"IOConcurrentNum": 1}):
                    data = table.readData([factor], self.ids, dates)
            np.testing.assert_array_equal(data.iloc[0].to_numpy(), [[1], [2]])
            self.assertEqual(fetch.call_count, 2)

    def test_trade_calendar_query(self):
        date = dt.datetime(2024, 1, 2)
        with patch.object(self.fdb, "fetchall", return_value=[("20240102",)]) as fetch:
            self.assertEqual(self.fdb.getTradeDay(date, date, exchange="CFFEX"), [date])
        self.assertIn("wind.CFuturesCalendar", fetch.call_args.args[0])
        with self.assertRaises(__QS_Error__):
            self.fdb.getTradeDay(date, date, exchange="不存在")

    def test_security_queries_keep_wind_prefix(self):
        date = dt.datetime(2024, 1, 2)
        for method, kwargs, table_name in ((self.fdb.getStockID, {}, "AShareDescription"),
                                          (self.fdb.getMutualFundID, {}, "ChinaMutualFundDescription"),
                                          (self.fdb.getFutureID, {}, "CFuturesDescription"),
                                          (self.fdb.getFutureCode, {}, "CFuturesDescription"),
                                          (self.fdb.getOptionID, {}, "ChinaOptionDescription")):
            with self.subTest(method=method.__name__):
                with patch.object(self.fdb, "fetchall", return_value=[("TEST",)]) as fetch:
                    self.assertEqual(method(date=date, **kwargs), ["TEST"])
                self.assertIn("wind." + table_name, fetch.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
