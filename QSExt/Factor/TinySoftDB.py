# coding=utf-8
"""基于天软的因子库"""
import os
import json
import datetime as dt
from typing import Union, Optional, Dict, List, Literal

import numpy as np
import pandas as pd
import pyTSL
from pydantic import Field

from QSExt import __QS_MainPath__, __QS_ConfigPath__
from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.QSObject import Panel
from QuantStudio.Factor.FactorDB import FactorDB
from QuantStudio.Factor.FactorTable import FactorTable
from QuantStudio.Factor.FactorUtils import updateInfo, importInfo, SQL_Table, SQL_WideTable, SQL_FeatureTable, SQL_MappingTable
from QuantStudio.Tools.DateTimeFun import getDateTimeSeries


def _adjustID(ids):
    return pd.Series(ids, index=["".join(reversed(iID.split("."))) for iID in ids])


class _TSTable(FactorTable):
    class __QS_ArgClass__(FactorTable.__QS_ArgClass__):
        FilterCondition: str = Field(default="", title="筛选条件", frozen=True, repr=False)
        TableType: str = Field(default="", title="因子表类型", frozen=True)

    def getMetaData(self, key=None):
        TableInfo = self._FactorDB._TableInfo.loc[self.Name]
        if key is None: return TableInfo
        else: return TableInfo.get(key, None)

    @property
    def FactorNames(self):
        FactorInfo = self._FactorDB._FactorInfo.loc[self.Name]
        return FactorInfo[FactorInfo["FieldType"]=="因子"].index.tolist()

    def getFactorMetaData(self, factor_names=None, key=None):
        if factor_names is None: factor_names = self.FactorNames
        FactorInfo = self._FactorDB._FactorInfo.loc[self.Name]
        if key=="DataType":
            if hasattr(self, "_DataType"): return self._DataType.loc[factor_names]
            MetaData = FactorInfo["DataType"].loc[factor_names]
            for i in range(MetaData.shape[0]):
                iDataType = MetaData.iloc[i].lower()
                if (iDataType.find("real")!=-1) or (iDataType.find("int")!=-1): MetaData.iloc[i] = "double"
                else: MetaData.iloc[i] = "string"
            return MetaData
        elif key=="Description": return FactorInfo["Description"].loc[factor_names]
        elif key is None:
            return pd.DataFrame({"DataType":self.getFactorMetaData(factor_names, key="DataType", args=args),
                                 "Description":self.getFactorMetaData(factor_names, key="Description", args=args)})
        else:
            return pd.Series([None]*len(factor_names), index=factor_names, dtype=np.dtype("O"))

    def getID(self, ifactor_name=None, idt=None):
        return []


class _CalendarTable(FactorTable):
    """交易日历因子表"""
    @property
    def FactorNames(self):
        return ["交易日"]

    def getFactorMetaData(self, factor_names=None, key=None):
        if factor_names is None: factor_names = self.FactorNames
        if key=="DataType": return pd.Series(["double"]*len(factor_names), index=factor_names)
        elif key=="Description": return pd.Series(["0 or nan: 非交易日; 1: 交易日"]*len(factor_names), index=factor_names)
        elif key is None:
            return pd.DataFrame({"DataType": self.getFactorMetaData(factor_names, key="DataType"), "Description": self.getFactorMetaData(factor_names, key="Description")})
        else:
            return pd.Series([None]*len(factor_names), index=factor_names, dtype=np.dtype("O"))

    def getID(self, ifactor_name=None, idt=None):
        return ["SSE", "SZSE"]

    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None):
        if start_dt is None: start_dt = dt.date(1900, 1, 1)
        if end_dt is None: end_dt = dt.date.today()
        return self._FactorDB.getTradeDay(start_date=start_dt, end_date=end_dt)

    def __QS_calcData__(self, raw_data, factor_names, ids, dts):
        Data = pd.DataFrame(1, index=self.getDateTime(start_dt=dts[0], end_dt=dts[-1]), columns=["SSE", "SZSE"])
        if Data.index.intersection(dts).shape[0]==0: return Panel(np.nan, items=factor_names, major_axis=dts, minor_axis=ids)
        Data = Data.reindex(index=dts, columns=ids)
        return Panel({"交易日": Data})


class _TradeTable(_TSTable):
    """tradetable"""
    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None):
        if iid is None: iid = "000001.SH"
        if start_dt is None: start_dt = dt.datetime(1970, 1, 1)
        if end_dt is None: end_dt = dt.datetime.now()
        CodeStr = "return select "+"['date'] "
        CodeStr += "from tradetable datekey inttodate("+start_dt.strftime("%Y%m%d")+") "
        CodeStr += "to (inttodate("+end_dt.strftime("%Y%m%d")+")+0.9999) of '{ID}' end;"
        r = self._FactorDB._exec(CodeStr.format(ID="".join(reversed(iid.split(".")))))
        DTs = np.array([pyTSL.DoubleToDatetime(iData["date"]) for iData in r], dtype="O")
        return DTs[(DTs>=start_dt) & (DTs<=end_dt)].tolist()

    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        Fields = self._FactorDB._FactorInfo["DBFieldName"].loc[self.Name].loc[factor_names].tolist()
        CodeStr = "return select "+"['date'],['"+("'],['".join(Fields))+"'] "
        CodeStr += "from tradetable datekey inttodate("+dts[0].strftime("%Y%m%d")+") "
        CodeStr += "to (inttodate("+dts[-1].strftime("%Y%m%d")+")+0.9999) of '{ID}' end;"
        Data = {}
        for iID in ids:
            iCodeStr = CodeStr.format(ID="".join(reversed(iID.split("."))))
            iData = self._FactorDB._exec(iCodeStr)
            if iData:
                df = pd.DataFrame(iData)
                df["date"] = df["date"].apply(pyTSL.DoubleToDatetime)
                Data[iID] = df.set_index(["date"])
        if not Data: return Panel(Data)
        Data = Panel(Data).swapaxes(0, 2)
        Data = Data.loc[Fields]
        Data.items = factor_names
        return Data

    def __QS_calcData__(self, raw_data, factor_names, ids, dts):
        if raw_data.shape[2]==0: return Panel(items=factor_names, major_axis=dts, minor_axis=ids)
        return raw_data.loc[:, dts, ids]

    def readDayData(self, factor_names, ids, start_date, end_date):
        RawData = self.__QS_prepareRawData__(factor_names, ids, dts=[start_date, end_date])
        if RawData.shape[2]==0: return Panel(items=factor_names, major_axis=[], minor_axis=ids)
        return RawData.loc[:, :, ids]


class _QuoteTable(_TSTable):
    """markettable"""
    class __QS_ArgClass__(_TSTable.__QS_ArgClass__):
        Cycle: Union[int, str] = Field(default=60, title="周期", frozen=False)
        CycleUnit: str = Field(default="s", title="周期单位", frozen=False)

    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None):
        if iid is None: iid = "000001.SH"
        CycleStr = self._genCycleStr(self._QSArgs.Cycle, self._QSArgs.CycleUnit)
        if start_dt is None: start_dt = dt.datetime(1970, 1, 1)
        if end_dt is None: end_dt = dt.datetime.now()
        CodeStr = "SetSysParam(pn_cycle(),"+CycleStr+");"
        CodeStr += "return select "+"['date'] "
        CodeStr += "from markettable datekey inttodate("+start_dt.strftime("%Y%m%d")+") "
        CodeStr += "to (inttodate("+end_dt.strftime("%Y%m%d")+")+0.9999) of '{ID}' end;"
        r = self._FactorDB._exec(CodeStr.format(ID="".join(reversed(iid.split(".")))))
        DTs = np.array([pyTSL.DoubleToDatetime(iData["date"]) for iData in r], dtype="O")
        return DTs[(DTs>=start_dt) & (DTs<=end_dt)].tolist()

    def _genCycleStr(self, cycle, cycle_unit):
        if isinstance(cycle, str): return "cy_"+cycle+"()"
        elif cycle_unit=="s": return ("cy_trailingseconds(%d)" % cycle)
        elif cycle_unit=="d": return ("cy_trailingdays(%d)" % cycle)
        else: raise __QS_Error__("不支持的和周期单位: '%s'!" % (cycle_unit, ))

    def __QS_genGroupInfo__(self, factors, operation_mode):
        CycleStrGroup = {}
        for iFactor in factors:
            iCycleStr = self._genCycleStr(iFactor.Cycle, iFactor.CycleUnit)
            if iCycleStr not in CycleStrGroup:
                CycleStrGroup[iCycleStr] = {"FactorNames":[iFactor.Name],
                                            "RawFactorNames":{iFactor._NameInFT},
                                            "StartDT":operation_mode._FactorStartDT[iFactor.Name],
                                            "args":iFactor.Args.copy()}
            else:
                CycleStrGroup[iCycleStr]["FactorNames"].append(iFactor.Name)
                CycleStrGroup[iCycleStr]["RawFactorNames"].add(iFactor._NameInFT)
                CycleStrGroup[iCycleStr]["StartDT"] = min(operation_mode._FactorStartDT[iFactor.Name], CycleStrGroup[iCycleStr]["StartDT"])
        EndInd = operation_mode.DTRuler.index(operation_mode.DateTimes[-1])
        Groups = []
        for iCycleStr in CycleStrGroup:
            StartInd = operation_mode.DTRuler.index(CycleStrGroup[iCycleStr]["StartDT"])
            Groups.append((self, CycleStrGroup[iCycleStr]["FactorNames"], list(CycleStrGroup[iCycleStr]["RawFactorNames"]), operation_mode.DTRuler[StartInd:EndInd+1], CycleStrGroup[iCycleStr]["args"]))
        return Groups

    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        CycleStr = self._genCycleStr(self._QSArgs.Cycle, self._QSArgs.CycleUnit)
        Fields = self._FactorDB._FactorInfo["DBFieldName"].loc[self.Name].loc[factor_names].tolist()
        CodeStr = "SetSysParam(pn_cycle(),"+CycleStr+");"
        CodeStr += "return select "+"['date'],['"+"'],['".join(Fields)+"'] "
        CodeStr += "from markettable datekey inttodate("+dts[0].strftime("%Y%m%d")+") "
        CodeStr += "to (inttodate("+dts[-1].strftime("%Y%m%d")+")+0.9999) of '{ID}' end;"
        Data = {}
        for iID in ids:
            iCodeStr = CodeStr.format(ID="".join(reversed(iID.split("."))))
            iData = self._FactorDB._exec(iCodeStr)
            if iData:
                df = pd.DataFrame(iData)
                df["date"] = df["date"].apply(pyTSL.DoubleToDatetime)
                Data[iID] = df.set_index(["date"])
        if not Data: return Panel(Data)
        Data = Panel(Data).swapaxes(0, 2)
        Data = Data.loc[Fields]
        Data.items = factor_names
        return Data

    def __QS_calcData__(self, raw_data, factor_names, ids, dts):
        if raw_data.shape[2]==0: return Panel(items=factor_names, major_axis=dts, minor_axis=ids)
        return raw_data.loc[:, dts, ids]

    def readDayData(self, factor_names, ids, start_date, end_date):
        RawData = self.__QS_prepareRawData__(factor_names, ids, dts=[start_date, end_date])
        if RawData.shape[2]==0: return Panel(items=factor_names, major_axis=[], minor_axis=ids)
        return RawData.loc[:, :, ids]


class _TS_SQL_Table(SQL_Table):
    def __init__(self, fdb, args={}, table_info=None, factor_info=None, **kwargs):
        if table_info is None:
            name = args.get("Name", "")
            table_info = fdb._TableInfo.loc[name]
        if factor_info is None:
            name = args.get("Name", "")
            factor_info = fdb._FactorInfo.loc[name]
        super().__init__(fdb=fdb, args=args, table_prefix="", table_info=table_info, factor_info=factor_info, security_info=None, exchange_info=None, **kwargs)
        self._DBTableName = "[1]"
        self._MainTableName = self._DBTableName
        self._DTFormat = "%Y%m%d"

    def __QS_adjustID__(self, ids):
        return ["".join(reversed(iID.split("."))) for iID in ids]

    def __QS_restoreID__(self, ids):
        return ids

    def _genFromSQLStr(self, setable_join_str=[]):
        SQLStr = "FROM INFOTABLE "+str(int(self._TableInfo["DBTableName"]))+" "
        return SQLStr[:-1]

    def _genIDSQLStr(self, ids, init_keyword="AND"):
        if ids is None:
            raise __QS_Error__("TinysoftDB 的因子表方法参数 ids 不能为 None")
        SQLStr = "OF ARRAY('"+"','".join(self.__QS_adjustID__(ids))+"')"
        return SQLStr

    def getID(self, ifactor_name=None, idt=None):
        return []


class _WideTable(_TS_SQL_Table, SQL_WideTable):
    """宽因子表"""
    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None):
        DTField = self._FactorInfo.loc[self.DTField, "DBFieldName"]
        SQLStr = "SELECT DISTINCT "+DTField+" "
        if iid is not None:
            SQLStr += self._genFromSQLStr()+" "
            SQLStr += self._genIDSQLStr([iid], init_keyword="WHERE")+" "
            SQLStr += self._genConditionSQLStr(use_main_table=True)+" "
        else:
            raise __QS_Error__("TinysoftDB 的因子表方法 getDateTime 参数 iid 不能为 None")
        if start_dt is not None: SQLStr += "AND "+DTField+">="+start_dt.strftime(self._DTFormat)+" "
        if end_dt is not None: SQLStr += "AND "+DTField+"<="+end_dt.strftime(self._DTFormat)+" "
        SQLStr += "ORDER BY "+DTField+" END"
        Rslt = self._FactorDB._exec("RETURN exportjsonstring("+SQLStr+");")
        Rslt = pd.DataFrame(json.loads(Rslt)).iloc[:, 0]
        return Rslt.apply(lambda x: dt.datetime.strptime(str(x), self._DTFormat)).tolist()

    def _genNullIDSQLStr_WithPublDT(self, factor_names, ids, end_date, args={}):
        IDStr = "','".join(self.__QS_adjustID__(ids))
        EndDTField = self._FactorInfo.loc[self._QSArgs.DTField, "DBFieldName"]
        AnnDTField = self._FactorInfo.loc[self._QSArgs.PublDTField, "DBFieldName"]
        IDField = self._FactorInfo.loc[self._QSArgs.IDField if self._QSArgs.IDField else self._IDField, "DBFieldName"]
        SubSQLStr = "SELECT "+IDField+", "
        SubSQLStr += "MAXOF("+EndDTField+") AS 'MaxEndDate' "
        SubSQLStr += self._genFromSQLStr()+" "
        SubSQLStr += "OF ARRAY('"+IDStr+"') "
        SubSQLStr += "WHERE ("+AnnDTField+"<"+end_date.strftime(self._DTFormat)+" "
        SubSQLStr += "AND "+EndDTField+"<"+end_date.strftime(self._DTFormat)+") "
        SubSQLStr += self._genConditionSQLStr(use_main_table=False)+" "
        SubSQLStr += "GROUP BY "+IDField+" END"
        SQLStr = "SELECT MAX([1]."+AnnDTField+", [2].['MaxEndDate']) AS 'QS_DT', "
        SQLStr += "[1]."+IDField+" AS 'QS_ID', "
        SQLStr += "[2].['MaxEndDate'] AS 'MaxEndDate', "
        for iField in factor_names: SQLStr += "[1]."+self._FactorInfo.loc[iField, "DBFieldName"]+", "
        SQLStr = SQLStr[:-2]+" "+self._genFromSQLStr()+" "
        SQLStr += "OF ARRAY('"+IDStr+"') "
        SQLStr += "JOIN ("+SubSQLStr+") WITH ([1]."+IDField+", [1]."+EndDTField+" ON [2]."+IDField+", [2].['MaxEndDate']) "
        SQLStr += self._genConditionSQLStr(use_main_table=False, init_keyword="WHERE")+" END"
        return "RETURN exportjsonstring("+SQLStr+");"

    def _prepareRawData_WithPublDT(self, factor_names, ids, dts, args={}):
        if (dts==[]) or (ids==[]): return pd.DataFrame(columns=["QS_DT", "QS_ID"]+factor_names)
        IDMapping = _adjustID(ids)
        IDStr = "','".join(self.__QS_adjustID__(IDMapping.index))
        StartDate, EndDate = dts[0].date(), dts[-1].date()
        LookBack = self._QSArgs.LookBack
        if not np.isinf(LookBack): StartDate -= dt.timedelta(LookBack)
        EndDTField = self._FactorInfo.loc[self._QSArgs.DTField, "DBFieldName"]
        AnnDTField = self._FactorInfo.loc[self._QSArgs.PublDTField, "DBFieldName"]
        IDField = self._FactorInfo.loc[self._QSArgs.IDField if self._QSArgs.IDField else self._IDField, "DBFieldName"]
        SubSQLStr = "SELECT "+IDField+", "
        SubSQLStr += "MAX("+AnnDTField+", "+EndDTField+") AS 'AnnDate', "
        SubSQLStr += "MAXOF("+EndDTField+") AS 'MaxEndDate' "
        SubSQLStr += self._genFromSQLStr()+" "
        SubSQLStr += "OF ARRAY('"+IDStr+"') "
        SubSQLStr += "WHERE ("+AnnDTField+">="+StartDate.strftime(self._DTFormat)+" "
        SubSQLStr += "OR "+EndDTField+">="+StartDate.strftime(self._DTFormat)+") "
        SubSQLStr += "AND ("+AnnDTField+"<="+EndDate.strftime(self._DTFormat)+" "
        SubSQLStr += "AND "+EndDTField+"<="+EndDate.strftime(self._DTFormat)+") "
        SubSQLStr += self._genConditionSQLStr(use_main_table=False)+" "
        SubSQLStr += "GROUP BY "+IDField+", "+ "MAX("+AnnDTField+", "+EndDTField+") END"
        SQLStr = "SELECT [2].['AnnDate'] AS 'QS_DT', "
        SQLStr += IDField+" AS 'QS_ID', "
        SQLStr += "[2].['MaxEndDate'] AS 'MaxEndDate', "
        for iField in factor_names: SQLStr += "[1]."+self._FactorInfo.loc[iField, "DBFieldName"]+", "
        SQLStr = SQLStr[:-2]+" "+self._genFromSQLStr()+" "
        SQLStr += "OF ARRAY('"+IDStr+"') "
        SQLStr += "JOIN ("+SubSQLStr+") WITH ([1]."+IDField+", [1]."+EndDTField+" ON [2]."+IDField+", [2].['MaxEndDate']) "
        SQLStr += self._genConditionSQLStr(use_main_table=False, init_keyword="WHERE")+" "
        SQLStr += "ORDER BY [1].['QS_ID'], [1].['QS_DT'] END"
        RawData = json.loads(self._FactorDB._exec("RETURN exportjsonstring("+SQLStr+");"))
        if not RawData: RawData = pd.DataFrame(columns=["QS_DT", "QS_ID", "MaxEndDate"]+factor_names)
        else: RawData = pd.DataFrame(RawData).loc[:, ["QS_DT", "QS_ID", "MaxEndDate"]+factor_names]
        if np.isinf(LookBack):
            NullIDs = set(ids).difference(set(RawData[RawData["QS_DT"]==dt.datetime.combine(StartDate,dt.time(0))]["QS_ID"]))
            if NullIDs:
                NullRawData = json.loads(self._FactorDB._exec(self._genNullIDSQLStr_WithPublDT(factor_names, list(NullIDs), StartDate, args=args)))
                if NullRawData:
                    NullRawData = pd.DataFrame(NullRawData).loc[:, ["QS_DT", "QS_ID", "MaxEndDate"]+factor_names]
                    RawData = pd.concat([NullRawData, RawData], ignore_index=True)
                    RawData.sort_values(by=["QS_ID", "QS_DT"])
        if RawData.shape[0]==0: return RawData.loc[:, ["QS_DT", "QS_ID"]+factor_names]
        RawData["QS_ID"] = IDMapping.loc[RawData["QS_ID"].values].values
        RawData["QS_DT"] = RawData["QS_DT"].apply(lambda x: dt.datetime.strptime(str(int(x)), self._DTFormat))
        if self.EndDateASC:# 删除截止日期非递增的记录
            DTRank = RawData.loc[:, ["QS_ID", "QS_DT", "MaxEndDate"]].set_index(["QS_ID"]).astype(np.datetime64).groupby(axis=0, level=0).rank(method="min")
            RawData = RawData[(DTRank["QS_DT"]<=DTRank["MaxEndDate"]).values]
        return RawData.loc[:, ["QS_DT", "QS_ID"]+factor_names]

    def _genNullIDSQLStr_IgnorePublDT(self, factor_names, ids, end_date, args={}):
        IDStr ="','".join(self.__QS_adjustID__(ids))
        DTField = self._FactorInfo.loc[self._QSArgs.DTField, "DBFieldName"]
        IDField = self._FactorInfo.loc[self._QSArgs.IDField if self._QSArgs.IDField else self._IDField, "DBFieldName"]
        SubSQLStr = "SELECT "+IDField+", "
        SubSQLStr += "MAXOF("+DTField+") AS 'MaxEndDate' "
        SubSQLStr += self._genFromSQLStr()+" "
        SubSQLStr += "OF ARRAY('"+IDStr+"') "
        SubSQLStr += "WHERE "+DTField+"<"+end_date.strftime(self._DTFormat)+" "
        SubSQLStr += self._genConditionSQLStr(use_main_table=False)+" "
        SubSQLStr += "GROUP BY "+IDField+" END"
        SQLStr = "SELECT [1]."+DTField+" AS 'QS_DT', "
        SQLStr += "[1]."+IDField+" AS 'QS_ID', "
        for iField in factor_names: SQLStr += "[1]."+self._FactorInfo.loc[iField, "DBFieldName"]+", "
        SQLStr = SQLStr[:-2]+" "+self._genFromSQLStr()+" "
        SQLStr += "OF ARRAY('"+IDStr+"') "
        SQLStr += "JOIN ("+SubSQLStr+") WITH ([1]."+IDField+", [1]."+DTField+" ON [2]."+IDField+", [2].['MaxEndDate']) "
        SQLStr += self._genConditionSQLStr(use_main_table=False, init_keyword="WHERE")+" END"
        return "RETURN exportjsonstring("+SQLStr+");"

    def _prepareRawData_IgnorePublDT(self, factor_names, ids, dts, args={}):
        if (dts==[]) or (ids==[]): return pd.DataFrame(columns=["QS_DT", "QS_ID"]+factor_names)
        IDMapping = _adjustID(ids)
        StartDate, EndDate = dts[0].date(), dts[-1].date()
        LookBack = self._QSArgs.LookBack
        if not np.isinf(LookBack): StartDate -= dt.timedelta(LookBack)
        DTField = self._FactorInfo.loc[self._QSArgs.DTField, "DBFieldName"]
        IDField = self._FactorInfo.loc[self._QSArgs.IDField if self._QSArgs.IDField else self._IDField, "DBFieldName"]
        # 形成SQL语句, 日期, ID, 因子数据
        SQLStr = "SELECT "+DTField+" AS 'QS_DT', "
        SQLStr += IDField+" AS 'QS_ID', "
        for iField in factor_names: SQLStr += self._FactorInfo.loc[iField, "DBFieldName"]+", "
        SQLStr = SQLStr[:-2]+" "+self._genFromSQLStr()+" "
        SQLStr += "OF ARRAY('"+"','".join(IDMapping.index)+"') "
        SQLStr += "WHERE "+DTField+">="+StartDate.strftime(self._DTFormat)+" "
        SQLStr += "AND "+DTField+"<="+EndDate.strftime(self._DTFormat)+" "
        SQLStr += self._genConditionSQLStr()+" "
        SQLStr += "ORDER BY ['QS_ID'], ['QS_DT'] END"
        RawData = json.loads(self._FactorDB._exec("RETURN exportjsonstring("+SQLStr+");"))
        if not RawData: RawData = pd.DataFrame(columns=["QS_DT", "QS_ID"]+factor_names)
        else: RawData = pd.DataFrame(RawData).loc[:, ["QS_DT", "QS_ID"]+factor_names]
        if np.isinf(LookBack):
            NullIDs = set(ids).difference(set(RawData[RawData["QS_DT"]==dt.datetime.combine(StartDate,dt.time(0))]["QS_ID"]))
            if NullIDs:
                NullRawData = json.loads(self._FactorDB._exec(self._genNullIDSQLStr_IgnorePublDT(factor_names, list(NullIDs), StartDate, args=args)))
                if NullRawData:
                    NullRawData = pd.DataFrame(NullRawData).loc[:, ["QS_DT", "QS_ID"]+factor_names]
                    RawData = pd.concat([NullRawData, RawData], ignore_index=True)
                    RawData.sort_values(by=["QS_ID", "QS_DT"])
        RawData["QS_ID"] = IDMapping.loc[RawData["QS_ID"].values].values
        RawData["QS_DT"] = RawData["QS_DT"].apply(lambda x: dt.datetime.strptime(str(int(x)), self._DTFormat))
        return RawData


class _FeatureTable(_TS_SQL_Table, SQL_FeatureTable):
    """特征因子表"""
    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        if ids==[]: return pd.DataFrame(columns=["QS_ID"]+factor_names)
        IDMapping = _adjustID(ids)
        IDField = self._FactorInfo.loc[self._QSArgs.IDField if self._QSArgs.IDField else self._IDField, "DBFieldName"]
        # 形成SQL语句, ID, 因子数据
        SQLStr = "SELECT "+IDField+" AS 'QS_ID', "
        for iField in factor_names: SQLStr += self._FactorInfo.loc[iField, "DBFieldName"]+", "
        SQLStr = SQLStr[:-2]+" "+self._genFromSQLStr()+" "
        SQLStr += "OF ARRAY('"+"','".join(IDMapping.index)+"') "
        SQLStr += self._genConditionSQLStr()+" "
        SQLStr += "ORDER BY ['QS_ID'] END"
        RawData = json.loads(self._FactorDB._exec("RETURN exportjsonstring("+SQLStr+");"))
        if not RawData: return pd.DataFrame(columns=["QS_ID"]+factor_names)
        RawData = pd.DataFrame(RawData).loc[:, ["QS_ID"]+factor_names]
        RawData["QS_ID"] = IDMapping.loc[RawData["QS_ID"].values].values
        return RawData


class _MappingTable(_TS_SQL_Table, SQL_MappingTable):
    """映射因子表"""
    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None):
        DTField = self._FactorInfo.loc[self._QSArgs.DTField, "DBFieldName"]
        SQLStr = "SELECT MINOF("+DTField+") AS 'StartDT'"# 起始日期
        if iid is not None:
            SQLStr += self._genFromSQLStr()+" "
            SQLStr += self._genIDSQLStr([iid])+" "
            SQLStr += self._genConditionSQLStr(use_main_table=True)+" "
        else:
            raise __QS_Error__("TinysoftDB 的因子表方法 getDateTime 参数 iid 不能为 None")
        StartDT = dt.datetime.strptime(str(int(json.loads(self._FactorDB._exec("RETURN exportjsonstring("+SQLStr+"END);"))[0]["StartDT"])), self._DTFormat)
        if start_dt is not None: StartDT = max((StartDT, start_dt))
        if end_dt is None: end_dt = dt.datetime.combine(dt.date.today(), dt.time(0))
        return getDateTimeSeries(start_dt=StartDT, end_dt=end_dt, timedelta=dt.timedelta(1))

    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        IDMapping = _adjustID(ids)
        IDField = self._FactorInfo.loc[self._QSArgs.IDField if self._QSArgs.IDField else self._IDField, "DBFieldName"]
        StartDate, EndDate = dts[0].date(), dts[-1].date()
        DTField = self._FactorInfo.loc[self._QSArgs.DTField, "DBFieldName"]
        EndDTField = self._FactorInfo.loc[self._QSArgs.EndDTField, "DBFieldName"]
        # 形成SQL语句, ID, 开始日期, 结束日期, 因子数据
        SQLStr = "SELECT "+IDField+" AS 'QS_ID', "
        SQLStr += DTField+" AS 'QS_起始日', "
        SQLStr += EndDTField+" AS 'QS_结束日', "
        for iField in factor_names: SQLStr += self._FactorInfo.loc[iField, "DBFieldName"]+", "
        SQLStr = SQLStr[:-2]+" "+self._genFromSQLStr()+" "
        SQLStr += "OF ARRAY('"+"','".join(IDMapping.index)+"') "
        SQLStr += "WHERE (("+EndDTField+">="+StartDate.strftime(self._DTFormat)+") "
        SQLStr += "OR ("+EndDTField+" IS NULL) "
        SQLStr += "OR ("+EndDTField+"<"+DTField+")) "
        SQLStr += "AND "+DTField+"<="+EndDate.strftime(self._DTFormat)+" "
        SQLStr += self._genConditionSQLStr()+" "
        SQLStr += "ORDER BY ['QS_ID'], ['QS_起始日'] END"
        RawData = json.loads(self._FactorDB._exec("RETURN exportjsonstring("+SQLStr+");"))
        if not RawData: return pd.DataFrame(columns=["QS_ID", "QS_起始日", "QS_结束日"]+factor_names)
        RawData = pd.DataFrame(RawData).loc[:, ["QS_ID", "QS_起始日", "QS_结束日"]+factor_names]
        RawData["QS_ID"] = IDMapping.loc[RawData["QS_ID"].values].values
        RawData["QS_起始日"] = RawData["QS_起始日"].apply(lambda x: dt.datetime.strptime(str(int(x)), self._DTFormat) if pd.notnull(x) and (x!=0) else None)
        RawData["QS_结束日"] = RawData["QS_结束日"].apply(lambda x: dt.datetime.strptime(str(int(x)), self._DTFormat) if pd.notnull(x) and (x!=0) else None)
        return RawData


class TinySoftDB(FactorDB):
    """TinySoft"""
    class __QS_ArgClass__(FactorDB.__QS_ArgClass__):
        Name: str = Field(default="TinySoftDB", title="名称", frozen=True)
        IPAddr: str = Field(default="tsl.tinysoft.com.cn", title="IP地址", frozen=True)
        Port: int = Field(default=443, ge=0, le=65535, title="端口", frozen=True)
        User: str = Field(default="", title="用户名", frozen=True)
        Pwd: str = Field(default="", title="密码", frozen=True, repr=False)
        DBInfoFile: str = Field(default="", title="库信息文件", frozen=True)
        FTArgs: dict = Field(default={}, title="因子表参数", frozen=True)

    def __init__(self, args={}, config_file=None, **kwargs):
        super().__init__(args=args, config_file=(__QS_ConfigPath__+os.sep+"TinySoftDBConfig.json" if config_file is None else config_file), **kwargs)
        self._Client = None
        self._TableInfo = None
        self._FactorInfo = None
        self._InfoFilePath = __QS_MainPath__+os.sep+"Resource"+os.sep+"TinySoftDBInfo.hdf5"
        if not os.path.isfile(self._QSArgs.DBInfoFile):
            if self._QSArgs.DBInfoFile: self._QS_Logger.warning("找不到指定的库信息文件 : '%s'" % self._QSArgs.DBInfoFile)
            self._InfoResourcePath = __QS_MainPath__+os.sep+"Resource"+os.sep+"TinySoftDBInfo.xlsx"
            self._TableInfo, self._FactorInfo = updateInfo(self._InfoFilePath, self._InfoResourcePath, self._QS_Logger)
        else:
            self._InfoResourcePath = self._QSArgs.DBInfoFile
            self._TableInfo, self._FactorInfo = importInfo(self._InfoFilePath, self._InfoResourcePath)
        return

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_Client"] = (True if self.isAvailable() else False)
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        if self._Client: self.connect()
        else: self._Client = None

    def connect(self):
        self._Client = pyTSL.Client(self._QSArgs.User, self._QSArgs.Pwd, self._QSArgs.IPAddr, self._QSArgs.Port)
        self._Client.login()
        return self

    def disconnect(self):
        if self._Client is not None:
            try:
                self._Client.logout()
            except Exception as e:
                self._QS_Logger.warning("'%s' 断开连接错误: %s" % (self.Name, str(e)))
            finally:
                self._Client = None
        return 0

    def isAvailable(self):
        if self._Client is not None:
            try:
                r = self._Client.exec('return "ping";')
                return r.value() == "ping"
            except:
                return False
        else:
            return False

    def _exec(self, tsl_str, **kwargs):
        """执行 TSL 代码并返回结果值"""
        r = self._Client.exec(tsl_str, **kwargs)
        if r.error()!=0:
            raise __QS_Error__("TinySoft 执行错误: "+r.message())
        return r.value()

    def _call(self, func_name, *args, code="", **kwargs):
        """调用 TSL 函数并返回结果值"""
        r = self._Client.call(func_name, *args, code=code, **kwargs)
        if r.error()!=0:
            raise __QS_Error__("TinySoft 调用错误: "+r.message())
        return r.value()

    @property
    def TableNames(self):
        if self._TableInfo is not None: return self._TableInfo[pd.notnull(self._TableInfo["TableClass"])].index.tolist()
        else: return []

    @staticmethod
    def _filterArgs(table_cls, args):
        """过滤掉因子表 __QS_ArgClass__ 不接受的参数键"""
        for cls in table_cls.__mro__:
            ArgClass = getattr(cls, "__QS_ArgClass__", None)
            if ArgClass is not None and hasattr(ArgClass, "model_fields"):
                ValidKeys = set(ArgClass.model_fields)
                return {k: v for k, v in args.items() if k in ValidKeys}
        return args

    def getTable(self, table_name, args={}):
        if table_name in self._TableInfo.index:
            TableClass = args.get("TableType", self._TableInfo.loc[table_name, "TableClass"])
            DefaultArgs = self._TableInfo.loc[table_name, "DefaultArgs"]
            if pd.isnull(DefaultArgs): DefaultArgs = {}
            else: DefaultArgs = eval(DefaultArgs)
            if pd.notnull(TableClass) and (TableClass!=""):
                Args = self._QSArgs.FTArgs.copy()
                Args.update(DefaultArgs)
                Args.update(args)
                Args["Name"] = table_name
                TableCls = eval("_"+TableClass)
                Args = self._filterArgs(TableCls, Args)
                if TableClass in ("WideTable", "FeatureTable", "MappingTable"):
                    return TableCls(fdb=self, args=Args, table_info=self._TableInfo.loc[table_name], factor_info=self._FactorInfo.loc[table_name], logger=self._QS_Logger)
                else:
                    return TableCls(fdb=self, args=Args, logger=self._QS_Logger)
        Msg = ("因子库 '%s' 目前尚不支持因子表: '%s'" % (self.Name, table_name))
        self._QS_Logger.error(Msg)
        raise __QS_Error__(Msg)

    def getTradeDay(self, start_date:Optional[dt.datetime]=None, end_date:Optional[dt.datetime]=None, exchange:Literal["SSE", "SZSE"]="SSE", **kwargs) -> List[dt.datetime]:
        """给定交易所、起始日和结束日, 获取交易日序列

        Args:
            start_date: 起始日, None 表示从 1900-01-01 开始
            end_date: 结束日, None 表示当前日期
            exchange: 交易所, 默认 SSE(上交所)

        Returns:
            交易日序列
        """
        if exchange not in ("SSE", "SZSE"): raise __QS_Error__("不支持交易所: '%s' 的交易日序列!" % exchange)
        if start_date is None: start_date = dt.datetime(1900, 1, 1)
        if end_date is None: end_date = dt.datetime.combine(dt.date.today(), dt.time(0))
        CodeStr = "SetSysParam(pn_cycle(), cy_day());return MarketTradeDayQk(inttodate({StartDate}), inttodate({EndDate}));"
        CodeStr = CodeStr.format(StartDate=start_date.strftime("%Y%m%d"), EndDate=end_date.strftime("%Y%m%d"))
        Data = self._exec(CodeStr)
        return [pyTSL.DoubleToDatetime(x) for x in Data]

    def _getAllAStock(self, date=None, is_current=True):
        if date is None: Date = dt.date.today()
        if is_current:
            CodeStr = f"""return getAbkbydate('A股',{Date.strftime("%Y%m%d")}T);"""
        elif date is None:
            CodeStr = "return getBK('A股;暂停上市;终止上市');"
        else:
            raise __QS_Error__("目前不支持提取指定日期的历史 A 股 ID")
        Data = self._exec(CodeStr)
        return sorted(iID[2:]+"."+iID[:2] for iID in Data)

    def getStockID(self, type:Literal["全体A股"]="全体A股", date:Optional[dt.datetime]=None, is_current:bool=True) -> List[str]:
        """给定股票类型和日期, 获取股票证券 ID 序列

        Args:
            type: 股票类型, 默认 全体A股
            date: 指定日, 默认值 None 表示当前日期
            is_current: False 表示上市日期在指定日之前的股票, True 表示上市日期在指定日之前且尚未退市的股票
        
        Returns:
            股票证券 ID 序列
        """
        if type=="全体A股": return self._getAllAStock(date=date, is_current=is_current)
        raise __QS_Error__(f"目前不支持提取 type={type} 的股票列表")

    def getMutualFundID(self, date:Optional[dt.datetime]=None, board:str="开放式基金;封闭式基金", **kwargs) -> List[str]:
        """获取公募基金 ID 序列

        通过 TinySoft 的 BK_ListedOfFunds 函数获取指定日已上市的公募基金列表,
        判断基金是否上市的依据为指定日是否已开始公布净值。

        Args:
            date: 指定日, 默认值 None 表示当前日期
            board: 基金板块名称, 默认 "开放式基金;封闭式基金" 覆盖全体公募基金

        Returns:
            公募基金 ID 序列, 格式如 ["000001.OF", "000011.OF", ...]
        """
        if date is None: date = dt.date.today()
        CodeStr = f'SetSysParam(Pn_Bk(),"{board}");'
        CodeStr += f'return BK_ListedOfFunds({date.strftime("%Y%m%d")}T,-1);'
        Data = self._exec(CodeStr)
        if not Data: return []
        return sorted(iID[2:]+"."+iID[:2] for iID in Data)

    def getMutualFundInfo(self, date:Optional[dt.datetime]=None, **kwargs) -> pd.DataFrame:
        """获取公募基金的基本信息

        通过 TinySoft 的批量函数获取基金列表和基金经理信息,
        再通过 INFOTABLE 302 批量查询基金名称、风格、上市日、设立日、基金管理人等属性。

        字段映射 (INFOTABLE 302):
            基金名称(302000), 投资类型(302013), 设立日(302003),
            上市日(302004), 基金管理人(302009), 标的指数代码

        Args:
            date: 指定日, 默认值 None 表示当前日期

        Returns:
            DataFrame(columns=["ID", "Name", "Type", "EstablishmentDate",
                "ListedDate", "Org", "Manager", "MainCode", "TrackIndexID"])
        """
        if date is None: date = dt.datetime.combine(dt.date.today(), dt.time())
        DateInt = int(date.strftime("%Y%m%d"))
        DateT = f"{DateInt}T"
        # 1) 获取公募基金列表 (ID 格式: "000001.OF")
        fund_ids = self.getMutualFundID(date=date)
        if not fund_ids:
            return pd.DataFrame(columns=["ID", "Name", "Type", "EstablishmentDate", "ListedDate", "Org", "Manager", "MainCode", "TrackIndexID"])
        # 转为 TinySoft 内部格式 ("OF000001") 用于 INFOTABLE 查询
        funds = ["".join(reversed(iID.split("."))) for iID in fund_ids]
        funds_str = "','".join(funds)
        # 2) 批量获取基金经理信息
        try:
            mgr_data = self._exec(f"return FundManagerDataByEndt(array('{funds_str}'), {DateT});")
        except Exception:
            mgr_data = None
        mgr_map = {}
        if mgr_data:
            for row in mgr_data:
                if isinstance(row, dict):
                    fid = row.get("StockID", "")
                    name = row.get("姓名", "")
                else:
                    fid, name = (row[0], row[1]) if len(row) >= 2 else ("", "")
                if fid and name and fid not in mgr_map:
                    mgr_map[fid] = name
        # 3) 通过 INFOTABLE 302 批量查询基金基本信息
        try:
            tsl = (
                "return exportjsonstring("
                "select ['StockID'],['基金名称'],['投资类型'],['设立日'],['上市日'],['基金管理人'],['标的指数代码'] "
                f"from infotable 302 of array('{funds_str}') end);"
            )
            info_data = json.loads(self._exec(tsl))
        except Exception:
            info_data = []
        info_map = {row["StockID"]: row for row in info_data}
        results = []
        for fund_id, fund in zip(fund_ids, funds):
            row = info_map.get(fund, {})
            issue_dt = row.get("设立日")
            listed_dt = row.get("上市日")
            results.append({
                "ID": fund_id,
                "Name": row.get("基金名称") or None,
                "Type": row.get("投资类型") or None,
                "EstablishmentDate": dt.datetime.strptime(str(int(issue_dt)), "%Y%m%d") if issue_dt else None,
                "ListedDate": dt.datetime.strptime(str(int(listed_dt)), "%Y%m%d") if listed_dt else None,
                "Org": row.get("基金管理人") or None,
                "Manager": mgr_map.get(fund),
                "MainCode": fund_id,
                "TrackIndexID": row.get("标的指数代码") or None,
            })
        MFInfo = pd.DataFrame(results, columns=["ID", "Name", "Type", "EstablishmentDate", "ListedDate", "Org", "Manager", "MainCode", "TrackIndexID"])
        return MFInfo

    def getIndexComponentID(self, index_id:str, date:Optional[dt.datetime]=None, is_current:bool=True) -> List[str]:
        if date is None: Date = dt.date.today()
        IndexID = "".join(reversed(index_id.split(".")))
        if is_current:
            CodeStr = f"return GetBKByDate('{IndexID}', {Date.strftime('%Y%m%d')}T);"
        else:
            raise __QS_Error__("目前不支持提取历史指数成分股 ID")
        Data = self._exec(CodeStr)
        return sorted(iID[2:]+"."+iID[:2] for iID in Data)

    def getFutureID(self, future_code:Optional[str]="IF", date=None, is_current=True):
        if date is None: Date = dt.date.today()
        if future_code is not None: future_code = "".join(reversed(future_code.split(".")))
        if future_code is None:
            if is_current: CodeStr = f"return GetFuturesID ('', {Date.strftime('%Y%m%d')}T);"
            else: CodeStr = f"EndT:= {Date.strftime('%Y%m%d')}T;Return getbk('上市期货;退市期货');"
        else:
            if is_current:
                CodeStr = f"""EndT:= {Date.strftime('%Y%m%d')}T;return GetFuturesID('{future_code}',EndT);"""
            elif date is None:
                CodeStr = f"""pz:='{future_code}'; return getbkall(spec(base(708003),pz));"""
            else:
                raise __QS_Error__("目前不支持提取指定日期的历史期货 ID")
        Data = self._exec(CodeStr)
        return Data
    
    def _OptionID2InnerCode(self, option_ids:List[str]) -> Dict[str, str]:
        CodeStr = "Return select ['StockID'], ['合约交易代码'] from infotable 720 where ['合约交易代码'] in ARRAY('"+"','".join(option_ids)+"') end;"
        Data = pd.DataFrame(self._exec(CodeStr))
        Data = Data.groupby(["合约交易代码"]).first()
        return Data["StockID"].to_dict()

    def _OptionInnerCode2ID(self, option_inner_codes:List[str]) -> List[str]:
        CodeStr = "Return select ['StockID'], ['合约交易代码'] from infotable 720 of ARRAY('"+"','".join(option_inner_codes)+"') end;"
        Data = pd.DataFrame(self._exec(CodeStr))
        Data = Data.groupby(["StockID"]).first()
        return Data["合约交易代码"].to_dict()

    def getOptionID(self, option_code:Optional[str]="510050.SH", date:Optional[dt.datetime]=None, is_current:bool=True) -> List[str]:
        if date is None: Date = dt.date.today()
        if option_code is not None: option_code = "".join(reversed(option_code.split(".")))
        if option_code is None:
            if is_current:
                CodeStr = "pzs:=OP_GetUnderlyingSecurity();return OP_GetOptionList(array2str(pzs),{Date}T);"
                Data = self._exec(CodeStr.format(Date=Date.strftime("%Y%m%d")))
                return sorted(iID.replace("-", "").upper() for iID in Data)
            else: CodeStr = "EndT:= {Date}T;Return getbk('上市期权;退市期权');"
            CodeStr = CodeStr.format(Date=Date.strftime("%Y%m%d"))
        else:
            if is_current:
                CodeStr = """return OP_GetOptionList("{OptionCode}",{Date}T);"""
                CodeStr = CodeStr.format(OptionCode=option_code, Date=Date.strftime("%Y%m%d"))
            elif date is None:
                CodeStr = """pz:='{OptionCode}';name:=spec(base(720003),"OP"+pz);return getbkall(name);"""
                CodeStr = CodeStr.format(OptionCode=option_code)
            else:
                raise __QS_Error__("目前不支持提取指定日期的历史期权 ID")
        Data = self._exec(CodeStr)
        return Data
