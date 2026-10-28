"""资源所有权、白名单分派和进程内写操作登记。"""

import logging
import os
import threading
import time
import uuid
from contextlib import nullcontext
from pathlib import Path
from filelock import Timeout as FileLockTimeout

from QuantStudio.Core.Node import Node
from QuantStudio.Factor.FactorTable import FactorTable
from QSExt.RuntimeConfig.config import DBPool

from . import adapters
from .config import ServiceConfig, validate_definitions
from .executor import ResourceExecutor
from .protocol import RemoteFactorError, digest

LOGGER = logging.getLogger("QS.FactorService")


class Resource:
    """仅在专用线程中创建和访问一个真实因子库。"""

    def __init__(self, definition, export, config, registry):
        self.definition, self.export, self.config = definition, export, config
        self.registry = registry
        self.revision = digest({"class": definition.resolved_class_name, "args": definition.args, "config": definition.config_file})
        self.metadata_revision = 0
        self.db = None
        self.executor = ResourceExecutor(config.Limits.MaxQueueSize, config.Limits.QueueTimeoutSeconds, self.close)

    def connect(self):
        """按需连接，失败后关闭残余连接以便再次尝试。"""
        if self.db is None:
            db = None
            try:
                db = DBPool([self.definition])._create_one(self.definition)
                self.registry.claim_paths(self.definition.name, db)
                db.connect()
                adapters.protect_duckdb(db)
            except Exception as exc:
                if db is not None:
                    try:
                        db.disconnect()
                    except Exception:
                        LOGGER.error("关闭连接失败的资源")
                if isinstance(exc, RemoteFactorError):
                    raise
                if isinstance(exc, FileLockTimeout):
                    raise RemoteFactorError("因子库正被其他进程使用，等待协调锁超时", code="RESOURCE_BUSY", status=503,
                                            effect="not_started") from None
                LOGGER.error("资源 %s 连接失败，异常类型 %s", self.export.ResourceID, type(exc).__name__)
                raise RemoteFactorError("因子库连接失败，请检查服务端配置", code="BACKEND_UNAVAILABLE", status=503) from exc
            self.db = db
        return self.db

    def close(self):
        """在所有者线程内关闭真实连接。"""
        if self.db is not None:
            self.db.disconnect()
            self.db = None

    def check_identity(self, request):
        if request.resource_id != self.export.ResourceID or request.config_revision != self.revision:
            raise RemoteFactorError("远程资源配置已变化，请重新连接", code="RESOURCE_CHANGED", status=409)

    def target(self, target):
        db = self.connect()
        if target.kind == "database":
            if target.table_name is not None or target.factor_name is not None or target.table_args or target.factor_args:
                raise RemoteFactorError("库描述包含多余参数", code="INVALID_ARGUMENT", status=422)
            return db
        if target.table_name is None:
            raise RemoteFactorError("缺少因子表名称", code="INVALID_ARGUMENT", status=422)
        if target.table_name not in db.TableNames:
            raise RemoteFactorError("因子表不存在", code="NOT_FOUND", status=404)
        adapters.validate_table_args(db, target.table_name, target.table_args)
        table = db.getTable(target.table_name, args=target.table_args)
        if target.kind == "table":
            if target.factor_name is not None or target.factor_args:
                raise RemoteFactorError("表描述包含多余因子参数", code="INVALID_ARGUMENT", status=422)
            return table
        if target.factor_name is None:
            raise RemoteFactorError("缺少因子名称", code="INVALID_ARGUMENT", status=422)
        if type(table).getFactor is FactorTable.getFactor and target.factor_name not in table.FactorNames:
            raise RemoteFactorError("因子不存在", code="NOT_FOUND", status=404)
        return table.getFactor(target.factor_name, args=target.factor_args)

    def capabilities(self):
        db = self.connect()
        extensions = adapters.EXTENSIONS.get(type(db).__name__, {})
        writes = adapters.supported_writes(db)
        allowed_write = self.export.Access == "read_write"
        operations = {kind: sorted(names) for kind, names in adapters.READS.items()}
        operations["database"] += sorted(writes) if allowed_write else []
        for name, mutates in extensions.items():
            if not mutates or allowed_write:
                operations["database"].append(name)
        return {"operations": operations, "extensions": {name: {"mutates": mutates} for name, mutates in extensions.items() if not mutates or allowed_write}, "read": True, "write": allowed_write and bool(writes), "metadata_revision": self.metadata_revision}

    def describe(self, target):
        obj = self.target(target)
        result = {"target": target.model_dump(), "resource_id": self.export.ResourceID, "config_revision": self.revision, "metadata_revision": self.metadata_revision}
        if target.kind == "database":
            return result | {"name": obj.Name, "capabilities": self.capabilities()}
        table = obj.FactorTable if target.kind == "factor" else obj
        result["target"]["table_args"] = adapters.backend_args(table, FactorTable)
        result["table_parameters"] = adapters.argument_schema(table, FactorTable)
        result["factor_names"] = list(table.FactorNames)
        # 视图的数据只读限制由后端维持，能力清单同时向调用者公开。
        readonly = target.table_name in getattr(self.db, "_ParquetTables", set())
        result["table_writable"] = self.export.Access == "read_write" and not readonly
        if target.kind == "factor":
            if obj.Descriptors or obj.FactorTable is None:
                raise RemoteFactorError("不允许远程计算图", code="UNSUPPORTED", status=422)
            result["target"]["factor_args"] = adapters.backend_args(obj, Node)
            result["factor_metadata"] = obj.getMetaData()
        return result

    def mutates(self, request):
        return request.target.kind == "database" and (request.operation in adapters.WRITES or adapters.EXTENSIONS.get(self.definition.resolved_class_name.rsplit(".", 1)[-1], {}).get(request.operation, False))

    def execute(self, request, action, data=None):
        """将一次协调 DuckDB 请求放入同一短连接和事务。"""
        self.check_identity(request)
        db = self.connect()
        from QSExt.Factor._DuckDBCoordination import CoordinatedDB
        entered = False
        try:
            with db.session() if isinstance(db, CoordinatedDB) and db.Args.CoordinatedAccess else nullcontext():
                entered = True
                return self._execute(request, action, data)
        except FileLockTimeout:
            raise RemoteFactorError("因子库正被其他进程使用，等待协调锁超时", code="RESOURCE_BUSY", status=503,
                                    effect="unknown" if entered else "not_started") from None

    def _execute(self, request, action, data=None):
        self.check_identity(request)
        if action == "describe":
            if request.operation != "describe" or request.kwargs:
                raise RemoteFactorError("描述请求包含多余操作", code="INVALID_ARGUMENT", status=422)
            return self.describe(request.target)
        obj = self.target(request.target)
        if action == "read":
            if request.target.kind == "database" or request.operation != "readData":
                raise RemoteFactorError("仅允许标准数据读取", code="UNSUPPORTED", status=422)
            kwargs = dict(request.kwargs)
            if request.target.kind == "factor":
                kwargs.pop("factor_names", None)
            self.check_cells(kwargs, request.target.kind)
            value = adapters.read_standard(obj, kwargs)
            if hasattr(value, "shape"):
                import math
                if math.prod(value.shape) > self.config.Limits.MaxCells:
                    raise RemoteFactorError("读取结果超过单元格限制", code="TOO_LARGE", status=413)
            return value
        allowed = self.capabilities()["operations"].get(request.target.kind, [])
        if request.operation not in allowed:
            raise RemoteFactorError("操作不支持或没有访问权限", code="FORBIDDEN", status=403, effect="not_started")
        kwargs = dict(request.kwargs)
        if request.operation == "setTableMetaData":
            metadata = kwargs.get("meta_data")
            if metadata is None:
                metadata = {kwargs.get("key"): kwargs.get("value")}
            if isinstance(metadata, dict):
                import re
                if "TableClass" in metadata and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(metadata["TableClass"])):
                    raise RemoteFactorError("表类型元信息不允许包含表达式", code="FORBIDDEN", status=403, effect="not_started")
                if isinstance(metadata.get("FTArgs"), dict):
                    adapters.validate_table_args(self.db, kwargs["table_name"], metadata["FTArgs"])
        table_name = kwargs.get("table_name", kwargs.get("old_table_name"))
        view_mutations = {"writeData", "renameTable", "createTable", "addFactor", "renameFactor", "deleteFactor", "deleteData"}
        if table_name in getattr(self.db, "_ParquetTables", set()) and request.operation in view_mutations:
            raise RemoteFactorError("Parquet 视图不支持该数据或结构修改", code="UNSUPPORTED", status=422, effect="not_started")
        if request.operation == "writeData":
            if action != "write":
                raise RemoteFactorError("写入数据必须通过上传接口", code="INVALID_ARGUMENT", status=422)
            kwargs["data"] = data
        elif action != "invoke":
            raise RemoteFactorError("接口与操作不匹配", code="INVALID_ARGUMENT", status=422)
        adapters.validate_call(obj, request.operation, kwargs)
        if request.operation in adapters.PROPERTY_NAMES:
            return getattr(obj, request.operation)
        if request.target.kind == "table" and request.operation in ("getIDMask", "getFilteredID"):
            if request.operation == "getFilteredID" and not kwargs.get("id_filter_str"):
                return obj.getID(idt=kwargs["idt"])
            mask = adapters.filter_ids(obj, kwargs, self.config.Limits.MaxCells)
            return mask if request.operation == "getIDMask" else mask.index[mask].tolist()
        if request.operation == "getDateTime" and request.target.kind in ("table", "factor") and kwargs.get("iid") is not None:
            table = obj.FactorTable if request.target.kind == "factor" else obj
            kwargs["iid"] = adapters.sql_ids(table, [kwargs["iid"]])[0]
        result = getattr(obj, request.operation)(**kwargs)
        if self.mutates(request):
            self.metadata_revision += 1
        # 某些后端返回 self，公开写操作只返回成功确认，不传真实连接。
        return None if result is obj else result

    def check_cells(self, kwargs, kind):
        count = 1
        for key in ("ids", "dts"):
            if key not in kwargs:
                raise RemoteFactorError("读取缺少 ids 或 dts 参数", code="INVALID_ARGUMENT", status=422)
            if kwargs[key] is None:
                # None 原样交给后端；实际返回结果仍检查上限，不转为空列表。
                continue
            count *= len(kwargs[key])
        if kind == "table":
            count *= len(kwargs.get("factor_names", []))
        if count > self.config.Limits.MaxCells:
            raise RemoteFactorError("读取超过单元格限制", code="TOO_LARGE", status=413)


class Registry:
    """资源目录和进程内写入结果登记。"""

    def __init__(self, definitions, config):
        self.config = ServiceConfig.model_validate(config) if isinstance(config, dict) else config
        validate_definitions(definitions, self.config)
        self.epoch = uuid.uuid4().hex
        self._paths = {}
        self._lock = threading.Lock()
        self.operations = {}
        self.resources = {item.name: Resource(item, self.config.Databases[item.name], self.config, self) for item in definitions if item.name in self.config.Databases}

    def claim_paths(self, name, db):
        """补查来自后端配置文件的真实路径，防止连接所有权冲突。"""
        if type(db).__name__ not in ("DuckDB", "HDF5DB"):
            return
        with self._lock:
            for key in ("DBFile", "ParquetDir", "MainDir"):
                value = db.Args.get(key)
                if not value or str(value) == ":memory:":
                    continue
                path = os.path.normcase(str(Path(value).expanduser().resolve()))
                if path in self._paths and self._paths[path] != name:
                    raise RemoteFactorError("后端路径被另一个导出资源占用", code="RESOURCE_CONFLICT", status=409)
                self._paths[path] = name

    def resource(self, name):
        if name not in self.resources:
            raise RemoteFactorError("因子库未导出或不存在", code="NOT_FOUND", status=404)
        return self.resources[name]

    def directory(self):
        """目录不触发连接，单个后端故障不阻塞目录。"""
        return [{"name": name, "resource_id": resource.export.ResourceID, "config_revision": resource.revision, "access": resource.export.Access, "status": "connected" if resource.db is not None else "not_connected"} for name, resource in self.resources.items()]

    def submit(self, name, request, action, data=None):
        """登记写入后分派，同标识请求不重复执行。"""
        resource = self.resource(name)
        resource.check_identity(request)
        if not resource.mutates(request):
            return resource.executor.submit(lambda: resource.execute(request, action, data))
        now = time.time()
        if request.epoch != self.epoch:
            raise RemoteFactorError("服务已重启，旧写入结果未知", code="OPERATION_UNKNOWN", status=409, operation_id=request.operation_id, effect="unknown")
        if not request.operation_id or request.expires_at is None or not now < request.expires_at <= now + self.config.Limits.OperationTTLSeconds:
            raise RemoteFactorError("写入标识缺失或已经过期", code="OPERATION_EXPIRED", status=409, operation_id=request.operation_id)
        summary = digest({"name": name, "action": action, "request": request.model_dump(exclude={"request_id"}), "data": None if data is None else self._data_digest(data)})
        with self._lock:
            self.operations = {key: item for key, item in self.operations.items() if item["expires_at"] > now or item["state"] in ("QUEUED", "RUNNING")}
            old = self.operations.get(request.operation_id)
            if old:
                if old["digest"] != summary:
                    raise RemoteFactorError("相同操作标识包含不同参数", code="OPERATION_CONFLICT", status=409)
                return old["future"]
            record = {"state": "QUEUED", "effect": "not_started", "digest": summary, "expires_at": request.expires_at, "operation_id": request.operation_id}
            def invoke():
                if time.time() >= request.expires_at:
                    raise RemoteFactorError("排队期间写入标识过期，操作未执行", code="OPERATION_EXPIRED", status=409, operation_id=request.operation_id, effect="not_started")
                record.update(state="RUNNING", effect="unknown")
                try:
                    result = resource.execute(request, action, data)
                except BaseException as exc:
                    effect = exc.details.get("effect", "unknown") if isinstance(exc, RemoteFactorError) else "unknown"
                    record.update(state="FAILED", effect=effect)
                    raise
                record.update(state="SUCCEEDED", effect="applied")
                return result
            future = resource.executor.submit(invoke)
            record["future"] = future
            self.operations[request.operation_id] = record
            def completed(item):
                if record["state"] == "QUEUED":
                    record.update(state="FAILED", effect="not_started")
            future.add_done_callback(completed)
            return future

    @staticmethod
    def _data_digest(data):
        from .codec import pack
        import hashlib
        return hashlib.sha256(pack(data)).hexdigest()

    def operation(self, operation_id):
        with self._lock:
            record = self.operations.get(operation_id)
            if record is None or (record["expires_at"] <= time.time() and record["state"] not in ("QUEUED", "RUNNING")):
                return {"operation_id": operation_id, "state": "UNKNOWN", "effect": "unknown", "epoch": self.epoch}
            return {key: value for key, value in record.items() if key not in ("future", "digest")}

    def close(self):
        for resource in self.resources.values():
            resource.executor.close()
