# coding=utf-8
"""DuckDB 元信息持久化及结构变更一致性回归测试。"""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import duckdb
import pandas as pd

from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.QSObject import Panel
from QSExt.Factor.DuckDB import DuckDB


class TestDuckDBMetaData(unittest.TestCase):
    """使用临时磁盘库验证元信息完整生命周期。"""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db_file = str(Path(self.directory.name) / "factors.duckdb")
        self.db = DuckDB(args={"DBFile": self.db_file}, config_file={}).connect()
        self.addCleanup(self.db.disconnect)
        self.db.createTable("daily", {"close": "DOUBLE", "volume": "DOUBLE"})

    def reconnect(self):
        """关闭并重新打开同一磁盘库。"""
        self.db.disconnect()
        self.db.connect()

    def test_table_ftargs_defaults_are_empty_independent_dicts(self):
        """新建表和旧库扫描均提供独立的空字典，不额外写入数据库。"""
        self.db.createTable("other", {"value": "DOUBLE"})
        for reconnect in (False, True):
            if reconnect:
                self.reconnect()
            first = self.db.getTable("daily").getMetaData("FTArgs")
            second = self.db.getTable("other").getMetaData("FTArgs")
            self.assertEqual(first, {})
            self.assertEqual(second, {})
            self.assertIsNot(first, second)
            self.assertFalse(self.db._hasMetaDataTable("table_metadata"))

    def test_table_ftargs_initialization_precedence_and_persistence(self):
        """库级默认值、表级参数、调用参数按优先级合并并在重连后生效。"""
        db = DuckDB(args={
            "DBFile": self.db_file,
            "FTArgs": {"LookBack": 2, "IgnoreTime": False, "MultiMapping": False},
        }, config_file={}).connect()
        self.addCleanup(db.disconnect)
        table_args = {"LookBack": 5, "IgnoreTime": True, "AdditionalCondition": {"code": "A"}}
        db.setTableMetaData("daily", key="FTArgs", value=table_args)
        db.createTable("other", {"value": "DOUBLE"})
        for reconnect in (False, True):
            if reconnect:
                db.connect()
            ft = db.getTable("daily")
            self.assertEqual(ft.Args["LookBack"], 5)
            self.assertTrue(ft.Args["IgnoreTime"])
            self.assertFalse(ft.Args["MultiMapping"])
            override = db.getTable("daily", args={"LookBack": 9, "IgnoreTime": False})
            self.assertEqual(override.Args["LookBack"], 9)
            self.assertFalse(override.Args["IgnoreTime"])
            self.assertEqual(ft.getMetaData("FTArgs"), table_args)
            self.assertEqual(db.getTable("other").Args["LookBack"], 2)
            prepared = db._initFTArgs("daily", {})
            prepared["AdditionalCondition"]["code"] = "B"
            self.assertEqual(db.getTable("daily").getMetaData("FTArgs"), table_args)
        db.deleteTableMetaData("daily", "FTArgs")
        self.assertEqual(db.getTable("daily").getMetaData("FTArgs"), {})
        self.assertEqual(db.getTable("daily").Args["LookBack"], 2)
        db.connect()
        self.assertEqual(db.getTable("daily").getMetaData("FTArgs"), {})
        self.assertEqual(db.getTable("daily").Args["LookBack"], 2)

    def test_table_ftargs_controls_table_type(self):
        """表级参数可选择因子表类型，显式调用参数仍有最高优先级。"""
        self.db.setTableMetaData("daily", meta_data={"FTArgs": {"TableType": "TimeSeriesTable", "IDField": None}})
        self.assertEqual(type(self.db.getTable("daily")).__name__, "SQL_TimeSeriesTable")
        self.assertEqual(type(self.db.getTable("daily", args={"TableType": "WideTable", "IDField": "code"})).__name__, "SQL_WideTable")

    def test_table_ftargs_rejects_non_dict_without_partial_updates(self):
        """表级 FTArgs 不能设为空值或其他类型，批量设置失败保持原值。"""
        self.db.setTableMetaData("daily", meta_data={"FTArgs": {"LookBack": 4}, "Description": "原描述"})
        for value in (None, [], "参数", 1, False):
            with self.subTest(value=value), self.assertRaisesRegex(TypeError, "FTArgs"):
                self.db.setTableMetaData("daily", meta_data={"Description": "未提交", "FTArgs": value})
            self.assertEqual(self.db.getTable("daily").getMetaData("Description"), "原描述")
            self.assertEqual(self.db.getTable("daily").getMetaData("FTArgs"), {"LookBack": 4})
        self.reconnect()
        self.assertEqual(self.db.getTable("daily").getMetaData("FTArgs"), {"LookBack": 4})
        self.db.Connection.execute("UPDATE qs_meta.table_metadata SET meta_value = 'null' WHERE meta_key = 'FTArgs'")
        with self.assertRaisesRegex(TypeError, "FTArgs"):
            self.reconnect()

    def test_roundtrip_json_values_and_upsert(self):
        """标量、容器和显式空值在新连接中保持类型和值。"""
        values = {
            "Description": "股票日行情：'收盘价'",
            "TableClass": "WideTable",
            "Tags": ["日频", "股票"],
            "Config": {"enabled": True, "period": 5, "scale": 1.5, "optional": None},
            "EmptyList": [], "EmptyDict": {}, "Empty": None,
            "Enabled": False, "Count": 0, "Ratio": 0.25,
        }
        self.db.setTableMetaData("daily", meta_data=values)
        self.db.setFactorMetaData("daily", "close", meta_data=values)
        self.db.setFactorMetaData("daily", "close", key="Description", value="收盘价")
        # 修改传入容器不会暗中修改缓存与持久化结果。
        values["Tags"].append("外部变更")
        self.assertEqual(self.db.getTable("daily").getMetaData("Tags"), ["日频", "股票"])
        self.reconnect()
        ft = self.db.getTable("daily")
        values["Tags"].pop()
        for key, value in values.items():
            with self.subTest(key=key):
                self.assertEqual(ft.getMetaData(key), value)
                expected = "收盘价" if key == "Description" else value
                self.assertEqual(ft.getFactorMetaData(["close"], key).at["close"], expected)
        self.assertEqual(self.db.TableNames, ["daily"])
        self.assertEqual(self.db.Connection.execute(
            "SELECT count(*) FROM qs_meta.factor_metadata WHERE meta_key = 'Description'"
        ).fetchone()[0], 1)

    def test_field_roles_are_restored(self):
        """字段角色覆盖参与重连后的因子表初始化。"""
        self.db.setFactorMetaData("daily", "code", key="FieldType", value="因子")
        self.db.setFactorMetaData("daily", "close", key="Supplementary", value="自定义")
        self.reconnect()
        self.assertEqual(self.db._initFTArgs("daily", {})["TableType"], "TimeSeriesTable")
        self.assertEqual(self.db._FactorInfo.at[("daily", "close"), "Supplementary"], "自定义")
        self.assertEqual(self.db._initFTArgs("daily", {"TableType": "WideTable"})["TableType"], "WideTable")

    def test_legacy_database_and_lazy_creation(self):
        """读取旧库不创建元信息表，第一次设置时再创建。"""
        self.reconnect()
        self.assertEqual(self.db.getTable("daily").getMetaData("Description"), "")
        self.assertFalse(self.db._hasMetaDataTable("table_metadata"))
        self.db.deleteTableMetaData("daily", "Description")
        self.assertFalse(self.db._hasMetaDataTable("table_metadata"))
        self.db.setTableMetaData("daily", key="Description", value="行情")
        self.assertTrue(self.db._hasMetaDataTable("table_metadata"))
        self.assertTrue(self.db._hasMetaDataTable("factor_metadata"))

    def test_live_database_structure_remains_authoritative(self):
        """外部结构变更在重连时生效，描述覆盖仍然保留。"""
        self.db.setFactorMetaData("daily", "close", key="Description", value="收盘价")
        self.db.execute('ALTER TABLE qs_daily ALTER COLUMN close TYPE BIGINT')
        self.db.execute('ALTER TABLE qs_daily ALTER COLUMN close SET NOT NULL')
        self.reconnect()
        info = self.db._FactorInfo.loc[("daily", "close")]
        self.assertEqual(info["DataType"], "BIGINT")
        self.assertEqual(info["Nullable"], "NO")
        self.assertEqual(info["Description"], "收盘价")

    def test_validation_does_not_partially_update(self):
        """无效类型、非字符串键和结构字段导致整批拒绝。"""
        self.db.setTableMetaData("daily", key="Description", value="原描述")
        bad_values = [dt.datetime(2026, 1, 1), (1, 2), {1: "值"}, {"x": {1, 2}}, float("nan"), float("inf")]
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    self.db.setTableMetaData("daily", meta_data={"Description": "未提交", "Bad": value})
        for key in ("DBTableName", "DBFieldName", "DataType", "Nullable", "FieldKey", "TableName", "FieldName"):
            with self.subTest(key=key), self.assertRaises(__QS_Error__):
                self.db.setFactorMetaData("daily", "close", meta_data={"Description": "未提交", key: "非法"})
        with self.assertRaises(TypeError):
            self.db.setTableMetaData("daily", meta_data={1: "非法"})
        self.assertNotIn("Bad", self.db._TableInfo.columns)
        self.reconnect()
        self.assertEqual(self.db.getTable("daily").getMetaData("Description"), "原描述")
        self.assertEqual(self.db.getTable("daily").getFactorMetaData(["close"], "Description").at["close"], "")

    def test_missing_targets_do_not_create_phantom_entries(self):
        """不存在的表或字段不能通过元信息接口隐式创建。"""
        with self.assertRaises(__QS_Error__):
            self.db.setTableMetaData("missing", key="Description", value="不存在")
        with self.assertRaises(__QS_Error__):
            self.db.setFactorMetaData("daily", "missing", key="Description", value="不存在")
        self.assertEqual(self.db.TableNames, ["daily"])
        self.assertNotIn(("daily", "missing"), self.db._FactorInfo.index)

    def test_batch_write_failure_rolls_back_database_and_cache(self):
        """批量写入中途失败时，磁盘和缓存都保留旧值。"""
        self.db.setTableMetaData("daily", key="Description", value="原描述")
        connection = self.db.Connection
        proxy = mock.Mock(wraps=connection)

        def fail_after_first_row(sql, rows):
            connection.execute(sql, rows[0])
            raise RuntimeError("模拟批量写入失败")

        proxy.executemany.side_effect = fail_after_first_row
        with mock.patch.object(self.db, "_Connection", proxy):
            with self.assertRaises(RuntimeError):
                self.db.setTableMetaData("daily", meta_data={"Description": "未提交", "New": [1, 2]})
        self.assertEqual(self.db.getTable("daily").getMetaData("Description"), "原描述")
        self.assertNotIn("New", self.db._TableInfo.columns)
        self.reconnect()
        self.assertEqual(self.db.getTable("daily").getMetaData("Description"), "原描述")
        self.assertIsNone(self.db.getTable("daily").getMetaData("New"))

    def test_rename_and_delete_follow_physical_objects(self):
        """重命名后可立即读取数据，删除后元信息记录被清理。"""
        dates = [dt.datetime(2026, 1, 1)]
        self.db.writeData(Panel({"close": pd.DataFrame([[12.5]], index=dates, columns=["A"])}), "daily")
        self.db.setTableMetaData("daily", key="Description", value="日行情")
        self.db.setFactorMetaData("daily", "close", key="Unit", value="元")
        self.db.renameFactor("daily", "close", "price")
        self.db.renameTable("daily", "prices")
        ft = self.db.getTable("prices")
        self.assertEqual(ft.readData(["price"], ids=["A"], dts=dates).iloc[0, 0, 0], 12.5)
        self.assertEqual(ft.getFactorMetaData(["price"], "Unit").at["price"], "元")
        self.reconnect()
        self.assertEqual(self.db.getTable("prices").getMetaData("Description"), "日行情")
        self.assertEqual(self.db.Connection.execute(
            "SELECT db_table, field_name FROM qs_meta.factor_metadata"
        ).fetchall(), [("qs_prices", "price")])
        self.db.deleteFactor("prices", ["price"])
        self.assertEqual(self.db.Connection.execute("SELECT count(*) FROM qs_meta.factor_metadata").fetchone()[0], 0)
        self.db.addFactor("prices", {"price": "DOUBLE"})
        self.reconnect()
        self.assertNotIn("Unit", self.db._FactorInfo.columns)
        self.db.setFactorMetaData("prices", "price", key="Unit", value="元")
        self.db.deleteTable("prices")
        for table in ("table_metadata", "factor_metadata"):
            self.assertEqual(self.db.Connection.execute(f"SELECT count(*) FROM qs_meta.{table}").fetchone()[0], 0)
        self.reconnect()
        self.assertEqual(self.db.TableNames, [])

    def test_ddl_metadata_failure_rolls_back_structure(self):
        """DDL 成功后元信息维护失败，结构与缓存均回滚。"""
        self.db.setTableMetaData("daily", key="Description", value="行情")
        operations = [
            lambda: self.db.renameTable("daily", "new_daily"),
            lambda: self.db.renameFactor("daily", "close", "price"),
            lambda: self.db.deleteFactor("daily", ["close"]),
            lambda: self.db.deleteTable("daily"),
        ]
        for operation in operations:
            with mock.patch.object(self.db, "_hasMetaDataTable", side_effect=RuntimeError("模拟元信息维护失败")):
                with self.assertRaises(RuntimeError):
                    operation()
            self.assertEqual(self.db.TableNames, ["daily"])
            self.assertIn("close", self.db.getTable("daily").FactorNames)
            self.assertEqual(self.db.Connection.execute("SELECT close FROM qs_daily").fetchall(), [])
        self.reconnect()
        self.assertEqual(self.db.getTable("daily").getMetaData("Description"), "行情")

    def test_multi_column_delete_is_atomic(self):
        """多列删除中第二列无效时，第一列和元信息均保留。"""
        self.db.setFactorMetaData("daily", "close", key="Unit", value="元")
        with self.assertRaises(Exception):
            self.db.deleteFactor("daily", ["close", "missing"])
        self.reconnect()
        self.assertIn("close", self.db.getTable("daily").FactorNames)
        self.assertEqual(self.db.getTable("daily").getFactorMetaData(["close"], "Unit").at["close"], "元")

    def test_index_dependency_failure_preserves_structure_and_metadata(self):
        """索引依赖导致删除失败时完整回滚；单独删除索引后可重试。"""
        self.db.setFactorMetaData("daily", "close", key="Unit", value="元")
        self.db.execute("CREATE INDEX close_idx ON qs_daily(close)")
        with self.assertRaises(duckdb.Error):
            self.db.deleteFactor("daily", ["close"])
        self.assertIn("close", self.db.getTable("daily").FactorNames)
        self.assertEqual(self.db._FactorInfo.at[("daily", "close"), "Unit"], "元")
        self.assertEqual(self.db.Connection.execute(
            "SELECT count(*) FROM duckdb_indexes() WHERE index_name = 'close_idx'"
        ).fetchone()[0], 1)
        self.db.execute("DROP INDEX close_idx")
        self.db.deleteFactor("daily", ["close"])
        self.reconnect()
        self.assertNotIn("close", self.db.getTable("daily").FactorNames)
        self.assertEqual(self.db.Connection.execute("SELECT count(*) FROM qs_meta.factor_metadata").fetchone()[0], 0)

    def test_first_write_failure_does_not_leave_metadata_tables(self):
        """首次设置失败时连同新建的 schema 和元信息表一起回滚。"""
        connection = self.db.Connection
        proxy = mock.Mock(wraps=connection)
        proxy.executemany.side_effect = RuntimeError("模拟首次写入失败")
        with mock.patch.object(self.db, "_Connection", proxy), self.assertRaises(RuntimeError):
            self.db.setTableMetaData("daily", key="Description", value="未提交")
        self.assertEqual(self.db.getTable("daily").getMetaData("Description"), "")
        self.assertEqual(connection.execute(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'qs_meta'"
        ).fetchone()[0], 0)

    def test_delete_metadata_failure_preserves_override(self):
        """删除覆盖失败时缓存与磁盘保留原值。"""
        self.db.setFactorMetaData("daily", "close", key="Description", value="收盘价")
        connection = self.db.Connection
        proxy = mock.Mock(wraps=connection)

        def fail_delete(sql, *args):
            if sql.startswith("DELETE FROM qs_meta."):
                raise RuntimeError("模拟删除元信息失败")
            return connection.execute(sql, *args)

        proxy.execute.side_effect = fail_delete
        with mock.patch.object(self.db, "_Connection", proxy), self.assertRaises(RuntimeError):
            self.db.deleteFactorMetaData("daily", "close", "Description")
        self.assertEqual(self.db._FactorInfo.at[("daily", "close"), "Description"], "收盘价")
        self.reconnect()
        self.assertEqual(self.db._FactorInfo.at[("daily", "close"), "Description"], "收盘价")

    def test_null_and_deleting_override_are_distinct(self):
        """空值可以往返，删除覆盖则恢复推导默认值。"""
        self.db.setTableMetaData("daily", key="Description", value=None)
        self.db.setFactorMetaData("daily", "datetime", key="Supplementary", value=None)
        self.db.setFactorMetaData("daily", "close", key="Description", value="收盘价")
        self.reconnect()
        self.assertIsNone(self.db.getTable("daily").getMetaData("Description"))
        self.assertIsNone(self.db._FactorInfo.at[("daily", "datetime"), "Supplementary"])
        self.db.deleteTableMetaData("daily", "Description")
        self.db.deleteFactorMetaData("daily", "datetime", "Supplementary")
        self.db.deleteFactorMetaData("daily", "close", "Description")
        for reconnect in (False, True):
            if reconnect:
                self.reconnect()
            self.assertEqual(self.db.getTable("daily").getMetaData("Description"), "")
            self.assertEqual(self.db._FactorInfo.at[("daily", "datetime"), "Supplementary"], "Default")
            self.assertEqual(self.db._FactorInfo.at[("daily", "close"), "Description"], "")

    def test_stale_records_do_not_create_tables_or_fields(self):
        """外部删除的表或字段不会被历史元信息恢复到缓存。"""
        self.db.setFactorMetaData("daily", "close", key="Unit", value="元")
        self.db.setTableMetaData("daily", key="Description", value="行情")
        self.db.execute("ALTER TABLE qs_daily DROP COLUMN close")
        self.reconnect()
        self.assertNotIn("close", self.db.getTable("daily").FactorNames)
        self.db.execute("DROP TABLE qs_daily")
        self.reconnect()
        self.assertEqual(self.db.TableNames, [])

    def test_prefixes_are_literal_and_isolate_metadata(self):
        """前缀中的下划线按字面匹配，元信息按物理表隔离。"""
        for table_prefix, inner_prefix in (("p_", "qs_"), ("", "other_"), ("", "")):
            with self.subTest(table_prefix=table_prefix, inner_prefix=inner_prefix):
                db = DuckDB(args={"DBFile": self.db_file, "TablePrefix": table_prefix, "InnerPrefix": inner_prefix}, config_file={}).connect()
                try:
                    db.createTable("sample", {"value": "DOUBLE"})
                    name = table_prefix + inner_prefix + "sample"
                    db.setTableMetaData("sample", key="Description", value=name)
                    db.connect()
                    self.assertEqual(db.getTable("sample").getMetaData("Description"), name)
                    self.assertEqual(db.getTable("sample")._DBTableName, name)
                    self.assertNotIn("table_metadata", db.TableNames)
                    self.assertNotIn("factor_metadata", db.TableNames)
                finally:
                    db.disconnect()
        self.db.execute("CREATE TABLE qsXforeign (value DOUBLE)")
        self.db.execute("CREATE SCHEMA other")
        self.db.execute("CREATE TABLE other.qs_daily (wrong DOUBLE)")
        self.reconnect()
        self.assertEqual(self.db.TableNames, ["daily"])

    def test_quoted_identifiers_and_keys(self):
        """引号和中文键值通过标识符引用及参数绑定正确保存。"""
        self.db.createTable('带"引号', {"a'b": "DOUBLE"})
        self.db.setTableMetaData('带"引号', key="描'述", value="中文")
        self.db.setFactorMetaData('带"引号', "a'b", key="配置", value={"单位": "元"})
        self.reconnect()
        self.assertEqual(self.db._TableInfo.at['带"引号', "描'述"], "中文")
        self.assertEqual(self.db._FactorInfo.at[('带"引号', "a'b"), "配置"], {"单位": "元"})

    def test_parquet_metadata_persists_and_view_stays_readonly(self):
        """Parquet 视图元信息可修改，重连后继续按只读视图管理。"""
        root = Path(self.directory.name) / "parquet"
        table_dir = root / "minute"
        table_dir.mkdir(parents=True)
        file_name = str(table_dir / "data.parquet").replace("\\", "/").replace("'", "''")
        self.db.execute(
            f"COPY (SELECT 'A' AS code, '2026-01-01 09:30:00' AS datetime, 12.5 AS close) "
            f"TO '{file_name}' (FORMAT PARQUET)"
        )
        db = DuckDB(args={"DBFile": self.db_file, "ParquetDir": str(root)}, config_file={}).connect()
        try:
            self.assertEqual(db.getTable("minute").getMetaData("FTArgs"), {})
            db.setTableMetaData("minute", key="Description", value="分钟行情")
            db.setTableMetaData("minute", key="FTArgs", value={"LookBack": 6})
            db.setFactorMetaData("minute", "close", key="Unit", value="元")
            db.connect()
            self.assertEqual(db.getTable("minute").getMetaData("Description"), "分钟行情")
            self.assertEqual(db.getTable("minute").Args["LookBack"], 6)
            self.assertEqual(db.getTable("minute").getFactorMetaData(["close"], "Unit").at["close"], "元")
            with self.assertRaises(__QS_Error__):
                db.addFactor("minute", {"new": "DOUBLE"})
            db.deleteTable("minute")
            db.connect()
            self.assertEqual(db.getTable("minute").getMetaData("Description"), "")
            self.assertEqual(db.getTable("minute").getMetaData("FTArgs"), {})
            self.assertNotIn("Unit", db._FactorInfo.columns)
            self.assertTrue((table_dir / "data.parquet").exists())
        finally:
            db.disconnect()

    def test_parquet_directory_automatically_loads_metadata_database(self):
        """仅指定 ParquetDir 时自动恢复目录内的窄表参数及数据。"""
        root = Path(self.directory.name) / "parquet"
        table_dir = root / "narrow"
        table_dir.mkdir(parents=True)
        parquet_file = str(table_dir / "data.parquet").replace("\\", "/").replace("'", "''")
        self.db.execute(
            "COPY (SELECT TIMESTAMP '2026-01-01' AS datetime, 'A' AS code, "
            f"'alpha' AS factor_name, 1.5 AS factor_value) TO '{parquet_file}' (FORMAT PARQUET)"
        )
        metadata_file = root / "_metadata.duckdb"
        ftargs = {"TableType": "NarrowTable", "FactorValueField": "factor_value", "FactorNameField": "factor_name"}
        writer = DuckDB(args={"DBFile": str(metadata_file), "ParquetDir": str(root)}, config_file={}).connect()
        try:
            writer.setTableMetaData("narrow", key="FTArgs", value=ftargs)
        finally:
            writer.disconnect()
        args = {"ParquetDir": str(root)}
        db = DuckDB(args=args, config_file={}).connect()
        try:
            self.assertEqual(args, {"ParquetDir": str(root)})
            self.assertEqual(Path(db.Args["DBFile"]), metadata_file.resolve())
            ft = db.getTable("narrow")
            self.assertEqual(type(ft).__name__, "SQL_NarrowTable")
            self.assertEqual(ft.getMetaData("FTArgs"), ftargs)
            self.assertEqual(ft.FactorNames, ["alpha"])
            data = ft.readData(["alpha"], ids=["A"], dts=[dt.datetime(2026, 1, 1)])
            self.assertEqual(data.iloc[0, 0, 0], 1.5)
            db.setTableMetaData("narrow", key="Description", value="自动加载后保存")
            db.connect()
            self.assertEqual(db.getTable("narrow").getMetaData("Description"), "自动加载后保存")
        finally:
            db.disconnect()

    def test_parquet_directory_without_metadata_keeps_memory_database(self):
        """目录没有元信息库时继续使用内存，不创建磁盘库。"""
        root = Path(self.directory.name) / "empty_parquet"
        root.mkdir()
        db = DuckDB(args={"ParquetDir": str(root)}, config_file={}).connect()
        try:
            self.assertEqual(db.Args["DBFile"], ":memory:")
            db.createTable("temporary", {"value": "DOUBLE"})
            db.setTableMetaData("temporary", key="Description", value="内存元信息")
            self.assertFalse(db._hasMetaDataTable("table_metadata"))
            self.assertFalse((root / "_metadata.duckdb").exists())
        finally:
            db.disconnect()

    def test_explicit_dbfile_and_configuration_take_priority_over_auto_loading(self):
        """显式 DBFile（包括内存库）及配置文件中的 DBFile 优先于自动发现。"""
        root = Path(self.directory.name) / "parquet"
        root.mkdir()
        metadata_file = root / "_metadata.duckdb"
        writer = DuckDB(args={"DBFile": str(metadata_file)}, config_file={}).connect()
        try:
            writer.createTable("stored", {"value": "DOUBLE"})
        finally:
            writer.disconnect()
        for db_file in (":memory:", str(Path(self.directory.name) / "explicit.duckdb")):
            db = DuckDB(args={"ParquetDir": str(root), "DBFile": db_file}, config_file={}).connect()
            try:
                self.assertEqual(db.Args["DBFile"], db_file)
                self.assertNotIn("stored", db.TableNames)
            finally:
                db.disconnect()
        config_file = Path(self.directory.name) / "duckdb.json"
        for config in ({"ParquetDir": str(root)}, {"ParquetDir": str(root), "DBFile": ":memory:"}):
            config_file.write_text(json.dumps(config), encoding="utf-8")
            db = DuckDB(config_file=str(config_file)).connect()
            try:
                self.assertEqual("stored" in db.TableNames, "DBFile" not in config)
            finally:
                db.disconnect()
        db = DuckDB(args={"DBFile": str(metadata_file)}, config_file=str(config_file)).connect()
        try:
            self.assertIn("stored", db.TableNames)
        finally:
            db.disconnect()

    def test_memory_database_never_creates_metadata_storage(self):
        """内存库只更新缓存，不创建持久化元信息 schema。"""
        db = DuckDB(args={"DBFile": ":memory:"}, config_file={}).connect()
        try:
            db.createTable("daily", {"close": "DOUBLE"})
            db.setTableMetaData("daily", key="Tags", value=["日频"])
            db.setTableMetaData("daily", key="FTArgs", value={"LookBack": 3})
            self.assertEqual(db.getTable("daily").Args["LookBack"], 3)
            db.deleteTableMetaData("daily", "FTArgs")
            self.assertEqual(db.getTable("daily").getMetaData("FTArgs"), {})
            db.setFactorMetaData("daily", "close", key="Description", value="收盘价")
            self.assertEqual(db.getTable("daily").getMetaData("Tags"), ["日频"])
            self.assertEqual(db.Connection.execute(
                "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'qs_meta'"
            ).fetchone()[0], 0)
            db.deleteFactorMetaData("daily", "close", "Description")
            self.assertEqual(db._FactorInfo.at[("daily", "close"), "Description"], "")
        finally:
            db.disconnect()


if __name__ == "__main__":
    unittest.main()
