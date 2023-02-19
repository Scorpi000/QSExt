# coding=utf-8
"""朝阳永续数据库"""
import re
import os
import json
import shelve
import datetime as dt

import numpy as np
import pandas as pd
from traits.api import Enum, Int, Str, List, ListStr, Dict, Callable, File

from QuantStudio.Tools.api import Panel
from QuantStudio.Tools.SQLDBFun import genSQLInCondition
from QuantStudio.Tools.FileFun import getShelveFileSuffix
from QuantStudio.Tools.QSObjects import QSSQLObject
from QuantStudio import __QS_Error__, __QS_LibPath__, __QS_ConfigPath__
from QuantStudio.FactorDataBase.FactorDB import FactorDB
from QuantStudio.FactorDataBase.FDBFun import adjustDataDTID, SQL_Table, SQL_FeatureTable, SQL_WideTable, SQL_MappingTable, SQL_NarrowTable, SQL_TimeSeriesTable, SQL_ConstituentTable, SQL_FinancialTable

__QS_MainPath__ = os.path.abspath(os.path.split(os.path.realpath(__file__))[0]+os.sep+"..")

# 将信息源文件中的表和字段信息导入信息文件
def _importInfo(info_file, info_resource, logger, out_info=False):
    Suffix = info_resource.split(".")[-1]
    if Suffix in ("xlsx", "xls"):
        TableInfo = pd.read_excel(info_resource, "TableInfo").set_index(["TableName"])
        FactorInfo = pd.read_excel(info_resource, "FactorInfo").set_index(['TableName', 'FieldName'])
    elif Suffix == "json":
        Info = json.load(open(info_resource, "r"))
        TableInfo = pd.DataFrame(Info["TableInfo"]).T
        TableNames = sorted(Info["FactorInfo"].keys())
        FactorInfo = pd.concat([pd.DataFrame(Info["FactorInfo"][iTableName]).T for iTableName in TableNames], keys=TableNames)
    else:
        Msg = ("不支持的库信息文件 : '%s'" % (info_resource,))
        logger.error(Msg)
        raise __QS_Error__(Msg)
    if not out_info:
        try:
            from QuantStudio.Tools.DataTypeFun import writeNestedDict2HDF5
            writeNestedDict2HDF5(TableInfo, info_file, "/TableInfo")
            writeNestedDict2HDF5(FactorInfo, info_file, "/FactorInfo")
        except Exception as e:
            logger.warning("更新数据库信息文件 '%s' 失败 : %s" % (info_file, str(e)))
    return (TableInfo, FactorInfo)


# 更新信息文件
def _updateInfo(info_file, info_resource, logger, out_info=False):
    if out_info: return _importInfo(info_file, info_resource, logger, out_info=out_info)
    if not os.path.isfile(info_file):
        logger.warning("数据库信息文件: '%s' 缺失, 尝试从 '%s' 中导入信息." % (info_file, info_resource))
    elif (os.path.getmtime(info_resource) > os.path.getmtime(info_file)):
        logger.warning("数据库信息文件: '%s' 有更新, 尝试从中导入新信息." % info_resource)
    else:
        try:
            from QuantStudio.Tools.DataTypeFun import readNestedDictFromHDF5
            return (readNestedDictFromHDF5(info_file, ref="/TableInfo"), readNestedDictFromHDF5(info_file, ref="/FactorInfo"))
        except:
            logger.warning("数据库信息文件: '%s' 损坏, 尝试从 '%s' 中导入信息." % (info_file, info_resource))
    if not os.path.isfile(info_resource): raise __QS_Error__("缺失数据库信息源文件: %s" % info_resource)
    return _importInfo(info_file, info_resource, logger, out_info=out_info)


# 给 ID 去后缀
def deSuffixID(ids, sep='.'):
    return [(".".join(iID.split(".")[:-1]) if iID.find(".") != -1 else iID) for iID in ids]


# 根据字段的数据类型确定 QS 的数据类型
def _identifyDataType(field_data_type):
    field_data_type = field_data_type.lower()
    if (field_data_type.find("num") != -1) or (field_data_type.find("int") != -1) or (field_data_type.find("decimal") != -1) or (field_data_type.find("double") != -1) or (field_data_type.find("float") != -1):
        return "double"
    elif field_data_type.find("date") != -1:
        return "object"
    else:
        return "string"


class GoGoalDB(QSSQLObject, FactorDB):
    """朝阳永续数据库"""

    class __QS_ArgClass__(QSSQLObject.__QS_ArgClass__, FactorDB.__QS_ArgClass__):
        Name = Str("GoGoalDB", arg_type="String", label="名称", order=-100)
        DBInfoFile = File(label="库信息文件", arg_type="File", order=100)
        FTArgs = Dict(label="因子表参数", arg_type="Dict", order=101)

    def __init__(self, sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=(__QS_ConfigPath__ + os.sep + "GoGoalDBInfo.json" if config_file is None else config_file), **kwargs)
        self._InfoFilePath = __QS_LibPath__ + os.sep + "GoGoalDBInfo.hdf5"  # 数据库信息文件路径
        if not os.path.isfile(self._QSArgs.DBInfoFile):
            if self._QSArgs.DBInfoFile: self._QS_Logger.warning("找不到指定的库信息文件 : '%s'" % self._QSArgs.DBInfoFile)
            self._InfoResourcePath = __QS_MainPath__ + os.sep + "Resource" + os.sep + "GoGoalDBInfo.xlsx"  # 默认数据库信息源文件路径
            self._TableInfo, self._FactorInfo = _updateInfo(self._InfoFilePath, self._InfoResourcePath, self._QS_Logger)  # 数据库表信息, 数据库字段信息
        else:
            self._InfoResourcePath = self._QSArgs.DBInfoFile
            self._TableInfo, self._FactorInfo = _updateInfo(self._InfoFilePath, self._InfoResourcePath, self._QS_Logger, out_info=True)  # 数据库表信息, 数据库字段信息
        return

    @property
    def TableNames(self):
        if self._TableInfo is not None:
            return self._TableInfo[pd.notnull(self._TableInfo["TableClass"])].index.tolist()
        else:
            return []

    def getTable(self, table_name, args={}):
        if table_name in self._TableInfo.index:
            TableClass = args.get("因子表类型", self._TableInfo.loc[table_name, "TableClass"])
            if pd.notnull(TableClass) and (TableClass != ""):
                DefaultArgs = self._TableInfo.loc[table_name, "DefaultArgs"]
                if pd.isnull(DefaultArgs):
                    DefaultArgs = {}
                else:
                    DefaultArgs = eval(DefaultArgs)
                Args = self._QSArgs.FTArgs.copy()
                Args.update(DefaultArgs)
                Args.update(args)
                TableInfo, FactorInfo = self._TableInfo.loc[table_name], self._FactorInfo.loc[table_name]
                return eval(f"SQL_{TableClass}(name='{table_name}', fdb=self, sys_args=Args, table_prefix=self._QSArgs.TablePrefix, table_info=TableInfo, factor_info=FactorInfo, logger=self._QS_Logger)")
        Msg = ("因子库 '%s' 目前尚不支持因子表: '%s'" % (self.Name, table_name))
        self._QS_Logger.error(Msg)
        raise __QS_Error__(Msg)

    # -----------------------------------------数据提取---------------------------------
    # 给定起始日期和结束日期, 获取交易所交易日期, 目前支持: "SSE", "SZSE", "SHFE", "DCE", "CZCE", "INE", "CFFEX"
    def getTradeDay(self, start_date=None, end_date=None, exchange="SSE", **kwargs):
        if start_date is None: start_date = dt.datetime(1900, 1, 1)
        if end_date is None: end_date = dt.datetime.today()
        ExchangeMap = {"SSE": "001001", "SZSE": "001002"}
        if exchange not in ExchangeMap:
            raise __QS_Error__(f"不支持的交易所: {exchange}, 支持的交易所为: {sorted(ExchangeMap)}")
        SQLStr = "SELECT {Prefix}qt_trade_date.trade_date FROM {Prefix}qt_trade_date "
        SQLStr += "WHERE {Prefix}qt_trade_date.trade_date>='{StartDate}' AND {Prefix}qt_trade_date.trade_date<='{EndDate}' "
        SQLStr += "AND {Prefix}qt_trade_date.is_trade_date=1 "
        SQLStr += f"AND {{Prefix}}qt_trade_date.exchange={ExchangeMap[exchange]} "
        SQLStr += "ORDER BY {Prefix}qt_trade_date.trade_date"
        SQLStr = SQLStr.format(Prefix=self._QSArgs.TablePrefix, StartDate=start_date.strftime("%Y-%m-%d"), EndDate=end_date.strftime("%Y-%m-%d"))
        Rslt = self.fetchall(SQLStr)
        if kwargs.get("output_type", "datetime") == "date":
            return [iRslt[0].date() for iRslt in Rslt]
        else:
            return [iRslt[0] for iRslt in Rslt]

    # 获取私募基金 ID
    def getPrivateFundID(self, date=None, is_current=True, start_date=None, **kwargs):
        if date is None: date = dt.date.today()
        if start_date is not None: start_date = start_date.strftime("%Y-%m-%d")
        SQLStr = "SELECT CAST({Prefix}t_fund_info.fund_id AS CHAR) AS ID FROM {Prefix}t_fund_info "
        SQLStr += "WHERE {Prefix}t_fund_info.foundation_date <= '{Date}' "
        if start_date is not None:
            SQLStr += "AND (({Prefix}t_fund_info.end_date IS NULL) OR ({Prefix}t_fund_info.end_date >= '{StartDate}')) "
        if is_current:
            if start_date is None:
                SQLStr += "AND (({Prefix}t_fund_info.end_date IS NULL) OR ({Prefix}t_fund_info.end_date >= '{Date}')) "
            else:
                SQLStr += "AND {Prefix}t_fund_info.foundation_date <= '{StartDate}' "
                SQLStr += "AND (({Prefix}t_fund_info.end_date IS NULL) OR ({Prefix}t_fund_info.end_date >= '{Date}')) "
        Conditions, FactorInfo = kwargs.get("conditions", {}), self._FactorInfo.loc["基金信息表"]
        for iField, iVals in Conditions.items():
            iDBField = FactorInfo.loc[iField, "DBFieldName"]
            if isinstance(iVals[0], str):
                iValStr = "'"+"', '".join(str(jVal) for jVal in iVals if pd.notnull(jVal))+"'"
            else:
                iValStr = ", ".join(str(jVal) for jVal in iVals if pd.notnull(jVal))
            if None in iVals:
                SQLStr += f"AND ({{Prefix}}t_fund_info.{iDBField} IS NULL OR {{Prefix}}t_fund_info.{iDBField} IN ({iValStr})) "
            else:
                SQLStr += f"AND {{Prefix}}t_fund_info.{iDBField} IN ({iValStr}) "
        SQLStr += "ORDER BY ID"
        Rslt = np.array(self.fetchall(SQLStr.format(Prefix=self._QSArgs.TablePrefix, Date=date.strftime("%Y-%m-%d"), StartDate=start_date)))
        if Rslt.shape[0] > 0:
            return Rslt[:, 0].tolist()
        else:
            return []


if __name__ == "__main__":
    iDB = GoGoalDB()
    iDB.getStockID()