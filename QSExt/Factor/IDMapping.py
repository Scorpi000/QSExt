"""Generic ID-mapped FactorDB wrappers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Literal, Optional

import pandas as pd
from pydantic import Field

from QuantStudio.Core import __QS_Args__, __QS_Error__, __QS_Object__
from QuantStudio.Core.Node import Node
from QuantStudio.Core.QSObject import Panel
from QuantStudio.Factor.Factor import Factor, FactorContext, FactorInitData
from QuantStudio.Factor.FactorDB import FactorDB
from QuantStudio.Factor.FactorTable import FactorTable
from QuantStudio.Tools.DataTypeFun import dict2id


@dataclass(frozen=True)
class IDMappingRequest:
    """Resolved external-to-native IDs for a single request."""

    external_ids: list[str]
    native_ids: list[str]
    external_to_native: list[Optional[str]]


class IDMapping(__QS_Object__):
    """Map caller-facing IDs to a factor database's native IDs."""

    class __QS_ArgClass__(__QS_Object__.__QS_ArgClass__):
        Name: str = Field(default="IDMapping", frozen=True, title="名称")
        UnmappedPolicy: Literal["empty", "raise", "passthrough"] = Field(
            default="empty", frozen=True, title="未映射ID策略"
        )

    @property
    def MappingID(self) -> str:
        """Stable digest of mapping behavior and current mapping contents."""
        raise NotImplementedError

    @property
    def QSID(self) -> str:
        return self.MappingID

    def _mapping(self) -> dict[str, str]:
        raise NotImplementedError

    def _reverseMapping(self) -> dict[str, list[str]]:
        mapping_id = self.MappingID
        if getattr(self, "_ValueReverseMappingID", None) != mapping_id:
            reverse = {}
            for external_id, native_id in self._mapping().items():
                reverse.setdefault(native_id, []).append(external_id)
            self._ValueReverseMapping = reverse
            self._ValueReverseMappingID = mapping_id
        return self._ValueReverseMapping

    def _externalValueCandidates(self, native_id, idt=None) -> list[str]:
        return self._reverseMapping().get(native_id, [])

    def resolve(self, ids: Optional[List[str]]) -> Optional[IDMappingRequest]:
        if ids is None:
            return None
        mapping = self._mapping()
        native_ids, external_to_native, seen, missing = [], [], set(), []
        for external_id in ids:
            native_id = mapping.get(external_id)
            if native_id is None:
                if self.Args.UnmappedPolicy == "raise":
                    missing.append(external_id)
                elif self.Args.UnmappedPolicy == "passthrough":
                    native_id = external_id
            external_to_native.append(native_id)
            if (native_id is not None) and (native_id not in seen):
                native_ids.append(native_id)
                seen.add(native_id)
        if missing:
            sample = ", ".join(map(str, missing[:10]))
            suffix = " ..." if len(missing) > 10 else ""
            raise __QS_Error__(f"ID映射 '{self.Args.Name}' 缺少 {len(missing)} 个ID: {sample}{suffix}")
        return IDMappingRequest(list(ids), native_ids, external_to_native)

    def toExternal(self, native_ids: List[str]) -> List[str]:
        reverse: dict[str, list[str]] = {}
        for external_id, native_id in self._mapping().items():
            reverse.setdefault(native_id, []).append(external_id)
        result, missing = [], []
        for native_id in native_ids:
            external_ids = reverse.get(native_id)
            if external_ids:
                result.extend(external_ids)
            elif self.Args.UnmappedPolicy == "passthrough":
                result.append(native_id)
            elif self.Args.UnmappedPolicy == "raise":
                missing.append(native_id)
        if missing:
            sample = ", ".join(map(str, missing[:10]))
            suffix = " ..." if len(missing) > 10 else ""
            raise __QS_Error__(f"ID映射 '{self.Args.Name}' 无法反向映射 {len(missing)} 个ID: {sample}{suffix}")
        return result

    def toExternalValue(
        self,
        native_id: Any,
        idt=None,
        ambiguity: Literal["raise", "first", "list"] = "raise",
    ):
        """Convert an ID stored inside a factor value to the external namespace."""
        if isinstance(native_id, list):
            return [self.toExternalValue(i, idt=idt, ambiguity=ambiguity) for i in native_id]
        if isinstance(native_id, tuple):
            return tuple(self.toExternalValue(i, idt=idt, ambiguity=ambiguity) for i in native_id)
        if isinstance(native_id, set):
            return {self.toExternalValue(i, idt=idt, ambiguity=ambiguity) for i in native_id}
        if native_id is None or (not isinstance(native_id, str) and pd.isna(native_id)):
            return native_id
        external_ids = self._externalValueCandidates(native_id, idt=idt)
        if len(external_ids) == 1:
            return external_ids[0]
        if len(external_ids) > 1:
            if ambiguity == "first":
                return external_ids[0]
            if ambiguity == "list":
                return external_ids
            raise __QS_Error__(
                f"ID映射 '{self.Args.Name}' 对值 {native_id} 存在多个反向映射: {external_ids}"
            )
        if self.Args.UnmappedPolicy == "passthrough":
            return native_id
        if self.Args.UnmappedPolicy == "raise":
            raise __QS_Error__(f"ID映射 '{self.Args.Name}' 无法反向映射值: {native_id}")
        return None


class StaticIDMapping(IDMapping):
    """An in-memory external-to-native mapping."""

    class __QS_ArgClass__(IDMapping.__QS_ArgClass__):
        Mapping: dict[str, str] = Field(default_factory=dict, frozen=True, title="映射关系")

    @property
    def MappingID(self) -> str:
        return dict2id({
            "class": type(self).__module__ + "." + type(self).__qualname__,
            "mapping": self.Args.Mapping,
            "unmapped_policy": self.Args.UnmappedPolicy,
        })

    def _mapping(self) -> dict[str, str]:
        return self.Args.Mapping


class FactorDBIDMappingConfig(__QS_Args__):
    """Default mapping and exact table-level overrides for a wrapped database."""

    Default: Optional[IDMapping] = Field(default=None, frozen=True, title="默认ID映射")
    Tables: dict[str, Optional[IDMapping]] = Field(default_factory=dict, frozen=True, title="表ID映射")
    IDValueMappings: dict[str, dict[str, IDMapping]] = Field(
        default_factory=dict, frozen=True, title="因子值ID映射"
    )
    IDValueAmbiguity: Literal["raise", "first", "list"] = Field(
        default="raise", frozen=True, title="因子值反向映射歧义策略"
    )

    def resolve(self, table_name: str) -> Optional[IDMapping]:
        return self.Tables.get(table_name, self.Default)

    def resolveIDValueMappings(self, table_name: str) -> dict[str, IDMapping]:
        return self.IDValueMappings.get(table_name, {})


IDMappingBase = IDMapping


class IDMappingFactorTable(FactorTable):
    """A factor table exposing external IDs while delegating to a native table."""

    class __QS_ArgClass__(FactorTable.__QS_ArgClass__):
        SourceTable: FactorTable = Field(frozen=True, title="原生因子表", repr=False)
        IDMapping: Optional["IDMappingBase"] = Field(default=None, frozen=True, title="ID映射", repr=False)
        IDValueMappings: dict[str, "IDMappingBase"] = Field(
            default_factory=dict, frozen=True, title="因子值ID映射"
        )
        IDValueAmbiguity: Literal["raise", "first", "list"] = Field(
            default="raise", frozen=True, title="因子值反向映射歧义策略"
        )

    def __init__(
        self,
        fdb,
        source_table: FactorTable,
        id_mapping: Optional[IDMapping],
        id_value_mappings: Optional[dict[str, IDMapping]] = None,
        id_value_ambiguity: str = "raise",
        args: dict = {},
        **kwargs,
    ):
        values = args | {
            "Name": source_table.Name,
            "SourceTable": source_table,
            "IDMapping": id_mapping,
            "IDValueMappings": id_value_mappings or {},
            "IDValueAmbiguity": id_value_ambiguity,
        }
        super().__init__(fdb=fdb, args=values, **kwargs)

    @property
    def SourceTable(self) -> FactorTable:
        return self._QSArgs.SourceTable

    @property
    def PrepareID(self):
        return None

    @property
    def FactorNames(self):
        return self.SourceTable.FactorNames

    def getMetaData(self, key=None):
        return self.SourceTable.getMetaData(key=key)

    def getFactorMetaData(self, factor_names=None, key=None):
        return self.SourceTable.getFactorMetaData(factor_names=factor_names, key=key)

    def getFactor(self, factor_name: str, args: dict = {}):
        if factor_name not in self.FactorNames:
            raise __QS_Error__(f"因子表中不存在因子: {factor_name}")
        return Factor(ft=self, args=args | {"Name": factor_name, "Parallel": False}, logger=self._QS_Logger)

    def _resolve(self, ids):
        if self._QSArgs.IDMapping is None:
            return None
        return self._QSArgs.IDMapping.resolve(ids)

    def getID(self, ifactor_name=None, idt=None):
        native_ids = self.SourceTable.getID(ifactor_name=ifactor_name, idt=idt)
        if self._QSArgs.IDMapping is None:
            return native_ids
        return self._QSArgs.IDMapping.toExternal(native_ids)

    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None, **kwargs):
        if (iid is not None) and (self._QSArgs.IDMapping is not None):
            request = self._QSArgs.IDMapping.resolve([iid])
            iid = request.external_to_native[0]
            if iid is None:
                return []
        return self.SourceTable.getDateTime(
            ifactor_name=ifactor_name, iid=iid, start_dt=start_dt, end_dt=end_dt, **kwargs
        )

    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        return None

    def _project(self, data: Panel, request: Optional[IDMappingRequest], factor_names, dts):
        if request is None:
            result = {factor_name: data.loc[factor_name].copy() for factor_name in factor_names}
        else:
            result = {}
            for factor_name in factor_names:
                native = data.loc[factor_name]
                external = pd.DataFrame(index=dts, columns=request.external_ids)
                for external_id, native_id in zip(request.external_ids, request.external_to_native):
                    if (native_id is not None) and (native_id in native.columns):
                        external[external_id] = native[native_id]
                result[factor_name] = external
        for factor_name, value_mapping in self._QSArgs.IDValueMappings.items():
            if factor_name in factor_names:
                frame = result[factor_name]
                converted = pd.DataFrame(index=frame.index, columns=frame.columns, dtype=object)
                for idt in frame.index:
                    for iid in frame.columns:
                        converted.at[idt, iid] = value_mapping.toExternalValue(
                            frame.at[idt, iid], idt=idt,
                            ambiguity=self._QSArgs.IDValueAmbiguity,
                        )
                result[factor_name] = converted
        return Panel(result, items=factor_names, major_axis=dts,
                     minor_axis=(data.minor_axis if request is None else request.external_ids))

    def __QS_calcData__(self, raw_data, factor_names, ids, dts):
        request = self._resolve(ids)
        native_ids = ids if request is None else request.native_ids
        native_raw = self.SourceTable.__QS_prepareRawData__(
            factor_names=factor_names, ids=native_ids, dts=dts
        )
        native_data = self.SourceTable.__QS_calcData__(
            raw_data=native_raw, factor_names=factor_names, ids=native_ids, dts=dts
        )
        if not isinstance(native_data, Panel):
            raise __QS_Error__(f"原生因子表 {self.SourceTable.Name} 未返回 Panel，无法应用 ID 映射")
        return self._project(native_data, request, factor_names, dts)

    def init_compute(self, path: List[str], init_data: FactorInitData, context: FactorContext):
        return Node.init_compute(self, path=path, init_data=init_data, context=context)


class IDMappingFactorDB(FactorDB):
    """A read-only database view that applies ID mappings to another FactorDB."""

    class __QS_ArgClass__(FactorDB.__QS_ArgClass__):
        SourceFDB: FactorDB = Field(frozen=True, title="原生因子库", repr=False)
        IDMappingConfig: FactorDBIDMappingConfig = Field(
            default_factory=FactorDBIDMappingConfig, frozen=True, title="ID映射配置", repr=False
        )

    def __init__(self, source_fdb: FactorDB, args: dict = {}, **kwargs):
        values = {"Name": f"IDMapping({source_fdb.Name})", "SourceFDB": source_fdb} | args
        super().__init__(args=values, **kwargs)

    @property
    def SourceFDB(self) -> FactorDB:
        return self._QSArgs.SourceFDB

    def connect(self):
        self.SourceFDB.connect()
        return self

    def disconnect(self):
        return self.SourceFDB.disconnect()

    @property
    def TableNames(self):
        return self.SourceFDB.TableNames

    def getTable(self, table_name: str, args: dict = {}):
        source_args = dict(args)
        nested_source_args = source_args.pop("SourceArgs", {})
        if not isinstance(nested_source_args, dict):
            raise __QS_Error__("SourceArgs 必须是 dict")
        sentinel = object()
        mapping = source_args.pop("IDMapping", sentinel)
        if mapping is sentinel:
            mapping = self._QSArgs.IDMappingConfig.resolve(table_name)
        id_value_mappings = source_args.pop("IDValueMappings", sentinel)
        if id_value_mappings is sentinel:
            id_value_mappings = self._QSArgs.IDMappingConfig.resolveIDValueMappings(table_name)
        id_value_ambiguity = source_args.pop(
            "IDValueAmbiguity", self._QSArgs.IDMappingConfig.IDValueAmbiguity
        )
        source_args.update(nested_source_args)
        source_table = self.SourceFDB.getTable(table_name, args=source_args)
        return IDMappingFactorTable(
            fdb=self,
            source_table=source_table,
            id_mapping=mapping,
            id_value_mappings=id_value_mappings,
            id_value_ambiguity=id_value_ambiguity,
            logger=self._QS_Logger,
        )
