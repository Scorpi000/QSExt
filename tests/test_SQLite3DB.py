# -*- coding: utf-8 -*-
"""测试 SQLite3DB 因子库"""
import os
import datetime as dt
import tempfile
import unittest

import numpy as np
import pandas as pd

from QSExt.Factor.SQLite3DB import SQLite3DB
from QuantStudio.Core.QSObject import Panel


def compareDataFrame(df1, df2, dtype="double"):
    """比较两个 DataFrame，返回逐元素误差"""
    m1, m2 = pd.isnull(df1), pd.isnull(df2)
    if dtype == "double":
        Err = (df1 - df2).abs()
        Err[pd.isnull(Err)] = 0
        return np.maximum(Err, (m1 ^ m2).astype("float"))
    else:
        Err = (df1 != df2)
        Err[m1 | m2] = False
        return np.maximum(Err.astype("float"), (m1 ^ m2).astype("float"))


class TestSQLite3DB(unittest.TestCase):
    """SQLite3DB 单元测试"""

    @classmethod
    def setUpClass(cls):
        cls.TempDir = tempfile.TemporaryDirectory()
        cls.DBPath = os.path.join(cls.TempDir.name, "test.db")
        cls.FDB = SQLite3DB(args={
            "DBFile": cls.DBPath,
            "InnerPrefix": "",
            "TablePrefix": "",
        }).connect()

    @classmethod
    def tearDownClass(cls):
        cls.FDB.disconnect()
        cls.TempDir.cleanup()

    # ==================== 数据读写测试 ====================

    def test_DataIO(self):
        """测试 double 类型因子的读写"""
        TestTable = "TestTable_DataIO"
        TestFactor1 = "TestFactor1_DataIO"
        TestFactor2 = "TestFactor2_DataIO"
        DTs = [dt.datetime(2018, 1, 1) + dt.timedelta(i) for i in range(4)]
        IDs = ["00000%d.SZ" % i for i in range(3)]

        Data1 = pd.DataFrame(np.zeros((4, 3)), index=DTs, columns=IDs, dtype=float)
        Data2 = pd.DataFrame(np.zeros((4, 3)), index=DTs, columns=IDs, dtype=float)
        TargetData = Panel({TestFactor1: Data1, TestFactor2: Data2})

        # 创建因子表并写入部分数据
        self.FDB.writeData(TargetData.iloc[:, 0:2, 0:1], TestTable)
        FT = self.FDB.getTable(TestTable)
        self.assertListEqual(sorted([TestFactor1, TestFactor2]), sorted([f for f in FT.FactorNames if f not in ("datetime", "code")]))

        TestData = FT.readData(factor_names=[TestFactor1, TestFactor2], ids=IDs[0:1], dts=DTs[0:2])
        Err = compareDataFrame(TestData.iloc[0], TargetData.iloc[0, 0:2, 0:1], dtype="double")
        self.assertAlmostEqual(Err.max().max(), 0)
        Err = compareDataFrame(TestData.iloc[1], TargetData.iloc[1, 0:2, 0:1], dtype="double")
        self.assertAlmostEqual(Err.max().max(), 0)

        # 以 update 方式写入更多数据（DTs[1:3], IDs[0:2]）
        NewData1 = pd.DataFrame(np.ones((2, 2)), index=DTs[1:3], columns=IDs[0:2], dtype=float)
        NewData2 = pd.DataFrame(np.ones((2, 2)), index=DTs[1:3], columns=IDs[0:2], dtype=float)
        self.FDB.writeData(Panel({TestFactor1: NewData1, TestFactor2: NewData2}), TestTable, if_exists="update")
        TestData = FT.readData(factor_names=[TestFactor1, TestFactor2], ids=IDs[0:2], dts=DTs[0:3])
        # (DTs[0], IDs[1]) 不在更新范围内，应为 NaN
        self.assertTrue(pd.isnull(TestData.iloc[0].iloc[0, 1]))
        # (DTs[1], IDs[0]) 在更新范围内，应为 1.0
        self.assertAlmostEqual(TestData.iloc[0].iloc[1, 0], 1.0)
        # (DTs[0], IDs[0]) 未在更新范围内，保持原值 0.0
        self.assertAlmostEqual(TestData.iloc[0].iloc[0, 0], 0.0)

        # 以 append 方式写入数据（不覆盖已有非空值）
        AppendData = pd.DataFrame(np.full((2, 3), 2.0), index=DTs[2:4], columns=IDs[0:3], dtype=float)
        self.FDB.writeData(Panel({TestFactor1: AppendData, TestFactor2: AppendData}), TestTable, if_exists="append")
        TestData = FT.readData(factor_names=[TestFactor1, TestFactor2], ids=IDs[0:3], dts=DTs[0:4])
        # DTs[1:3] 已有值 1.0，append 不应覆盖
        self.assertAlmostEqual(TestData.iloc[0].iloc[1, 0], 1.0)

    def test_StringDataIO(self):
        """测试 string 类型因子的读写"""
        TestTable = "TestTable_StringDataIO"
        TestFactor = "TestFactor_StringDataIO"
        DTs = [dt.datetime(2019, 1, 1), dt.datetime(2019, 1, 2), dt.datetime(2019, 1, 3)]
        IDs = ["000001.SZ", "600000.SH"]

        TargetData = pd.DataFrame([["A", "B"], ["C", None], [None, "D"]], index=DTs, columns=IDs, dtype=object)
        self.FDB.writeData(Panel({TestFactor: TargetData}), TestTable, data_type={TestFactor: "string"})
        FT = self.FDB.getTable(TestTable)
        TestData = FT.readData(factor_names=[TestFactor], ids=IDs, dts=DTs).iloc[0]
        self.assertEqual(TestData.iloc[0, 0], "A")
        self.assertTrue(pd.isnull(TestData.iloc[1, 1]))

    # Note: SQLite3DB 不支持 object 类型因子的原生存储，该类型需通过 JSON 序列化处理

    def test_MultipleWrite(self):
        """测试多次写入不重复创建表"""
        TestTable = "TestTable_MultipleWrite"
        TestFactor = "TestFactor_MultipleWrite"
        DTs = [dt.datetime(2019, 1, 1)]
        IDs = ["000001.SZ"]

        Data = pd.DataFrame(np.ones((1, 1)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: Data}), TestTable)
        self.assertIn(TestTable, self.FDB.TableNames)
        # 再次写入
        NewData = pd.DataFrame([[2.0]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: NewData}), TestTable, if_exists="update")
        FT = self.FDB.getTable(TestTable)
        TestData = FT.readData(factor_names=[TestFactor], ids=IDs, dts=DTs).iloc[0]
        self.assertAlmostEqual(TestData.iloc[0, 0], 2.0)

    def test_WriteWithNewFactor(self):
        """测试写入时自动添加新因子列"""
        TestTable = "TestTable_WriteNewFactor"
        TestFactor1 = "TestFactor1_WriteNewFactor"
        TestFactor2 = "TestFactor2_WriteNewFactor"
        DTs = [dt.datetime(2019, 1, 1)]
        IDs = ["000001.SZ"]

        Data1 = pd.DataFrame([[1.0]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor1: Data1}), TestTable)
        self.assertIn(TestFactor1, self.FDB.getTable(TestTable).FactorNames)

        # 写入新因子
        Data2 = pd.DataFrame([[2.0]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor1: Data1, TestFactor2: Data2}), TestTable)
        self.assertIn(TestFactor2, self.FDB.getTable(TestTable).FactorNames)

    # ==================== ID / 时点读取测试 ====================

    def test_getID(self):
        """测试 ID 读取"""
        TestTable = "TestTable_getID"
        TestFactor = "TestFactor_getID"
        DTs = [dt.datetime(2019, 1, 1), dt.datetime(2019, 1, 2), dt.datetime(2019, 1, 3)]
        IDs = ["000001.SZ", "600000.SH"]
        Data = pd.DataFrame(np.ones((3, 2)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: Data}), TestTable)
        FT = self.FDB.getTable(TestTable)
        TestIDs = FT.getID()
        self.assertListEqual(IDs, TestIDs)

    def test_getID_with_idt(self):
        """测试带时点过滤的 ID 读取"""
        TestTable = "TestTable_getID_idt"
        TestFactor = "TestFactor_getID_idt"
        DTs = [dt.datetime(2019, 1, 1), dt.datetime(2019, 1, 2)]
        IDs = ["000001.SZ", "600000.SH"]
        Data = pd.DataFrame([[1.0, np.nan], [np.nan, 2.0]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: Data}), TestTable)
        FT = self.FDB.getTable(TestTable)
        IDsWithData = FT.getID(idt=DTs[0])
        self.assertListEqual(IDsWithData, ["000001.SZ"])

    def test_getDateTime(self):
        """测试时点读取"""
        TestTable = "TestTable_getDateTime"
        TestFactor = "TestFactor_getDateTime"
        DTs = [dt.datetime(2019, 1, 1), dt.datetime(2019, 1, 2), dt.datetime(2019, 1, 3)]
        IDs = ["000001.SZ", "600000.SH"]
        Data = pd.DataFrame(np.ones((3, 2)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: Data}), TestTable)
        FT = self.FDB.getTable(TestTable)
        TestDTs = FT.getDateTime()
        self.assertListEqual(DTs, TestDTs)

    def test_getDateTime_with_range(self):
        """测试带时间范围过滤的时点读取"""
        TestTable = "TestTable_getDateTime_range"
        TestFactor = "TestFactor_getDateTime_range"
        DTs = [dt.datetime(2019, 1, 1), dt.datetime(2019, 1, 2), dt.datetime(2019, 1, 3)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame(np.ones((3, 1)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: Data}), TestTable)
        FT = self.FDB.getTable(TestTable)
        TestDTs = FT.getDateTime(start_dt=DTs[0], end_dt=DTs[1])
        self.assertListEqual(TestDTs, DTs[0:2])

    # ==================== 因子操作测试 ====================

    def test_renameFactor(self):
        """测试因子重命名"""
        TestTable = "TestTable_renameFactor"
        TestFactor = "TestFactor_renameFactor"
        DTs = [dt.datetime(2019, 1, 1), dt.datetime(2019, 1, 2)]
        IDs = ["000001.SZ", "600000.SH"]
        Data = pd.DataFrame(np.ones((2, 2)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: Data}), TestTable)
        FT = self.FDB.getTable(TestTable)
        self.assertTrue(TestFactor in FT.FactorNames)
        NewFactorName = "New_" + TestFactor
        self.FDB.renameFactor(TestTable, TestFactor, NewFactorName)
        FT = self.FDB.getTable(TestTable)
        self.assertFalse(TestFactor in FT.FactorNames)
        self.assertTrue(NewFactorName in FT.FactorNames)

    def test_deleteFactor(self):
        """测试因子删除"""
        TestTable = "TestTable_deleteFactor"
        TestFactor1 = "TestFactor1_deleteFactor"
        TestFactor2 = "TestFactor2_deleteFactor"
        DTs = [dt.datetime(2019, 1, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame(np.ones((1, 1)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor1: Data, TestFactor2: Data}), TestTable)
        FT = self.FDB.getTable(TestTable)
        self.assertTrue(TestFactor1 in FT.FactorNames)
        self.FDB.deleteFactor(TestTable, [TestFactor1])
        FT = self.FDB.getTable(TestTable)
        self.assertFalse(TestFactor1 in FT.FactorNames)
        self.assertTrue(TestFactor2 in FT.FactorNames)
        # 删除所有自定义因子后表仍存在（保留 datetime, code 字段）
        self.FDB.deleteFactor(TestTable, [TestFactor2])
        self.assertTrue(TestTable in self.FDB.TableNames)

    # ==================== 表操作测试 ====================

    def test_renameTable(self):
        """测试表重命名"""
        TestTable = "TestTable_renameTable"
        TestFactor = "TestFactor_renameTable"
        DTs = [dt.datetime(2019, 1, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame(np.ones((1, 1)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: Data}), TestTable)
        self.assertTrue(TestTable in self.FDB.TableNames)
        NewTableName = "New_" + TestTable
        self.FDB.renameTable(TestTable, NewTableName)
        self.assertFalse(TestTable in self.FDB.TableNames)
        self.assertTrue(NewTableName in self.FDB.TableNames)

    def test_deleteTable(self):
        """测试表删除"""
        TestTable = "TestTable_deleteTable"
        TestFactor = "TestFactor_deleteTable"
        DTs = [dt.datetime(2019, 1, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame(np.ones((1, 1)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: Data}), TestTable)
        self.assertTrue(TestTable in self.FDB.TableNames)
        self.FDB.deleteTable(table_name=TestTable)
        self.assertFalse(TestTable in self.FDB.TableNames)

    # ==================== 创建和添加因子 ====================

    def test_createTable(self):
        """测试手动创建表"""
        TestTable = "TestTable_createTable"
        self.FDB.createTable(TestTable, {
            "Factor0": "real",
            "Factor1": "text",
        })
        self.assertIn(TestTable, self.FDB.TableNames)
        FT = self.FDB.getTable(TestTable)
        self.assertIn("Factor0", FT.FactorNames)
        self.assertIn("Factor1", FT.FactorNames)

    def test_addFactor(self):
        """测试向已有表添加因子"""
        TestTable = "TestTable_addFactor"
        TestFactor1 = "TestFactor1_addFactor"
        DTs = [dt.datetime(2019, 1, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame([[1.0]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor1: Data}), TestTable)

        NewFactor = "TestFactor2_addFactor"
        self.FDB.addFactor(TestTable, {NewFactor: "text"})
        self.assertIn(NewFactor, self.FDB.getTable(TestTable).FactorNames)

    # ==================== deleteData 测试 ====================

    def test_deleteData(self):
        """测试删除数据"""
        TestTable = "TestTable_deleteData"
        TestFactor = "TestFactor_deleteData"
        DTs = [dt.datetime(2019, 1, 1), dt.datetime(2019, 1, 2), dt.datetime(2019, 1, 3)]
        IDs = ["000001.SZ", "600000.SH"]
        Data = pd.DataFrame(np.ones((3, 2)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: Data}), TestTable)

        # 删除指定 ID 的数据
        self.FDB.deleteData(TestTable, ids=["000001.SZ"])
        FT = self.FDB.getTable(TestTable)
        TestIDs = FT.getID()
        self.assertListEqual(TestIDs, ["600000.SH"])

    # ==================== update_notnull 测试 ====================

    def test_UpdateNotNull(self):
        """测试 update_notnull 写入方式：新数据非空时覆盖旧值，新数据空时保留旧值"""
        TestTable = "TestTable_UpdateNotNull"
        TestFactor = "TestFactor_UpdateNotNull"
        DTs = [dt.datetime(2019, 1, 1), dt.datetime(2019, 1, 2)]
        IDs = ["000001.SZ", "600000.SH"]

        Data = pd.DataFrame([[1.0, np.nan], [np.nan, 2.0]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: Data}), TestTable)

        # 用 update_notnull 写入，新数据非空则覆盖，新数据为空则保留旧值
        NewData = pd.DataFrame([[np.nan, 10.0], [10.0, np.nan]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({TestFactor: NewData}), TestTable, if_exists="update_notnull")

        FT = self.FDB.getTable(TestTable)
        TestData = FT.readData(factor_names=[TestFactor], ids=IDs, dts=DTs).iloc[0]
        # 原非空值，新数据为空 → 保留
        self.assertAlmostEqual(TestData.iloc[0, 0], 1.0)
        self.assertAlmostEqual(TestData.iloc[1, 1], 2.0)
        # 原空值，新数据非空 → 填充
        self.assertAlmostEqual(TestData.iloc[0, 1], 10.0)
        self.assertAlmostEqual(TestData.iloc[1, 0], 10.0)

    # ==================== 连接与断开 ====================

    def test_disconnect(self):
        """测试断开连接"""
        TestDB = SQLite3DB(args={
            "DBFile": ":memory:",
            "InnerPrefix": "",
            "TablePrefix": "",
        }).connect()
        self.assertIsNotNone(TestDB.Connection)
        TestDB.disconnect()
        self.assertIsNone(TestDB.Connection)

    def test_InnerPrefix(self):
        """测试内部前缀过滤"""
        DBPath = os.path.join(self.TempDir.name, "test_prefix.db")
        DB = SQLite3DB(args={
            "DBFile": DBPath,
            "InnerPrefix": "qs_",
            "TablePrefix": "",
        }).connect()
        TestTable = "TestTable_Prefix"
        TestFactor = "TestFactor_Prefix"
        DTs = [dt.datetime(2019, 1, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame([[1.0]], index=DTs, columns=IDs)
        DB.writeData(Panel({TestFactor: Data}), TestTable)
        # InnerPrefix 为 qs_，实际表名应为 qs_TestTable_Prefix
        self.assertIn(TestTable, DB.TableNames)
        DB.disconnect()


if __name__ == "__main__":
    unittest.main()
