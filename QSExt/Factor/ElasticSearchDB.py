# coding=utf-8
"""基于 Elasticsearch 的因子库"""
import os
import time
import datetime as dt
from typing import List, Optional, Dict, Literal

import numpy as np
import pandas as pd
from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import ConnectionTimeout
from pydantic import Field

from QuantStudio import __QS_ConfigPath__
from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.QSObject import Panel
from QuantStudio.Factor.FactorDB import WritableFactorDB
from QuantStudio.Factor.FactorTable import FactorTable
from QuantStudio.Tools.DataPreprocessingFun import fillNaByLookback


_TypeMapping = {
    "keyword": "string",
    "text": "string",
    "float": "double",
    "double": "double",
    "integer": "double",
    "long": "double",
    "short": "double",
    "byte": "double",
    "half_float": "double",
    "date": "object",
}


def _identifyDataType(dtypes):
    if np.dtype('O') in dtypes.values:
        return 'keyword'
    else:
        return 'double'


def _adjustData(data, look_back, factor_names, ids, dts):
    if ids is not None:
        data = Panel(data).loc[factor_names, :, ids]
    else:
        data = Panel(data).loc[factor_names, :, :]
    if look_back == 0:
        if dts is not None:
            return data.loc[:, dts]
        else:
            return data
    if dts is not None:
        AllDTs = data.major_axis.union(dts).sort_values()
        data = data.loc[:, AllDTs, :]
    if np.isinf(look_back):
        for i, iFactorName in enumerate(data.items):
            data.iloc[i].fillna(method="pad", inplace=True)
    else:
        data = dict(data)
        Limits = look_back * 24.0 * 3600
        for iFactorName in data:
            data[iFactorName] = fillNaByLookback(data[iFactorName], lookback=Limits)
        data = Panel(data).loc[factor_names]
    if dts is not None:
        return data.loc[:, dts]
    else:
        return data


# -------------------- 因子表 --------------------

class _WideTable(FactorTable):
    """ElasticSearchDB 宽因子表"""

    class __QS_ArgClass__(FactorTable.__QS_ArgClass__):
        TableType: str = Field(default="WideTable", frozen=True, title="因子表类型")
        PreFilterID: bool = Field(default=True, frozen=True, title="预筛选ID")
        FilterCondition: list = Field(default=[], frozen=True, title="筛选条件")
        DTField: str = Field(default="datetime", frozen=True, title="时点字段")
        IDField: str = Field(default="code", frozen=True, title="ID字段")
        LookBack: float = Field(default=0, frozen=True, title="回溯天数")
        KeywordSuffix: bool = Field(default=False, frozen=True, title="ID字段加keyword后缀")

    def __init__(self, fdb, args={}, table_info=None, factor_info=None, logger=None, **kwargs):
        self._TableInfo = table_info
        self._FactorInfo = factor_info
        self._Connection = fdb.Connection
        self._IndexName = fdb._QSArgs.InnerPrefix + args.get("Name", "")
        super().__init__(fdb=fdb, args=args, **kwargs)

    @property
    def FactorNames(self) -> List[str]:
        return sorted(self._FactorInfo.index)

    def getFactorMetaData(self, factor_names=None, key=None):
        if factor_names is None:
            factor_names = self.FactorNames
        if key == "DataType":
            return self._FactorInfo["DataType"].loc[factor_names]
        elif key is None:
            return pd.DataFrame({"DataType": self.getFactorMetaData(factor_names, key="DataType")})
        else:
            return pd.Series([None] * len(factor_names), index=factor_names, dtype=np.dtype("O"))

    def _getIDKeyword(self):
        IDField = self._QSArgs.IDField
        if IDField in self._FactorInfo.index and self._FactorInfo.loc[IDField, "Keyword"]:
            return f"{IDField}.keyword"
        return IDField

    def getID(self, ifactor_name=None, idt=None):
        IDField = self._QSArgs.IDField
        IDKeyword = self._getIDKeyword()
        Query = {"bool": {"filter": [{"exists": {"field": IDField}}]}}
        if ifactor_name is not None:
            Query["bool"]["filter"].append({"exists": {"field": ifactor_name}})
        if idt is not None:
            DTField = self._QSArgs.DTField
            Query["bool"]["filter"].append({"term": {DTField: idt}})
        Rslt = self._Connection.search(
            index=self._IndexName, query=Query,
            _source=[IDField], collapse={"field": IDKeyword},
            sort=[{IDKeyword: {"order": "asc"}}]
        )
        return [r["_source"][IDField] for r in Rslt["hits"]["hits"]]

    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None, **kwargs):
        DTField = self._QSArgs.DTField
        Query = {"bool": {"filter": [{"exists": {"field": DTField}}]}}
        if ifactor_name is not None:
            Query["bool"]["filter"].append({"exists": {"field": ifactor_name}})
        if iid is not None:
            IDKeyword = self._getIDKeyword()
            Query["bool"]["filter"].append({"term": {IDKeyword: iid}})
        if (start_dt is not None) or (end_dt is not None):
            Range = {"range": {DTField: {}}}
            if start_dt is not None:
                Range["range"][DTField]["gte"] = start_dt
            if end_dt is not None:
                Range["range"][DTField]["lte"] = end_dt
            Query["bool"]["filter"].append(Range)
        Aggs = {"qs_dt_count": {"terms": {"field": DTField}}}
        Rslt = self._Connection.search(index=self._IndexName, query=Query, size=0, aggs=Aggs)
        return [
            dt.datetime.strptime(r["key_as_string"], "%Y-%m-%dT%H:%M:%S.%fZ")
            for r in Rslt["aggregations"]["qs_dt_count"]["buckets"]
        ]

    def _genNullIDRawData(self, factor_names, ids, end_date):
        DTField = self._QSArgs.DTField
        IDField = self._QSArgs.IDField
        IDKeyword = self._getIDKeyword()
        Query = {"bool": {"filter": [{"exists": {"field": DTField}}]}}
        Query["bool"]["filter"].append({"terms": {IDKeyword: ids}})
        Query["bool"]["filter"].append({"range": {DTField: {"lt": end_date}}})
        FilterConds = self._QSArgs.FilterCondition
        if FilterConds:
            Query["bool"]["filter"] += FilterConds
        Aggs = {
            "qs_code_group": {
                "terms": {"field": IDKeyword},
                "aggs": {"qs_dt_max": {"max": {"field": DTField}}}
            }
        }
        Rslt = self._Connection.search(index=self._IndexName, query=Query, size=0, aggs=Aggs)
        Query = {"bool": {"should": []}}
        for iRslt in Rslt["aggregations"]["qs_code_group"]["buckets"]:
            Query["bool"]["should"].append({
                "bool": {
                    "must": [
                        {"term": {DTField: iRslt["qs_dt_max"]["value_as_string"]}},
                        {"term": {IDKeyword: iRslt["key"]}}
                    ]
                }
            })
        RawData = self._Connection.search(
            index=self._IndexName, query=Query,
            _source=[IDField, DTField] + factor_names
        )
        RawData = pd.DataFrame(data=(iData["_source"] for iData in RawData["hits"]["hits"]))
        if RawData.shape[1] == 0:
            return pd.DataFrame(columns=[DTField, IDField] + factor_names)
        return RawData

    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        if (dts == []) or (ids == []):
            return pd.DataFrame(columns=["QS_DT", "ID"] + factor_names)
        IDField = self._QSArgs.IDField
        IDKeyword = self._getIDKeyword()
        DTField = self._QSArgs.DTField
        LookBack = self._QSArgs.LookBack
        if dts is not None:
            dts = sorted(dts)
            StartDT, EndDT = dts[0], dts[-1]
            if not np.isinf(LookBack):
                StartDT -= dt.timedelta(LookBack)
        else:
            StartDT = EndDT = None
        Query = {"bool": {"filter": [{"exists": {"field": DTField}}]}}
        if self._QSArgs.PreFilterID:
            Query["bool"]["filter"].append({"terms": {IDKeyword: ids}})
        else:
            Query["bool"]["filter"].append({"exists": {"field": IDField}})
        if (StartDT is not None) or (EndDT is not None):
            Range = {"range": {DTField: {}}}
            if StartDT is not None:
                Range["range"][DTField]["gte"] = StartDT
            if EndDT is not None:
                Range["range"][DTField]["lte"] = EndDT
            Query["bool"]["filter"].append(Range)
        FilterConds = self._QSArgs.FilterCondition
        if FilterConds:
            Query["bool"]["filter"] += FilterConds
        # 使用 PIT + search_after 分页查询
        RawData = list(self._FactorDB.search(
            index=self._IndexName, query=Query,
            sort=[{IDKeyword: {"order": "asc"}}, {DTField: {"order": "asc"}}],
            only_source=True, _source=[DTField, IDField] + factor_names
        ))
        RawData = pd.DataFrame(RawData)
        if RawData.shape[1] == 0:
            RawData = pd.DataFrame(columns=[DTField, IDField] + factor_names)
        if (StartDT is not None) and np.isinf(LookBack):
            NullIDs = set(ids).difference(set(RawData[RawData[DTField] == StartDT][IDField]))
            if NullIDs:
                NullRawData = self._genNullIDRawData(factor_names, list(NullIDs), StartDT)
                if NullRawData.shape[0] > 0:
                    RawData = pd.concat([NullRawData, RawData], ignore_index=True)
        RawData = RawData.sort_values(by=[DTField, IDField]).rename(columns={DTField: "QS_DT", IDField: "ID"})
        RawData["QS_DT"] = RawData["QS_DT"].apply(lambda d: dt.datetime.strptime(d, "%Y-%m-%dT%H:%M:%S"))
        return RawData

    def __QS_calcData__(self, raw_data, factor_names, ids, dts):
        if raw_data.shape[0] == 0:
            return Panel(items=factor_names, major_axis=dts, minor_axis=ids)
        raw_data = raw_data.set_index(["QS_DT", "ID"])
        DataType = self.getFactorMetaData(factor_names=factor_names, key="DataType")
        Data = {}
        for iFactorName in raw_data.columns:
            iRawData = raw_data[iFactorName].unstack()
            if DataType.get(iFactorName, "double") == "double":
                iRawData = iRawData.astype("float")
            Data[iFactorName] = iRawData
        # 补充缺失的因子（全 NaN）
        for iFactorName in factor_names:
            if iFactorName not in Data:
                Data[iFactorName] = pd.DataFrame(np.nan, index=dts, columns=ids)
        return _adjustData(Data, self._QSArgs.LookBack, factor_names, ids, dts)


# -------------------- 因子库 --------------------

class ElasticSearchDB(WritableFactorDB):
    """基于 Elasticsearch 的因子库"""

    class __QS_ArgClass__(WritableFactorDB.__QS_ArgClass__):
        Name: str = Field(default="ElasticSearchDB", title="名称", frozen=True)
        ConnectArgs: dict = Field(default={}, title="连接参数", frozen=True)
        InnerPrefix: str = Field(default="qs_", title="内部前缀", frozen=True)
        DTField: str = Field(default="datetime", title="时点字段", frozen=True)
        IDField: str = Field(default="code", title="ID字段", frozen=True)
        IgnoreFields: List[str] = Field(default=[], title="忽略字段", frozen=True)
        FTArgs: dict = Field(default={}, title="因子表参数", frozen=True)
        SearchRetryNum: int = Field(default=10, title="查询重试次数", frozen=True)

    def __init__(self, args={}, config_file=None, **kwargs):
        self._Connection = None
        self._TableInfo = pd.DataFrame()
        self._FactorInfo = pd.DataFrame()
        super().__init__(args=args, config_file=(__QS_ConfigPath__ + os.sep + "ElasticSearchDBConfig.json" if config_file is None else config_file), **kwargs)

    # -------------------- 连接管理 --------------------
    @property
    def Connection(self):
        return self._Connection

    def connect(self):
        connect_args = self._QSArgs.ConnectArgs.copy()
        # 转换为 elasticsearch 9.x 连接格式
        host = connect_args.pop("host", "localhost")
        port = connect_args.pop("port", 9200)
        hosts = f"http://{host}:{port}"
        kwargs = {"hosts": hosts}
        auth = connect_args.pop("http_auth", None)
        if auth and auth != [None, None]:
            kwargs["basic_auth"] = (auth[0], auth[1])
        # 移除 null 值参数
        for k in list(connect_args.keys()):
            if connect_args[k] is None:
                connect_args.pop(k)
        kwargs.update(connect_args)
        self._Connection = Elasticsearch(**kwargs)
        # 读取索引元信息
        nPrefix = len(self._QSArgs.InnerPrefix)
        TableInfoList = []
        FactorInfoList = []
        try:
            TableInfo = self._Connection.indices.get_settings(index=f"{self._QSArgs.InnerPrefix}*")
        except Exception:
            TableInfo = {}
        for iTableName in TableInfo:
            TableInfoList.append({
                "DBTableName": iTableName,
                "Description": "",
                "TableClass": "WideTable",
            })
        if TableInfoList:
            self._TableInfo = pd.DataFrame(TableInfoList, index=[i["DBTableName"][nPrefix:] for i in TableInfoList])
            self._TableInfo.index.name = "TableName"
        else:
            self._TableInfo = pd.DataFrame(columns=["DBTableName", "Description", "TableClass"])
            self._TableInfo.index.name = "TableName"
        # 读取字段映射信息
        try:
            FactorInfo = self._Connection.indices.get_mapping(index=f"{self._QSArgs.InnerPrefix}*")
        except Exception:
            FactorInfo = {}
        for iTableName in FactorInfo:
            iShortName = iTableName[nPrefix:]
            iFactorInfo = FactorInfo[iTableName]["mappings"].get("properties", {})
            if iFactorInfo:
                for iFactorName, iInfo in iFactorInfo.items():
                    if iFactorName in self._QSArgs.IgnoreFields:
                        continue
                    FactorInfoList.append({
                        "TableName": iShortName,
                        "DBFieldName": iFactorName,
                        "DataType": _TypeMapping.get(iInfo["type"], "object"),
                        "FieldType": iInfo["type"],
                        "Keyword": "keyword" in iInfo.get("fields", {}),
                        "Supplementary": None,
                        "Description": "",
                    })
        if FactorInfoList:
            self._FactorInfo = pd.DataFrame(FactorInfoList)
            self._FactorInfo = self._FactorInfo.set_index(["TableName", "DBFieldName"])
            self._FactorInfo.index.names = ["TableName", "FieldName"]
        else:
            self._FactorInfo = pd.DataFrame(columns=["DataType", "FieldType", "Keyword", "Supplementary", "Description"])
            self._FactorInfo.index = pd.MultiIndex.from_tuples([], names=["TableName", "FieldName"])
        return self

    def disconnect(self):
        if self._Connection is not None:
            self._Connection.close()
            self._Connection = None
        return 0

    # -------------------- 查询方法 --------------------
    def search_scroll(self, index, query, sort, only_source=True, flattened=True, return_size=None, size=3000, scroll="10m", **kwargs):
        if self._Connection is None:
            Msg = f"'{self.Name}' 调用 search_scroll 失败: 数据库尚未连接!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        if return_size is not None:
            size = min(size, return_size)
        Body = {"query": query, "size": size, "sort": sort}
        Body.update(kwargs)
        iRslt = self._Connection.search(body=Body, scroll=scroll)
        ScrollID = iRslt.pop("_scroll_id")
        iReturnedNum = 0
        while iRslt and iRslt["hits"]["hits"]:
            iRslt = iRslt["hits"]["hits"]
            if return_size is not None:
                iRslt = iRslt[:return_size - iReturnedNum]
            if only_source:
                for ijRslt in iRslt:
                    yield ijRslt.get("_source", {})
            elif flattened:
                for ijRslt in iRslt:
                    ijRslt.update(ijRslt.pop("_source", {}))
                    yield ijRslt
            else:
                for ijRslt in iRslt:
                    yield ijRslt
            if len(iRslt) < size:
                break
            if return_size is not None:
                iReturnedNum += len(iRslt)
                if iReturnedNum >= return_size:
                    break
            iRslt = self._Connection.scroll(scroll_id=ScrollID, scroll=scroll)
            ScrollID = iRslt.pop("_scroll_id")
        self._Connection.clear_scroll(scroll_id=ScrollID)

    def _try_search(self, try_num, **kwargs):
        iRetryNum = 0
        while iRetryNum < try_num:
            try:
                return self._Connection.search(**kwargs)
            except ConnectionTimeout as e:
                SleepTime = 0.05 + (iRetryNum % 10) / 10.0
                if iRetryNum % 10 == 0:
                    self._QS_Logger.warning(f"ElasticSearchDB search failed: {e}, try again {SleepTime} seconds later!")
                iRetryNum += 1
                time.sleep(SleepTime)
        Msg = f"ElasticSearchDB search failed after trying {iRetryNum} times"
        self._QS_Logger.error(Msg)
        raise __QS_Error__(Msg)

    def search(self, index, query, sort, only_source=True, flattened=True, return_size=None, size=3000, keep_alive="10m", **kwargs):
        if self._Connection is None:
            Msg = f"'{self.Name}' 调用 search 失败: 数据库尚未连接!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        if return_size is not None:
            size = min(size, return_size)
        SortFields = [tuple(iSort.keys())[0].split(".")[0] for iSort in sort]
        PIT = self._Connection.open_point_in_time(index=index, keep_alive=keep_alive)
        try:
            iRslt = self._Connection.search(
                query=query, size=size, sort=sort,
                pit={"keep_alive": keep_alive, "id": PIT["id"]},
                **kwargs
            )
            iReturnedNum = 0
            while iRslt and iRslt["hits"]["hits"]:
                iRslt = iRslt["hits"]["hits"]
                if return_size is not None:
                    iRslt = iRslt[:return_size - iReturnedNum]
                iLastRslt = iRslt[-1]
                iSorts = [iLastRslt[iField] if iField in iLastRslt else iLastRslt["_source"][iField] for iField in SortFields]
                if only_source:
                    for ijRslt in iRslt:
                        yield ijRslt.get("_source", {})
                elif flattened:
                    for ijRslt in iRslt:
                        ijRslt.update(ijRslt.pop("_source", {}))
                        yield ijRslt
                else:
                    for ijRslt in iRslt:
                        yield ijRslt
                if len(iRslt) < size:
                    break
                if return_size is not None:
                    iReturnedNum += len(iRslt)
                    if iReturnedNum >= return_size:
                        break
                iRslt = self._Connection.search(
                    query=query, size=size, sort=sort,
                    pit={"keep_alive": keep_alive, "id": PIT["id"]},
                    search_after=iSorts, **kwargs
                )
        finally:
            self._Connection.close_point_in_time(id=PIT["id"])

    # -------------------- 因子表访问 --------------------
    @property
    def TableNames(self) -> List[str]:
        return sorted(self._TableInfo.index)

    def _initFTArgs(self, table_name: str, args: dict) -> dict:
        if table_name not in self._TableInfo.index:
            Msg = f"因子库 '{self.Name}' 调用方法 getTable 错误: 不存在因子表: '{table_name}'!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        Args = self._QSArgs.FTArgs.copy()
        Args.update(args)
        Args.setdefault("DTField", self._QSArgs.DTField)
        Args.setdefault("IDField", self._QSArgs.IDField)
        Args["Name"] = table_name
        return Args

    def getTable(self, table_name: str, args: dict = {}):
        Args = self._initFTArgs(table_name=table_name, args=args)
        return _WideTable(
            fdb=self, args=Args,
            table_info=self._TableInfo.loc[table_name],
            factor_info=self._FactorInfo.loc[table_name],
            logger=self._QS_Logger
        )

    # -------------------- 因子表管理 --------------------
    def renameTable(self, old_table_name: str, new_table_name: str):
        if old_table_name not in self._TableInfo.index:
            Msg = f"因子库 '{self.Name}' 调用方法 renameTable 错误: 不存在因子表 '{old_table_name}'!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        if (new_table_name != old_table_name) and (new_table_name in self._TableInfo.index):
            Msg = f"因子库 '{self.Name}' 调用方法 renameTable 错误: 新因子表名 '{new_table_name}' 已经存在于库中!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        OldIndex = self._QSArgs.InnerPrefix + old_table_name
        NewIndex = self._QSArgs.InnerPrefix + new_table_name
        Mappings = self._Connection.indices.get_mapping(index=OldIndex)[OldIndex]["mappings"]
        self._Connection.indices.create(index=NewIndex, mappings=Mappings)
        self._Connection.reindex(source={"index": OldIndex}, dest={"index": NewIndex})
        self._Connection.indices.delete(index=OldIndex)
        self._TableInfo = self._TableInfo.rename(index={old_table_name: new_table_name})
        self._FactorInfo = self._FactorInfo.rename(index={old_table_name: new_table_name}, level=0)

    def deleteTable(self, table_name: str):
        if table_name not in self._TableInfo.index:
            return
        self._Connection.indices.delete(index=self._QSArgs.InnerPrefix + table_name)
        TableNames = self._TableInfo.index.tolist()
        TableNames.remove(table_name)
        self._TableInfo = self._TableInfo.loc[TableNames]
        if TableNames:
            self._FactorInfo = self._FactorInfo.loc[TableNames]
        else:
            self._FactorInfo = pd.DataFrame(columns=["DataType", "FieldType", "Keyword", "Supplementary", "Description"])
            self._FactorInfo.index = pd.MultiIndex.from_tuples([], names=["TableName", "FieldName"])

    def createTable(self, table_name: str, field_types: Dict[str, str]):
        IndexName = self._QSArgs.InnerPrefix + table_name
        if not self._Connection.indices.exists(index=IndexName):
            Mappings = {"properties": {
                self._QSArgs.DTField: {"type": "date"},
                self._QSArgs.IDField: {"type": "keyword"},
            }}
            Mappings["properties"].update({iFactor: {"type": iFieldType} for iFactor, iFieldType in field_types.items()})
            self._Connection.indices.create(index=IndexName, mappings=Mappings)
        self._TableInfo = pd.concat([self._TableInfo, pd.DataFrame(
            [[IndexName, "", "WideTable"]],
            columns=["DBTableName", "Description", "TableClass"],
            index=[table_name]
        )])
        NewFactorInfo = []
        for iFactor, iFieldType in field_types.items():
            NewFactorInfo.append({
                "TableName": table_name,
                "FieldName": iFactor,
                "DataType": _TypeMapping.get(iFieldType, "object"),
                "FieldType": iFieldType,
                "Keyword": False,
                "Supplementary": None,
                "Description": "",
            })
        if NewFactorInfo:
            NewFactorInfo = pd.DataFrame(NewFactorInfo).set_index(["TableName", "FieldName"])
            self._FactorInfo = pd.concat([self._FactorInfo, NewFactorInfo]).sort_index()

    def addFactor(self, table_name: str, field_types: Dict[str, str]):
        if table_name not in self._TableInfo.index:
            return self.createTable(table_name, field_types)
        self._Connection.indices.put_mapping(
            index=self._QSArgs.InnerPrefix + table_name,
            properties={iFactor: {"type": iFieldType} for iFactor, iFieldType in field_types.items()}
        )
        NewFactorInfo = []
        for iFactor, iFieldType in field_types.items():
            NewFactorInfo.append({
                "TableName": table_name,
                "FieldName": iFactor,
                "DataType": _TypeMapping.get(iFieldType, "object"),
                "FieldType": iFieldType,
                "Keyword": False,
                "Supplementary": None,
                "Description": "",
            })
        if NewFactorInfo:
            NewFactorInfo = pd.DataFrame(NewFactorInfo).set_index(["TableName", "FieldName"])
            self._FactorInfo = pd.concat([self._FactorInfo, NewFactorInfo]).sort_index()

    def renameFactor(self, table_name: str, old_factor_name: str, new_factor_name: str):
        if old_factor_name not in self._FactorInfo.loc[table_name].index:
            Msg = f"因子库 '{self.Name}' 调用方法 renameFactor 错误: 因子表 '{table_name}' 中不存在因子 '{old_factor_name}'!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        if (new_factor_name != old_factor_name) and (new_factor_name in self._FactorInfo.loc[table_name].index):
            Msg = f"因子库 '{self.Name}' 调用方法 renameFactor 错误: 新因子名 '{new_factor_name}' 已经存在于因子表 '{table_name}' 中!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        IndexName = self._QSArgs.InnerPrefix + table_name
        # 备份原索引
        Mappings = self._Connection.indices.get_mapping(index=IndexName)[IndexName]["mappings"]
        BakIndexName = IndexName + "_bak"
        self._Connection.indices.create(index=BakIndexName, mappings=Mappings)
        self._Connection.reindex(source={"index": IndexName}, dest={"index": BakIndexName})
        # 删除原索引
        self._Connection.indices.delete(index=IndexName)
        # 修改名称并恢复索引
        Mappings["properties"][new_factor_name] = Mappings["properties"].pop(old_factor_name)
        self._Connection.indices.create(index=IndexName, mappings=Mappings)
        self._Connection.reindex(
            source={"index": BakIndexName}, dest={"index": IndexName},
            script={"source": f'ctx._source.{new_factor_name} = ctx._source.remove("{old_factor_name}")'}
        )
        # 删除临时索引
        self._Connection.indices.delete(index=BakIndexName)
        TableNames = self._TableInfo.index.tolist()
        TableNames.remove(table_name)
        self._FactorInfo = pd.concat([
            self._FactorInfo.loc[TableNames],
            self._FactorInfo.loc[[table_name]].rename(index={old_factor_name: new_factor_name}, level=1)
        ])

    def deleteFactor(self, table_name: str, factor_names: List[str]):
        if (not factor_names) or (table_name not in self._TableInfo.index):
            return 0
        FactorIndex = self._FactorInfo.loc[table_name].index.difference(factor_names).tolist()
        if not FactorIndex:
            return self.deleteTable(table_name)
        IndexName = self._QSArgs.InnerPrefix + table_name
        # 备份原索引
        Mappings = self._Connection.indices.get_mapping(index=IndexName)[IndexName]["mappings"]
        BakIndexName = IndexName + "_bak"
        self._Connection.indices.create(index=BakIndexName, mappings=Mappings)
        self._Connection.reindex(source={"index": IndexName}, dest={"index": BakIndexName})
        # 删除原索引
        self._Connection.indices.delete(index=IndexName)
        # 修改映射并恢复索引
        for iFactorName in factor_names:
            Mappings["properties"].pop(iFactorName, None)
        self._Connection.indices.create(index=IndexName, mappings=Mappings)
        Script = "\n".join(f'ctx._source.remove("{iFactorName}");' for iFactorName in factor_names)
        self._Connection.reindex(
            source={"index": BakIndexName}, dest={"index": IndexName},
            script={"source": Script}
        )
        # 删除临时索引
        self._Connection.indices.delete(index=BakIndexName)
        TableNames = self._TableInfo.index.tolist()
        TableNames.remove(table_name)
        Remaining = self._FactorInfo.loc[table_name].loc[FactorIndex]
        Remaining.index = pd.MultiIndex.from_product([[table_name], Remaining.index], names=["TableName", "FieldName"])
        self._FactorInfo = pd.concat([self._FactorInfo.loc[TableNames], Remaining])

    # -------------------- 数据操作 --------------------
    def deleteData(self, table_name: str, ids: Optional[List[str]] = None, dts: Optional[List[dt.datetime]] = None, **kwargs):
        if (ids is None) and (dts is None):
            Body = {"query": {"match_all": {}}}
        else:
            Body = {"query": {"bool": {"filter": []}}}
            if ids is not None:
                Body["query"]["bool"]["filter"].append({"terms": {f"{self._QSArgs.IDField}": ids}})
            if dts is not None:
                DTStrs = [iDT.strftime("%Y-%m-%dT%H:%M:%S") for iDT in dts]
                Body["query"]["bool"]["filter"].append({"terms": {self._QSArgs.DTField: DTStrs}})
        self._Connection.delete_by_query(index=self._QSArgs.InnerPrefix + table_name, **Body)
        return 0

    def writeData(self, data: Panel, table_name: str, if_exists: Literal["update", "replace", "append"] = "update", data_type: Dict[str, Literal["double", "string", "object"]] = {}, **kwargs):
        already_deleted = False
        if table_name not in self._TableInfo.index:
            FieldTypes = {iFactorName: _identifyDataType(data.iloc[i].dtypes) for i, iFactorName in enumerate(data.items)}
            self.createTable(table_name, field_types=FieldTypes)
        else:
            NewFactorNames = data.items.difference(self._FactorInfo.loc[table_name].index).tolist()
            if NewFactorNames:
                FieldTypes = {iFactorName: _identifyDataType(data.iloc[i].dtypes) for i, iFactorName in enumerate(NewFactorNames)}
                self.addFactor(table_name, FieldTypes)
            if if_exists == "update":
                OldFactorNames = self._FactorInfo.loc[table_name].index.difference(data.items).difference(
                    {self._QSArgs.DTField, self._QSArgs.IDField}
                ).tolist()
                if OldFactorNames:
                    OldData = self.getTable(table_name).readData(
                        factor_names=OldFactorNames,
                        ids=data.minor_axis.tolist(),
                        dts=data.major_axis.tolist()
                    )
                    for iFactorName in OldFactorNames:
                        data[iFactorName] = OldData[iFactorName]
            elif if_exists == "replace":
                self.deleteData(table_name)  # 删除所有数据
                already_deleted = True
            elif if_exists == "append":
                # 读取本次写入因子的旧数据，不覆盖已有非空值
                WriteFactorNames = [f for f in data.items if f in self._FactorInfo.loc[table_name].index]
                if WriteFactorNames:
                    OldData = self.getTable(table_name).readData(
                        factor_names=WriteFactorNames,
                        ids=data.minor_axis.tolist(),
                        dts=data.major_axis.tolist()
                    )
                    for iFactorName in WriteFactorNames:
                        data[iFactorName] = OldData[iFactorName].where(pd.notnull(OldData[iFactorName]), data[iFactorName])
            else:
                Msg = f"因子库 '{self.Name}' 调用方法 writeData 错误: 不支持的写入方式 '{if_exists}'!"
                self._QS_Logger.error(Msg)
                raise __QS_Error__(Msg)

        # 将 Panel 展开为 DataFrame
        DTs = data.major_axis
        data.major_axis = [iDT.strftime("%Y-%m-%dT%H:%M:%S") for iDT in DTs]
        NewData = {}
        for iFactorName in data.items:
            iData = data.loc[iFactorName].stack(future_stack=True)
            NewData[iFactorName] = iData
        NewData = pd.DataFrame(NewData).loc[:, data.items]
        Mask = pd.notnull(NewData).any(axis=1)
        NewData = NewData[Mask]
        if NewData.shape[0] == 0:
            return 0

        # 删除旧数据并写入新数据
        if not already_deleted:
            self.deleteData(table_name, ids=data.minor_axis.tolist(), dts=DTs.tolist())
        NewData = NewData.reset_index()
        NewData.columns = [self._QSArgs.DTField, self._QSArgs.IDField] + NewData.columns[2:].tolist()
        # 过滤掉 NaN 值（ES 不接受 NaN）
        def _clean_doc(row):
            return {k: v for k, v in row.items() if pd.notnull(v)}
        helpers.bulk(
            client=self._Connection,
            actions=({"_op_type": "index", "_index": self._QSArgs.InnerPrefix + table_name, "_source": _clean_doc(NewData.iloc[i].to_dict())} for i in range(NewData.shape[0]))
        )
        self._Connection.indices.refresh(index=self._QSArgs.InnerPrefix + table_name)
        return 0
