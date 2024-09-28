# coding=utf-8
"""基于 BaoStock 的因子库(http://baostock.com/baostock/)(TODO)"""
import os
import datetime as dt

import numpy as np
import pandas as pd
import baostock as bs
from traits.api import Enum, Int, Str, File, Dict, Password

from QuantStudio import __QS_Error__
from QSExt import  __QS_LibPath__, __QS_MainPath__, __QS_ConfigPath__
from QuantStudio.FactorDataBase.FactorDB import FactorDB, FactorTable
from QuantStudio.FactorDataBase.FDBFun import _QS_calcData_WideTable
from QuantStudio.Tools.IDFun import suffixAShareID
from QuantStudio.Tools.DateTimeFun import getDateTimeSeries

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


class _BSTable(FactorTable):
    class __QS_ArgClass__(FactorTable.__QS_ArgClass__):
        IDAdj = Enum("无", "前缀", arg_type="SingleOption", label="ID调整", order=50)
        DTFmt = Str(arg_type="String", label="时点格式", order=51)
        def __QS_initArgs__(self, args={}):
            super().__QS_initArgs__(args=args)
            ArgInfo = self._Owner._ArgInfo
            ArgInfo = ArgInfo[ArgInfo["FieldType"]=="QSArg"]
            for i, iArgName in enumerate(ArgInfo.index):
                iArgInfo = eval(ArgInfo.loc[iArgName, "ArgInfo"])
                if iArgInfo["arg_type"]=="SingleOption":
                    self.add_trait(iArgName, Enum(*iArgInfo["option_range"], arg_type="SingleOption", label=iArgName, order=i+100, option_range=iArgInfo["option_range"]))
                else:
                    raise __QS_Error__(f"无法识别的参数信息: {iArgInfo}")
                iDataType = ArgInfo.loc[iArgName, "DataType"]
                iDefaultVal = ArgInfo.loc[iArgName, "DefaultValue"]
                if iDataType=="str":
                    self[iArgName] = (str(iDefaultVal) if pd.notnull(iDefaultVal) else "")
                elif iDataType=="float":
                    self[iArgName] = float(iDefaultVal)
                elif iDataType=="int":
                    self[iArgName] = int(iDefaultVal)
                else:
                    self[iArgName] = iDefaultVal
    
    def __init__(self, name, fdb, sys_args={}, **kwargs):
        self._TableInfo = fdb._TableInfo.loc[name]
        self._FactorInfo = fdb._FactorInfo.loc[name]
        self._ArgInfo = fdb._ArgInfo.loc[name]
        return super().__init__(name=name, fdb=fdb, sys_args=sys_args, **kwargs)
    
    def _getAPIArgs(self, args={}):
        return {iArgName: args.get(iArgName, self.Args[iArgName]) for iArgName in self._ArgInfo.index[self._ArgInfo["FieldType"]=="QSArg"]}
    def __QS_adjustID__(self, ids, args={}):
        IDAdj = args.get("ID调整", self._QSArgs.IDAdj)
        if IDAdj=="无":
            return ids
        elif IDAdj=="前缀":
            return [iID.split(".")[-1].lower() + ".".join(iID.split(".")[:-1]) if "." in iID else iID for iID in ids]
        else:
            raise __QS_Error__(f"AKShareDB._AKSTable: 不支持的 ID 调整方法 '{IDAdj}'")
    def __QS_restoreID__(self, ids, args={}):
        return ids
    def __QS_adjustDT__(self, dts, args={}):
        DTFmt = args.get("时点格式", self._QSArgs.DTFmt)
        if not DTFmt:
            return dts
        else:
            return [dt.datetime.strptime(iDT, DTFmt) if pd.notnull(iDT) else pd.NaT for iDT in dts]
    def getMetaData(self, key=None, args={}):
        TableInfo = self._FactorDB._TableInfo.loc[self.Name]
        if key is None:
            return TableInfo
        else:
            return TableInfo.get(key, None)
    
    @property
    def FactorNames(self):
        FactorInfo = self._FactorInfo
        return FactorInfo[FactorInfo["FieldType"]=="因子"].index.tolist()
    
    def getFactorMetaData(self, factor_names=None, key=None, args={}):
        if factor_names is None:
            factor_names = self.FactorNames
        FactorInfo = self._FactorDB._FactorInfo.loc[self.Name]
        if key=="DataType":
            if hasattr(self, "_DataType"): return self._DataType.reindex(index=factor_names)
            MetaData = FactorInfo["DataType"].reindex(index=factor_names)
            for i in range(MetaData.shape[0]):
                iDataType = MetaData.iloc[i].lower()
                if iDataType.find("str")!=-1: MetaData.iloc[i] = "string"
                else: MetaData.iloc[i] = "double"
            return MetaData
        elif key=="Description": return FactorInfo["Description"].reindex(index=factor_names)
        elif key is None:
            return pd.DataFrame({"DataType":self.getFactorMetaData(factor_names, key="DataType", args=args),
                                 "Description":self.getFactorMetaData(factor_names, key="Description", args=args)})
        else:
            return pd.Series([None]*len(factor_names), index=factor_names, dtype=np.dtype("O"))


class _DTTable(_BSTable):
    """DTTable"""
    class __QS_ArgClass__(_BSTable.__QS_ArgClass__):
        LookBack = Int(0, arg_type="Integer", label="回溯天数", order=50)
    
    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        StartDT = dts[0] - dt.timedelta(args.get("回溯天数", self._QSArgs.LookBack))
        DTs = getDateTimeSeries(StartDT, dts[0]) + dts[1:]
        APIName = self._TableInfo.loc["DBTableName"]
        ArgInfo = self._ArgInfo
        DTArg = ArgInfo.index[ArgInfo["FieldType"]=="Date"][0]
        APIArgs = {DTArg: None}
        APIArgs.update(self._getAPIArgs(args=args))
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
            RawData = RawData.rename(columns={IDField: "ID"}).reindex(columns=["ID", "QS_DT"]+factor_names)
            RawData["ID"] = RawData["ID"].apply(suffixAShareID)
            return RawData.sort_values(by=["ID", "QS_DT"])
        else:
            return pd.DataFrame(columns=["ID", "QS_DT"]+factor_names)
    
    def __QS_calcData__(self, raw_data, factor_names, ids, dts, args={}):
        DataType = self.getFactorMetaData(factor_names=factor_names, key="DataType", args=args)
        Args = self.Args.to_dict()
        Args.update(args)
        ErrorFmt = {"DuplicatedIndex":  "%s 的表 %s 无法保证唯一性 : {Error}, 可以尝试将 '多重映射' 参数取值调整为 True" % (self._FactorDB.Name, self.Name)}
        return _QS_calcData_WideTable(raw_data, factor_names, ids, dts, DataType, args=Args, logger=self._QS_Logger, error_fmt=ErrorFmt)

class _DTRangeTable(_BSTable):
    """DTRangeTable"""
    class __QS_ArgClass__(_BSTable.__QS_ArgClass__):
        LookBack = Int(0, arg_type="Integer", label="回溯天数", order=50)
    
    def __QS_prepareRawData__(self, factor_names, ids, dts, args={}):
        StartDate, EndDate = dts[0].date(), dts[-1].date()
        StartDate -= dt.timedelta(args.get("回溯天数", self._QSArgs.LookBack))
        APIName = self._TableInfo.loc["DBTableName"]
        ArgInfo = self._ArgInfo
        StartDTArg = ArgInfo.index[ArgInfo["FieldType"]=="StartDate"][0]
        EndDTArg = ArgInfo.index[ArgInfo["FieldType"]=="EndDate"][0]
        IDArg = ArgInfo.index[ArgInfo["FieldType"]=="ID"][0]
        APIArgs = {StartDTArg: StartDate.strftime("%Y%m%d"), EndDTArg: EndDate.strftime("%Y%m%d")}
        APIArgs.update(self._getAPIArgs(args=args))
        AdjustedIDs = self.__QS_adjustID__(ids, args=args)
        RawData = []
        for i, iID in enumerate(AdjustedIDs):
            APIArgs[IDArg] = iID
            try:
                iRawData = getattr(ak, APIName)(**APIArgs)
            except:
                continue
            iRawData["ID"] = ids[i]
            RawData.append(iRawData)
        DTField = self._FactorInfo.index[self._FactorInfo["FieldType"]=="Date"][0]
        if RawData:
            RawData = pd.concat(RawData, axis=0, ignore_index=True)
            RawData = RawData.rename(columns={DTField: "QS_DT"}).reindex(columns=["ID", "QS_DT"]+factor_names)
            RawData["QS_DT"] = self.__QS_adjustDT__(RawData["QS_DT"])
            return RawData.sort_values(by=["ID", "QS_DT"])
        else:
            return pd.DataFrame(columns=["ID", "QS_DT"]+factor_names)
    
    def __QS_calcData__(self, raw_data, factor_names, ids, dts, args={}):
        DataType = self.getFactorMetaData(factor_names=factor_names, key="DataType", args=args)
        Args = self.Args.to_dict()
        Args.update(args)
        ErrorFmt = {"DuplicatedIndex":  "%s 的表 %s 无法保证唯一性 : {Error}, 可以尝试将 '多重映射' 参数取值调整为 True" % (self._FactorDB.Name, self.Name)}
        return _QS_calcData_WideTable(raw_data, factor_names, ids, dts, DataType, args=Args, logger=self._QS_Logger, error_fmt=ErrorFmt)


class BaoStockDB(FactorDB):
    """BaoStockDB"""
    class __QS_ArgClass__(FactorDB.__QS_ArgClass__):
        Name = Str("BaoStockDB", arg_type="String", label="名称", order=-100)
        UserID = Str("anonymous", arg_type="String", label="用户ID", order=0)
        Pwd = Password("123456", arg_type="String", label="密码", order=1)
        DBInfoFile = File(label="库信息文件", arg_type="File", order=100)
        FTArgs = Dict(label="因子表参数", arg_type="Dict", order=101)
    
    def __init__(self, sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=(__QS_ConfigPath__+os.sep+"BaoStockDBConfig.json" if config_file is None else config_file), **kwargs)
        self._InfoFilePath = __QS_LibPath__+os.sep+"BaoStockDBInfo.hdf5"# 数据库信息文件路径
        if not os.path.isfile(self._QSArgs.DBInfoFile):
            if self._QSArgs.DBInfoFile: self._QS_Logger.warning("找不到指定的库信息文件 : '%s'" % self._QSArgs.DBInfoFile)
            self._InfoResourcePath = __QS_MainPath__+os.sep+"Resource"+os.sep+"BaoStockDBInfo.xlsx"# 默认数据库信息源文件路径
            self._TableInfo, self._FactorInfo, self._ArgInfo = _updateInfo(self._InfoFilePath, self._InfoResourcePath, self._QS_Logger)# 数据库表信息, 数据库字段信息
        else:
            self._InfoResourcePath = self._QSArgs.DBInfoFile
            self._TableInfo, self._FactorInfo, self._ArgInfo = _updateInfo(self._InfoFilePath, self._InfoResourcePath, self._QS_Logger, out_info=True)# 数据库表信息, 数据库字段信息
        return
    
    @property
    def TableNames(self):
        if self._TableInfo is not None: return self._TableInfo.index.tolist()
        else: return []
    
    def connect(self):
        LG = bs.login(user_id=self._QSArgs.UserID, password=self._QSArgs.Pwd)
        if LG.error_code != "0":
            raise __QS_Error__(f"BaoStockDB.connect 登录错误码: {LG.error_code}, 错误信息: {LG.error_msg}")
        return self
    
    def disconnect(self):
        LG = bs.logout(user_id=self._QSArgs.UserID)
        if LG.error_code != "0":
            self._QS_Logger.error(f"BaoStockDB.disconnect 登出错误码: {LG.error_code}, 错误信息: {LG.error_msg}")
        return 0
    
    def getTable(self, table_name, args={}):
        if table_name in self._TableInfo.index:
            TableClass = args.get("因子表类型", self._TableInfo.loc[table_name, "TableClass"])
            if pd.notnull(TableClass) and (TableClass!=""):
                DefaultArgs = self._TableInfo.loc[table_name, "DefaultArgs"]
                if pd.isnull(DefaultArgs): DefaultArgs = {}
                else: DefaultArgs = eval(DefaultArgs)
                Args = self._QSArgs.FTArgs.copy()
                Args.update(DefaultArgs)
                Args.update(args)
                return eval("_"+TableClass+"(name='"+table_name+"', fdb=self, sys_args=Args, logger=self._QS_Logger)")
        Msg = ("因子库 '%s' 目前尚不支持因子表: '%s'" % (self.Name, table_name))
        self._QS_Logger.error(Msg)
        raise __QS_Error__(Msg)
    
    def _getResult(self, rs):
        Rslt = []
        while (rs.error_code == '0') & rs.next():
            # 获取一条记录，将记录合并在一起
            Rslt.append(rs.get_row_data())
        Rslt = pd.DataFrame(Rslt, columns=rs.fields)
        return Rslt
    
    # 给定起始日期和结束日期, 获取交易所交易日期
    def getTradeDay(self, start_date=None, end_date=None, exchange="SSE", **kwargs):
        if exchange != "SSE":
            self._QS_Logger.warning(f"BaoStockDB.getTradeDay 的参数 exchange 暂不支持除了 'SSE' 外的其他选项: '{exchange}', 该参数将被忽略!")
        rs = bs.query_trade_dates(start_date=(None if start_date is None else start_date.strftime("%Y-%m-%d")), end_date=(None if end_date is None else end_date.strftime("%Y-%m-%d")))
        if rs.error_code!="0":
            raise __QS_Error__(f"BaoStockDB.getTradeDay query_trade_dates 错误码: {LG.error_code}, 错误信息: {LG.error_msg}")
        Rslt = self._getResult(rs)
        return Rslt["calendar_date"][Rslt["is_trading_day"]==1].tolist()


if __name__=="__main__":
    BSDB = BaoStockDB().connect()
    print(BSDB.TableNames)
    
    #DTs = BSDB.getTradeDay(start_date=dt.datetime(2022, 1, 1), end_date=dt.datetime(2022, 1, 31))
    
    FT = BSDB.getTable("两市停复牌")
    Data = FT.readData(factor_names=["停牌时间", "停牌原因"], ids=IDs, dts=[dt.datetime(2022, 10, 28), dt.datetime(2022, 10, 31)])
    print(Data)
    
    print("===")