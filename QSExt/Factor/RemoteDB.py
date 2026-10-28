"""通用远程因子库；数据访问在远程，计算图在本地执行。"""

from copy import deepcopy

from pydantic import Field

from QuantStudio.Factor.FactorDB import WritableFactorDB
from QSExt.FactorService.client import FactorDBServiceClient
from QSExt.FactorService.protocol import RemoteFactorError, digest


class RemoteFactorDB(WritableFactorDB):
    """选择并代理服务端配置的因子库。"""

    class __QS_ArgClass__(WritableFactorDB.__QS_ArgClass__):
        Name: str = Field(default="远程因子库", frozen=True)
        ServerURL: str = Field(frozen=True)
        Database: str = Field(frozen=True)
        TokenEnv: str = Field(default="QS_FACTOR_CLIENT_TOKEN", frozen=True, exclude=True)
        TimeoutSeconds: float = Field(default=120, gt=0, frozen=True, exclude=True)
        ConnectTimeoutSeconds: float = Field(default=10, gt=0, frozen=True, exclude=True)

    def __init__(self, args=None, config_file=None, **kwargs):
        super().__init__(args=args or {}, config_file=config_file, **kwargs)
        self._client = FactorDBServiceClient(self.Args.ServerURL, self.Args.TokenEnv, self.Args.TimeoutSeconds, self.Args.ConnectTimeoutSeconds)
        self._identity = None
        self._capabilities = None

    def connect(self):
        self._client.connect()
        matches = [item for item in self._client.listDatabases() if item["name"] == self.Args.Database]
        if not matches:
            raise RemoteFactorError("远程因子库不存在或未导出", code="NOT_FOUND", status=404)
        identity = matches[0] | {"service_id": self._client.info["service_id"]}
        if self._identity and any(identity[key] != self._identity[key] for key in ("service_id", "resource_id", "config_revision")):
            raise RemoteFactorError("资源绑定变化，请创建新的因子库对象", code="RESOURCE_CHANGED", status=409)
        self._identity = identity
        description = self._call({"kind": "database"}, action="describe", operation="describe")
        self._capabilities = description["capabilities"]
        return self

    def disconnect(self):
        self._client.close()
        return 0

    def _call(self, target, operation, kwargs=None, action="invoke", data=None, mutation=False):
        if self._identity is None:
            self.connect()
        return self._client.call(self.Args.Database, self._identity, target, operation, kwargs, action, data, mutation)

    @property
    def QSID(self):
        return digest({"class": "RemoteFactorDB", "server": self.Args.ServerURL, "database": self.Args.Database, "identity": {key: self._identity[key] for key in ("service_id", "resource_id", "config_revision")} if self._identity else None})

    @property
    def TableNames(self):
        return self._call({"kind": "database"}, "TableNames")

    @property
    def Capabilities(self):
        if self._identity is None:
            self.connect()
        return deepcopy(self._capabilities)

    def getTable(self, table_name, args=None):
        from QSExt.FactorService.proxy import RemoteFactorTable
        target = {"kind": "table", "table_name": table_name, "table_args": args or {}}
        description = self._call(target, "describe", action="describe")
        return RemoteFactorTable(fdb=self, description=description)

    def _write(self, operation, **kwargs):
        return self._call({"kind": "database"}, operation, kwargs, mutation=True)

    def writeData(self, data, table_name, if_exists="update", data_type=None, **kwargs):
        return self._call({"kind": "database"}, "writeData", {"table_name": table_name, "if_exists": if_exists, "data_type": data_type or {}, **kwargs}, action="write", data=data, mutation=True)

    def renameTable(self, old_table_name, new_table_name):
        return self._write("renameTable", old_table_name=old_table_name, new_table_name=new_table_name)

    def deleteTable(self, table_name):
        return self._write("deleteTable", table_name=table_name)

    def setTableMetaData(self, table_name, key=None, value=None, meta_data=None):
        return self._write("setTableMetaData", table_name=table_name, key=key, value=value, meta_data=meta_data)

    def renameFactor(self, table_name, old_factor_name, new_factor_name):
        return self._write("renameFactor", table_name=table_name, old_factor_name=old_factor_name, new_factor_name=new_factor_name)

    def deleteFactor(self, table_name, factor_names):
        return self._write("deleteFactor", table_name=table_name, factor_names=factor_names)

    def setFactorMetaData(self, table_name, ifactor_name, key=None, value=None, meta_data=None):
        return self._write("setFactorMetaData", table_name=table_name, ifactor_name=ifactor_name, key=key, value=value, meta_data=meta_data)

    def callExtension(self, operation, **kwargs):
        if self._identity is None:
            self.connect()
        spec = self._capabilities["extensions"].get(operation)
        if spec is None:
            raise RemoteFactorError("远程库未声明该扩展", code="UNSUPPORTED", status=422)
        return self._call({"kind": "database"}, operation, kwargs, mutation=spec["mutates"])

    def __getattr__(self, name):
        # 仅为服务已声明的有限扩展绑定方法，保留既有 settings.method 用法。
        capabilities = self.__dict__.get("_capabilities") or {}
        if name in capabilities.get("extensions", {}):
            return lambda **kwargs: self.callExtension(name, **kwargs)
        raise AttributeError(name)

    def getOperation(self, operation_id):
        return self._client.getOperation(operation_id)

    @property
    def LastOperationID(self):
        """最近提交的写操作号，可用于查询超时后的执行状态。"""
        return getattr(self._client, "last_operation_id", None)


__all__ = ["RemoteFactorDB", "FactorDBServiceClient"]
