"""DuckDB 跨进程短连接、原子写入和本地计算图回归测试。"""

import datetime as dt
import multiprocessing
from contextlib import chdir
from pathlib import Path
import pickle
import tempfile
import threading
import unittest
from unittest import mock

import duckdb
from filelock import FileLock, Timeout
import pandas as pd

from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.CalcEngine import Engine, StackEngine
from QuantStudio.Core.ParallelEngine import ParallelEngine
from QuantStudio.Core.QSObject import Panel
from QuantStudio.Factor.Factor import FactorContext
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QSExt.Factor.DuckDB import DuckDB


def open_db(path, **kwargs):
    """创建已逻辑连接的协调因子库。"""
    return DuckDB(args={"DBFile": str(path), "CoordinatedAccess": True} | kwargs, config_file={}).connect()


def concurrent_writer(path, field, ready, start, output):
    """多个常驻对象同时更新同一行中的不同因子，验证更新不会相互覆盖。"""
    try:
        db = open_db(path)
        ready.set()
        if not start.wait(20):
            raise RuntimeError("启动信号超时")
        for value in range(1, 6):
            frame = pd.DataFrame([[float(value)]], index=[dt.datetime(2026, 1, 1)], columns=["A"])
            db.writeData(Panel({field: frame}), "daily")
        output.put(None)
    except BaseException as exc:
        output.put(repr(exc))


def hold_session(path, ready, release):
    """持锁并写入未提交数据，供超时、进程退出和回滚测试使用。"""
    db = open_db(path)
    with db.session():
        db.execute("UPDATE qs_daily SET close = 999")
        ready.set()
        if not release.wait(30):
            raise RuntimeError("释放信号超时")


def spawn_factor(factor, ids, dates, output):
    """从序列化的本地因子恢复协调访问。"""
    try:
        output.put((True, factor.readData(ids, dates)))
    except BaseException as exc:
        output.put((False, repr(exc)))


def assert_unlocked(f, idt, iid, x, args):
    """算子计算期间允许其他进程打开同一文件。"""
    with FileLock(args["path"] + ".qs.lock").acquire(timeout=0):
        connection = duckdb.connect(args["path"])
        connection.close()
    return x[0] * 3


class TestDuckDBCoordinated(unittest.TestCase):
    """仅使用临时磁盘库和真实 spawn 进程。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="qs_duck_coordinated_")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "data.duckdb"
        self.db = open_db(self.path)
        self.addCleanup(self.db.disconnect)
        self.dates = [dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 2)]
        self.ids = ["A", "B"]
        self.frame = pd.DataFrame([[1., 2.], [3., 4.]], index=self.dates, columns=self.ids)
        self.db.writeData(Panel({"close": self.frame, "volume": self.frame * 10}), "daily")

    def stop(self, process):
        """保证失败的测试也能清理子进程。"""
        if process.is_alive():
            process.terminate()
        process.join(10)
        self.assertFalse(process.is_alive())

    def read(self, db=None):
        return (db or self.db).getTable("daily").readData(["close"], self.ids, self.dates).iloc[0]

    def test_logical_connections_and_native_release(self):
        second = open_db(self.path)
        self.addCleanup(second.disconnect)
        self.assertIsNone(self.db.Connection)
        self.assertIsNone(second.Connection)
        pd.testing.assert_frame_equal(self.read(second), self.frame, check_index_type=False)
        with duckdb.connect(str(self.path)) as native:
            self.assertEqual(native.execute("SELECT count(*) FROM qs_daily").fetchone()[0], 4)
        self.db.disconnect()
        with self.assertRaises(__QS_Error__):
            self.db.TableNames
        self.db.connect()
        self.assertEqual(self.db.TableNames, ["daily"])

    def test_complete_write_is_atomic_on_failure(self):
        self.db.Args.CheckWriteData = True
        with mock.patch.object(self.db, "_adjustWriteData", side_effect=ValueError("写入失败")):
            with self.assertRaises(ValueError):
                self.db.writeData(Panel({"close": self.frame * 2}), "daily")
        pd.testing.assert_frame_equal(self.read(), self.frame, check_index_type=False)
        self.assertIsNone(self.db.Connection)
        with FileLock(str(self.path) + ".qs.lock").acquire(timeout=0):
            pass

    def test_batch_transaction_and_nested_failure(self):
        with self.assertRaises(ValueError):
            with self.db.session():
                self.db.createTable("uncommitted", {"value": "DOUBLE"})
                self.db.setTableMetaData("daily", key="Description", value="不应提交")
                raise ValueError("失败")
        self.assertNotIn("uncommitted", self.db.TableNames)
        self.assertEqual(self.db.getTable("daily").getMetaData("Description"), "")
        with self.assertRaises(__QS_Error__):
            with self.db.session():
                self.db.execute("UPDATE qs_daily SET close = 100")
                try:
                    self.db.getTable("不存在")
                except __QS_Error__:
                    pass
        pd.testing.assert_frame_equal(self.read(), self.frame, check_index_type=False)
        with self.db.session():
            self.db.createTable("committed", {"value": "DOUBLE"})
            self.db.connect()  # writeData 的异常恢复路径不会关闭活动会话。
        self.assertIn("committed", self.db.TableNames)

    def test_cursor_lifetime_and_shared_transaction(self):
        with self.assertRaises(__QS_Error__):
            self.db.cursor()
        with self.assertRaises(ValueError):
            with self.db.session():
                cursor = self.db.cursor()
                cursor.execute("UPDATE qs_daily SET close = 100")
                self.assertEqual(cursor.execute("SELECT close FROM qs_daily LIMIT 1").fetchone()[0], 100)
                raise ValueError("回滚")
        with self.assertRaises(__QS_Error__):
            cursor.fetchall()
        pd.testing.assert_frame_equal(self.read(), self.frame, check_index_type=False)
        with self.assertRaises(__QS_Error__):
            with self.db.session():
                cursor = self.db.cursor()
                cursor.execute("UPDATE qs_daily SET close = 100")
                try:
                    cursor.execute("SELECT * FROM missing_table")
                except duckdb.Error:
                    pass
        pd.testing.assert_frame_equal(self.read(), self.frame, check_index_type=False)

    def test_metadata_and_existing_table_refresh(self):
        table = self.db.getTable("daily")
        second = open_db(self.path)
        self.addCleanup(second.disconnect)
        second.addFactor("daily", {"new_factor": "DOUBLE"})
        second.setTableMetaData("daily", key="Description", value="新描述")
        second.setFactorMetaData("daily", "close", key="Description", value="收盘价")
        second.createTable("other", {"x": "DOUBLE"})
        self.assertIn("other", self.db.TableNames)
        self.assertIn("new_factor", table.FactorNames)
        self.assertEqual(table.getMetaData("Description"), "新描述")
        self.assertEqual(table.getFactorMetaData(["close"], "Description")["close"], "收盘价")
        second.renameFactor("daily", "new_factor", "renamed")
        self.assertIn("renamed", table.FactorNames)
        second.deleteFactor("daily", ["renamed"])
        self.assertNotIn("renamed", table.FactorNames)
        second.renameTable("other", "renamed_table")
        self.assertIn("renamed_table", self.db.TableNames)
        second.deleteTable("renamed_table")
        self.assertNotIn("renamed_table", self.db.TableNames)

    def test_sql_entry_refreshes_catalog(self):
        self.db.fetchall("ALTER TABLE qs_daily ADD COLUMN sql_factor DOUBLE")
        self.assertIn("sql_factor", self.db.getTable("daily").FactorNames)

    def test_canonical_path_uses_same_lock(self):
        alias = open_db(self.path.parent / ".." / self.path.parent.name / self.path.name, LockTimeout=.05)
        self.addCleanup(alias.disconnect)
        self.assertEqual(alias._FileLock.lock_file, self.db._FileLock.lock_file)
        with self.db.session():
            with self.assertRaises(Timeout):
                alias.TableNames
        self.assertEqual(alias.TableNames, ["daily"])

    def test_threads_cannot_share_active_connection(self):
        db = open_db(self.path, LockTimeout=.05)
        self.addCleanup(db.disconnect)
        output = []
        def read():
            output.append(db.Connection)
            for action in (lambda: db.fetchall("SELECT 1"), db.connect, db.disconnect):
                try:
                    action()
                except Timeout:
                    output.append("timeout")
        with db.session():
            thread = threading.Thread(target=read)
            thread.start()
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(output, [None, "timeout", "timeout", "timeout"])

    def test_concurrent_processes_preserve_other_factors(self):
        ctx = multiprocessing.get_context("spawn")
        start, ready1, ready2, output = ctx.Event(), ctx.Event(), ctx.Event(), ctx.Queue()
        processes = [ctx.Process(target=concurrent_writer, args=(str(self.path), field, ready, start, output)) for field, ready in (("close", ready1), ("volume", ready2))]
        for process in processes:
            process.start()
            self.addCleanup(self.stop, process)
        try:
            self.assertTrue(ready1.wait(20))
            self.assertTrue(ready2.wait(20))
            start.set()
            for _ in processes:
                self.assertIsNone(output.get(timeout=30))
            with self.db.session():
                value = self.db.fetchall("SELECT close, volume FROM qs_daily WHERE code = 'A' ORDER BY datetime LIMIT 1")
            self.assertEqual(value, [(5., 5.)])
        finally:
            start.set()
            output.close()

    def test_process_timeout_and_crash_release_lock(self):
        db = open_db(self.path, LockTimeout=.1)
        self.addCleanup(db.disconnect)
        ctx = multiprocessing.get_context("spawn")
        ready, release = ctx.Event(), ctx.Event()
        process = ctx.Process(target=hold_session, args=(str(self.path), ready, release))
        process.start()
        self.addCleanup(self.stop, process)
        self.assertTrue(ready.wait(20))
        with self.assertRaises(Timeout):
            db.TableNames
        self.assertIsNone(db.Connection)
        process.terminate()
        process.join(10)
        pd.testing.assert_frame_equal(self.read(db), self.frame, check_index_type=False)

    def test_pickle_and_node_reconstruction(self):
        table = self.db.getTable("daily")
        factor = table.getFactor("close")
        restored = pickle.loads(pickle.dumps(factor))
        self.addCleanup(restored.FactorTable.FactorDB.disconnect)
        pd.testing.assert_frame_equal(restored.readData(self.ids, self.dates), self.frame, check_index_type=False)
        self.assertEqual(table.new().FactorNames, table.FactorNames)
        with self.db.session():
            with self.assertRaises(__QS_Error__):
                pickle.dumps(factor)

    def test_relative_paths_remain_stable_after_pickle(self):
        with chdir(self.tmp.name):
            db = open_db("data.duckdb")
            self.addCleanup(db.disconnect)
            data = pickle.dumps(db)
        restored = pickle.loads(data)
        self.addCleanup(restored.disconnect)
        self.assertEqual(restored._DBPath, self.db._DBPath)
        pd.testing.assert_frame_equal(self.read(restored), self.frame, check_index_type=False)

    def test_open_failure_releases_coordination_lock(self):
        with mock.patch("duckdb.connect", side_effect=RuntimeError("模拟打开失败")):
            with self.assertRaises(RuntimeError):
                self.db.TableNames
        self.assertIsNone(self.db.Connection)
        with FileLock(str(self.path) + ".qs.lock").acquire(timeout=0):
            pass
        self.assertEqual(self.db.TableNames, ["daily"])

    def test_parquet_disk_metadata_and_directory_refresh(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        root = Path(self.tmp.name) / "market"
        (root / "minute").mkdir(parents=True)
        pq.write_table(pa.Table.from_pandas(pd.DataFrame({"datetime": self.dates, "code": ["A", "A"], "close": [1., 2.]})), root / "minute" / "part.parquet")
        metadata = root / "_metadata.duckdb"
        duckdb.connect(str(metadata)).close()
        args = {"ParquetDir": str(root), "CoordinatedAccess": True}
        first = DuckDB(args=args, config_file={}).connect()
        second = DuckDB(args=args, config_file={}).connect()
        self.addCleanup(first.disconnect)
        self.addCleanup(second.disconnect)
        table = first.getTable("minute")
        self.assertEqual(table.readData(["close"], ["A"], self.dates).iloc[0, 1, 0], 2.)
        second.setTableMetaData("minute", key="Description", value="分钟行情")
        self.assertEqual(table.getMetaData("Description"), "分钟行情")
        (root / "other").mkdir()
        pq.write_table(pa.Table.from_pandas(pd.DataFrame({"datetime": self.dates, "code": ["A", "A"], "value": [3., 4.]})), root / "other" / "part.parquet")
        self.assertIn("other", first.TableNames)
        with self.assertRaises(__QS_Error__):
            first.writeData(Panel({"close": self.frame}), "minute")
        self.assertIsNone(first.Connection)

    def test_spawn_local_factor(self):
        ctx = multiprocessing.get_context("spawn")
        output = ctx.Queue()
        process = ctx.Process(target=spawn_factor, args=(self.db.getTable("daily").getFactor("close"), self.ids, self.dates, output))
        process.start()
        self.addCleanup(self.stop, process)
        try:
            success, value = output.get(timeout=30)
            self.assertTrue(success, value)
            pd.testing.assert_frame_equal(value, self.frame, check_index_type=False)
        finally:
            output.close()

    def test_graph_cache_and_parallel_engine(self):
        table = self.db.getTable("daily")
        factor = table.getFactor("close")
        for parallel in (False, True):
            for cached in (False, True):
                with tempfile.TemporaryDirectory() as root:
                    with FeatherFactorCache(args={"DTRuler": self.dates, "CacheDir": root, "PIDs": ["0", "1"]}) as cache:
                        with FactorContext(DTRuler=self.dates, SectionIDs=self.ids, PIDList=["0", "1"] if parallel else ["0"], DataCache=cache if cached else None), (ParallelEngine if parallel else Engine)(args={"IOConcurrentNum": 1}):
                            actual = (factor * 2).readData(self.ids, self.dates)
                        pd.testing.assert_frame_equal(actual, self.frame * 2, check_index_type=False)
        with FactorContext(DTRuler=self.dates, SectionIDs=self.ids), StackEngine(args={"IOConcurrentNum": 1}):
            actual = table.readData(["close"], self.ids, self.dates).iloc[0]
        pd.testing.assert_frame_equal(actual, self.frame, check_index_type=False)

    def test_local_operator_runs_without_file_lock(self):
        from QuantStudio.Factor.FactorOperation import makeFactorOperator, OperandSpec
        close = self.db.getTable("daily").getFactor("close")
        factor = makeFactorOperator(assert_unlocked, "Point", args={"ModelArgs": {"path": str(self.path)}}, operand_info=(OperandSpec(),))(close)
        pd.testing.assert_frame_equal(factor.readData(self.ids, self.dates), self.frame * 3, check_index_type=False)

    def test_memory_and_invalid_timeout_rejected(self):
        with self.assertRaises(__QS_Error__):
            DuckDB(args={"CoordinatedAccess": True}, config_file={})
        for timeout in (-1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                DuckDB(args={"DBFile": str(self.path), "CoordinatedAccess": True, "LockTimeout": timeout}, config_file={})


if __name__ == "__main__":
    unittest.main()
