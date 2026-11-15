import datetime as dt
from datetime import datetime, timedelta
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from QuantStudio.Core.CalcEngine import Engine, StackEngine
from QuantStudio.Core.QSObject import Panel
from QuantStudio.Factor.Factor import FactorContext
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QuantStudio.Factor.FactorDB import FactorDB
from QuantStudio.Factor.HDF5DB import HDF5DB
from QSExt.Factor.IDMapping import (
    FactorDBIDMappingConfig,
    IDMappingFactorDB,
    StaticIDMapping,
)
from QSExt.Factor.JYDBWindDBIDMapping import (
    JYDBWindDBFactorDB,
    JYDBWindDBHKStockIDMapping,
    WINDDB_MANUAL_ID_VALUE_FACTORS,
    WINDDB_MANUAL_TABLES_BY_SECURITY_TYPE,
    WindDBMutualFundIDMapping,
)


class _FakeDB:
    def __init__(self, rows):
        self.Args = SimpleNamespace(TablePrefix="public.")
        self.rows = rows
        self.sql = None

    def fetchall(self, sql):
        self.sql = sql
        return self.rows


class _FakeWindFactorDB(FactorDB):
    class __QS_ArgClass__(FactorDB.__QS_ArgClass__):
        TablePrefix: str = "public."

    def __init__(self, rows):
        self.rows = rows
        super().__init__(args={"Name": "FakeWindDB"})
        self._TableInfo = pd.DataFrame(
            {"SecurityType": ["港股", "A股", "公募基金"]},
            index=["香港股票日行情", "中国A股日行情", "中国公募基金净值"],
        )

    def fetchall(self, sql):
        return self.rows

    def getStockID(self, *args, **kwargs):
        return ["1.HK", "UNMAPPED.HK", "600000.SH"]

    def getMutualFundID(self, *args, **kwargs):
        return ["000001.OF"]

    def getFutureID(self, *args, **kwargs):
        return ["IF2601.CFE"]

    def getOptionID(self, *args, **kwargs):
        return ["10000001.SH"]

    def getIndustryID(self, *args, **kwargs):
        return ["801010"]

    def getTradeDay(self, *args, **kwargs):
        return [dt.date(2026, 1, 1)]

    def getFutureCode(self, *args, **kwargs):
        return ["IF"]

    def getIndustryInfo(self, *args, **kwargs):
        return pd.DataFrame({"IndustryID": ["801010"]})


class TestIDMappingFactorDB(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = HDF5DB(args={"MainDir": self.directory.name}).connect()
        self.addCleanup(self.source.disconnect)
        self.dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(3)]
        self.native = pd.DataFrame(
            [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]],
            index=self.dates,
            columns=["A", "B"],
        )
        self.source.writeData(Panel({"close": self.native}), "prices")
        self.mapping = StaticIDMapping(args={
            "Mapping": {"X": "A", "Y": "A"},
            "UnmappedPolicy": "empty",
        })
        self.database = IDMappingFactorDB(
            self.source,
            args={"IDMappingConfig": FactorDBIDMappingConfig(Default=self.mapping)},
        )
        self.table = self.database.getTable("prices")

    def test_mapping_id_depends_on_contents(self):
        other = StaticIDMapping(args={"Mapping": {"X": "B"}})
        self.assertNotEqual(self.mapping.MappingID, other.MappingID)

    def test_table_metadata_and_id_methods_delegate(self):
        self.assertEqual(self.table.FactorNames, ["close"])
        self.assertEqual(self.table.getID(ifactor_name="close"), ["X", "Y"])
        self.assertEqual(self.table.getDateTime(ifactor_name="close", iid="X"), self.dates)
        self.assertEqual(self.table.getDateTime(ifactor_name="close", iid="MISSING"), [])

    def test_direct_and_engine_reads_expand_many_to_one(self):
        ids = ["X", "Y", "MISSING"]
        expected = pd.DataFrame(
            {"X": self.native["A"], "Y": self.native["A"], "MISSING": float("nan")},
            index=self.dates,
        )
        direct = self.table.readData(["close"], ids, self.dates).iloc[0]
        pd.testing.assert_frame_equal(direct, expected, check_dtype=False, check_index_type=False)
        for engine_type in (Engine, StackEngine):
            with self.subTest(engine=engine_type.__name__):
                with FactorContext(DTRuler=self.dates, SectionIDs=ids), engine_type(args={"IOConcurrentNum": 1}):
                    result = self.table.readData(["close"], ids, self.dates).iloc[0]
                pd.testing.assert_frame_equal(result, expected, check_dtype=False, check_index_type=False)

    def test_table_override_and_source_args(self):
        native = self.database.getTable("prices", args={
            "IDMapping": None,
            "SourceArgs": {"LookBack": 7},
        })
        self.assertEqual(native.SourceTable.Args.LookBack, 7)
        result = native.readData(["close"], ["B"], self.dates).iloc[0]
        pd.testing.assert_frame_equal(result, self.native[["B"]], check_index_type=False)

    def test_standard_factor_cache_uses_external_ids(self):
        ids = ["X", "Y", "MISSING"]
        with FeatherFactorCache(args={"DTRuler": self.dates}) as cache:
            with FactorContext(DTRuler=self.dates, SectionIDs=ids, DataCache=cache), Engine(args={"IOConcurrentNum": 1}):
                result = self.table.readData(["close"], ids, self.dates).iloc[0]
        pd.testing.assert_series_equal(result["X"], self.native["A"], check_names=False, check_dtype=False)
        pd.testing.assert_series_equal(result["Y"], self.native["A"], check_names=False, check_dtype=False)
        self.assertTrue(result["MISSING"].isna().all())

    def test_factor_values_configured_as_ids_are_converted(self):
        related = pd.DataFrame(
            [["A"], ["A"], ["A"]], index=self.dates, columns=["B"]
        )
        self.source.writeData(Panel({"related": related}), "links")
        mapping = StaticIDMapping(args={
            "Mapping": {"X": "A", "Y": "A", "Z": "B"},
            "UnmappedPolicy": "empty",
        })
        database = IDMappingFactorDB(self.source, args={
            "IDMappingConfig": FactorDBIDMappingConfig(
                Default=mapping,
                IDValueMappings={"links": {"related": mapping}},
                IDValueAmbiguity="list",
            ),
        })
        result = database.getTable("links").readData(
            ["related"], ["Z"], self.dates
        ).iloc[0]
        self.assertEqual(result.loc[self.dates[0], "Z"], ["X", "Y"])


class TestJYDBWindDBHKStockIDMapping(unittest.TestCase):

    def setUp(self):
        self.jy_rows = [
            (1, "00001", "ISIN-A", "2000-01-01", None, 51, "ONE"),
            (2, "08142", "ISIN-M", "2010-02-01", None, 51, "MIGRATE"),
            (3, "00266", None, "1998-03-01", None, 51, "FULL"),
            (4, "02979!AL", None, "2018-04-01", "2018-04-10", 78, "TEMP"),
            (5, "08233", "ISIN-OLD", "2005-06-01", "2018-01-29", 51, "CONFLICT"),
            (6, "02949", None, "2026-11-01", None, 78, "RIGHTS"),
        ]
        self.wind_rows = [
            ("1.HK", "0001", "ISIN-A", "20000101", None, "ONE"),
            ("2102.HK", "2102", "ISIN-M", "20100201", None, "MIGRATE"),
            ("266.HK", "0266", None, "19980301", None, "FULL"),
            ("2979!13.HK", "2979!13", None, "20180401", "20180410", "TEMP"),
            ("8233.HK", "8233", "ISIN-NEW", "20200101", None, "NEW"),
        ]
        self.mapping = JYDBWindDBHKStockIDMapping(
            _FakeDB(self.jy_rows),
            _FakeDB(self.wind_rows),
            args={"AsOfDate": dt.date(2026, 11, 14)},
        )

    def test_documented_matching_order_and_audit(self):
        resolved = self.mapping.resolve([
            "00001.HK", "08142.HK", "00266.HK", "02979!AL.HK",
            "08233.HK", "02949.HK",
        ])
        self.assertEqual(
            resolved.native_ids,
            ["1.HK", "2102.HK", "266.HK", "2979!13.HK"],
        )
        self.assertEqual(resolved.external_to_native[-2:], [None, None])
        info = self.mapping.MappingInfo.set_index("jy_secucode")
        self.assertEqual(info.loc["00001", "match_method"], "ISIN_BASE")
        self.assertEqual(info.loc["08142", "match_method"], "ISIN_MIGRATION")
        self.assertEqual(info.loc["00266", "match_method"], "FULL_CODE")
        self.assertEqual(info.loc["02979!AL", "match_method"], "BASE_LIST_DELIST")
        self.assertEqual(info.loc["08233", "unmapped_reason"], "ISIN_CONFLICT")
        self.assertEqual(info.loc["02949", "unmapped_reason"], "TEMPORARY_SECURITY_NOT_RETAINED")

    def test_mapping_id_is_content_digest(self):
        first = self.mapping.MappingID
        same = JYDBWindDBHKStockIDMapping(
            _FakeDB(list(self.jy_rows)),
            _FakeDB(list(self.wind_rows)),
            args={"AsOfDate": dt.date(2026, 11, 14)},
        )
        self.assertEqual(first, same.MappingID)
        changed_rows = list(self.wind_rows)
        changed_rows[0] = ("NEW.HK",) + changed_rows[0][1:]
        changed = JYDBWindDBHKStockIDMapping(
            _FakeDB(self.jy_rows),
            _FakeDB(changed_rows),
            args={"AsOfDate": dt.date(2026, 11, 14)},
        )
        self.assertNotEqual(first, changed.MappingID)

    def test_factor_db_subclass_converts_database_level_id_methods(self):
        database = JYDBWindDBFactorDB(
            jydb=_FakeDB(self.jy_rows),
            winddb=_FakeWindFactorDB(self.wind_rows),
            as_of_date=dt.date(2026, 11, 14),
        )
        self.assertIsInstance(database.MutualFundIDMapping, WindDBMutualFundIDMapping)
        self.assertIs(
            database.Args.IDMappingConfig.resolve("中国ETF申购赎回成份"),
            database.MutualFundIDMapping,
        )
        self.assertIs(
            database.Args.IDMappingConfig.resolve("香港股票日行情"),
            database.IDMapping,
        )
        self.assertIsNone(database.Args.IDMappingConfig.resolve("中国A股日行情"))
        self.assertIs(
            database.Args.IDMappingConfig.resolve("中国公募基金净值"),
            database.MutualFundIDMapping,
        )
        self.assertIn("香港股票日行情", WINDDB_MANUAL_TABLES_BY_SECURITY_TYPE["港股"])
        self.assertIn("中国ETF申购赎回清单", WINDDB_MANUAL_TABLES_BY_SECURITY_TYPE["公募基金"])
        self.assertIn(None, WINDDB_MANUAL_TABLES_BY_SECURITY_TYPE)
        self.assertEqual(database.getStockID(exchange="HKEX"), ["00001.HK", "600000.SH"])
        self.assertEqual(database.getMutualFundID(), ["000001.OF"])
        self.assertEqual(database.getFutureID(), ["IF2601.CFE"])
        self.assertEqual(database.getOptionID(), ["10000001.SH"])
        self.assertEqual(database.getIndustryID(), ["801010"])
        self.assertEqual(database.getTradeDay(), [dt.date(2026, 1, 1)])
        self.assertEqual(database.getFutureCode(), ["IF"])
        self.assertEqual(database.getIndustryInfo().iloc[0, 0], "801010")

    def test_each_id_value_factor_selects_its_mapping(self):
        with patch.dict(WINDDB_MANUAL_ID_VALUE_FACTORS, {
            "香港股票日行情": {
                "关联股票代码": "港股",
                "关联基金代码": "公募基金",
            },
        }):
            default_database = JYDBWindDBFactorDB(
                jydb=_FakeDB(self.jy_rows),
                winddb=_FakeWindFactorDB(self.wind_rows),
                as_of_date=dt.date(2026, 11, 14),
            )
            database = JYDBWindDBFactorDB(
                jydb=_FakeDB(self.jy_rows),
                winddb=_FakeWindFactorDB(self.wind_rows),
                as_of_date=dt.date(2026, 11, 14),
                id_value_factors={"香港股票日行情": {}},
            )
        value_mappings = default_database.Args.IDMappingConfig.resolveIDValueMappings(
            "香港股票日行情"
        )
        self.assertIs(value_mappings["关联股票代码"], default_database.IDMapping)
        self.assertIs(value_mappings["关联基金代码"], default_database.MutualFundIDMapping)
        self.assertEqual(
            database.Args.IDMappingConfig.resolveIDValueMappings("香港股票日行情"),
            {},
        )


class TestWindDBMutualFundIDMapping(unittest.TestCase):

    def test_mapping_replaces_winddb_native_feature(self):
        winddb = _FakeDB([
            ("000001", "WIND-1"),
            ("000002", "WIND-2"),
        ])
        mapping = WindDBMutualFundIDMapping(winddb)
        request = mapping.resolve(["000001", "UNKNOWN"])
        self.assertEqual(request.native_ids, ["WIND-1", "UNKNOWN"])
        self.assertEqual(mapping.toExternal(["WIND-2", "UNKNOWN"]), ["000002", "UNKNOWN"])
        self.assertIn("ChinaMutualFundDescription", winddb.sql)


if __name__ == "__main__":
    unittest.main()
