"""配置、串行队列、写入去重和协议边界测试。"""

from pathlib import Path
import tempfile
import threading
import time
import unittest
from filelock import FileLock

from QuantStudio.Factor.FactorDB import WritableFactorDB
from QSExt.RuntimeConfig.config import DBDef
from QSExt.FactorService.config import ServiceConfig, validate_definitions, load_settings
from QSExt.FactorService.executor import ResourceExecutor
from QSExt.FactorService.protocol import Request, RemoteFactorError, digest
from QSExt.FactorService.registry import Registry


class FixtureDB(WritableFactorDB):
    """记录连接所有者的测试后端，不访问外部资源。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = 0
        self.owner = None

    def connect(self):
        self.owner = threading.get_ident()
        return self

    def renameTable(self, old_table_name, new_table_name):
        if threading.get_ident() != self.owner:
            raise RuntimeError("连接跨线程访问")
        self.calls += 1
        return {"calls": self.calls}

    def deleteTable(self, table_name):
        self.calls += 1
        raise RuntimeError("模拟后端部分失败")


class TestProtocol(unittest.TestCase):
    """在不启动网络服务时覆盖状态转换和资源所有权。"""

    def registry(self, **limit_changes):
        config = ServiceConfig(ServiceID="test", Databases={"test": {"ResourceID": "resource", "Access": "read_write"}}, Limits={"QueueTimeoutSeconds": 1, **limit_changes})
        registry = Registry([DBDef(name="test", class_path=__name__ + ".FixtureDB")], config)
        self.addCleanup(registry.close)
        return registry

    def test_first_connect_lock_timeout_can_retry(self):
        """第一次惰性连接被外部锁阻塞时不创建残余连接，解锁后可重试。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "data.duckdb")
            config_path = Path(tmp) / "duck.json"
            config_path.write_text("{}", encoding="utf-8")
            config = ServiceConfig(ServiceID="test", Databases={"test": {"ResourceID": "resource"}})
            registry = Registry([DBDef(name="test", class_path="QSExt.Factor.DuckDB.DuckDB", config_file=str(config_path), args={
                "DBFile": path, "CoordinatedAccess": True, "LockTimeout": .05,
            })], config)
            resource = registry.resource("test")
            try:
                with FileLock(path + ".qs.lock"):
                    with self.assertRaises(RemoteFactorError) as error:
                        resource.executor.submit(resource.connect).result(timeout=2)
                    self.assertEqual(error.exception.code, "RESOURCE_BUSY")
                    self.assertEqual(error.exception.details["effect"], "not_started")
                    self.assertIsNone(resource.db)
                result = resource.executor.submit(lambda: (resource.connect().TableNames, resource.db.Connection)).result(timeout=2)
                self.assertEqual(result, ([], None))
            finally:
                registry.close()

    def request(self, registry, **changes):
        resource = registry.resource("test")
        values = {"request_id": "request", "resource_id": "resource", "config_revision": resource.revision, "operation": "renameTable", "kwargs": {"old_table_name": "old", "new_table_name": "new"}, "operation_id": "operation", "epoch": registry.epoch, "expires_at": time.time() + 30}
        return Request(**(values | changes))

    def test_operation_deduplication_and_conflict(self):
        registry = self.registry()
        request = self.request(registry)
        first = registry.submit("test", request, "invoke")
        second = registry.submit("test", request, "invoke")
        self.assertIs(first, second)
        self.assertEqual(first.result(timeout=2), {"calls": 1})
        self.assertEqual(registry.operation("operation")["state"], "SUCCEEDED")
        conflicting = request.model_copy(update={"kwargs": {"old_table_name": "other", "new_table_name": "new"}})
        with self.assertRaises(RemoteFactorError) as error:
            registry.submit("test", conflicting, "invoke")
        self.assertEqual(error.exception.code, "OPERATION_CONFLICT")

    def test_restart_expiry_and_partial_failure(self):
        registry = self.registry()
        for request, code in ((self.request(registry, epoch="old-epoch"), "OPERATION_UNKNOWN"), (self.request(registry, expires_at=time.time() - 1), "OPERATION_EXPIRED")):
            with self.assertRaises(RemoteFactorError) as error:
                registry.submit("test", request, "invoke")
            self.assertEqual(error.exception.code, code)
        request = self.request(registry, operation="deleteTable", kwargs={"table_name": "daily"})
        with self.assertRaises(RuntimeError):
            registry.submit("test", request, "invoke").result(timeout=2)
        self.assertEqual(registry.operation("operation")["effect"], "unknown")
        self.assertEqual(registry.operation("missing")["state"], "UNKNOWN")

    def test_queue_limit_and_not_started_timeout(self):
        release = threading.Event()
        started = threading.Event()
        calls = []
        executor = ResourceExecutor(1, .05, lambda: None)
        self.addCleanup(executor.close)
        def block():
            started.set()
            release.wait(timeout=2)
        running = executor.submit(block)
        self.assertTrue(started.wait(timeout=1))
        queued = executor.submit(lambda: calls.append(True))
        try:
            with self.assertRaises(RemoteFactorError) as error:
                executor.submit(lambda: None)
            self.assertEqual(error.exception.code, "QUEUE_FULL")
            time.sleep(.08)
        finally:
            release.set()
        running.result(timeout=1)
        with self.assertRaises(RemoteFactorError) as error:
            queued.result(timeout=1)
        self.assertEqual(error.exception.details["effect"], "not_started")
        self.assertEqual(calls, [])

    def test_definitions_and_config_inheritance(self):
        config = ServiceConfig(ServiceID="s", Databases={"one": {"ResourceID": "one"}, "two": {"ResourceID": "two"}})
        with self.assertRaises(ValueError):
            validate_definitions([DBDef(name="one", class_path="HDF5DB", args={"MainDir": "."}), DBDef(name="two", class_path="HDF5DB", args={"MainDir": "."})], config)
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "parent.py"
            child = Path(tmp) / "child.py"
            parent.write_text("FACTOR_DATABASES = []\nFACTOR_SERVICE = {'ServiceID': 's', 'Databases': {}}\n", encoding="utf-8")
            child.write_text("__INHERIT_FROM__ = " + repr(str(parent)) + "\n", encoding="utf-8")
            definitions, loaded = load_settings(child)
            self.assertEqual(definitions, [])
            self.assertEqual(loaded.ServiceID, "s")
        self.assertEqual(digest({"a": 1, "b": {"x": 2}}), digest({"b": {"x": 2}, "a": 1}))

    def test_standard_read_does_not_use_global_graph_context(self):
        """服务读取不会受同进程中的本地计算上下文影响。"""
        import datetime as dt
        import pandas as pd
        from unittest import mock
        from QuantStudio.Core.QSObject import Panel
        from QuantStudio.Core.CalcEngine import Engine
        from QuantStudio.Factor.Factor import FactorContext
        from QuantStudio.Factor.HDF5DB import HDF5DB
        from QSExt.FactorService.adapters import read_standard

        dates = [dt.datetime(2026, 1, 1)]
        with tempfile.TemporaryDirectory() as tmp:
            db = HDF5DB(args={"MainDir": tmp}, config_file={}).connect()
            try:
                expected = pd.DataFrame([[2.]], index=dates, columns=["A"])
                db.writeData(Panel({"value": expected}), "daily")
                factor = db.getTable("daily").getFactor("value")
                with FactorContext(DTRuler=dates, SectionIDs=["A"]), mock.patch.object(Engine, "run", side_effect=AssertionError("不允许服务端计算图")):
                    actual = read_standard(factor, {"ids": ["A"], "dts": dates})
                pd.testing.assert_frame_equal(actual, expected, check_index_type=False)
            finally:
                db.disconnect()


if __name__ == "__main__":
    unittest.main()
