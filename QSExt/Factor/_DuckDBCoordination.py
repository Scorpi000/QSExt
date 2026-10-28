"""DuckDB 的短连接会话和因子表协调包装。"""

import os
import threading
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from filelock import FileLock, Timeout

from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.Node import __QS_Context__
from QuantStudio.Factor.FactorTable import FactorTable
from QuantStudio.Factor import FactorUtils


def coordinated(method):
    """使完整的库操作复用同一个短连接会话。"""
    @wraps(method)
    def call(self, *args, **kwargs):
        if not self.Args.CoordinatedAccess:
            return method(self, *args, **kwargs)
        with self.session():
            # 原生 SQL 入口也可能执行 DDL，下一会话重新扫描结构。
            if method.__name__ not in {"fetchall", "getTable", "TableNames", "_getDBFieldInfo", "_hasMetaDataTable"}:
                self._CatalogDirty = True
            return method(self, *args, **kwargs)
    return call


class _SessionCursor:
    """复用会话事务的游标；禁止在会话结束后继续读取。"""

    def __init__(self, db):
        self._db = db
        self._connection = db._Connection
        self._closed = False

    def close(self):
        """关闭游标，不关闭所属会话。"""
        self._closed = True

    def __getattr__(self, name):
        if name not in {"execute", "executemany", "fetchone", "fetchmany", "fetchall", "description", "rowcount"}:
            raise AttributeError(name)
        def check():
            if self._closed or self._db.Connection is not self._connection:
                raise __QS_Error__("协调游标只能在创建它的 session 内使用")
        check()
        value = getattr(self._connection, name)
        if not callable(value):
            return value
        def call(*args, **kwargs):
            check()
            try:
                result = value(*args, **kwargs)
            except BaseException:
                self._db._SessionFailed = True
                raise
            return self if result is self._connection else result
        return call


class CoordinatedDB:
    """为 DuckDB 提供可重入、跨线程和跨进程互斥的会话。"""

    def _initCoordination(self):
        self._LogicalConnected = False
        self._SessionDepth = 0
        self._SessionFailed = False
        self._SessionOwner = None
        self._CatalogStamp = None
        self._CatalogDirty = False
        self._ProcessID = os.getpid()
        self._ThreadLock = threading.RLock()
        self._FileLock = None
        if self.Args.CoordinatedAccess:
            if self.Args.DBFile == ":memory:":
                raise __QS_Error__("CoordinatedAccess 需要磁盘 DBFile，不能使用 :memory:")
            self._DBPath = getattr(self, "_DBPath", None) or os.path.normcase(str(Path(self.Args.DBFile).expanduser().resolve()))
            self._ParquetPath = getattr(self, "_ParquetPath", None) or (str(Path(self.Args.ParquetDir).expanduser().resolve()) if self.Args.ParquetDir else "")
            self._FileLock = FileLock(self._DBPath + ".qs.lock")

    def _catalogStamp(self):
        paths = [Path(self._DBPath), Path(self._DBPath + ".wal")]
        if self._ParquetPath:
            paths.append(Path(self._ParquetPath))
        result = []
        for path in paths:
            try:
                stat = path.stat()
                result.append((stat.st_mtime_ns, stat.st_size))
            except FileNotFoundError:
                result.append(None)
        return tuple(result)

    @contextmanager
    def _coordinationThread(self):
        """在超时范围内取得当前对象的线程锁。"""
        if not self._ThreadLock.acquire(timeout=self.Args.LockTimeout):
            raise Timeout(self._DBPath + ".qs.lock")
        try:
            yield
        finally:
            self._ThreadLock.release()

    @contextmanager
    def session(self):
        """将一组操作放在同一文件锁和事务中。

        协调模式下先获得锁，再打开真实连接；离开最外层会话时提交或回滚，
        关闭连接后释放锁。内部异常即使被调用者捕获，也会使整个会话回滚。
        普通模式仅复用已有连接，不改变原有事务行为。

        Yields:
            当前因子库。

        Raises:
            Timeout: 在 LockTimeout 秒内未获得线程锁或文件锁。
            __QS_Error__: 未逻辑连接，或内部失败导致会话只能回滚。
        """
        if not self.Args.CoordinatedAccess:
            yield self
            return
        if os.getpid() != self._ProcessID:
            if self._SessionDepth:
                raise __QS_Error__("不能在活动的 DuckDB session 内 fork")
            connected = self._LogicalConnected
            self._initCoordination()
            self._LogicalConnected = connected
        started = time.monotonic()
        with self._coordinationThread():
            if not self._LogicalConnected:
                raise __QS_Error__("协调模式下请先调用 connect()")
            if self._SessionDepth:
                self._SessionDepth += 1
                try:
                    yield self
                except BaseException:
                    self._SessionFailed = True
                    raise
                finally:
                    self._SessionDepth -= 1
                return
            remaining = max(0, self.Args.LockTimeout - (time.monotonic() - started))
            with self._FileLock.acquire(timeout=remaining):
                import duckdb
                self._SessionDepth = 1
                self._SessionOwner = threading.get_ident()
                self._SessionFailed = False
                self._CatalogDirty = False
                try:
                    self._Connection = duckdb.connect(self._DBPath)
                    self._Connection.begin()
                    if self._CatalogStamp is None or self._CatalogStamp != self._catalogStamp():
                        self._loadCatalog()
                    yield self
                    if self._SessionFailed:
                        raise __QS_Error__("DuckDB session 内部操作失败，整个会话已回滚")
                    self._Connection.commit()
                except BaseException:
                    self._CatalogDirty = True
                    if self._Connection is not None:
                        self._Connection.rollback()
                    raise
                finally:
                    try:
                        if self._Connection is not None:
                            self._Connection.close()
                    finally:
                        self._Connection = None
                        self._SessionDepth = 0
                        self._SessionOwner = None
                        self._CatalogStamp = None if self._CatalogDirty else self._catalogStamp()

    def __getstate__(self):
        if self.Args.CoordinatedAccess:
            with self._coordinationThread():
                if self._SessionDepth:
                    raise __QS_Error__("活动的 DuckDB session 不能序列化，请在会话外启动计算进程")
                state = self.__dict__.copy()
        else:
            state = self.__dict__.copy()
        state.pop("_ThreadLock", None)
        state.pop("_FileLock", None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        connected = self._LogicalConnected
        self._initCoordination()
        self._LogicalConnected = connected


class CoordinatedTable:
    """保持本地因子节点，并在每次数据源访问时刷新原生表。"""

    @classmethod
    def from_dependencies(cls, deps, args=None, **kwargs):
        """用因子库重新构造带当前结构的因子表。"""
        values = args.to_dict(repr=False) if hasattr(args, "to_dict") else dict(args or {})
        db = values.pop("SourceFDB")
        return db.getTable(values.pop("Name"), args=values)

    def _nativeTable(self):
        values = self.Args.to_dict(repr=False)
        values.pop("SourceFDB", None)
        values.pop("Name", None)
        return self.FactorDB._makeTable(self.Name, values, coordinated=False)

    def readData(self, factor_names, ids, dts, **kwargs):
        """直接读取复用一个会话；计算上下文内由本地引擎准备原始数据。"""
        if __QS_Context__ and not self.FactorDB._SessionDepth:
            return FactorTable.readData(self, factor_names, ids, dts, **kwargs)
        with self.FactorDB.session():
            table = self._nativeTable()
            raw = table.__QS_prepareRawData__(factor_names=factor_names, ids=ids, dts=dts)
            return table.__QS_calcData__(raw_data=raw, factor_names=factor_names, ids=ids, dts=dts)

    @property
    def FactorNames(self):
        with self.FactorDB.session():
            return self._nativeTable().FactorNames


def _tableOperation(base, name):
    @wraps(getattr(base, name))
    def call(self, *args, **kwargs):
        with self.FactorDB.session():
            return getattr(self._nativeTable(), name)(*args, **kwargs)
    return call


# 生成具有稳定模块名称的 SQL 表子类，支持 pickle/spawn 与节点类型校验。
TABLE_CLASSES = {}
for _kind in ("WideTable", "FeatureTable", "MappingTable", "NarrowTable", "TimeSeriesTable", "ConstituentTable", "FinancialTable"):
    _base = getattr(FactorUtils, "SQL_" + _kind)
    _methods = {name: _tableOperation(_base, name) for name in (
        "getMetaData", "getFactorMetaData", "getID", "getDateTime", "getIDMask", "getFilteredID",
        "getCondition", "readSQLData", "__QS_prepareRawData__", "__QS_calcData__",
    )}
    _name = "CoordinatedSQL_" + _kind
    _class = type(_name, (CoordinatedTable, _base), _methods | {"__module__": __name__})
    globals()[_name] = _class
    TABLE_CLASSES[_kind] = _class
