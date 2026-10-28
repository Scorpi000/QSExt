"""本地表、原子因子及标准数据缓存适配，不传输计算图。"""

from copy import deepcopy
import uuid

import pandas as pd
from pydantic import Field

from QuantStudio.Core.Node import __QS_Context__
from QuantStudio.Factor.Factor import Factor, makeFactorRunningKey
from QuantStudio.Factor.FactorTable import FactorTable

from .protocol import RemoteFactorError, digest


class RemoteFactorTable(FactorTable):
    """将公开表操作委托远程，保留本地 FactorTable 类型。"""

    class __QS_ArgClass__(FactorTable.__QS_ArgClass__):
        BackendArgs: dict = Field(default_factory=dict, frozen=True)

    def __init__(self, fdb, description, **kwargs):
        self._description = deepcopy(description)
        self._target = deepcopy(description["target"])
        self._args_digest = digest(self._target["table_args"])
        super().__init__(fdb=fdb, args={"Name": self._target["table_name"], "BackendArgs": self._target["table_args"]}, **kwargs)

    def init_compute(self, path, init_data, context):
        """远程原子因子自行登记标准缓存，不登记后端原始数据。"""
        return []

    @classmethod
    def from_dependencies(cls, deps, args=None, **kwargs):
        """支持本地节点模板按来源配置重建代理。"""
        values = args.to_dict(repr=False) if hasattr(args, "to_dict") else dict(args or {})
        return values["SourceFDB"].getTable(values["Name"], args=values.get("BackendArgs", {}))

    def _call(self, operation, kwargs=None, action="invoke"):
        if digest(self.Args.BackendArgs) != self._args_digest:
            raise RemoteFactorError("请使用 new(args=...) 修改后端参数", code="IMMUTABLE_DESCRIPTOR", status=409)
        return self.FactorDB._call(self._target, operation, kwargs, action)

    @property
    def FactorNames(self):
        return self._call("FactorNames")

    def getMetaData(self, key=None):
        return self._call("getMetaData", {"key": key})

    def getFactorMetaData(self, factor_names=None, key=None):
        return self._call("getFactorMetaData", {"factor_names": factor_names, "key": key})

    def getID(self, ifactor_name=None, idt=None):
        return self._call("getID", {"ifactor_name": ifactor_name, "idt": idt})

    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None, **kwargs):
        return self._call("getDateTime", {"ifactor_name": ifactor_name, "iid": iid, "start_dt": start_dt, "end_dt": end_dt, **kwargs})

    def getIDMask(self, idt, ids=None, id_filter_str=None):
        return self._call("getIDMask", {"idt": idt, "ids": ids, "id_filter_str": id_filter_str})

    def getFilteredID(self, idt, ids=None, id_filter_str=None):
        return self._call("getFilteredID", {"idt": idt, "ids": ids, "id_filter_str": id_filter_str})

    def getFactor(self, factor_name, args=None):
        if digest(self.Args.BackendArgs) != self._args_digest:
            raise RemoteFactorError("请使用 new(args=...) 修改后端参数", code="IMMUTABLE_DESCRIPTOR", status=409)
        args = dict(args or {})
        local = {key: args.pop(key) for key in list(args) if key in Factor.__QS_ArgClass__.model_fields and key not in ("Name",)}
        target = deepcopy(self._target) | {"kind": "factor", "factor_name": factor_name, "factor_args": args}
        description = self.FactorDB._call(target, "describe", action="describe")
        return RemoteFactor(ft=self, description=description, args=local)

    def readData(self, factor_names, ids, dts, **kwargs):
        if __QS_Context__:
            return super().readData(factor_names, ids, dts, **kwargs)
        return self._call("readData", {"factor_names": factor_names, "ids": ids, "dts": dts, **kwargs}, action="read")

    def new(self, args=None, **kwargs):
        values = deepcopy(self.Args.BackendArgs)
        changes = dict(args or {})
        name = changes.pop("Name", self.Name)
        values.update(changes.pop("BackendArgs", {}))
        values.update(changes)
        return self.FactorDB.getTable(name, args=values)


class RemoteFactor(Factor):
    """可参与本地计算图的远程原子数据因子。"""

    class __QS_ArgClass__(Factor.__QS_ArgClass__):
        RemoteDescriptor: dict = Field(frozen=True)

    def __init__(self, ft, description, args=None, **kwargs):
        self._description = deepcopy(description)
        self._target = deepcopy(description["target"])
        remote = self._target["factor_args"]
        local = {key: value for key, value in remote.items() if key in Factor.__QS_ArgClass__.model_fields}
        local.update(args or {})
        local.update(Name=self._target["factor_name"], RemoteDescriptor={"target": deepcopy(self._target), "resource_id": description["resource_id"], "config_revision": description["config_revision"]})
        self._descriptor_digest = digest(local["RemoteDescriptor"])
        super().__init__(ft=ft, args=local, **kwargs)

    def _call(self, operation, kwargs=None, action="invoke"):
        self._validate_descriptor()
        return self.FactorTable.FactorDB._call(self._target, operation, kwargs, action)

    @classmethod
    def from_dependencies(cls, deps, args=None, **kwargs):
        """在本地恢复依赖，不向服务端发送节点定义。"""
        values = args.to_dict(repr=False) if hasattr(args, "to_dict") else dict(args or {})
        table = deps.factor_table if hasattr(deps, "factor_table") else deps["factor_table"]
        target = values["RemoteDescriptor"]["target"]
        description = table.FactorDB._call(target, "describe", action="describe")
        local = {key: value for key, value in values.items() if key in Factor.__QS_ArgClass__.model_fields}
        return cls(ft=table, description=description, args=local, **kwargs)

    def _validate_descriptor(self):
        if digest(self.Args.RemoteDescriptor) != self._descriptor_digest:
            raise RemoteFactorError("请使用 new(args=...) 创建新因子", code="IMMUTABLE_DESCRIPTOR", status=409)

    def _cache_data_type(self):
        """内部缓存使用创建时的类型描述及本地覆盖，避免重复元信息请求。"""
        return self.Args.Meta.get("DataType", self._description["factor_metadata"].get("DataType"))

    def getMetaData(self, key=None):
        meta = self._call("getMetaData", {"key": None})
        if not isinstance(meta, pd.Series):
            meta = pd.Series(meta)
        meta = pd.Series(self.Args.Meta, dtype=object).combine_first(meta)
        return meta.get(key) if key is not None else meta

    def getID(self, idt=None, **kwargs):
        return self._call("getID", {"idt": idt, **kwargs})

    def getDateTime(self, iid=None, start_dt=None, end_dt=None, **kwargs):
        return self._call("getDateTime", {"iid": iid, "start_dt": start_dt, "end_dt": end_dt, **kwargs})

    def readData(self, ids, dts, section_ids=None, dt_ruler=None, **kwargs):
        if __QS_Context__:
            return super().readData(ids, dts, section_ids=section_ids, dt_ruler=dt_ruler, **kwargs)
        return self._call("readData", {"ids": ids, "dts": dts, "section_ids": section_ids, "dt_ruler": dt_ruler, **kwargs}, action="read")

    def new(self, args=None, **kwargs):
        changes = dict(args or {})
        local = {key: value for key, value in self.Args.items() if key in Factor.__QS_ArgClass__.model_fields}
        name = changes.pop("Name", self.Name)
        backend = deepcopy(self._target["factor_args"])
        backend.update(changes.pop("BackendArgs", {}))
        for key, value in changes.items():
            if key in local:
                local[key] = value
            else:
                backend[key] = value
        result = self.FactorTable.getFactor(name, args=backend | local)
        return result

    def init_compute(self, path, init_data, context):
        self._validate_descriptor()
        values = super().init_compute(path, init_data, context)
        if context.DataCache is not None and self.Args.CacheEnabled:
            group = "remote:" + self.FactorTable.QSID
            if group not in context.PrepareNodeDict:
                context.PrepareNodeDict[group] = (self.InstanceID, {"nodes": []})
            nodes = context.PrepareNodeDict[group][1]["nodes"]
            if self.InstanceID not in nodes:
                nodes.append(self.InstanceID)
        return values

    def _request_spec(self, ids, dts, section_ids, ruler):
        return {"request_id": uuid.uuid4().hex, "resource_id": self.Args.RemoteDescriptor["resource_id"], "config_revision": self.Args.RemoteDescriptor["config_revision"], "target": deepcopy(self._target), "operation": "readData", "kwargs": {"ids": ids, "dts": dts, "section_ids": section_ids, "dt_ruler": ruler}}

    def prepare_compute(self, prepare_data, context):
        """将本地已展开的原子读取合并成一个 HTTP 批次。"""
        if context.DataCache is None:
            return
        pending, requests = [], []
        for node_id in prepare_data["nodes"]:
            node = context.NodeDict[node_id]
            for key, state in context.NodeState[node_id].items():
                if not isinstance(state, dict) or "dt_range" not in state:
                    continue
                missing = context.DataCache.getDTRange(key=key, dt_range=state["dt_range"])
                if missing is None:
                    continue
                ids = state["section_ids"] if state["section_ids"] is not None else context.SectionIDs
                dates = context.getDateTime(missing)
                calc_dates = node._QS_getCalcDTs(dates, mask=False)
                if calc_dates is not None and not calc_dates:
                    frame = pd.DataFrame(index=dates, columns=ids, dtype=float)
                    context.DataCache.writeFactorData(key=key, factor_data=frame, pid_ids=state["pid_ids"], data_type=node._cache_data_type())
                    context.DataCache.updateDTRange(key=key, dt_range=missing)
                    continue
                requests.append(node._request_spec(ids, dates if calc_dates is None else calc_dates, ids, context.DTRuler))
                pending.append((node, key, state, missing, dates))
        if not requests:
            return
        db = self.FactorTable.FactorDB
        results = db._client.readBatch(db.Args.Database, requests)
        for (node, key, state, missing, dates), frame in zip(pending, results):
            frame = frame.reindex(index=dates)
            context.DataCache.writeFactorData(key=key, factor_data=frame, pid_ids=state["pid_ids"], target_field="StdData", if_exists="append", data_type=node._cache_data_type())
            context.DataCache.updateDTRange(key=key, dt_range=missing)

    def _prepareCacheData(self, context, local_context):
        """缓存未命中的补读只保存标准因子数据。"""
        key = makeFactorRunningKey(self.QSID, local_context.SectionIDs or self.Args.SectionIDs, context=context)
        state = context.NodeState[self.InstanceID][key]
        missing = context.DataCache.getDTRange(key=key, dt_range=state["dt_range"])
        if missing is None:
            return
        dates = context.getDateTime(missing)
        ids = state["pid_ids"][context.PID]
        calc_dates = self._QS_getCalcDTs(dates, mask=False)
        if calc_dates is not None and not calc_dates:
            frame = pd.DataFrame(index=dates, columns=ids, dtype=float)
        else:
            frame = self._call("readData", {"ids": ids, "dts": dates if calc_dates is None else calc_dates, "section_ids": state["section_ids"], "dt_ruler": context.DTRuler}, action="read").reindex(index=dates)
        context.DataCache.writeFactorData(key=key, factor_data=frame, pid_ids=state["pid_ids"], pid=context.PID, if_exists="append", data_type=self._cache_data_type())
        context.DataCache.updateDTRange(key=key, dt_range=missing)

    def backward_compute(self, path, bwd_data_list, context, local_context=None):
        if context.DataCache is not None and self.Args.CacheEnabled:
            self._prepareCacheData(context, local_context)
            key = makeFactorRunningKey(self.QSID, local_context.SectionIDs or self.Args.SectionIDs, context=context)
            frame = context.DataCache.readFactorData(key=key, ipid=context.PID, target_field="StdData", pids=local_context.PIDs, data_type=self._cache_data_type())
            return frame.reindex(index=local_context.DTs, columns=local_context.IDs)
        return self._call("readData", {"ids": local_context.IDs, "dts": local_context.DTs, "section_ids": local_context.SectionIDs, "dt_ruler": context.DTRuler}, action="read")
