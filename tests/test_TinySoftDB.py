# -*- coding: utf-8 -*-
"""测试 TinySoftDB 因子库"""
import datetime as dt
import unittest

from QSExt.Factor.TinySoftDB import TinySoftDB, _CalendarTable, _TradeTable, _QuoteTable, _WideTable, _FeatureTable, _MappingTable
from QuantStudio.Factor.FactorDB import FactorDB
from QuantStudio.Factor.FactorTable import FactorTable
from QuantStudio.Factor.FactorUtils import SQL_Table, SQL_WideTable, SQL_FeatureTable, SQL_MappingTable


class TestTinySoftDBStructure(unittest.TestCase):
    """TinySoftDB 类结构测试（不需要数据库连接）"""

    def test_instantiation(self):
        """测试实例化和默认参数"""
        db = TinySoftDB()
        self.assertEqual(db.Name, "TinySoftDB")
        self.assertEqual(db._QSArgs.IPAddr, "tsl.tinysoft.com.cn")
        self.assertEqual(db._QSArgs.Port, 443)

    def test_class_hierarchy(self):
        """测试类继承关系"""
        self.assertTrue(issubclass(TinySoftDB, FactorDB))

    def test_argclass_fields(self):
        """测试 __QS_ArgClass__ 字段完整性"""
        fields = TinySoftDB.__QS_ArgClass__.model_fields
        expected = ["Name", "IPAddr", "Port", "User", "Pwd", "DBInfoFile", "FTArgs"]
        for f in expected:
            self.assertIn(f, fields, f"缺少字段: {f}")

    def test_table_classes(self):
        """测试因子表类继承关系"""
        self.assertTrue(issubclass(_CalendarTable, FactorTable))
        self.assertTrue(issubclass(_TradeTable, FactorTable))
        self.assertTrue(issubclass(_QuoteTable, FactorTable))
        self.assertTrue(issubclass(_WideTable, SQL_WideTable))
        self.assertTrue(issubclass(_FeatureTable, SQL_FeatureTable))
        self.assertTrue(issubclass(_MappingTable, SQL_MappingTable))

    def test_custom_args(self):
        """测试自定义参数"""
        db = TinySoftDB(args={"IPAddr": "192.168.1.1", "Port": 8080})
        self.assertEqual(db._QSArgs.IPAddr, "192.168.1.1")
        self.assertEqual(db._QSArgs.Port, 8080)

    def test_repr_html(self):
        """测试 HTML 表示"""
        db = TinySoftDB()
        html = db._repr_html_()
        self.assertIn("TinySoftDB", html)


class TestTinySoftDBConnection(unittest.TestCase):
    """TinySoftDB 连接和基本功能测试"""

    @classmethod
    def setUpClass(cls):
        cls.FDB = TinySoftDB()
        cls.FDB.connect()

    @classmethod
    def tearDownClass(cls):
        cls.FDB.disconnect()

    # ==================== 连接测试 ====================

    def test_connect(self):
        """测试连接成功"""
        self.assertIsNotNone(self.FDB._Client)

    def test_isAvailable(self):
        """测试连接可用性检查"""
        self.assertTrue(self.FDB.isAvailable())

    def test_disconnect_reconnect(self):
        """测试断开和重连"""
        TestDB = TinySoftDB()
        TestDB.connect()
        self.assertTrue(TestDB.isAvailable())
        TestDB.disconnect()
        self.assertFalse(TestDB.isAvailable())

    def test_properties(self):
        """测试基本属性"""
        self.assertEqual(self.FDB.Name, "TinySoftDB")

    # ==================== 表信息测试 ====================

    def test_TableNames(self):
        """测试获取表名列表"""
        names = self.FDB.TableNames
        self.assertIsInstance(names, list)
        self.assertGreater(len(names), 0)
        # 验证已知表存在
        self.assertIn("交易日历", names)
        self.assertIn("分时和日线数据", names)

    # ==================== 交易日历测试 ====================

    def test_getTradeDay(self):
        """测试获取交易日"""
        dts = self.FDB.getTradeDay(start_date=dt.date(2026, 6, 1), end_date=dt.date(2026, 6, 15))
        self.assertIsInstance(dts, list)
        self.assertGreater(len(dts), 0)
        for iDT in dts:
            self.assertIsInstance(iDT, dt.datetime)

    def test_getTradeDay_date_output(self):
        """测试获取交易日（date 类型输出）"""
        dts = self.FDB.getTradeDay(start_date=dt.date(2026, 6, 1), end_date=dt.date(2026, 6, 15), output_type="date")
        self.assertIsInstance(dts, list)
        self.assertGreater(len(dts), 0)
        for iDT in dts:
            self.assertIsInstance(iDT, dt.date)

    # ==================== 交易日历因子表测试 ====================

    def test_CalendarTable(self):
        """测试交易日历因子表"""
        FT = self.FDB.getTable("交易日历")
        self.assertIsInstance(FT, _CalendarTable)
        self.assertEqual(FT.FactorNames, ["交易日"])

        # 获取交易所列表
        IDs = FT.getID()
        self.assertIn("SSE", IDs)
        self.assertIn("SZSE", IDs)

        # 获取交易日序列
        DTs = FT.getDateTime(start_dt=dt.datetime(2026, 6, 1), end_dt=dt.datetime(2026, 6, 15))
        self.assertGreater(len(DTs), 0)

    def test_CalendarTable_readData(self):
        """测试交易日历因子表读取数据"""
        FT = self.FDB.getTable("交易日历")
        DTs = [dt.datetime(2026, 6, 10), dt.datetime(2026, 6, 11), dt.datetime(2026, 6, 12)]
        Data = FT.readData(factor_names=["交易日"], ids=["SSE", "SZSE"], dts=DTs)
        self.assertEqual(Data.shape[0], 1)  # 1 个因子
        self.assertEqual(Data.minor_axis.tolist(), ["SSE", "SZSE"])

    # ==================== 分时和日线数据测试 ====================

    def test_QuoteTable_getTable(self):
        """测试获取分时和日线数据表"""
        FT = self.FDB.getTable("分时和日线数据")
        self.assertIsInstance(FT, _QuoteTable)

    def test_QuoteTable_getDateTime(self):
        """测试分时和日线数据表获取时点序列"""
        FT = self.FDB.getTable("分时和日线数据")
        DTs = FT.getDateTime(iid="000001.SZ", start_dt=dt.datetime(2026, 6, 10), end_dt=dt.datetime(2026, 6, 15))
        self.assertIsInstance(DTs, list)
        self.assertGreater(len(DTs), 0)

    def test_QuoteTable_readData_daily(self):
        """测试分时和日线数据表读取日线数据"""
        FT = self.FDB.getTable("分时和日线数据", args={"Cycle": "day"})
        IDs = ["000001.SZ"]
        DTs = [dt.datetime(2026, 6, 10), dt.datetime(2026, 6, 11), dt.datetime(2026, 6, 12)]
        FactorNames = FT.FactorNames[:2]  # 只取前两个因子
        Data = FT.readData(factor_names=FactorNames, ids=IDs, dts=DTs)
        self.assertEqual(Data.shape[0], len(FactorNames))
        self.assertEqual(Data.minor_axis.tolist(), IDs)

    # ==================== 交易明细测试 ====================

    def test_TradeTable_getTable(self):
        """测试获取交易明细表"""
        FT = self.FDB.getTable("交易明细")
        self.assertIsInstance(FT, _TradeTable)

    def test_TradeTable_getDateTime(self):
        """测试交易明细表获取时点序列"""
        FT = self.FDB.getTable("交易明细")
        DTs = FT.getDateTime(iid="000001.SZ", start_dt=dt.datetime(2026, 6, 10), end_dt=dt.datetime(2026, 6, 15))
        self.assertIsInstance(DTs, list)
        self.assertGreater(len(DTs), 0)

    def test_TradeTable_readData(self):
        """测试交易明细表读取数据"""
        FT = self.FDB.getTable("交易明细")
        IDs = ["000001.SZ"]
        DTs = [dt.datetime(2026, 6, 10), dt.datetime(2026, 6, 11), dt.datetime(2026, 6, 12)]
        FactorNames = FT.FactorNames[:2]  # 只取前两个因子
        Data = FT.readData(factor_names=FactorNames, ids=IDs, dts=DTs)
        self.assertEqual(Data.shape[0], len(FactorNames))
        self.assertEqual(Data.minor_axis.tolist(), IDs)

    # ==================== 股票基本信息（FeatureTable）测试 ====================

    def test_FeatureTable_getTable(self):
        """测试获取股票基本信息表"""
        FT = self.FDB.getTable("股票基本信息")
        self.assertIsInstance(FT, _FeatureTable)

    def test_FeatureTable_FactorNames(self):
        """测试股票基本信息表因子名列表"""
        FT = self.FDB.getTable("股票基本信息")
        FactorNames = FT.FactorNames
        self.assertIsInstance(FactorNames, list)
        self.assertGreater(len(FactorNames), 0)

    # ==================== 宽因子表测试（名称变更） ====================

    def test_WideTable_getTable(self):
        """测试获取宽因子表"""
        FT = self.FDB.getTable("名称变更")
        self.assertIsInstance(FT, _WideTable)

    def test_WideTable_FactorNames(self):
        """测试宽因子表因子名列表"""
        FT = self.FDB.getTable("名称变更")
        FactorNames = FT.FactorNames
        self.assertIsInstance(FactorNames, list)
        self.assertGreater(len(FactorNames), 0)

    # ==================== MappingTable 测试（董事、监事、高管持股变动） ====================

    def test_MappingTable_getTable(self):
        """测试获取映射因子表"""
        FT = self.FDB.getTable("董事、监事、高管持股变动")
        self.assertIsInstance(FT, _MappingTable)

    def test_MappingTable_FactorNames(self):
        """测试映射因子表因子名列表"""
        FT = self.FDB.getTable("董事、监事、高管持股变动")
        FactorNames = FT.FactorNames
        self.assertIsInstance(FactorNames, list)
        self.assertGreater(len(FactorNames), 0)

    # ==================== 指数成份股测试 ====================

    def test_getStockID(self):
        """测试获取指数成份股（可能因账号权限返回空）"""
        IDs = self.FDB.getStockID("000001.SH")  # 上证指数
        self.assertIsInstance(IDs, list)
        # 验证 ID 格式（如果有数据）
        for iID in IDs[:5]:
            self.assertIn(".", iID)

    def test_getAllAStock(self):
        """测试获取全体 A 股"""
        IDs = self.FDB.getStockID("全体A股")
        self.assertIsInstance(IDs, list)
        self.assertGreater(len(IDs), 100)  # 应该有很多股票


if __name__ == "__main__":
    unittest.main()
