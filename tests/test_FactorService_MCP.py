import datetime as dt
import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from QSExt.FactorServiceMCP.catalog import FactorCatalog, decode_cursor, factor_id
from QSExt.FactorServiceMCP.service import FactorDataService
from QSExt.FactorServiceMCP.server import create_server
from QSExt.FactorServiceMCP.config import MCPConfig
from QSExt.FactorServiceMCP.refresh import CatalogRefreshManager
from QSExt.FactorService.protocol import RemoteFactorError


class FakeFactor:
    def __init__(self, table, name):
        self.table, self.name = table, name

    def getID(self):
        return list(self.table.ids)

    def getDateTime(self, start_dt=None, end_dt=None):
        return [value for value in self.table.dates
                if (start_dt is None or value >= start_dt) and (end_dt is None or value <= end_dt)]


class FakePanel:
    def __init__(self, frames):
        self.iloc = frames


class FakeTable:
    def __init__(self, name):
        self.name = name
        self.FactorNames = ["close", "open"]
        self.ids = ["A", "B"]
        self.dates = [dt.datetime(2026, 1, day) for day in range(1, 4)]

    def getFactorMetaData(self, factor_names=None, key=None):
        values = {name: {"DataType": "double", "Description": name + " description"}
                  for name in factor_names}
        if key is not None:
            return pd.Series({name: value[key] for name, value in values.items()})
        return pd.DataFrame.from_dict(values, orient="index")

    def getFactor(self, name):
        return FakeFactor(self, name)

    def getDateTime(self, ifactor_name=None, start_dt=None, end_dt=None):
        return self.getFactor(ifactor_name).getDateTime(start_dt, end_dt)

    def readData(self, factor_names, ids, dts):
        return FakePanel([pd.DataFrame([[position + row + column for column, _ in enumerate(ids)]
            for row, _ in enumerate(dts)], index=dts, columns=ids, dtype=float)
            for position, _ in enumerate(factor_names)])


class FakeDatabase:
    def __init__(self, client, name):
        self.client, self.name = client, name
        self.TableNames = client.table_names

    def connect(self):
        return self

    def disconnect(self):
        pass

    def getTable(self, name):
        if name == "requires_args":
            raise RemoteFactorError("需要参数", code="INVALID_ARGUMENT", status=422)
        return self.client.table


class FakeClient:
    def __init__(self):
        self.info = {"service_id": "test-service"}
        self.table = FakeTable("daily")
        self.table_names = ["daily"]

    def connect(self):
        return self

    def close(self):
        pass

    def listDatabases(self):
        return [{"name": "test", "resource_id": "resource", "config_revision": "revision"}]

    def getDatabase(self, name):
        return FakeDatabase(self, name)

    def getCatalog(self, name):
        table = self.table
        names = list(table.FactorNames)
        skipped = ([{"table_name": "requires_args", "code": "INVALID_ARGUMENT"}]
                   if "requires_args" in self.table_names else [])
        return {"tables": [{"table_name": "daily", "factor_names": names,
            "factor_metadata": table.getFactorMetaData(names)}], "skipped_tables": skipped}


class TestFactorServiceMCP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.catalog = FactorCatalog(Path(self.tmp.name) / "catalog.sqlite3", FakeClient, ttl_seconds=3600)
        self.service = FactorDataService(self.catalog, FakeClient, max_cells=20, max_result_bytes=65536)
        self.catalog.refresh()

    def test_catalog_search_and_stable_ids(self):
        result = self.service.search_factors("close", page_size=1)
        self.assertEqual(result["items"][0]["factor_name"], "close")
        self.assertEqual(result["items"][0]["factor_id"], factor_id("test-service", "resource", "daily", "close"))
        self.assertIsNone(result["next_cursor"])
        details = self.service.get_factor(result["items"][0]["factor_id"])
        self.assertEqual(details["metadata"]["Description"], "close description")

    def test_empty_catalog_reports_background_initialization(self):
        empty = FactorCatalog(Path(self.tmp.name) / "empty.sqlite3", FakeClient, ttl_seconds=3600)
        with self.assertRaisesRegex(ValueError, "后台初始化"):
            empty.search("close")

    def test_background_manager_initializes_and_rejects_duplicate_refresh(self):
        empty = FactorCatalog(Path(self.tmp.name) / "background.sqlite3", FakeClient, ttl_seconds=3600)
        manager = CatalogRefreshManager(FactorDataService(empty, FakeClient), interval_seconds=86400)
        manager.start()
        self.addCleanup(manager.stop)
        deadline = time.monotonic() + 5
        while manager.status()["factor_count"] == 0 and time.monotonic() < deadline:
            time.sleep(.01)
        status = manager.status()
        self.assertEqual(status["factor_count"], 2)
        self.assertEqual(status["source"], "startup")
        self.assertTrue(manager.request_refresh("manual"))
        self.assertFalse(manager.request_refresh("manual"))

    def test_table_pagination_and_cursor_validation(self):
        result = self.service.list_tables(page_size=1)
        self.assertEqual(result["items"][0]["factor_count"], 2)
        with self.assertRaises(ValueError):
            decode_cursor("not-a-cursor")

    def test_refresh_skips_tables_requiring_arguments(self):
        client = FakeClient()
        client.table_names.append("requires_args")
        original = self.catalog.client_factory
        self.catalog.client_factory = lambda: client
        try:
            result = self.catalog.refresh()
        finally:
            self.catalog.client_factory = original
        self.assertEqual(result["skipped_table_count"], 1)
        self.assertEqual(result["factor_count"], 2)

    def test_coverage_pages_ids(self):
        identifier = self.service.search_factors("close")["items"][0]["factor_id"]
        result = self.service.get_coverage(identifier, id_page_size=1)
        self.assertEqual(result["ids"], ["A"])
        self.assertEqual(result["date_count"], 3)
        next_page = self.service.get_coverage(identifier, id_cursor=result["next_id_cursor"], id_page_size=1)
        self.assertEqual(next_page["ids"], ["B"])

    def test_read_data_returns_long_rows_and_enforces_limits(self):
        factors = self.service.search_factors(page_size=2)["items"]
        identifiers = [item["factor_id"] for item in factors]
        result = self.service.read_data(identifiers, ["A", "B"], dates=["2026-01-01", "2026-01-02"])
        self.assertEqual(result["cell_count"], 8)
        self.assertEqual(len(result["rows"]), 8)
        self.assertEqual(set(result["rows"][0]), {"date", "asset_id", "factor_id", "factor", "value"})
        with self.assertRaisesRegex(ValueError, "超过上限"):
            self.service.read_data(identifiers, ["A", "B"],
                dates=[f"2026-01-{day:02d}" for day in range(1, 7)])

    def test_read_data_rejects_ambiguous_dates(self):
        identifier = self.service.search_factors("close")["items"][0]["factor_id"]
        with self.assertRaisesRegex(ValueError, "不能同时"):
            self.service.read_data([identifier], ["A"], dates=["2026-01-01"],
                                   start_date="2026-01-01", end_date="2026-01-02")

    def test_server_publishes_readonly_tools(self):
        server = create_server(MCPConfig(catalog_path=Path(self.tmp.name) / "server.sqlite3"), self.service)
        names = {tool.name for tool in asyncio.run(server.list_tools())}
        self.assertEqual(names, {"factor_list_databases", "factor_list_tables",
            "factor_search_factors", "factor_get_factor", "factor_get_coverage", "factor_read_data"})

    def test_http_server_requires_independent_token(self):
        config = MCPConfig(catalog_path=Path(self.tmp.name) / "http.sqlite3",
                           transport="streamable-http", mcp_token_env="QS_TEST_MISSING_MCP_TOKEN")
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("QS_TEST_MISSING_MCP_TOKEN", None)
            with self.assertRaisesRegex(ValueError, "MCP 入站令牌"):
                create_server(config, self.service)

    def test_http_admin_catalog_routes_require_token_and_queue_refresh(self):
        from fastapi.testclient import TestClient
        config = MCPConfig(catalog_path=Path(self.tmp.name) / "admin.sqlite3",
                           transport="streamable-http", mcp_token_env="QS_TEST_MCP_ADMIN_TOKEN")
        with mock.patch.dict("os.environ", {"QS_TEST_MCP_ADMIN_TOKEN": "admin-test-token"}):
            server = create_server(config, self.service)
            manager = server.factor_refresh_manager
            manager.start()
            self.addCleanup(manager.stop)
            with TestClient(server.http_app(path="/mcp", stateless_http=True)) as client:
                self.assertEqual(client.get("/admin/catalog").status_code, 401)
                headers = {"Authorization": "Bearer admin-test-token"}
                status = client.get("/admin/catalog", headers=headers)
                self.assertEqual(status.status_code, 200)
                self.assertEqual(status.json()["factor_count"], 2)
                refresh = client.post("/admin/catalog/refresh", headers=headers)
                self.assertIn(refresh.status_code, (200, 202))


if __name__ == "__main__":
    unittest.main()
