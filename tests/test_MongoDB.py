# -*- coding: utf-8 -*-
"""测试 MongoDB 因子库"""
import datetime as dt
import unittest

import numpy as np
import pandas as pd

from QSExt.Factor.MongoDB import MongoDB
from QuantStudio.Core.QSObject import Panel


class TestMongoDB(unittest.TestCase):
    """MongoDB 单元测试 —— 测试数据保留在 MongoDB 中，测试结束后不删除"""

    @classmethod
    def setUpClass(cls):
        cls.FDB = MongoDB().connect()

    # ==================== 连接测试 ====================

    def test_connect(self):
        """测试连接成功"""
        self.assertIsNotNone(self.FDB.Connection)

    def test_properties(self):
        """测试基本属性"""
        self.assertEqual(self.FDB.Name, "MongoDB")
        self.assertEqual(self.FDB._QSArgs.DBType, "Mongo")
        self.assertEqual(self.FDB._QSArgs.InnerPrefix, "qs_")
        self.assertEqual(self.FDB._QSArgs.DBName, "QSData")
        self.assertEqual(self.FDB._QSArgs.IPAddr, "localhost")
        self.assertEqual(self.FDB._QSArgs.Port, 27017)

    def test_TableNames(self):
        """测试获取表名列表"""
        names = self.FDB.TableNames
        self.assertIsInstance(names, list)

    # ==================== 表创建测试 ====================

    def test_createTable(self):
        """测试手动创建表"""
        TestTable = "UnitTest_Mongo_CreateTable"
        self.FDB.createTable(TestTable, {"cf1": "double", "cf2": "string"})
        self.assertIn(TestTable, self.FDB.TableNames)
        FT = self.FDB.getTable(TestTable)
        self.assertIn("cf1", FT.FactorNames)
        self.assertIn("cf2", FT.FactorNames)

    # ==================== 因子操作测试 ====================

    def test_addFactor(self):
        """测试向已有表添加因子"""
        TestTable = "UnitTest_Mongo_AddFactor"
        NewFactor = "af2"
        # 清理上次运行残留的数据
        if TestTable in self.FDB.TableNames:
            if NewFactor in self.FDB._TableFactorDict.get(TestTable, []):
                self.FDB.deleteFactor(TestTable, [NewFactor])

        Factor = "af1"
        DTs = [dt.datetime(2020, 12, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame([[1.0]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: Data}), TestTable)

        self.FDB.addFactor(TestTable, {NewFactor: "double"})
        self.assertIn(NewFactor, self.FDB.getTable(TestTable).FactorNames)

    def test_renameFactor(self):
        """测试因子重命名"""
        TestTable = "UnitTest_Mongo_RenameFactor"
        Factor = "rf_old"
        NewName = "rf_new"
        # 清理上次运行残留：不管哪个存在，都恢复到 rf_old
        if TestTable in self.FDB.TableNames:
            FT = self.FDB.getTable(TestTable)
            if NewName in FT.FactorNames:
                if Factor in FT.FactorNames:
                    self.FDB.deleteFactor(TestTable, [NewName])
                else:
                    self.FDB.renameFactor(TestTable, NewName, Factor)

        DTs = [dt.datetime(2020, 8, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame(np.ones((1, 1)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: Data}), TestTable)

        self.FDB.renameFactor(TestTable, Factor, NewName)
        FT = self.FDB.getTable(TestTable)
        self.assertNotIn(Factor, FT.FactorNames)
        self.assertIn(NewName, FT.FactorNames)

    def test_deleteFactor(self):
        """测试因子删除"""
        TestTable = "UnitTest_Mongo_DeleteFactor"
        Factor1, Factor2 = "df1", "df2"
        DTs = [dt.datetime(2020, 9, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame(np.ones((1, 1)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor1: Data, Factor2: Data}), TestTable)

        self.FDB.deleteFactor(TestTable, [Factor1])
        FT = self.FDB.getTable(TestTable)
        self.assertNotIn(Factor1, FT.FactorNames)
        self.assertIn(Factor2, FT.FactorNames)

    # ==================== 表操作测试 ====================

    def test_renameTable(self):
        """测试表重命名"""
        TestTable = "UnitTest_Mongo_RenameTable"
        NewTable = "UnitTest_Mongo_RenameTable_New"
        # 清理上次运行残留
        if NewTable in self.FDB.TableNames:
            if TestTable in self.FDB.TableNames:
                self.FDB.deleteTable(NewTable)
            else:
                self.FDB.renameTable(NewTable, TestTable)

        Factor = "rt"
        DTs = [dt.datetime(2020, 10, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame(np.ones((1, 1)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: Data}), TestTable)

        self.FDB.renameTable(TestTable, NewTable)
        self.assertNotIn(TestTable, self.FDB.TableNames)
        self.assertIn(NewTable, self.FDB.TableNames)

    def test_deleteTable(self):
        """测试表删除"""
        TestTable = "UnitTest_Mongo_DeleteTable"
        Factor = "dt"
        DTs = [dt.datetime(2020, 11, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame(np.ones((1, 1)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: Data}), TestTable)
        self.assertIn(TestTable, self.FDB.TableNames)

        self.FDB.deleteTable(TestTable)
        self.assertNotIn(TestTable, self.FDB.TableNames)

    # ==================== 数据读写测试 ====================

    def test_double_data_io(self):
        """测试 double 类型因子的读写"""
        TestTable = "UnitTest_Mongo_DoubleIO"
        Factor1 = "factor1"
        Factor2 = "factor2"
        DTs = [dt.datetime(2020, 1, 1) + dt.timedelta(i) for i in range(4)]
        IDs = ["00000%d.SZ" % i for i in range(3)]

        Data1 = pd.DataFrame(np.arange(12).reshape(4, 3).astype(float), index=DTs, columns=IDs)
        Data2 = pd.DataFrame(np.arange(12, 24).reshape(4, 3).astype(float), index=DTs, columns=IDs)
        Target = Panel({Factor1: Data1, Factor2: Data2})

        # 写入
        self.FDB.writeData(Target.iloc[:, 0:2, 0:1], TestTable)
        self.assertIn(TestTable, self.FDB.TableNames)

        FT = self.FDB.getTable(TestTable)
        self.assertIn(Factor1, FT.FactorNames)
        self.assertIn(Factor2, FT.FactorNames)

        # 读取并验证
        TestData = FT.readData(factor_names=[Factor1, Factor2], ids=IDs[0:1], dts=DTs[0:2])
        self.assertAlmostEqual(TestData.iloc[0].iloc[0, 0], 0.0)
        self.assertAlmostEqual(TestData.iloc[1].iloc[0, 0], 12.0)

        # update 方式追加
        NewData1 = pd.DataFrame(np.ones((2, 2)), index=DTs[1:3], columns=IDs[0:2], dtype=float)
        NewData2 = pd.DataFrame(np.ones((2, 2)) * 2, index=DTs[1:3], columns=IDs[0:2], dtype=float)
        self.FDB.writeData(Panel({Factor1: NewData1, Factor2: NewData2}), TestTable, if_exists="update")
        TestData = FT.readData(factor_names=[Factor1], ids=IDs[0:2], dts=DTs[0:3])
        # DTs[0], IDs[1] 不在更新范围，应为 NaN
        self.assertTrue(pd.isnull(TestData.iloc[0].iloc[0, 1]))
        # DTs[1], IDs[0] 被更新为 1.0
        self.assertAlmostEqual(TestData.iloc[0].iloc[1, 0], 1.0)

    def test_string_data_io(self):
        """测试 string 类型因子的读写"""
        TestTable = "UnitTest_Mongo_StringIO"
        Factor = "str_factor"
        DTs = [dt.datetime(2020, 2, 1), dt.datetime(2020, 2, 2)]
        IDs = ["000001.SZ", "600000.SH"]

        Data = pd.DataFrame([["hello", "world"], [None, "test"]], index=DTs, columns=IDs, dtype=object)
        self.FDB.writeData(Panel({Factor: Data}), TestTable, data_type={Factor: "string"})

        FT = self.FDB.getTable(TestTable)
        TestData = FT.readData(factor_names=[Factor], ids=IDs, dts=DTs).iloc[0]
        self.assertEqual(TestData.iloc[0, 0], "hello")
        self.assertEqual(TestData.iloc[0, 1], "world")
        self.assertTrue(pd.isnull(TestData.iloc[1, 0]))

    def test_multiple_write_no_duplicate(self):
        """测试多次写入不重复创建表"""
        TestTable = "UnitTest_Mongo_MultiWrite"
        Factor = "mf"
        DTs = [dt.datetime(2020, 3, 1)]
        IDs = ["000001.SZ"]

        self.FDB.writeData(Panel({Factor: pd.DataFrame([[1.0]], index=DTs, columns=IDs)}), TestTable)
        self.assertIn(TestTable, self.FDB.TableNames)

        self.FDB.writeData(Panel({Factor: pd.DataFrame([[2.0]], index=DTs, columns=IDs)}), TestTable, if_exists="update")
        FT = self.FDB.getTable(TestTable)
        TestData = FT.readData(factor_names=[Factor], ids=IDs, dts=DTs).iloc[0]
        self.assertAlmostEqual(TestData.iloc[0, 0], 2.0)

    def test_write_new_factor_auto_add(self):
        """测试写入时自动添加新因子列"""
        TestTable = "UnitTest_Mongo_NewFactor"
        Factor1, Factor2 = "nf1", "nf2"
        DTs = [dt.datetime(2020, 4, 1)]
        IDs = ["000001.SZ"]

        self.FDB.writeData(Panel({Factor1: pd.DataFrame([[1.0]], index=DTs, columns=IDs)}), TestTable)
        self.assertIn(Factor1, self.FDB.getTable(TestTable).FactorNames)

        self.FDB.writeData(Panel({Factor1: pd.DataFrame([[1.0]], index=DTs, columns=IDs),
                                   Factor2: pd.DataFrame([[2.0]], index=DTs, columns=IDs)}), TestTable)
        self.assertIn(Factor2, self.FDB.getTable(TestTable).FactorNames)

    # ==================== ID / 时点读取测试 ====================

    def test_getID(self):
        """测试 ID 读取"""
        TestTable = "UnitTest_Mongo_GetID"
        Factor = "gid"
        DTs = [dt.datetime(2020, 5, 1), dt.datetime(2020, 5, 2)]
        IDs = ["000001.SZ", "600000.SH"]
        Data = pd.DataFrame(np.ones((2, 2)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: Data}), TestTable)

        FT = self.FDB.getTable(TestTable)
        TestIDs = FT.getID()
        self.assertListEqual(sorted(TestIDs), sorted(IDs))

    def test_getDateTime(self):
        """测试时点读取"""
        TestTable = "UnitTest_Mongo_GetDT"
        Factor = "gdt"
        DTs = [dt.datetime(2020, 6, 1), dt.datetime(2020, 6, 2), dt.datetime(2020, 6, 3)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame(np.ones((3, 1)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: Data}), TestTable)

        FT = self.FDB.getTable(TestTable)
        TestDTs = FT.getDateTime()
        self.assertListEqual(TestDTs, DTs)

    def test_getDateTime_with_range(self):
        """测试带范围过滤的时点读取"""
        TestTable = "UnitTest_Mongo_GetDT_Range"
        Factor = "gdtr"
        DTs = [dt.datetime(2020, 7, 1), dt.datetime(2020, 7, 2), dt.datetime(2020, 7, 3)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame(np.ones((3, 1)), index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: Data}), TestTable)

        FT = self.FDB.getTable(TestTable)
        TestDTs = FT.getDateTime(start_dt=DTs[0], end_dt=DTs[1])
        self.assertListEqual(TestDTs, DTs[0:2])

    # ==================== deleteData 测试 ====================

    def test_deleteData_by_ids(self):
        """测试按 ID 删除数据"""
        TestTable = "UnitTest_Mongo_DeleteData_ID"
        Factor = "dd_id"
        DTs = [dt.datetime(2021, 1, 1), dt.datetime(2021, 1, 2)]
        IDs = ["000001.SZ", "600000.SH"]
        if TestTable not in self.FDB.TableNames:
            Data = pd.DataFrame(np.ones((2, 2)), index=DTs, columns=IDs)
            self.FDB.writeData(Panel({Factor: Data}), TestTable)

        self.FDB.deleteData(TestTable, ids=["000001.SZ"])
        FT = self.FDB.getTable(TestTable)
        TestIDs = FT.getID()
        self.assertNotIn("000001.SZ", TestIDs)

    def test_deleteData_by_dts(self):
        """测试按时点删除数据"""
        TestTable = "UnitTest_Mongo_DeleteData_DT"
        Factor = "dd_dt"
        DTs = [dt.datetime(2021, 2, 1), dt.datetime(2021, 2, 2)]
        IDs = ["000001.SZ"]
        if TestTable not in self.FDB.TableNames:
            Data = pd.DataFrame(np.ones((2, 1)), index=DTs, columns=IDs)
            self.FDB.writeData(Panel({Factor: Data}), TestTable)

        self.FDB.deleteData(TestTable, dts=[DTs[0]])
        FT = self.FDB.getTable(TestTable)
        TestDTs = FT.getDateTime()
        self.assertNotIn(DTs[0], TestDTs)

    # ==================== 写入模式测试 ====================

    def test_update_notnull(self):
        """测试 update_notnull 写入方式"""
        TestTable = "UnitTest_Mongo_UpdateNotNull"
        Factor = "un"
        DTs = [dt.datetime(2021, 3, 1), dt.datetime(2021, 3, 2)]
        IDs = ["000001.SZ", "600000.SH"]

        Data = pd.DataFrame([[1.0, np.nan], [np.nan, 2.0]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: Data}), TestTable)

        NewData = pd.DataFrame([[np.nan, 10.0], [10.0, np.nan]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: NewData}), TestTable, if_exists="update_notnull")

        FT = self.FDB.getTable(TestTable)
        TestData = FT.readData(factor_names=[Factor], ids=IDs, dts=DTs).iloc[0]
        # 原非空，新为空 → 保留原值
        self.assertAlmostEqual(TestData.iloc[0, 0], 1.0)
        self.assertAlmostEqual(TestData.iloc[1, 1], 2.0)
        # 原空，新非空 → 填充新值
        self.assertAlmostEqual(TestData.iloc[0, 1], 10.0)
        self.assertAlmostEqual(TestData.iloc[1, 0], 10.0)

    def test_append(self):
        """测试 append 写入方式：不覆盖已有非空值"""
        TestTable = "UnitTest_Mongo_Append"
        Factor = "ap"
        DTs = [dt.datetime(2021, 4, 1), dt.datetime(2021, 4, 2)]
        IDs = ["000001.SZ"]

        Data = pd.DataFrame([[1.0], [np.nan]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: Data}), TestTable)

        AppendData = pd.DataFrame([[99.0], [2.0]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: AppendData}), TestTable, if_exists="append")

        FT = self.FDB.getTable(TestTable)
        TestData = FT.readData(factor_names=[Factor], ids=IDs, dts=DTs).iloc[0]
        # DTs[0] 已有值 1.0，append 不覆盖
        self.assertAlmostEqual(TestData.iloc[0, 0], 1.0)
        # DTs[1] 原为空，被填充为 2.0
        self.assertAlmostEqual(TestData.iloc[1, 0], 2.0)

    # ==================== 元数据测试 ====================

    def test_getFactorMetaData(self):
        """测试获取因子元数据"""
        TestTable = "UnitTest_Mongo_MetaData"
        Factor = "meta1"
        DTs = [dt.datetime(2021, 5, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame([[1.0]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: Data}), TestTable)

        FT = self.FDB.getTable(TestTable)
        meta = FT.getFactorMetaData(factor_names=[Factor])
        self.assertIsInstance(meta, pd.DataFrame)
        self.assertIn(Factor, meta.columns)

    def test_getFactorMetaData_key(self):
        """测试按 key 获取因子元数据"""
        TestTable = "UnitTest_Mongo_MetaDataKey"
        Factor = "meta2"
        DTs = [dt.datetime(2021, 6, 1)]
        IDs = ["000001.SZ"]
        Data = pd.DataFrame([[2.0]], index=DTs, columns=IDs)
        self.FDB.writeData(Panel({Factor: Data}), TestTable)

        FT = self.FDB.getTable(TestTable)
        dtype = FT.getFactorMetaData(factor_names=[Factor], key="DataType")
        self.assertEqual(dtype[Factor], "double")

    # ==================== 连接与断开 ====================

    def test_disconnect_reconnect(self):
        """测试断开和重连"""
        TestDB = MongoDB().connect()
        self.assertIsNotNone(TestDB.Connection)
        TestDB.disconnect()
        # 重连
        self.assertIsNotNone(TestDB.connect().Connection)
        if hasattr(TestDB, "_Connection") and TestDB._Connection is not None:
            TestDB._Connection.close()


class TestMongoDBStructure(unittest.TestCase):
    """MongoDB 类结构测试（不需要数据库写入）"""

    def test_instantiation(self):
        """测试实例化和参数"""
        db = MongoDB()
        self.assertEqual(db.Name, "MongoDB")
        self.assertEqual(db._QSArgs.DBType, "Mongo")
        self.assertEqual(db._QSArgs.Connector, "default")
        self.assertEqual(db._QSArgs.InnerPrefix, "qs_")
        self.assertEqual(db._QSArgs.DBName, "QSData")
        self.assertEqual(db._QSArgs.IPAddr, "localhost")
        self.assertEqual(db._QSArgs.Port, 27017)

    def test_custom_args(self):
        """测试自定义参数"""
        db = MongoDB(args={"InnerPrefix": "test_", "DBName": "TestDB"})
        self.assertEqual(db._QSArgs.InnerPrefix, "test_")
        self.assertEqual(db._QSArgs.DBName, "TestDB")

    def test_class_hierarchy(self):
        """测试类继承关系"""
        from QuantStudio.Factor.FactorDB import WritableFactorDB
        self.assertTrue(issubclass(MongoDB, WritableFactorDB))

    def test_argclass_fields(self):
        """测试 __QS_ArgClass__ 字段完整性"""
        fields = MongoDB.__QS_ArgClass__.model_fields
        expected = ["Name", "DBType", "DBName", "IPAddr", "Port", "User", "Pwd",
                     "CharSet", "Connector", "InnerPrefix", "IgnoreFields"]
        for f in expected:
            self.assertIn(f, fields, f"缺少字段: {f}")


if __name__ == "__main__":
    unittest.main()
