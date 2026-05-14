# coding=utf-8
"""基于 akshare 的因子库(TODO)"""
import os
import datetime as dt
from typing import Tuple, Optional, List, Literal, Union, Any

import numpy as np
import pandas as pd
import akshare as ak
from pydantic import Field, FilePath

from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.FactorDB import FactorDB
from QuantStudio.Factor.FactorTable import FactorTable
from QuantStudio.Factor.FactorUtils import _QS_calcData_WideTable
from QuantStudio.Tools.IDFun import suffixAShareID
from QuantStudio.Tools.DateTimeFun import getDateTimeSeries
from QSExt import __QS_MainPath__, __QS_ConfigPath__


# 将信息源文件中的表和字段信息导入信息文件
def _importInfo(info_file, info_resource, logger, out_info=False):
    Suffix = info_resource.split(".")[-1]
    if Suffix in ("xlsx", "xls"):
        TableInfo = pd.read_excel(info_resource, "TableInfo").set_index(["TableName"])
        FactorInfo = pd.read_excel(info_resource, "FactorInfo").set_index(['TableName', 'FieldName'])
        ArgInfo = pd.read_excel(info_resource, "ArgInfo").set_index(["TableName", "ArgName"])
    else:
        Msg = ("不支持的库信息文件 : '%s'" % (info_resource, ))
        logger.error(Msg)
        raise __QS_Error__(Msg)
    if not out_info:
        try:
            from QuantStudio.Tools.DataTypeFun import writeNestedDict2HDF5
            writeNestedDict2HDF5(TableInfo, info_file, "/TableInfo")
            writeNestedDict2HDF5(FactorInfo, info_file, "/FactorInfo")
            writeNestedDict2HDF5(ArgInfo, info_file, "/ArgInfo")
        except Exception as e:
            logger.warning("更新数据库信息文件 '%s' 失败 : %s" % (info_file, str(e)))
    return (TableInfo, FactorInfo, ArgInfo)

# 更新信息文件
def _updateInfo(info_file, info_resource, logger, out_info=False):
    if out_info: return _importInfo(info_file, info_resource, logger, out_info=out_info)
    if not os.path.isfile(info_file):
        logger.warning("数据库信息文件: '%s' 缺失, 尝试从 '%s' 中导入信息." % (info_file, info_resource))
    elif (os.path.getmtime(info_resource)>os.path.getmtime(info_file)):
        logger.warning("数据库信息文件: '%s' 有更新, 尝试从中导入新信息." % info_resource)
    else:
        try:
            from QuantStudio.Tools.DataTypeFun import readNestedDictFromHDF5
            return (readNestedDictFromHDF5(info_file, ref="/TableInfo"), readNestedDictFromHDF5(info_file, ref="/FactorInfo"), readNestedDictFromHDF5(info_file, ref="/ArgInfo"))
        except:
            logger.warning("数据库信息文件: '%s' 损坏, 尝试从 '%s' 中导入信息." % (info_file, info_resource))
    if not os.path.isfile(info_resource): raise __QS_Error__("缺失数据库信息源文件: %s" % info_resource)
    return _importInfo(info_file, info_resource, logger, out_info=out_info)


class _AKSTable(FactorTable):
    class __QS_ArgClass__(FactorTable.__QS_ArgClass__):
        TableType: str = Field(default="AKSTable", title="因子表类型", frozen=True, description="""只能在 getTable 时传入，因子表创建后不可改变, 用于指明形成的因子表的类型""")
        IDAdj: Literal["去后缀", "无", "前缀"] = Field(default="去后缀", title="ID调整")
        DTFmt: str = Field(default="", title="时点格式")
        APIArgs: dict = Field(default={}, title="API参数", frozen=True, repr=False)
    
    def __init__(self, fdb:"AKShareDB", args:dict={}, **kwargs):
        super().__init__(fdb=fdb, args=args, **kwargs)
        self._TableInfo = fdb._TableInfo.loc[self._QSArgs.Name]
        self._FactorInfo = fdb._FactorInfo.loc[self._QSArgs.Name]
        if self._QSArgs.Name in fdb._ArgInfo.index.get_level_values(0):
            self._ArgInfo = fdb._ArgInfo.loc[self._QSArgs.Name]
        else:
            self._ArgInfo = pd.DataFrame(columns=fdb._ArgInfo.columns)

    def model_dump(self):
        DumpedMdl = super().model_dump()
        DumpedMdl["__module__"] = "AKShare"
        DumpedMdl["__qsargs__"]["APIArgs"] = self._getAPIArgs()
        return DumpedMdl

    def _getAPIArgs(self):
        APIArgs = {}
        for iArgName in self._ArgInfo.index[self._ArgInfo["FieldType"] == "QSArg"]:
            iArgInfo = eval(self._ArgInfo.loc[iArgName, "ArgInfo"])
            if iArgName in self._QSArgs.APIArgs:
                iArgVal = self._QSArgs.APIArgs[iArgName]
                if iArgInfo["arg_type"]=="SingleOption":
                    if iArgVal not in iArgInfo["option_range"]:
                        raise __QS_Error__(f"不支持的参数值: {iArgVal}, 所有可选值: {iArgInfo['option_range']}")
                else:
                    raise __QS_Error__(f"不支持的参数类型: {iArgInfo['arg_type']}")
            else:
                if iArgInfo["arg_type"]=="SingleOption":
                    iArgVal = self._ArgInfo.loc[iArgName, "DefaultValue"]
                    iDataType = self._ArgInfo.loc[iArgName, "DataType"]
                    if iDataType == "int":
                        iArgVal = int(iArgVal)
                    elif iDataType == "float":
                        iArgVal = float(iArgVal)
                    elif iDataType == "str":
                        iArgVal = "" if pd.isnull(iArgVal) else str(iArgVal)
                    else:
                        raise __QS_Error__(f"不支持的参数数据类型: {iDataType}")
                else:
                    raise __QS_Error__(f"不支持的参数类型: {iArgInfo['arg_type']}")
            APIArgs[iArgName] = iArgVal
        return APIArgs
    
    def __QS_getIDMapping__(self, ids):
        if self._QSArgs.IDAdj=="无":
            return {}
        elif self._QSArgs.IDAdj=="前缀":
            return {iID: (iID.split(".")[-1].lower() + ".".join(iID.split(".")[:-1]) if "." in iID else iID) for iID in ids}
        elif self._QSArgs.IDAdj=="去后缀":
            return {iID: (".".join(iID.split(".")[:-1]) if "." in iID else iID) for iID in ids}
        else:
            raise __QS_Error__(f"AKShareDB._AKSTable: 不支持的 ID 调整方法 '{self._QSArgs.IDAdj}'")
    
    def __QS_adjustDT__(self, dts):
        if not self._QSArgs.DTFmt:
            return dts
        else:
            return [dt.datetime.strptime(iDT, self._QSArgs.DTFmt) if pd.notnull(iDT) else pd.NaT for iDT in dts]

    @property
    def FactorNames(self) -> List[str]:
        FactorInfo = self._FactorInfo
        return FactorInfo[FactorInfo["FieldType"]=="因子"].index.tolist()
    
    def getMetaData(self, key:Optional[str]=None) -> Union[Any, pd.Series]:
        if key is None:
            return self._TableInfo
        else:
            return self._TableInfo.get(key, None)

    def getFactorMetaData(self, factor_names:Optional[List[str]]=None, key:Optional[str]=None) -> Union[pd.DataFrame, pd.Series]:
        if factor_names is None: factor_names = self.FactorNames
        if key == "DataType":
            if hasattr(self, "_DataType"): return self._DataType.reindex(index=factor_names)
            MetaData = self._FactorInfo["DataType"].reindex(index=factor_names)
            for i in range(MetaData.shape[0]):
                iDataType = MetaData.iloc[i].lower()
                if iDataType.find("str")!=-1: MetaData.iloc[i] = "string"
                else: MetaData.iloc[i] = "double"
            return MetaData
        elif key == "Description":
            return self._FactorInfo.loc[factor_names, "Description"]
        elif key is None:
            return self._FactorInfo.loc[factor_names, ["DataType", "Description"]]
        else:
            return None


class _DTTable(_AKSTable):
    """AKShareDB 库中基于取单个时点数据 API 的因子表"""

    class __QS_ArgClass__(_AKSTable.__QS_ArgClass__):
        TableType: Literal["DTTable"] = Field(default="DTTable", title="因子表类型", frozen=True)
        LookBack: int = Field(default=0, title="回溯天数", frozen=True, ge=0)
    
    def __init__(self, fdb:"AKShareDB", args:dict={}, **kwargs):
        super().__init__(fdb=fdb, args=args, **kwargs)
        self._QS_PrepareIgnoredArgs += ("LookBack",)
    
    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        StartDT = dts[0] - dt.timedelta(args.get("LookBack", self._QSArgs.LookBack))
        DTs = getDateTimeSeries(StartDT, dts[0]) + dts[1:]
        APIName = self._TableInfo.loc["DBTableName"]
        ArgInfo = self._ArgInfo
        DTArg = ArgInfo.index[ArgInfo["FieldType"]=="Date"][0]
        APIArgs = {DTArg: None}
        APIArgs.update(self._getAPIArgs())
        RawData = []
        for iDT in DTs:
            APIArgs[DTArg] = iDT.strftime("%Y%m%d")
            try:
                iRawData = getattr(ak, APIName)(**APIArgs)
            except:
                continue
            iRawData["QS_DT"] = iDT
            RawData.append(iRawData)
        IDField = self._FactorInfo.index[self._FactorInfo["FieldType"]=="ID"][0]
        if RawData:
            RawData = pd.concat(RawData, axis=0, ignore_index=True)
            RawData = RawData.rename(columns={IDField: "QS_ID"}).reindex(columns=["QS_ID", "QS_DT"]+factor_names)
            RawData["QS_ID"] = RawData["QS_ID"].apply(suffixAShareID)
            return RawData.sort_values(by=["QS_ID", "QS_DT"])
        else:
            return pd.DataFrame(columns=["QS_ID", "QS_DT"]+factor_names)
    
    def __QS_calcData__(self, raw_data, factor_names, ids, dts):
        DataType = self.getFactorMetaData(factor_names=factor_names, key="DataType")
        Args = self._QSArgs.to_dict(repr=False)
        ErrorFmt = {"DuplicatedIndex":  "%s 的表 %s 无法保证唯一性 : {Error}, 可以尝试将 '多重映射' 参数取值调整为 True" % (self._FactorDB.Name, self.Name)}
        return _QS_calcData_WideTable(raw_data, factor_names, ids, dts, DataType, args=Args, logger=self._QS_Logger, error_fmt=ErrorFmt)

class _DTRangeTable(_AKSTable):
    """AKShareDB 库中基于取时间区间数据 API 的因子表"""

    class __QS_ArgClass__(_AKSTable.__QS_ArgClass__):
        TableType: Literal["DTRangeTable"] = Field(default="DTRangeTable", title="因子表类型", frozen=True)
        LookBack: int = Field(default=0, title="回溯天数", frozen=True, ge=0)
    
    def __init__(self, fdb: "AKShareDB", args:dict={}, **kwargs):
        super().__init__(fdb=fdb, args=args, **kwargs)
        self._QS_PrepareIgnoredArgs += ("LookBack",)
    
    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        StartDate, EndDate = dts[0].date(), dts[-1].date()
        StartDate -= dt.timedelta(args.get("LookBack", self._QSArgs.LookBack))
        APIName = self._TableInfo.loc["DBTableName"]
        ArgInfo = self._ArgInfo
        StartDTArg = ArgInfo.index[ArgInfo["FieldType"]=="StartDate"][0]
        EndDTArg = ArgInfo.index[ArgInfo["FieldType"]=="EndDate"][0]
        IDArg = ArgInfo.index[ArgInfo["FieldType"]=="ID"][0]
        APIArgs = {StartDTArg: StartDate.strftime("%Y%m%d"), EndDTArg: EndDate.strftime("%Y%m%d")}
        APIArgs.update(self._getAPIArgs())
        IDMapping = self.__QS_getIDMapping__(ids)
        RawData = []
        for iID in ids:
            APIArgs[IDArg] = IDMapping.get(iID, iID)
            try:
                iRawData = getattr(ak, APIName)(**APIArgs)
            except Exception as e:
                continue
            iRawData["QS_ID"] = iID
            RawData.append(iRawData)
        DTField = self._FactorInfo.index[self._FactorInfo["FieldType"]=="Date"][0]
        if RawData:
            RawData = pd.concat(RawData, axis=0, ignore_index=True)
            RawData = RawData.rename(columns={DTField: "QS_DT"}).reindex(columns=["QS_ID", "QS_DT"]+factor_names)
            RawData["QS_DT"] = self.__QS_adjustDT__(RawData["QS_DT"])
            return RawData.sort_values(by=["QS_ID", "QS_DT"])
        else:
            return pd.DataFrame(columns=["QS_ID", "QS_DT"]+factor_names)
    
    def __QS_calcData__(self, raw_data, factor_names, ids, dts):
        DataType = self.getFactorMetaData(factor_names=factor_names, key="DataType")
        Args = self._QSArgs.to_dict(repr=False)
        ErrorFmt = {"DuplicatedIndex":  "%s 的表 %s 无法保证唯一性 : {Error}, 可以尝试将 '多重映射' 参数取值调整为 True" % (self._FactorDB.Name, self.Name)}
        return _QS_calcData_WideTable(raw_data, factor_names, ids, dts, DataType, args=Args, logger=self._QS_Logger, error_fmt=ErrorFmt)


class AKShareDB(FactorDB):
    """基于 akshare 的因子库
    Document: https://akshare.akfamily.xyz/index.html
    GitHub: https://github.com/akfamily/akshare
    库配置信息文件在 Resource 目录下的 AKShareDBInfo.xlsx, 记录了相关配置信息"""
    class __QS_ArgClass__(FactorDB.__QS_ArgClass__):
        Name: str = Field(default="AKShareDB", title="名称", frozen=True)
        UserID: str = Field(default="anonymous", title="用户ID", frozen=True, repr=False)
        Pwd: str = Field(default="123456", title="密码", frozen=True, repr=False)
        DBInfoFile: Optional[FilePath] = Field(default=None, title="库信息文件", frozen=True, repr=False)
        FTArgs: dict = Field(default={}, title="因子表参数", frozen=True, repr=False)
    
    def __init__(self, args:dict={}, config_file:Optional[str]=None, **kwargs):
        """初始化 AKShareDB

        Args:
            args: 指定的对象参数集
            config_file: 配置文件路径, 默认配置文件为 "~/QuantStudioConfig/AKShareDBConfig.json"
        """
        super().__init__(args=args, config_file=(__QS_ConfigPath__ + os.sep + "AKShareDBConfig.json" if config_file is None else config_file), **kwargs)
        self._InfoFilePath = __QS_MainPath__ + os.sep + "Resource" + os.sep + "AKShareDBInfo.hdf5"  # 数据库信息文件路径
        if (not self._QSArgs.DBInfoFile) or (not os.path.isfile(self._QSArgs.DBInfoFile)):
            if self._QSArgs.DBInfoFile: self._QS_Logger.warning("找不到指定的库信息文件 : '%s'" % self._QSArgs.DBInfoFile)
            self._InfoResourcePath = __QS_MainPath__ + os.sep + "Resource" + os.sep + "AKShareDBInfo.xlsx"  # 默认数据库信息源文件路径
            self._TableInfo, self._FactorInfo, self._ArgInfo = _updateInfo(self._InfoFilePath, self._InfoResourcePath, self._QS_Logger)  # 数据库表信息, 数据库字段信息
        else:
            self._InfoResourcePath = self._QSArgs.DBInfoFile
            self._TableInfo, self._FactorInfo, self._ArgInfo = _updateInfo(self._InfoFilePath, self._InfoResourcePath, self._QS_Logger, out_info=True)  # 数据库表信息, 数据库字段信息
    
    @property
    def TableNames(self) -> List[str]:
        if self._TableInfo is not None: return self._TableInfo.index.tolist()
        else: return []
    
    def getTable(self, table_name:str, args:dict={}) -> _AKSTable:
        if table_name in self._TableInfo.index:
            TableClass = args.get("TableType", self._TableInfo.loc[table_name, "TableClass"])
            if pd.notnull(TableClass) and (TableClass != ""):
                DefaultArgs = self._TableInfo.loc[table_name, "DefaultArgs"]
                if pd.isnull(DefaultArgs):
                    DefaultArgs = {}
                else:
                    DefaultArgs = eval(DefaultArgs)
                Args = self._QSArgs.FTArgs.copy()
                Args.update(DefaultArgs)
                Args.update(args)
                Args["Name"] = table_name
                return eval("_"+TableClass+"(fdb=self, args=Args, logger=self._QS_Logger)")
        Msg = ("因子库 '%s' 目前尚不支持因子表: '%s'" % (self.Name, table_name))
        self._QS_Logger.error(Msg)
        raise __QS_Error__(Msg)
    
    def getTradeDay(self, start_date:Optional[dt.datetime]=None, end_date:Optional[dt.datetime]=None, **kwargs) -> List[dt.datetime]:
        """给定交易所、起始日和结束日, 获取交易日序列

        Args:
            start_date: 起始日, None 表示从可取的最早日期开始
            end_date: 结束日, None 表示当前日期

        Returns:
            交易日序列
        """
        DTs = ak.tool_trade_date_hist_sina().iloc[:, 0]
        if start_date: DTs = DTs[DTs>=(start_date.date() if isinstance(start_date, dt.datetime) else start_date)]
        if end_date: DTs = DTs[DTs<=(end_date.date() if isinstance(end_date, dt.datetime) else end_date)]
        if kwargs.get("output_type", "datetime")=="date":
            return DTs.tolist()
        else:
            return [dt.datetime.combine(iDT, dt.time(0)) for iDT in DTs]
    
    def getStockID(self, exchange:Tuple[str]=("SSE", "SZSE", "BSE"), **kwargs) -> List[str]:
        """给定交易所和日期, 获取股票证券代码序列, 包括已退市的

        Args:
            exchange: 交易所列表(tuple), 默认 ("SSE", "SZSE", "BSE") 表示上交所、深交所、北交所
            
        Returns:
            股票证券代码序列
        """
        if set(exchange)=={"SSE", "SZSE", "BSE"}:
            try:
                Rslt = ak.stock_zh_a_spot_em()
            except Exception as e:
                self._QS_Logger.warning(f"API ak.stock_zh_a_spot_em 访问失败：{e}")
            else:
                IDs = sorted(suffixAShareID(Rslt["代码"]))
                return IDs
        IDs = []
        if "SSE" in exchange:
            IDs = ak.stock_sh_a_spot_em()["代码"].tolist()
        if "SZSE" in exchange:
            IDs += ak.stock_sz_a_spot_em()["代码"].tolist()
        if "BSE" in exchange:
            IDs += ak.stock_bj_a_spot_em()["代码"].tolist()
        IDs = sorted(suffixAShareID(IDs))
        return IDs
