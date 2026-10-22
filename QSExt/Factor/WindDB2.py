# -*- coding: utf-8 -*-
"""Wind 量化研究数据库，适配当前 QuantStudio 因子表和计算图接口。"""
import ast
import os
import datetime as dt
from typing import Any, Callable, Literal, Optional

import numpy as np
import pandas as pd
from pydantic import Field, FilePath

from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.QSObject import Panel, QSSQLObject
from QuantStudio.Factor.FactorDB import FactorDB
from QuantStudio.Factor.FactorUtils import (
    SQL_Table, SQL_WideTable, SQL_FeatureTable, SQL_MappingTable,
    SQL_NarrowTable, SQL_TimeSeriesTable, SQL_ConstituentTable, SQL_FinancialTable,
)
from QuantStudio.Tools.SQLDBFun import genSQLInCondition
from QSExt import __QS_MainPath__, __QS_ConfigPath__


def _normalizeArgs(args, arg_class):
    """将旧元数据中的中文参数名转换为当前参数名，英文键优先。"""
    fields = arg_class.model_fields
    titles = {field.title: name for name, field in fields.items() if field.title}
    values = {titles.get(key, key): value for key, value in args.items()}
    values.update({key: value for key, value in args.items() if key in fields})
    return values


def _importInfo(info_resource):
    """读取并整理 Wind 的两张元数据工作表。"""
    TableInfo = pd.read_excel(info_resource, "TableInfo", engine="openpyxl").set_index("TableName")
    FactorInfo = pd.read_excel(info_resource, "FactorInfo", engine="openpyxl")
    FactorInfo["TableName"] = FactorInfo["TableName"].replace({"中国LOF基本资料": "中国LOF基金基本资料"})
    FactorInfo["FieldType"] = FactorInfo["FieldType"].fillna("因子")
    FactorInfo = FactorInfo.set_index(["TableName", "FieldName"])
    TableInfo = TableInfo.loc[~TableInfo.index.duplicated(keep="first")]
    FactorInfo = FactorInfo.loc[~FactorInfo.index.duplicated(keep="first")].copy()
    for name, info in TableInfo.iterrows():
        if name not in FactorInfo.index.get_level_values(0): continue
        if info["TableClass"] == "FinancialTable":
            fields = FactorInfo.loc[name, "FieldType"]
            for field in fields[fields == "ReportDate"].index:
                FactorInfo.loc[(name, field), "Supplementary"] = "Default"
            mapping = {"ANNDate": "AnnDate", "ReportDate": "Date", "ReportType": "AdjustType"}
            FactorInfo.loc[name, "FieldType"] = FactorInfo.loc[name, "FieldType"].replace(mapping).to_numpy()
        elif info["TableClass"] == "ConstituentTable":
            fields = FactorInfo.loc[name, "FieldType"]
            for field in fields[fields == "OutDate"].index:
                FactorInfo.loc[(name, field), "Supplementary"] = "不包含"
            FactorInfo.loc[name, "FieldType"] = fields.replace({"InDate": "Date", "OutDate": "EndDate"}).to_numpy()
    return TableInfo, FactorInfo


class _WindSQLTable:
    """为通用 SQL 表注入 Wind 元数据和表名前缀。"""

    def __init__(self, fdb, args={}, **kwargs):
        args = _normalizeArgs(args, self.__QS_ArgClass__)
        args = {"TablePrefix": fdb.Args.TablePrefix, **args}
        name = args["Name"]
        super().__init__(fdb=fdb, args=args, table_info=fdb._TableInfo.loc[name],
                         factor_info=fdb._FactorInfo.loc[name], security_info=None,
                         exchange_info=None, **kwargs)


class _WideTable(_WindSQLTable, SQL_WideTable):
    """Wind 宽因子表。"""


class _NarrowTable(_WindSQLTable, SQL_NarrowTable):
    """Wind 窄因子表。"""


class _FeatureTable(_WindSQLTable, SQL_FeatureTable):
    """Wind 特征因子表。"""


class _TimeSeriesTable(_WindSQLTable, SQL_TimeSeriesTable):
    """Wind 时序因子表。"""


class _MappingTable(_WindSQLTable, SQL_MappingTable):
    """Wind 映射因子表。"""


class _ConstituentTable(_WindSQLTable, SQL_ConstituentTable):
    """Wind 成份因子表。"""


class _FinancialTable(_WindSQLTable, SQL_FinancialTable):
    """保留 Wind 公告日期和业绩快报口径的财务因子表。"""

    class __QS_ArgClass__(SQL_FinancialTable.__QS_ArgClass__):
        ReportType: list[str] = Field(default_factory=lambda: ["408001000", "408004000", "408005000"], title="报表类型", frozen=True)
        ExprFactor: str = Field(default="", title="业绩快报因子", frozen=True)
        NoticeFactor: str = Field(default="", title="业绩预告因子", frozen=True)

    def __init__(self, fdb, args={}, **kwargs):
        super().__init__(fdb=fdb, args=args, **kwargs)
        self._ANNDateField = self.Args.PublDTField
        self._ReportDateField = self.Args.DTField
        self._ReportTypeField = self.Args.AdjustTypeField
        self._QS_RawDataMaskCols = ["QS_ID", "AnnDate", "ReportDate", "AdjustType"]

    def _genConditionSQLStr(self, use_main_table=True, init_keyword="AND"):
        # 报表类型由 Wind 查询处理，季度筛选交给通用计算逻辑。
        return SQL_Table._genConditionSQLStr(self, use_main_table=use_main_table, init_keyword=init_keyword)

    def getID(self, ifactor_name=None, idt=None):
        field = self._DBTableName + "." + self._FactorInfo.loc[self._ANNDateField, "DBFieldName"]
        sql = f"SELECT DISTINCT {self._getIDField()} {self._genFromSQLStr()} "
        sql += self._genIDSQLStr(None, init_keyword="WHERE") + " "
        if idt is not None: sql += f"AND {field}<={idt.strftime(self._DTFormat)} "
        sql += self._genConditionSQLStr() + f" ORDER BY {self._getIDField()}"
        return [row[0] for row in self.FactorDB.fetchall(sql)]

    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None):
        field = self._DBTableName + "." + self._FactorInfo.loc[self._ANNDateField, "DBFieldName"]
        sql = f"SELECT DISTINCT {field} {self._genFromSQLStr()} "
        sql += self._genIDSQLStr(None if iid is None else [iid], init_keyword="WHERE") + " "
        sql += f"AND {field} IS NOT NULL "
        if start_dt is not None: sql += f"AND {field}>={start_dt.strftime(self._DTFormat)} "
        if end_dt is not None: sql += f"AND {field}<={end_dt.strftime(self._DTFormat)} "
        sql += self._genConditionSQLStr() + f" ORDER BY {field}"
        values = pd.Series([row[0] for row in self.FactorDB.fetchall(sql)], dtype="O")
        return self.__QS_adjustDT__(values).tolist()

    def _readSupplement(self, table_name, factor_name, ids, factor_names, report_type, scale=1):
        """将快报或预告值转换为财务原始数据，预告的万元单位转换为元。"""
        info = self.FactorDB._FactorInfo.loc[table_name, "DBFieldName"]
        table = self.Args.TablePrefix + self.FactorDB._TableInfo.loc[table_name, "DBTableName"]
        id_field, ann_field, report_field, value_field = [table + "." + info[name] for name in ("Wind代码", "公告日期", "报告期", factor_name)]
        condition = id_field + " IS NOT NULL" if ids is None else genSQLInCondition(id_field, ids, is_str=True, max_num=1000)
        sql = f"SELECT {id_field}, {ann_field}, {report_field}, {value_field}*{scale} FROM {table} WHERE ({condition}) AND {ann_field} IS NOT NULL"
        data = pd.DataFrame(self.FactorDB.fetchall(sql), columns=["QS_ID", "AnnDate", "ReportDate", "QS_Value"])
        data["AdjustType"] = report_type
        for name in factor_names: data[name] = data["QS_Value"]
        return data.drop(columns="QS_Value")

    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        columns = ["QS_ID", "AnnDate", "ReportDate", "AdjustType"] + factor_names
        if ids == [] or not dts: return pd.DataFrame(columns=columns)
        fields = self._FactorInfo["DBFieldName"]
        table = self._DBTableName
        id_field, ann_field, report_field = [table + "." + fields[name] for name in (self._IDField, self._ANNDateField, self._ReportDateField)]
        join = ""
        type_field = self._ReportTypeField
        if type_field is not None:
            type_field = table + "." + fields[type_field]
            ann_table = self.Args.TablePrefix + "AShareIssuingDatePredict"
            ann_field = f"CASE WHEN {type_field}='408004000' OR {ann_table}.s_stm_actual_issuingdate IS NULL THEN {ann_field} ELSE {ann_table}.s_stm_actual_issuingdate END"
            join = f" LEFT JOIN {ann_table} ON ({id_field}={ann_table}.s_info_windcode AND {report_field}={ann_table}.report_period)"
        selections = [f"{id_field} AS QS_ID", f"{ann_field} AS AnnDate", f"{report_field} AS ReportDate", f"{type_field or 'NULL'} AS AdjustType"]
        selections += [f"{table}.{fields[name]} AS QS_Factor_{i}" for i, name in enumerate(factor_names)]
        sql = f"SELECT {', '.join(selections)} FROM {table}{join} "
        sql += self._genIDSQLStr(ids, init_keyword="WHERE") + " "
        sql += self._genConditionSQLStr() + " "
        if type_field:
            report_types = args.get("ReportType", self.Args.ReportType)
            sql += "AND (" + genSQLInCondition(type_field, report_types, is_str=True, max_num=1000) + ") "
        sql = f"SELECT t.* FROM ({sql}) t WHERE t.AnnDate IS NOT NULL AND t.AnnDate<={dts[-1].strftime(self._DTFormat)} ORDER BY t.QS_ID, t.AnnDate, t.ReportDate, t.AdjustType"
        data = pd.DataFrame(self.FactorDB.fetchall(sql), columns=columns)
        for arg, table_name, report_type, scale in (("ExprFactor", "中国A股业绩快报", "1ProfitExpress", 1), ("NoticeFactor", "中国A股业绩预告", "0ProfitNotice", 10000)):
            factor = args.get(arg, getattr(self.Args, arg))
            if factor:
                supplement = self._readSupplement(table_name, factor, ids, factor_names, report_type, scale)
                data = pd.concat([data, supplement], ignore_index=True)
        for field in ("AnnDate", "ReportDate"):
            data[field] = self.__QS_adjustDT__(data[field])
        # 排序使用字符串，确保空报表类型和业绩预告、快报也有稳定顺序。
        data["AdjustType"] = data["AdjustType"].fillna("").astype(str)
        data = data[data["AnnDate"] <= dts[-1]].sort_values(["QS_ID", "AnnDate", "ReportDate", "AdjustType"])
        data = self._adjustRawDataByRelatedField(data, factor_names)
        for name in factor_names:
            if self.__QS_identifyDataType__(self._FactorInfo.loc[name, "DataType"]) == "double":
                data[name] = data[name].astype(float)
        return data

    def __QS_calcData__(self, raw_data, factor_names, ids, dts, args={}):
        if args.get("YearLookBack", self.Args.YearLookBack) > 0:
            args = {**args, "PeriodLookBack": 0}
        return super().__QS_calcData__(raw_data.copy(), factor_names, ids, dts, args=args)


def _alignAnalystData(data, factor_names, ids, dts):
    """按交易日计算后恢复调用者给定的时点和 ID 顺序。"""
    dates = [dt.datetime.combine(value.date(), dt.time()) for value in dts]
    result = {}
    for name in factor_names:
        values = data.loc[name].reindex(index=dates, columns=ids)
        values.index = pd.DatetimeIndex(dts)
        result[name] = values
    return Panel(result, items=factor_names, major_axis=dts, minor_axis=ids)


class _AnalystTable(_WindSQLTable, SQL_Table):
    """分析师表的字段识别、时点查询和原始数据缓存。"""

    def __init__(self, fdb, args={}, **kwargs):
        super().__init__(fdb=fdb, args=args, **kwargs)
        fields = self._FactorInfo["FieldType"]
        for field_type, attribute in (("Date", "_DateField"), ("ReportDate", "_ReportDateField"),
                                      ("Period", "_PeriodField"), ("Institute", "_InstituteField"),
                                      ("Analyst", "_AnalystField"), ("Capital", "_CapitalField")):
            matches = fields[fields == field_type].index
            if len(matches): setattr(self, attribute, matches[0])
        self._QS_RawDataMaskCols = ["QS_ID", "日期"]
        if hasattr(self, "_ReportDateField"):
            self._QS_RawDataMaskCols.append("报告期" if hasattr(self, "_PeriodField") else self._ReportDateField)
        for attribute in ("_InstituteField", "_AnalystField"):
            if hasattr(self, attribute): self._QS_RawDataMaskCols.append(getattr(self, attribute))
        self._QS_LookbackArgs = ("LookBack",) if hasattr(self.Args, "LookBack") else ("Period",)
        self._QS_PrepareIgnoredArgs = ("Operator", "ModelArgs", "DataType", "ForwardYears")

    def getID(self, ifactor_name=None, idt=None):
        field = self._DBTableName + "." + self._FactorInfo.loc[self._DateField, "DBFieldName"]
        sql = f"SELECT DISTINCT {self._getIDField()} {self._genFromSQLStr()} "
        sql += self._genIDSQLStr(None, init_keyword="WHERE") + " "
        if idt is not None: sql += f"AND {field}={idt.strftime(self._DTFormat)} "
        sql += self._genConditionSQLStr() + f" ORDER BY {self._getIDField()}"
        return [row[0] for row in self.FactorDB.fetchall(sql)]

    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None):
        field = self._DBTableName + "." + self._FactorInfo.loc[self._DateField, "DBFieldName"]
        sql = f"SELECT DISTINCT {field} {self._genFromSQLStr()} "
        sql += self._genIDSQLStr(None if iid is None else [iid], init_keyword="WHERE") + " "
        sql += f"AND {field} IS NOT NULL "
        if start_dt is not None: sql += f"AND {field}>={start_dt.strftime(self._DTFormat)} "
        if end_dt is not None: sql += f"AND {field}<={end_dt.strftime(self._DTFormat)} "
        sql += self._genConditionSQLStr() + f" ORDER BY {field}"
        values = pd.Series([row[0] for row in self.FactorDB.fetchall(sql)], dtype="O")
        return self.__QS_adjustDT__(values).tolist()

    def getFactorMetaData(self, factor_names=None, key=None):
        data = super().getFactorMetaData(factor_names=factor_names, key=key)
        if hasattr(self.Args, "DataType"):
            if key == "DataType": data[:] = self.Args.DataType
            elif key is None: data["DataType"] = self.Args.DataType
        return data

    def __QS_saveRawData__(self, raw_data, key, target_fields, pid_ids, context, **kwargs):
        if not isinstance(raw_data, dict):
            return super().__QS_saveRawData__(raw_data, key, target_fields, pid_ids, context, **kwargs)
        super().__QS_saveRawData__(raw_data["RawData"], key, target_fields, pid_ids, context, **kwargs)
        for name in target_fields:
            context.DataCache.writeRawData(key + "-" + name, {"ReportANN": raw_data["ReportANN"]},
                                           pid_ids, id_col="QS_ID", if_exists="replace")


def RollBackNPeriod(report_date, n_period):
    Date = report_date
    for i in range(1, n_period+1):
        if Date[-4:]=='1231':
            Date = Date[0:4]+'0930'
        elif Date[-4:]=='0930':
            Date = Date[0:4]+'0630'
        elif Date[-4:]=='0630':
            Date = Date[0:4]+'0331'
        elif Date[-4:]=='0331':
            Date = str(int(Date[0:4])-1)+'1231'
    return Date

def findNoteDate(report_date, report_note_dates):
    for i in range(0, report_note_dates.shape[0]):
        if report_date==report_note_dates['报告期'].iloc[i]: return report_note_dates['公告日期'].iloc[i]
    return None

def genANN_ReportSQLStr(table_prefix, ids, report_period="1231"):
    DBTableName = table_prefix+"AShareIssuingDatePredict"
    # 提取财报的公告期数据, ID, 公告日期, 报告期
    SQLStr = "SELECT "+DBTableName+".s_info_windcode, "
    SQLStr += DBTableName+".s_stm_actual_issuingdate, "
    SQLStr += DBTableName+".report_period "
    SQLStr += "FROM "+DBTableName+" "
    SQLStr += "WHERE ("+(DBTableName+".s_info_windcode IS NOT NULL" if ids is None else genSQLInCondition(DBTableName+".s_info_windcode", ids, is_str=True, max_num=1000))+") "
    if report_period is not None:
        SQLStr += "AND "+DBTableName+".report_period LIKE '%"+report_period+"' "
    SQLStr += "ORDER BY "+DBTableName+".s_info_windcode, "
    SQLStr += DBTableName+".s_stm_actual_issuingdate, "+DBTableName+".report_period"
    return SQLStr

def _prepareReportANNRawData(fdb, ids):
    if ids == []: return pd.DataFrame(columns=["QS_ID", "公告日期", "报告期"])
    SQLStr = genANN_ReportSQLStr(fdb.Args.TablePrefix, ids, report_period="1231")
    RawData = fdb.fetchall(SQLStr)
    if not RawData: return pd.DataFrame(columns=["QS_ID", "公告日期", "报告期"])
    else: return pd.DataFrame(np.array(RawData, dtype="O"), columns=["QS_ID", "公告日期", "报告期"])

def _DefaultOperator(f, idt, iid, x, args):
    return np.nan

class _AnalystConsensusTable(_AnalystTable):
    """分析师汇总表。"""

    class __QS_ArgClass__(_AnalystTable.__QS_ArgClass__):
        TableType: Literal["AnalystConsensusTable"] = Field(default="AnalystConsensusTable", title="因子表类型", frozen=True)
        CalcType: Literal["FY0", "FY1", "FY2", "Fwd12M"] = Field(default="FY0", title="计算方法", frozen=True)
        Period: Literal["263001000", "263002000", "263003000", "263004000"] = Field(default="263001000", title="周期", frozen=True)
        LookBack: int = Field(default=180, title="回溯天数", ge=0, frozen=True)

    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        if not dts or ids == []: return {"RawData": pd.DataFrame(columns=["日期", "QS_ID", "报告期"]+factor_names), "ReportANN": pd.DataFrame(columns=["QS_ID", "公告日期", "报告期"])}
        CalcType = args.get("CalcType", self._QSArgs.CalcType)
        StartDate, EndDate = dts[0].date(), dts[-1].date()
        StartDate -= dt.timedelta(args.get("LookBack", self._QSArgs.LookBack))
        FieldDict = self._FactorInfo["DBFieldName"]
        DBTableName = self._QSArgs.TablePrefix + self._FactorDB._TableInfo.loc[self._QSArgs.Name, "DBTableName"]
        # 形成SQL语句, 日期, ID, 报告期, 数据
        SQLStr = 'SELECT '+DBTableName+"."+FieldDict[self._DateField]+", "
        SQLStr += DBTableName+"."+FieldDict[self._IDField]+", "
        SQLStr += DBTableName+"."+FieldDict[self._ReportDateField]+", "
        for iField in factor_names: SQLStr += DBTableName+"."+FieldDict[iField]+", "
        SQLStr = SQLStr[:-2]+" FROM "+DBTableName+" "
        SQLStr += self._genIDSQLStr(ids, init_keyword="WHERE") + " "
        SQLStr += self._genConditionSQLStr() + " "
        SQLStr += "AND "+DBTableName+"."+FieldDict[self._PeriodField]+"='"+args.get("Period", self._QSArgs.Period)+"' "
        SQLStr += "AND "+DBTableName+"."+FieldDict[self._DateField]+">='"+StartDate.strftime("%Y%m%d")+"' "
        SQLStr += "AND "+DBTableName+"."+FieldDict[self._DateField]+"<='"+EndDate.strftime("%Y%m%d")+"' "
        SQLStr += 'ORDER BY '+DBTableName+"."+FieldDict[self._IDField]+", "+DBTableName+"."+FieldDict[self._DateField]+", "+DBTableName+"."+FieldDict[self._ReportDateField]
        RawData = self._FactorDB.fetchall(SQLStr)
        if not RawData: RawData = pd.DataFrame(columns=['日期',"QS_ID",'报告期']+factor_names)
        else: RawData = pd.DataFrame(np.array(RawData, dtype="O"), columns=['日期',"QS_ID",'报告期']+factor_names)
        ReportANN = _prepareReportANNRawData(self.FactorDB, ids) if CalcType != "Fwd12M" else pd.DataFrame(columns=["QS_ID", "公告日期", "报告期"])
        return {"RawData": RawData, "ReportANN": ReportANN}

    def __QS_calcData__(self, raw_data, factor_names, ids, dts, args={}):
        ANNReportData = raw_data["ReportANN"]
        raw_data = raw_data["RawData"]
        if raw_data.shape[0]==0: return Panel(np.nan, items=factor_names, major_axis=dts, minor_axis=ids)
        Dates = sorted({iDT.strftime("%Y%m%d") for iDT in dts})
        CalcType, LookBack = args.get("CalcType", self._QSArgs.CalcType), args.get("LookBack", self._QSArgs.LookBack)
        if CalcType=="Fwd12M":
            CalcFun, FYNum, ANNReportData = self._calcIDData_Fwd12M, None, None
        else:
            CalcFun, FYNum = self._calcIDData_FY, int(CalcType[-1])
            ANNReportData = ANNReportData.set_index(["QS_ID"])
        raw_data = raw_data.set_index(["QS_ID"])
        Data = {}
        for iID in raw_data.index.unique():
            if ANNReportData is not None:
                if iID in ANNReportData.index:
                    iANNReportData = ANNReportData.loc[[iID]]
                else:
                    iANNReportData = ANNReportData.iloc[:0]
            else:
                iANNReportData = None
            Data[iID] = CalcFun(Dates, raw_data.loc[[iID]], iANNReportData, factor_names, LookBack, FYNum)
        Data = Panel(Data, major_axis=Dates, minor_axis=factor_names)
        Data.major_axis = [dt.datetime.strptime(iDate, "%Y%m%d") for iDate in Dates]
        Data = Data.swapaxes(0, 2)
        return _alignAnalystData(Data, factor_names, ids, dts)

    def _calcIDData_FY(self, date_seq, raw_data, report_ann_data, factor_names, lookback, fy_num):
        StdData = np.full(shape=(len(date_seq), len(factor_names)), fill_value=np.nan)
        tempInd = -1
        tempLen = raw_data.shape[0]
        NoteDate = None
        for i, iDate in enumerate(date_seq):
            while (tempInd<tempLen-1) and (iDate>=raw_data['日期'].iloc[tempInd+1]): tempInd = tempInd+1
            if tempInd<0: continue
            LastYear = str(int(iDate[0:4])-1)
            NoteDate = findNoteDate(LastYear+'1231', report_ann_data)
            if (NoteDate is None) or (NoteDate>iDate):
                ObjectDate = str(int(LastYear)+fy_num)+'1231'
            else:
                ObjectDate = str(int(iDate[0:4])+fy_num)+'1231'
            iDate = dt.date(int(iDate[0:4]), int(iDate[4:6]), int(iDate[6:]))
            for j in range(0, tempInd+1):
                if raw_data['报告期'].iloc[tempInd-j]==ObjectDate:
                    FYNoteDate = raw_data['日期'].iloc[tempInd-j]
                    if (iDate - dt.date(int(FYNoteDate[0:4]), int(FYNoteDate[4:6]), int(FYNoteDate[6:]))).days<=lookback:
                        StdData[i] = raw_data[factor_names].iloc[tempInd-j].values
                        break
        return StdData

    def _calcIDData_Fwd12M(self, date_seq, raw_data, report_ann_data, factor_names, lookback, fy_num):
        StdData = np.full(shape=(len(date_seq), len(factor_names)), fill_value=np.nan)
        tempInd = -1
        tempLen = raw_data.shape[0]
        NoteDate = None
        for i, iDate in enumerate(date_seq):
            while (tempInd<tempLen-1) and (iDate>=raw_data['日期'].iloc[tempInd+1]): tempInd = tempInd+1
            if tempInd<0: continue
            ObjectDate1 = iDate[0:4]+'1231'
            ObjectDate2 = str(int(iDate[0:4])+1)+'1231'
            ObjectData1 = None
            ObjectData2 = None
            iDate = dt.date(int(iDate[0:4]), int(iDate[4:6]), int(iDate[6:]))
            for j in range(0, tempInd+1):
                if (ObjectData1 is None) and (raw_data['报告期'].iloc[tempInd-j]==ObjectDate1):
                    NoteDate = raw_data['日期'].iloc[tempInd-j]
                    if (iDate-dt.date(int(NoteDate[0:4]), int(NoteDate[4:6]), int(NoteDate[6:]))).days<=lookback:
                        ObjectData1 = raw_data[factor_names].iloc[tempInd-j].values
                if (ObjectData2 is None) and (raw_data['报告期'].iloc[tempInd-j]==ObjectDate2):
                    NoteDate = raw_data['日期'].iloc[tempInd-j]
                    if (iDate-dt.date(int(NoteDate[0:4]), int(NoteDate[4:6]), int(NoteDate[6:]))).days<=lookback:
                        ObjectData2 = raw_data[factor_names].iloc[tempInd-j].values
                if (ObjectData1 is not None) and (ObjectData2 is not None):
                    break
            if (ObjectData1 is not None) and (ObjectData2 is not None):
                Weight1 = (dt.date(int(ObjectDate1[0:4]), 12, 31) - iDate).days
                if (iDate.month==2) and (iDate.day==29): Weight1 = Weight1/366
                else:
                    Weight1 = Weight1/(dt.date(iDate.year+1, iDate.month, iDate.day)-iDate).days
                StdData[i] = Weight1*ObjectData1.astype("float") + (1-Weight1)*ObjectData2.astype("float")
        return StdData


class _AnalystRatingDetailTable(_AnalystTable):
    """分析师投资评级明细表。"""

    class __QS_ArgClass__(_AnalystTable.__QS_ArgClass__):
        TableType: Literal["AnalystRatingDetailTable"] = Field(default="AnalystRatingDetailTable", title="因子表类型", frozen=True)
        Operator: Callable = Field(default=_DefaultOperator, title="算子", frozen=True)
        ModelArgs: dict = Field(default_factory=dict, title="参数", frozen=True)
        AdditionalFields: list[str] = Field(default_factory=list, title="附加字段", frozen=True)
        Deduplication: list[str] = Field(default_factory=list, title="去重字段", frozen=True)
        Period: int = Field(default=180, title="周期", ge=0, frozen=True)
        DataType: Literal["double", "string", "object"] = Field(default="double", title="数据类型", frozen=True)

        def __init__(self, /, _owner=None, _logger=None, **data: Any):
            if "Deduplication" not in data:
                fields = _owner._FactorInfo
                data["Deduplication"] = fields[fields["FieldType"] == "Institute"].index.tolist()
            super().__init__(_owner=_owner, _logger=_logger, **data)

    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        if not dts or ids == []: return pd.DataFrame(columns=["日期", "QS_ID"]+list(dict.fromkeys(factor_names+self.Args.AdditionalFields+self.Args.Deduplication)))
        StartDate, EndDate = dts[0].date(), dts[-1].date()
        StartDate -= dt.timedelta(args.get("Period", self._QSArgs.Period))
        AdditiveFields = args.get("AdditionalFields", self._QSArgs.AdditionalFields)
        DeduplicationFields = args.get("Deduplication", self._QSArgs.Deduplication)
        AllFields = list(dict.fromkeys(factor_names+AdditiveFields+DeduplicationFields))
        FieldDict = self._FactorInfo["DBFieldName"]
        DBTableName = self._QSArgs.TablePrefix + self._FactorDB._TableInfo.loc[self._QSArgs.Name, "DBTableName"]
        # 形成SQL语句, 日期, ID, 其他字段
        SQLStr = "SELECT "+DBTableName+"."+FieldDict[self._DateField]+", "
        SQLStr += DBTableName+"."+FieldDict[self._IDField]+", "
        for iField in AllFields: SQLStr += DBTableName+"."+FieldDict[iField]+", "
        SQLStr = SQLStr[:-2]+" FROM "+DBTableName+" "
        SQLStr += self._genIDSQLStr(ids, init_keyword="WHERE") + " "
        SQLStr += self._genConditionSQLStr() + " "
        SQLStr += "AND "+DBTableName+"."+FieldDict[self._DateField]+">='"+StartDate.strftime("%Y%m%d")+"' "
        SQLStr += "AND "+DBTableName+"."+FieldDict[self._DateField]+"<='"+EndDate.strftime("%Y%m%d")+"' "
        SQLStr += 'ORDER BY '+DBTableName+"."+FieldDict[self._IDField]+", "+DBTableName+"."+FieldDict[self._DateField]
        RawData = self._FactorDB.fetchall(SQLStr)
        if not RawData: RawData = pd.DataFrame(columns=["日期", "QS_ID"]+AllFields)
        else: RawData = pd.DataFrame(np.array(RawData, dtype="O"), columns=["日期", "QS_ID"]+AllFields)
        return RawData

    def __QS_calcData__(self, raw_data, factor_names, ids, dts, args={}):
        if raw_data.shape[0]==0: return Panel(np.nan, items=factor_names, major_axis=dts, minor_axis=ids)
        Dates = sorted({dt.datetime.combine(iDT.date(), dt.time(0)) for iDT in dts})
        DeduplicationFields = args.get("Deduplication", self._QSArgs.Deduplication)
        AdditionalFields = list(dict.fromkeys(args.get("AdditionalFields", self._QSArgs.AdditionalFields)+DeduplicationFields))
        AllFields = list(dict.fromkeys(factor_names+AdditionalFields))
        raw_data = raw_data.loc[:, ["日期", "QS_ID"]+AllFields].set_index(["QS_ID"])
        Period = args.get("Period", self._QSArgs.Period)
        ModelArgs = args.get("ModelArgs", self._QSArgs.ModelArgs)
        Operator = args.get("Operator", self._QSArgs.Operator)
        DataType = args.get("DataType", self._QSArgs.DataType)
        AllIDs = set(raw_data.index)
        Data = {}
        for kFactorName in factor_names:
            if DataType=="double": kData = np.full(shape=(len(Dates), len(ids)), fill_value=np.nan)
            else: kData = np.full(shape=(len(Dates), len(ids)), fill_value=None, dtype="O")
            kFields = ["日期", kFactorName]+AdditionalFields
            for j, jID in enumerate(ids):
                if jID not in AllIDs: continue
                jRawData = raw_data.loc[[jID]][kFields]
                for i, iDate in enumerate(Dates):
                    iStartDate = (iDate - dt.timedelta(Period)).strftime("%Y%m%d")
                    ijRawData = jRawData[(jRawData["日期"]<=iDate.strftime("%Y%m%d")) & (jRawData["日期"]>iStartDate)]
                    if DeduplicationFields:
                        ijTemp = ijRawData.groupby(by=DeduplicationFields)[["日期"]].max()
                        ijTemp = ijTemp.reset_index()
                        ijRawData = pd.merge(ijTemp, ijRawData, how='left', left_on=DeduplicationFields+["日期"], right_on=DeduplicationFields+["日期"])
                    kData[i, j] = Operator(self, iDate, jID, ijRawData, ModelArgs)
            Data[kFactorName] = kData
        return _alignAnalystData(Panel(Data, items=factor_names, major_axis=Dates, minor_axis=ids), factor_names, ids, dts)


class _AnalystEstDetailTable(_AnalystRatingDetailTable):
    """分析师盈利预测明细表。"""

    class __QS_ArgClass__(_AnalystRatingDetailTable.__QS_ArgClass__):
        TableType: Literal["AnalystEstDetailTable"] = Field(default="AnalystEstDetailTable", title="因子表类型", frozen=True)
        ForwardYears: list[int] = Field(default_factory=lambda: [0], title="向前年数", frozen=True)

    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        if not dts or ids == []: return {"RawData": pd.DataFrame(columns=["日期", "QS_ID", self._ReportDateField, self._CapitalField]+list(dict.fromkeys(factor_names+self.Args.AdditionalFields+self.Args.Deduplication))), "ReportANN": pd.DataFrame(columns=["QS_ID", "公告日期", "报告期"])}
        StartDate, EndDate = dts[0].date(), dts[-1].date()
        StartDate -= dt.timedelta(args.get("Period", self._QSArgs.Period))
        AdditiveFields = args.get("AdditionalFields", self._QSArgs.AdditionalFields)
        DeduplicationFields = args.get("Deduplication", self._QSArgs.Deduplication)
        AllFields = list(dict.fromkeys(factor_names+AdditiveFields+DeduplicationFields))
        FieldDict = self._FactorInfo["DBFieldName"]
        DBTableName = self._QSArgs.TablePrefix + self._FactorDB._TableInfo.loc[self._QSArgs.Name, "DBTableName"]
        # 形成SQL语句, 日期, ID, 报告期, 研究机构名称, 分析师名称, 预测基准股本(万股), 因子数据
        SQLStr = "SELECT "+DBTableName+"."+FieldDict[self._DateField]+", "
        SQLStr += DBTableName+"."+FieldDict[self._IDField]+", "
        SQLStr += DBTableName+"."+FieldDict[self._ReportDateField]+", "
        SQLStr += DBTableName+"."+FieldDict[self._CapitalField]+", "
        for iField in AllFields: SQLStr += DBTableName+"."+FieldDict[iField]+", "
        SQLStr = SQLStr[:-2]+" FROM "+DBTableName+" "
        SQLStr += self._genIDSQLStr(ids, init_keyword="WHERE") + " "
        SQLStr += self._genConditionSQLStr() + " "
        SQLStr += "AND "+DBTableName+"."+FieldDict[self._DateField]+">='"+StartDate.strftime("%Y%m%d")+"' "
        SQLStr += "AND "+DBTableName+"."+FieldDict[self._DateField]+"<='"+EndDate.strftime("%Y%m%d")+"' "
        SQLStr += "ORDER BY "+DBTableName+"."+FieldDict[self._IDField]+", "+DBTableName+"."+FieldDict[self._DateField]+", "+DBTableName+"."+FieldDict[self._ReportDateField]
        RawData = self._FactorDB.fetchall(SQLStr)
        if not RawData: RawData = pd.DataFrame(columns=["日期", "QS_ID", self._ReportDateField, self._CapitalField]+AllFields)
        else: RawData = pd.DataFrame(np.array(RawData, dtype="O"), columns=["日期", "QS_ID", self._ReportDateField, self._CapitalField]+AllFields)
        return {"RawData": RawData, "ReportANN": _prepareReportANNRawData(self.FactorDB, ids)}

    def __QS_calcData__(self, raw_data, factor_names, ids, dts, args={}):
        ANNReportData = raw_data["ReportANN"]
        raw_data = raw_data["RawData"]
        if not dts: return Panel(items=factor_names, major_axis=dts, minor_axis=ids)
        Dates = sorted({dt.datetime.combine(iDT.date(), dt.time(0)) for iDT in dts})
        DeduplicationFields = args.get("Deduplication", self._QSArgs.Deduplication)
        AdditionalFields = list(dict.fromkeys(args.get("AdditionalFields", self._QSArgs.AdditionalFields)+DeduplicationFields))
        AllFields = list(dict.fromkeys(factor_names+AdditionalFields))
        raw_data = raw_data.loc[:, ["日期", "QS_ID", self._ReportDateField, self._CapitalField]+AllFields].set_index(["QS_ID"])
        Period = args.get("Period", self._QSArgs.Period)
        ForwardYears = args.get("ForwardYears", self._QSArgs.ForwardYears)
        ModelArgs = args.get("ModelArgs", self._QSArgs.ModelArgs)
        Operator = args.get("Operator", self._QSArgs.Operator)
        DataType = args.get("DataType", self._QSArgs.DataType)
        ANNReportData = ANNReportData.set_index(["QS_ID"])
        raw_data[self._CapitalField] = raw_data[self._CapitalField].astype("float")
        AllIDs = set(raw_data.index)
        Data = {}
        for kFactorName in factor_names:
            if DataType=="double": kData = np.full(shape=(len(Dates), len(ids)), fill_value=np.nan)
            else: kData = np.full(shape=(len(Dates), len(ids)), fill_value=None, dtype="O")
            kFields = ["日期", self._ReportDateField, self._CapitalField, kFactorName]+AdditionalFields
            for j, jID in enumerate(ids):
                if jID not in AllIDs:
                    x = [pd.DataFrame(columns=kFields)]*len(ForwardYears)
                    for i, iDate in enumerate(Dates):
                        kData[i, j] = Operator(self, iDate, jID, x, ModelArgs)
                    continue
                if jID in ANNReportData.index:
                    jReportNoteDate = ANNReportData.loc[[jID]].reset_index()
                else:
                    jReportNoteDate = pd.DataFrame(columns=ANNReportData.columns)
                jRawData = raw_data.loc[[jID], kFields]
                ijNoteDate = None
                for i, iDate in enumerate(Dates):
                    iStartDate = (iDate - dt.timedelta(Period)).strftime("%Y%m%d")
                    ijRawData = jRawData[(jRawData["日期"]<=iDate.strftime("%Y%m%d")) & (jRawData["日期"]>iStartDate)]
                    iLastYear = str(iDate.year-1)
                    ijNoteDate = findNoteDate(iLastYear+"1231", jReportNoteDate)
                    x = []
                    for iiNFY in ForwardYears:
                        if (ijNoteDate is None) or ((ijNoteDate is not None) and (ijNoteDate>iDate.strftime("%Y%m%d"))):
                            ObjectDate = str(int(iLastYear)+iiNFY)+"1231"
                        else:
                            ObjectDate = str(iDate.year+iiNFY)+"1231"
                        iijRawData = ijRawData[ijRawData[self._ReportDateField]==ObjectDate].copy()
                        if iijRawData.shape[0]==0: x.append(iijRawData)
                        else:
                            if DeduplicationFields:
                                ijTemp = iijRawData.groupby(by=DeduplicationFields)[["日期"]].max()
                                ijTemp = ijTemp.reset_index()
                                iijRawData = pd.merge(ijTemp, iijRawData, how="left", left_on=DeduplicationFields+["日期"], right_on=DeduplicationFields+["日期"])
                            x.append(iijRawData)
                    kData[i, j] = Operator(self, iDate, jID, x, ModelArgs)
            Data[kFactorName] = kData
        return _alignAnalystData(Panel(Data, items=factor_names, major_axis=Dates, minor_axis=ids), factor_names, ids, dts)



class WindDB2(QSSQLObject, FactorDB):
    """Wind 量化研究数据库。

    Args:
        args: 当前框架的英文参数，如 TablePrefix、DBInfoFile 和 FTArgs。
        config_file: JSON 配置文件，默认查找 WindDB2Config.json。
    """

    class __QS_ArgClass__(QSSQLObject.__QS_ArgClass__, FactorDB.__QS_ArgClass__):
        Name: str = Field(default="WindDB2", title="名称", frozen=True)
        DBInfoFile: Optional[FilePath] = Field(default=None, title="库信息文件", frozen=True, repr=False)
        FTArgs: dict = Field(default_factory=lambda: {"DTFmt": "%Y%m%d", "DateFmt": "%Y%m%d"}, title="因子表参数", frozen=True, exclude=True)

    def __init__(self, args: dict={}, config_file: Optional[str]=None, **kwargs):
        if config_file is None:
            default_config = os.path.join(__QS_ConfigPath__, "WindDB2Config.json")
            if os.path.isfile(default_config): config_file = default_config
        super().__init__(args=args, config_file=config_file, **kwargs)
        self._initInfo()

    def _initInfo(self):
        self._InfoResourcePath = os.fspath(self.Args.DBInfoFile) if self.Args.DBInfoFile else os.path.join(__QS_MainPath__, "Resource", "WindDB2Info.xlsx")
        self._TableInfo, self._FactorInfo = _importInfo(self._InfoResourcePath)

    @property
    def TableNames(self) -> list[str]:
        if self._TableInfo is None: return []
        if not getattr(self, "_AllTables", None): self._AllTables = self.getDBTable()
        names = {name.lower() for name in self._AllTables}
        mask = self._TableInfo["TableClass"].notna() & self._TableInfo["DBTableName"].str.lower().isin(names)
        return self._TableInfo.index[mask].tolist()

    def getTable(self, table_name: str, args: dict={}) -> SQL_Table:
        if self._TableInfo is not None and table_name in self._TableInfo.index:
            info = self._TableInfo.loc[table_name]
            table_type = args.get("TableType", args.get("因子表类型", info["TableClass"]))
            table_class = _TABLE_CLASSES.get(table_type)
            if table_class is not None:
                defaults = info["DefaultArgs"] if table_type == info["TableClass"] else None
                defaults = {} if pd.isna(defaults) else ast.literal_eval(defaults)
                if table_type == "MappingTable" and defaults.get("公告时点字段") is None:
                    defaults.pop("公告时点字段", None)
                arg_class = table_class.__QS_ArgClass__
                values = {"DTFmt": "%Y%m%d", "DateFmt": "%Y%m%d"}
                for source in (self.Args.FTArgs, defaults, args):
                    values.update(_normalizeArgs(source, arg_class))
                values["Name"] = table_name
                return table_class(fdb=self, args=values, logger=self.Logger)
        raise __QS_Error__(f"因子库 '{self.Args.Name}' 目前尚不支持因子表: '{table_name}'")

    def getTradeDay(self, start_date=None, end_date=None, exchange="SSE", **kwargs):
        if start_date is None: start_date = dt.datetime(1900, 1, 1)
        if end_date is None: end_date = dt.datetime.today()
        ExchangeInfo = self._TableInfo.reindex(["香港交易所交易日历", "中国A股交易日历", "中国期货交易日历", "中国债券市场交易日", "中国期权交易日历"])
        ExchangeInfo = ExchangeInfo[ExchangeInfo["Description"].str.contains(exchange, regex=False, na=False)]
        if ExchangeInfo.shape[0]==0: raise __QS_Error__("不支持交易所: '%s' 的交易日序列!" % exchange)
        else: Dates = self.getTable(ExchangeInfo.index[0]).getDateTime(iid=exchange, start_dt=start_date, end_dt=end_date)
        if kwargs.get("output_type", "datetime")=="date": return list(map(lambda x: x.date(), Dates))
        else: return Dates

    def _getAllAStock(self, date, is_current=True):
        if is_current:
            SQLStr = "SELECT S_INFO_WINDCODE FROM {Prefix}AShareDescription WHERE (S_INFO_DELISTDATE is NULL OR S_INFO_DELISTDATE>'{Date}') AND S_INFO_LISTDATE<='{Date}' ORDER BY S_INFO_WINDCODE"
        else:
            SQLStr = "SELECT S_INFO_WINDCODE FROM {Prefix}AShareDescription WHERE S_INFO_LISTDATE<='{Date}' ORDER BY S_INFO_WINDCODE"
        return [iRslt[0] for iRslt in self.fetchall(SQLStr.format(Prefix=self.Args.TablePrefix, Date=date.strftime("%Y%m%d")))]

    def getStockID(self, index_id="全体A股", date=None, is_current=True, **kwargs):
        if date is None: date = dt.date.today()
        if index_id=="全体A股": return self._getAllAStock(date=date, is_current=is_current)
        for iTableName in self._TableInfo[(self._TableInfo["TableClass"]=="ConstituentTable") & self._TableInfo.index.str.contains("A股")].index:
            IDs = self.getTable(iTableName).getID(ifactor_name=index_id, idt=date, is_current=is_current)
            if IDs: return IDs
        else: return []

    def getMutualFundID(self, exchange=None, date=None, is_current=True, start_date=None, **kwargs):
        if date is None: date = dt.date.today()
        if start_date is not None: start_date = start_date.strftime("%Y%m%d")
        SQLStr = "SELECT f_info_windcode AS ID FROM {Prefix}ChinaMutualFundDescription "
        SQLStr += "WHERE {Prefix}ChinaMutualFundDescription.f_info_setupdate <= '{Date}' "
        if start_date is not None:
            SQLStr += "AND (({Prefix}ChinaMutualFundDescription.f_info_maturitydate IS NULL) OR ({Prefix}ChinaMutualFundDescription.f_info_maturitydate >= '{StartDate}')) "
        if is_current:
            if start_date is None:
                SQLStr += "AND (({Prefix}ChinaMutualFundDescription.f_info_maturitydate IS NULL) OR ({Prefix}ChinaMutualFundDescription.f_info_maturitydate >= '{Date}')) "
            else:
                SQLStr += "AND {Prefix}ChinaMutualFundDescription.f_info_setupdate <= '{StartDate}' "
                SQLStr += "AND (({Prefix}ChinaMutualFundDescription.f_info_maturitydate IS NULL) OR ({Prefix}ChinaMutualFundDescription.f_info_maturitydate >= '{Date}')) "
        if exchange:
            if isinstance(exchange, str):
                SQLStr += f"AND {self.Args.TablePrefix}ChinaMutualFundDescription.f_info_exchmarket = '{exchange}' "
            else:
                SQLStr += "AND {Prefix}ChinaMutualFundDescription.f_info_exchmarket IN ('"+"', '".join(exchange)+"') "
        SQLStr += "ORDER BY ID"
        Rslt = np.array(self.fetchall(SQLStr.format(Prefix=self.Args.TablePrefix, Date=date.strftime("%Y%m%d"), StartDate=start_date)))
        if Rslt.shape[0]>0: return Rslt[:, 0].tolist()
        else: return []

    def getFutureID(self, future_code="IF", date=None, is_current=True, **kwargs):
        if date is None: date = dt.date.today()
        SQLStr = "SELECT DISTINCT s_info_windcode FROM {Prefix}CFuturesDescription "
        if future_code:
            if isinstance(future_code, str): SQLStr += "WHERE fs_info_sccode='"+future_code+"' "
            else: SQLStr += "WHERE fs_info_sccode IN ('"+"', '".join(future_code)+"') "
        else: SQLStr += "WHERE fs_info_sccode IS NOT NULL "
        if not kwargs.get("include_simulation", False): SQLStr += "AND s_info_name NOT LIKE '%仿真%' "
        ContractType = kwargs.get("contract_type", "月合约")
        if ContractType!="所有": SQLStr += "AND fs_info_type="+("2" if ContractType=="连续合约" else "1")+" "
        if ContractType!="连续合约":
            SQLStr += "AND ((s_info_listdate<='{Date}') OR (s_info_listdate IS NULL)) "
            if is_current: SQLStr += "AND ((s_info_delistdate>='{Date}') OR (s_info_delistdate IS NULL)) "
        SQLStr += "ORDER BY s_info_windcode"
        return [iRslt[0] for iRslt in self.fetchall(SQLStr.format(Prefix=self.Args.TablePrefix, Date=date.strftime("%Y%m%d"), FutureCode=future_code))]

    def getFutureCode(self, exchange=None, date=None, is_current=True, **kwargs):
        if date is None: date = dt.date.today()
        SQLStr = "SELECT DISTINCT fs_info_sccode FROM {Prefix}CFuturesDescription "
        SQLStr += "WHERE s_info_listdate<='{Date}' "
        if is_current: SQLStr += "AND s_info_delistdate>='{Date}' "
        if exchange:
            if isinstance(exchange, str): SQLStr += "AND s_info_exchmarket='"+exchange+"' "
            else: SQLStr += "AND s_info_exchmarket IN ('"+"', '".join(exchange)+"') "
        if not kwargs.get("include_simulation", False): SQLStr += "AND s_info_name NOT LIKE '%仿真%' "
        SQLStr += "ORDER BY fs_info_sccode"
        return [iRslt[0] for iRslt in self.fetchall(SQLStr.format(Prefix=self.Args.TablePrefix, Date=date.strftime("%Y%m%d")))]

    def getOptionID(self, option_code="510050OP", date=None, is_current=True, **kwargs):
        if date is None: date = dt.date.today()
        SQLStr = "SELECT DISTINCT s_info_windcode FROM {Prefix}ChinaOptionDescription "
        SQLStr += "WHERE s_info_sccode LIKE '{OptionCode}%%' "
        SQLStr += "AND s_info_ftdate<='{Date}' "
        if is_current: SQLStr += "AND s_info_lasttradingdate>='{Date}' "
        SQLStr += "ORDER BY s_info_windcode"
        return [iRslt[0] for iRslt in self.fetchall(SQLStr.format(Prefix=self.Args.TablePrefix, Date=date.strftime("%Y%m%d"), OptionCode=option_code))]

_TABLE_CLASSES = {
    "WideTable": _WideTable,
    "NarrowTable": _NarrowTable,
    "FeatureTable": _FeatureTable,
    "TimeSeriesTable": _TimeSeriesTable,
    "MappingTable": _MappingTable,
    "ConstituentTable": _ConstituentTable,
    "FinancialTable": _FinancialTable,
    "AnalystConsensusTable": _AnalystConsensusTable,
    "AnalystRatingDetailTable": _AnalystRatingDetailTable,
    "AnalystEstDetailTable": _AnalystEstDetailTable,
}
