"""真实独立 HTTP 服务的读写、本地引擎和进程恢复对照测试。"""

import datetime as dt
import os
import multiprocessing
from pathlib import Path
import pickle
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import httpx
import pandas as pd

from QuantStudio.Core.CalcEngine import Engine, StackEngine
from QuantStudio.Core.ParallelEngine import ParallelEngine
from QuantStudio.Core.QSObject import Panel
from QuantStudio.Factor.Factor import FactorContext
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QuantStudio.Factor.HDF5DB import HDF5DB
from QSExt.Factor.DuckDB import DuckDB
from QSExt.Factor.RemoteDB import RemoteFactorDB, FactorDBServiceClient
from QSExt.FactorService.protocol import RemoteFactorError


def spawn_read(factor, ids, dates, output):
    """在 spawn 子进程恢复代理并读取，验证 socket 不跨进程。"""
    try:
        output.put((True, factor.readData(ids, dates)))
    except Exception as exc:
        output.put((False, str(exc)))
    finally:
        factor.FactorTable.FactorDB.disconnect()


def local_rolling(f, idt, iid, x, args):
    """只在客户端执行的确定性滚动窗口算子。"""
    import numpy as np
    return np.mean(x[0], axis=0)


def local_section(f, idt, iid, x, args):
    """只在客户端执行的截面去均值算子。"""
    import numpy as np
    return x[0] - np.mean(x[0], axis=-1, keepdims=True)


class TestRemoteService(unittest.TestCase):
    """服务与本地计算运行在不同进程，避免共享全局上下文。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="qs_factor_service_")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        cls.dates = [dt.datetime(2026, 1, 1) + dt.timedelta(days=i) for i in range(6)]
        cls.ids = ["A", "B"]
        cls.frame = pd.DataFrame([[float(i + 1), float(i + 10)] for i in range(6)], index=cls.dates, columns=cls.ids)
        cls.hdf_path = cls.root / "hdf"
        cls.hdf_path.mkdir()
        cls.hdf_write_path = cls.root / "hdf_write"
        cls.hdf_write_path.mkdir()
        cls.parquet_path = cls.root / "parquet"
        cls.parquet_path.mkdir()
        (cls.parquet_path / "minute").mkdir()
        import pyarrow as pa
        import pyarrow.parquet as pq
        pq.write_table(pa.Table.from_pandas(pd.DataFrame({"datetime": cls.dates, "code": ["A"] * len(cls.dates), "close": list(range(len(cls.dates)))})), cls.parquet_path / "minute" / "part.parquet")
        cls.db_path = cls.root / "data.duckdb"
        for db in (DuckDB(args={"DBFile": str(cls.db_path)}, config_file={}), HDF5DB(args={"MainDir": str(cls.hdf_path)}, config_file={})):
            db.connect()
            db.writeData(Panel({"close": cls.frame * 2, "open": cls.frame}), "daily", if_exists="update")
            db.setTableMetaData("daily", key="Description", value="中文说明")
            db.disconnect()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.url = f"http://127.0.0.1:{port}"
        settings = cls.root / "settings.py"
        definitions = [
            {"name": "duck", "class": "QSExt.Factor.DuckDB.DuckDB", "args": {"DBFile": str(cls.db_path), "CoordinatedAccess": True, "LockTimeout": .2}},
            {"name": "hdf", "class": "HDF5DB", "args": {"MainDir": str(cls.hdf_path)}},
            {"name": "hdf_write", "class": "HDF5DB", "args": {"MainDir": str(cls.hdf_write_path)}},
            {"name": "parquet", "class": "QSExt.Factor.DuckDB.DuckDB", "args": {"DBFile": ":memory:", "ParquetDir": str(cls.parquet_path)}},
        ]
        config = {"ServiceID": "test-service", "Port": port, "Auth": {"TokenEnv": "QS_TEST_SERVICE_TOKEN"}, "Databases": {"duck": {"ResourceID": "duck-resource", "Access": "read_write"}, "hdf": {"ResourceID": "hdf-resource", "Access": "read"}}}
        config["Databases"].update(hdf_write={"ResourceID": "hdf-write-resource", "Access": "read_write"}, parquet={"ResourceID": "parquet-resource", "Access": "read_write"})
        settings.write_text("FACTOR_DATABASES = " + repr(definitions) + "\nFACTOR_SERVICE = " + repr(config) + "\n", encoding="utf-8")
        cls.old_token = os.environ.get("QS_TEST_CLIENT_TOKEN")
        os.environ["QS_TEST_CLIENT_TOKEN"] = "temporary-test-value"
        cls.addClassCleanup(cls.restore_env)
        env = os.environ.copy()
        env["QS_TEST_SERVICE_TOKEN"] = os.environ["QS_TEST_CLIENT_TOKEN"]
        env["PYTHONIOENCODING"] = "utf-8"
        cls.log = (cls.root / "server.log").open("w", encoding="utf-8")
        cls.addClassCleanup(cls.log.close)
        script = Path(__file__).resolve().parents[1] / "scripts" / "run_factor_service.py"
        cls.process = subprocess.Popen([sys.executable, str(script), "--settings", str(settings)], env=env, stdout=cls.log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        cls.addClassCleanup(cls.stop_server)
        for _ in range(160):
            try:
                if httpx.get(cls.url + "/api/factor/v1/health", timeout=.3).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if cls.process.poll() is not None:
                raise RuntimeError((cls.root / "server.log").read_text(encoding="utf-8"))
            time.sleep(.05)
        else:
            raise RuntimeError("测试服务启动超时")

    @classmethod
    def restore_env(cls):
        if cls.old_token is None:
            os.environ.pop("QS_TEST_CLIENT_TOKEN", None)
        else:
            os.environ["QS_TEST_CLIENT_TOKEN"] = cls.old_token

    @classmethod
    def stop_server(cls):
        if os.name == "nt" and cls.process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(cls.process.pid), "/T", "/F"], capture_output=True, check=False)
        else:
            cls.process.terminate()
        try:
            cls.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=10)
        cls.log.close()
        # Windows 进程树的继承句柄可能在退出通知后才释放。
        time.sleep(.2)

    def connect(self, name):
        db = RemoteFactorDB(args={"ServerURL": self.url, "Database": name, "TokenEnv": "QS_TEST_CLIENT_TOKEN"}).connect()
        self.addCleanup(db.disconnect)
        return db

    def test_directory_and_both_backends(self):
        with FactorDBServiceClient(self.url, "QS_TEST_CLIENT_TOKEN") as service:
            self.assertEqual({row["name"] for row in service.listDatabases()}, {"duck", "hdf", "hdf_write", "parquet"})
        for backend in ("duck", "hdf"):
            with self.subTest(backend=backend):
                db = self.connect(backend)
                self.assertIn("daily", db.TableNames)
                ft = db.getTable("daily")
                self.assertEqual(ft.getMetaData("Description"), "中文说明")
                data = ft.readData(["close", "open"], ["B", "A"], self.dates[1:])
                pd.testing.assert_frame_equal(data.iloc[0], (self.frame * 2).loc[self.dates[1:], ["B", "A"]], check_index_type=False)
                pd.testing.assert_frame_equal(ft.getFactor("close").readData(self.ids, self.dates), self.frame * 2, check_index_type=False)
                self.assertEqual(ft.getID(), self.ids)
                self.assertEqual(ft.getDateTime(), self.dates)

    def test_local_database_and_http_service_share_file(self):
        """QSWeb 本地访问与独立 FactorService 使用同一文件且同时逻辑连接。"""
        remote = self.connect("duck")
        local = DuckDB(args={"DBFile": str(self.db_path), "CoordinatedAccess": True}, config_file={}).connect()
        self.addCleanup(local.disconnect)
        try:
            remote.writeData(Panel({"value": self.frame}), "coordinated_local_http")
            table = local.getTable("coordinated_local_http")
            pd.testing.assert_frame_equal(table.readData(["value"], self.ids, self.dates).iloc[0], self.frame, check_index_type=False)
            local.writeData(Panel({"value": self.frame * 3}), "coordinated_local_http")
            pd.testing.assert_frame_equal(remote.getTable("coordinated_local_http").getFactor("value").readData(self.ids, self.dates), self.frame * 3, check_index_type=False)
            local.setTableMetaData("coordinated_local_http", key="Description", value="本地更新")
            self.assertEqual(remote.getTable("coordinated_local_http").getMetaData("Description"), "本地更新")
            remote.addFactor(table_name="coordinated_local_http", field_types={"new_field": "DOUBLE"})
            self.assertIn("new_field", table.FactorNames)
        finally:
            remote.deleteTable("coordinated_local_http")

    def test_local_graph_with_and_without_cache(self):
        db = self.connect("duck")
        ft = db.getTable("daily")
        factor = ft.getFactor("close") / ft.getFactor("open") - 1
        expected = self.frame * 0 + 1
        pd.testing.assert_frame_equal(factor.readData(self.ids, self.dates), expected, check_index_type=False)
        with tempfile.TemporaryDirectory() as tmp:
            with FeatherFactorCache(args={"DTRuler": self.dates, "CacheDir": tmp}) as cache:
                with FactorContext(DTRuler=self.dates, SectionIDs=self.ids, DataCache=cache, DataVersion="immutable-test-fixture"), Engine(args={"IOConcurrentNum": 1}):
                    with mock.patch.object(db._client, "readBatch", wraps=db._client.readBatch) as read:
                        first = factor.readData(self.ids, self.dates)
                        second = factor.readData(self.ids, self.dates)
                        self.assertEqual(read.call_count, 1)
                pd.testing.assert_frame_equal(first, expected, check_index_type=False)
                pd.testing.assert_frame_equal(second, expected, check_index_type=False)

    def test_local_lock_timeout_is_reported_without_mutation(self):
        """外部进程持锁时，HTTP 写入返回明确的未执行状态。"""
        remote = self.connect("duck")
        local = DuckDB(args={"DBFile": str(self.db_path), "CoordinatedAccess": True}, config_file={}).connect()
        self.addCleanup(local.disconnect)
        with local.session():
            with self.assertRaises(RemoteFactorError) as error:
                remote.createTable(table_name="should_not_exist", field_types={"value": "DOUBLE"})
            self.assertEqual(error.exception.code, "RESOURCE_BUSY")
            self.assertEqual(error.exception.details["effect"], "not_started")
        self.assertNotIn("should_not_exist", remote.TableNames)

    def test_write_metadata_extensions_and_readonly(self):
        db = self.connect("duck")
        db.writeData(Panel({"value": self.frame}), "written")
        db.setFactorMetaData("written", "value", key="Description", value="远程写入")
        self.assertEqual(db.getTable("written").getFactorMetaData(["value"], "Description").iloc[0], "远程写入")
        db.renameFactor("written", "value", "renamed")
        db.renameTable("written", "renamed_table")
        self.assertIn("renamed", db.getTable("renamed_table").FactorNames)
        db.deleteTable("renamed_table")
        db.createTable(table_name="created", field_types={"value": "DOUBLE"})
        db.deleteTable("created")
        readonly = self.connect("hdf")
        with self.assertRaises(RemoteFactorError) as error:
            readonly.deleteTable("daily")
        self.assertEqual(error.exception.status, 403)
        self.assertIn("daily", readonly.TableNames)

    def test_pickle_rebuild_and_new(self):
        factor = self.connect("duck").getTable("daily").getFactor("close")
        restored = pickle.loads(pickle.dumps(factor))
        self.addCleanup(restored.FactorTable.FactorDB.disconnect)
        self.assertEqual(restored.QSID, factor.QSID)
        pd.testing.assert_frame_equal(restored.readData(self.ids, self.dates), self.frame * 2, check_index_type=False)
        other = factor.FactorTable.new(args={"LookBack": 3})
        self.assertEqual(other.Args.BackendArgs["LookBack"], 3)
        clone = type(factor).from_dependencies(factor.Dependencies, args=factor.Args)
        self.assertEqual(clone.QSID, factor.QSID)
        factor.Args.RemoteDescriptor["target"]["factor_name"] = "open"
        with self.assertRaises(RemoteFactorError):
            factor.readData(self.ids, self.dates)

    def test_hdf_write_and_parquet_readonly_capability(self):
        hdf = self.connect("hdf_write")
        hdf.writeData(Panel({"value": self.frame}), "created")
        pd.testing.assert_frame_equal(hdf.getTable("created").getFactor("value").readData(self.ids, self.dates), self.frame, check_index_type=False)
        operation = hdf.getOperation(hdf.LastOperationID)
        self.assertEqual(operation["state"], "SUCCEEDED")
        hdf.deleteTable("created")
        parquet = self.connect("parquet")
        table = parquet.getTable("minute")
        self.assertFalse(table._description["table_writable"])
        self.assertEqual(table.getFactor("close").readData(["A"], self.dates).iloc[:, 0].tolist(), list(range(len(self.dates))))
        with self.assertRaises(RemoteFactorError):
            parquet.writeData(Panel({"close": self.frame}), "minute")
        self.assertIn("minute", parquet.TableNames)

    def test_spawn_and_parallel_engine(self):
        factor = self.connect("duck").getTable("daily").getFactor("close")
        ctx = multiprocessing.get_context("spawn")
        output = ctx.Queue()
        process = ctx.Process(target=spawn_read, args=(factor, self.ids, self.dates, output))
        process.start()
        try:
            success, value = output.get(timeout=30)
            self.assertTrue(success, value)
            pd.testing.assert_frame_equal(value, self.frame * 2, check_index_type=False)
        finally:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            output.close()
        for cached in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                with FeatherFactorCache(args={"DTRuler": self.dates, "CacheDir": tmp, "PIDs": ["0", "1"]}) as cache:
                    with FactorContext(DTRuler=self.dates, SectionIDs=self.ids, PIDList=["0", "1"], DataCache=cache if cached else None), ParallelEngine(args={"IOConcurrentNum": 1}):
                        actual = (factor * 2).readData(self.ids, self.dates)
                    pd.testing.assert_frame_equal(actual, self.frame * 4, check_index_type=False)

    def test_rolling_section_and_active_table_context(self):
        from QuantStudio.Factor.FactorOperation import makeFactorOperator, OperandSpec
        ft = self.connect("duck").getTable("daily")
        close = ft.getFactor("close")
        rolling = makeFactorOperator(local_rolling, "Time", args={"LookBack": [2], "DTMode": "单时点", "IDMode": "多ID"}, operand_info=(OperandSpec(),))(close)
        actual = rolling.readData(self.ids, self.dates[2:], dt_ruler=self.dates)
        pd.testing.assert_frame_equal(actual, (self.frame * 2).rolling(3).mean().iloc[2:], check_index_type=False)
        section = makeFactorOperator(local_section, "Section", args={"DTMode": "多时点"}, operand_info=(OperandSpec(),))(close)
        actual = section.readData(self.ids, self.dates)
        expected = (self.frame * 2).sub((self.frame * 2).mean(axis=1), axis=0)
        pd.testing.assert_frame_equal(actual, expected, check_index_type=False)
        with FactorContext(DTRuler=self.dates, SectionIDs=self.ids), StackEngine(args={"IOConcurrentNum": 1}):
            result = ft.readData(["close", "open"], ["B"], self.dates[1:])
        pd.testing.assert_frame_equal(result.iloc[0], (self.frame * 2).loc[self.dates[1:], ["B"]], check_index_type=False)

    def test_backtest_ic_uses_remote_sources_locally(self):
        """真实 IC 回测算子在本地使用远程数据，与本地数据因子一致。"""
        from QuantStudio.BackTest.SectionFactor.IC import CalcIC
        from QuantStudio.Factor.Factor import DataFactor, FactorLocalContext
        table = self.connect("duck").getTable("daily")
        operator = CalcIC(descriptor_ids=self.ids, lookback=1, period_lookback=1, corr_method="spearman")
        remote = operator(table.getFactor("close"), price=table.getFactor("open"), factor_name_list=["signal"])
        local = operator(DataFactor(self.frame * 2), price=DataFactor(self.frame), factor_name_list=["signal"])
        values = []
        for factor in (local, remote):
            with tempfile.TemporaryDirectory() as tmp:
                with FeatherFactorCache(args={"DTRuler": self.dates, "CacheDir": tmp}) as cache:
                    context = FactorContext(DTRuler=self.dates, SectionIDs=["signal"], DataCache=cache)
                    request = FactorLocalContext(DTs=self.dates[1:], IDs=["signal"], SectionIDs=["signal"])
                    values.append(Engine(args={"IOConcurrentNum": 1}).run([factor], context, fwd_data_list=[request])[0])
        pd.testing.assert_frame_equal(values[1], values[0])

    def test_auth_protocol_and_arbitrary_graph_rejected(self):
        response = httpx.get(self.url + "/api/factor/v1/databases")
        self.assertEqual(response.status_code, 401)
        db = self.connect("duck")
        client = db._client
        request = {"request_id": "invalid", "resource_id": db._identity["resource_id"], "config_revision": db._identity["config_revision"], "graph": {"operator": "exec"}}
        with self.assertRaises(RemoteFactorError) as error:
            client._request("POST", "/databases/duck/invoke", request)
        self.assertEqual(error.exception.status, 422)
        with self.assertRaises(RemoteFactorError) as error:
            db._call({"kind": "database"}, "execute", {"sql_str": "DROP TABLE qs_daily"})
        self.assertEqual(error.exception.status, 403)
        self.assertIn("daily", db.TableNames)

    def test_sql_fragments_and_python_filter_are_rejected(self):
        db = self.connect("duck")
        for args in ({"TableType": "WideTable); __import__('os')"}, {"FilterCondition": "1=1; DROP TABLE qs_daily; --"}, {"AdditionalCondition": {"code": "A') OR 1=1 --"}}):
            with self.assertRaises(RemoteFactorError):
                db.getTable("daily", args=args)
        table = db.getTable("daily")
        self.assertEqual(table.getFilteredID(self.dates[0], ids=["A"]), self.ids)
        self.assertEqual(table.getFilteredID(self.dates[0], id_filter_str="(@close > 5) & (@open > 0)"), ["B"])
        self.assertEqual(table.getFilteredID(self.dates[0], id_filter_str="@_ID.isin(['A'])"), ["A"])
        with self.assertRaises(RemoteFactorError):
            table.getIDMask(self.dates[0], id_filter_str="__import__('os').getcwd() or True")
        injected = table.getFactor("close").readData(["A'); DROP TABLE qs_daily; --"], self.dates)
        self.assertTrue(injected.isna().all().all())
        for key, value in (("TableClass", "WideTable); __import__('os')"), ("FTArgs", {"TableType": "WideTable); __import__('os')"})):
            with self.assertRaises(RemoteFactorError):
                db.setTableMetaData("daily", key=key, value=value)
        self.assertIn("daily", db.TableNames)
        quoted = self.frame.iloc[:, [0]].copy()
        quoted.columns = ["Q'1"]
        db.writeData(Panel({"value": quoted}), "quoted_ids")
        quote_table = db.getTable("quoted_ids")
        pd.testing.assert_frame_equal(quote_table.getFactor("value").readData(["Q'1"], self.dates), quoted, check_index_type=False)
        self.assertEqual(quote_table.getDateTime(iid="Q'1"), self.dates)
        db.deleteTable("quoted_ids")


if __name__ == "__main__":
    unittest.main()
