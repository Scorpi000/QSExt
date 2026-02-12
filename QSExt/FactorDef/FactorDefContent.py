# -*- coding: utf-8 -*-
import os
import re
import importlib
import traceback
import datetime as dt
from typing import Literal, Any, List, Dict, Union, Callable, Optional

import numpy as np
import pandas as pd
from pydantic import Field

from QuantStudio.Tools.DateTimeFun import getDateTimeSeries, getMonthLastDateTime, getWeekLastDateTime, getYearLastDateTime, getQuarterLastDateTime
from QuantStudio.Core import QSArgs, __QS_Error__
from QuantStudio.Core.Factor import Factor
from QuantStudio.Core.FactorDB import FactorDB, WritableFactorDB


_IDFunMapping = {
    "A股": "getStockID",
    "债券": "getBondID",
    "公募基金": "getMutualFundID",
    "私募基金": "getPrivateFundID"
}

def importExternalFT(source, context):
    ModuleSpec = importlib.util.find_spec(source)
    if ModuleSpec is None:
        raise __QS_Error__("Module: {} not found".format(source))
    Module = importlib.util.module_from_spec(ModuleSpec)
    ModuleSpec.loader.exec_module(Module)
    Args = context.to_dict()
    MdlArgs = Args.pop("模型参数", {})
    Context = Module.DefContext(sys_args=Args)
    Context["模型参数"].update(MdlArgs)
    Context._QS_DependentSource = context._QS_DependentSource
    Context.ifProper(raise_error=True)
    Context.getDependentSource()
    Factors = Module.defFactor(Context)
    CFT = CustomFT(name=Context.TargetTable, sys_args={"元信息": {"Author": Context.Author, "Description": Context.Info}})
    CFT.addFactors(factor_list=Factors)
    return Module, CFT, Context

# 因子定义上下文对象
class FactorDefContext(QSArgs):
    Debug: bool = Field(default=True, title="调试环境", frozen=True)
    FDB: Dict = Field(default={}, title="因子库", frozen=False)
    # DTDB = Enum(label="时点因子库", order=2, arg_type="SingleOption")
    DTType: Literal["交易日", "自然日", "自定义"] = Field(default="交易日", title="时点类型")
    StartDT: dt.datetime = Field(default=dt.datetime.combine(dt.date.today(), dt.time(0))-dt.timedelta(30), title="开始时点")
    EndDT: dt.datetime = Field(dt.datetime.combine(dt.date.today(), dt.time(0)), title="结束时点")
    Freq: Union[str, Callable] = Field(default="1d", title="时点频率")
    LastDTIncluded: bool = Field(default=True, title="包含结束时点")
    DTs: List[dt.datetime] = Field(default=[], title="计算时点")
    DTRuler: List[dt.datetime] = Field(title="时点标尺")
    # IDDB = Enum(label="ID因子库", order=10, arg_type="SingleOption")
    IDType: Literal["自定义", "全A"] = Field(default="自定义", title="ID类型")
    IDs: List[str] = Field(title="截面ID")
    MdlArgs: Dict = Field(default={}, title="模型参数")
    UpdateMethod: Literal["update", "update_notnull", "append", "replace", "direct"] = Field(default="update", title="更新方式")
    
    def __init__(self, args={}, config_file=None, **kwargs):
        if "logger" not in kwargs: kwargs["logger"] = getLogger(log_dir=None, log_level="INFO")
        super().__init__(args=args, config_file=config_file, **kwargs)
        self._DTs = None
        self._DTRuler = None
        self._IDs = None
        self._QS_DependentSource = {}# 依赖的定义, {Source: (Module, FT, Context)}
        self._setDTAttr()
        self._setIDAttr()
        if self.DTType=="自定义":
            self._checkDT()

    def __QS_initArgs__(self, args={}):
        super().__QS_initArgs__(args=args)
        FDB = args.get("因子库", {})
        DTDBNames = sorted(iDBName for iDBName, iDB in FDB.items() if hasattr(iDB, "getTradeDay")) + [None]
        self.add_trait("DTDB", Enum(*DTDBNames, arg_type="SingleOption", label="时点因子库", order=2, option_range=DTDBNames))
        DTTypeList = self.SupportedDTType + ("自定义",)
        self.add_trait("DTType", Enum(*DTTypeList, label="时点类型", arg_type="SingleOption", order=3, option_range=DTTypeList))
        IDTypeList = self.SupportedIDType + ("自定义",)
        self.add_trait("IDType", Enum(*IDTypeList, label="ID类型", arg_type="SingleOption", order=11, option_range=IDTypeList))
        IDDBNames = sorted(FDB.keys()) + [None]
        self.add_trait("IDDB", Enum(*IDDBNames, arg_type="SingleOption", label="ID因子库", order=10, option_range=IDDBNames))
        self.RunArgs = _RunArgs(logger=self._QS_Logger)
        self.Freq = "1d"
    
    def __QS_initArgValue__(self, args={}):
        self.initModelArgs()
        return super().__QS_initArgValue__(args=args)

    @property
    def Author(self) -> str:
        raise NotImplementedError

    @property
    def Info(self) -> str:
        return ""

    @property
    def SupportedDTType(self):
        return ("自然日",)

    @property
    def SupportedFreq(self):
        return ("d", "w", "m", "q", "y")
    
    @property
    def SupportedDTs(self):
        return self.DTs, self.DTRuler

    @property
    def SupportedIDType(self):
        return ()
    
    @property
    def SupportedIDs(self):
        return self.IDs

    @property
    def IndispensableModelArgs(self):
        return ()

    @property
    def DependentDef(self):
        return ()

    @property
    def TargetTable(self):
        raise NotImplementedError

    def initModelArgs(self):
        pass

    # 运行时参数是否合适
    def ifProper(self, raise_error=True):
        Proper = True
        if (self.DTType!="自定义") and (self.DTType not in self.SupportedDTType):
            self._QS_Logger.error(f"时点类型 '{self.DTType}' 不支持, 可取的时点类型为: {self.SupportedDTType}")
            Proper = False
        if self.DTType!="自定义":
            if isinstance(self.Freq, str):
                iFreq, iFreqType = int(re.findall(r"\d+", self.Freq)[0]), re.findall(r"\D+", self.Freq)[0].lower()
            else:
                iFreqType = "自定义"
            if (iFreqType != "自定义") and (iFreqType not in self.SupportedFreq):
                self._QS_Logger.error(f"时点频率 '{iFreqType}' 不支持, 可取的时点频率为: {self.SupportedFreq}")
                Proper = False
        if (self.IDType!="自定义") and (self.IDType not in self.SupportedIDType):
            self._QS_Logger.error(f"ID类型 '{self.IDType}' 不支持, 可取的ID类型为: {self.SupportedIDType}")
            Proper = False
        MissingArgs = set(self.IndispensableModelArgs).difference(self.MdlArgs.keys())
        if MissingArgs:
            self._QS_Logger.error(f"缺失模型参数: {MissingArgs}")
            Proper = False
        Proper = (Proper and self._checkDT())
        if raise_error and (not Proper):
            raise __QS_Error__("参数不合适!")
        return Proper

    def getDependentSource(self):
        for iSource in self.DependentDef:
            if iSource not in self._QS_DependentSource:
                self._QS_DependentSource[iSource] = importExternalFT(iSource, self)
        return self._QS_DependentSource

    def getFactorTable(self, source):
        if source not in self.DependentDef:
            raise __QS_Error__(f"{source} 不在依赖项 {self.DependentDef} 中")
        if source not in self._QS_DependentSource:
            self._QS_DependentSource[source] = importExternalFT(source, self)
        return self._QS_DependentSource[source][1]

    def getOperator(self, source, operator_name):
        if source not in self.DependentDef:
            raise __QS_Error__(f"{source} 不在依赖项 {self.DependentDef} 中")
        if source not in self._QS_DependentSource:
            self._QS_DependentSource[source] = importExternalFT(source, self)
        return getattr(self._QS_DependentSource[source][0], operator_name)

    def getID(self):
        if self._IDs is None:
            if self.IDType=="自定义":
                if self.IDs:
                    self._IDs = self.IDs
                else:
                    self._IDs = self.SupportedIDs
            else:
                self._IDs = self._genIDs()
        return self._IDs

    def getDateTime(self):
        if self._DTs is None:
            if self.DTType=="自定义":
                if (not self.DTs) or (not self.DTRuler):
                    self._DTs, self._DTRuler = self.SupportedDTs
                if self.DTs:
                    self._DTs = self.DTs
                if self.DTRuler:
                    self._DTRuler = self.DTRuler
            else:
                self._DTs, self._DTRuler = self._genDTs()
        return self._DTs

    def getDTRuler(self):
        if self._DTRuler is None:
            if self.DTType == "自定义":
                if (not self.DTs) or (not self.DTRuler):
                    self._DTs, self._DTRuler = self.SupportedDTs
                if self.DTs:
                    self._DTs = self.DTs
                if self.DTRuler:
                    self._DTRuler = self.DTRuler
            else:
                self._DTs, self._DTRuler = self._genDTs()
        return self._DTRuler

    @property
    def ObservedArgs(self):
        return super().ObservedArgs + ("调试环境", "时点类型", "开始时点", "结束时点", "时点频率", "包含结束时点", "ID类型")

    def _on_Debug_changed(self, obj, name, old, new):
        for iDB in self.FDB:
            if "因子表参数" in iDB.Args:
                iDB.Args["因子表参数"]["预筛选ID"] = new
    
    def _on_FDB_changed(self, obj, name, old, new):
        FDB = self.FDB
        DTDBNames = sorted(iDBName for iDBName, iDB in FDB.items() if hasattr(iDB, "getTradeDay")) + [None]
        if (self.DTDB is not None) and (self.DTDB not in DTDBNames) and (self.DTType=="交易日"):
            self._QS_Logger.warning(f"时点因子库 '{self.DTDB}' 不存在, 所有可选的因子库: {sorted(DTDBNames[:-1])}")
        DTDB = (self.DTDB if self.DTDB in DTDBNames else DTDBNames[0])
        self._QS_Frozen = False
        self.add_trait("DTDB", Enum(*DTDBNames, arg_type="SingleOption", label="时点因子库", order=2, option_range=DTDBNames))
        self._QS_Frozen = True
        self.DTDB = DTDB
        
        IDDBNames = sorted(FDB.keys()) + [None]
        if (self.IDDB is not None) and (self.IDDB not in IDDBNames) and (self.IDType!="自定义"):
            self._QS_Logger.warning(f"ID因子库 '{self.IDDB}' 不存在, 所有可选的因子库: {sorted(IDDBNames[:-1])}")
        IDDB = (self.IDDB if self.IDDB in IDDBNames else IDDBNames[0])
        self._QS_Frozen = False
        self.add_trait("IDDB", Enum(*IDDBNames, arg_type="SingleOption", label="ID因子库", order=10, option_range=IDDBNames))
        self._QS_Frozen = True
        self.IDDB = IDDB

    # 检查时点标尺是否合适
    def _checkDT(self):
        DTs = pd.Series(np.arange(0, len(self.getDTRuler())), index=list(self.getDTRuler())).reindex(index=list(self.getDateTime()))
        if pd.isnull(DTs).any():
            self._QS_Logger.error("计算时点序列超出了时点标尺, 请重新设置时点参数!")
            return False
        elif (DTs.diff().iloc[1:] != 1).any():
            self._QS_Logger.error("计算时点序列的频率与时点标尺不一致, 请重新设置时点参数!")
            return False
        return True

    def _genDTs(self):
        if self.DTType == "交易日":
            DTDB = self.FDB[self.DTDB]
            DTs = DTDB.getTradeDay(start_date=self.StartDT, end_date=self.EndDT, output_type="datetime")
            DTRuler = DTDB.getTradeDay(start_date=dt.datetime(1990,1,1), end_date=self.EndDT, output_type="datetime")
        elif self.DTType == "自然日":
            DTs = getDateTimeSeries(start_dt=self.StartDT, end_dt=self.EndDT, timedelta=dt.timedelta(1))
            DTRuler = getDateTimeSeries(start_dt=dt.datetime(1990,1,1), end_dt=self.EndDT, timedelta=dt.timedelta(1))
        else:
            return None, None
        if isinstance(self.Freq, str):
            iFreq, iFreqType = int(re.findall(r"\d+", self.Freq)[0]), re.findall(r"\D+", self.Freq)[0].lower()
            if iFreqType == "y":
                DTs = getYearLastDateTime(DTs)
                DTRuler = getYearLastDateTime(DTRuler)
            elif iFreqType == "q":
                DTs = getQuarterLastDateTime(DTs)
                DTRuler = getQuarterLastDateTime(DTRuler)
            elif iFreqType == "m":
                DTs = getMonthLastDateTime(DTs)
                DTRuler = getMonthLastDateTime(DTRuler)
            elif iFreqType == "w":
                DTs = getWeekLastDateTime(DTs)
                DTRuler = getWeekLastDateTime(DTRuler)
            elif iFreqType != "d":
                raise __QS_Error__(f"{iFreqType} is not a supported frequency type!")
            if not self.LastDTIncluded:
                DTs, DTRuler = DTs[:-1], DTRuler[:-1]
            return DTs[::iFreq], DTRuler[::iFreq]
        else:
            DTs, DTRuler = self.Freq(DTs), self.Freq(DTRuler)
            if not self.LastDTIncluded:
                DTs, DTRuler = DTs[:-1], DTRuler[:-1]
            return DTs, DTRuler

    def _setDTAttr(self):
        if self.DTType=="自定义":
            self._QS_setArgVisible("时点因子库", visible=False)
            # self._QS_setArgVisible("开始时点", visible=False)
            # self._QS_setArgVisible("结束时点", visible=False)
            # self._QS_setArgVisible("时点频率", visible=False)
            # self._QS_setArgVisible("包含结束时点", visible=False)
            self._QS_setArgVisible("计算时点", visible=True)
            self._QS_setArgVisible("时点标尺", visible=True)
        else:
            self._QS_setArgVisible("时点因子库", visible=(self.DTType=="交易日"))
            # self._QS_setArgVisible("开始时点", visible=True)
            # self._QS_setArgVisible("结束时点", visible=True)
            # self._QS_setArgVisible("时点频率", visible=True)
            # self._QS_setArgVisible("包含结束时点", visible=True)
            self._QS_setArgVisible("计算时点", visible=False)
            self._QS_setArgVisible("时点标尺", visible=False)

    def _on_DTType_changed(self, obj, name, old, new):
        self._setDTAttr()
        self._DTs, self._DTRuler = None, None

    def _on_DTDB_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None
    
    def _on_StartDT_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    def _on_EndDT_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    def _on_Freq_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    def _on_LastDTIncluded_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    def _on_DTs_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    def _on_DTRuler_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    def _genIDs(self):
        IDDB = self.FDB[self.IDDB]
        IDFun = _IDFunMapping.get(self.IDType)
        IDs = getattr(IDDB, IDFun)(is_current=False)
        return IDs

    def _setIDAttr(self):
        if self.IDType == "自定义":
            self._QS_setArgVisible("截面ID", visible=True)
            self._QS_setArgVisible("ID因子库", visible=False)
        else:
            self._QS_setArgVisible("截面ID", visible=False)
            self._QS_setArgVisible("ID因子库", visible=True)

    def _on_IDType_changed(self, obj, name, old, new):
        self._setIDAttr()
        self._IDs = None

    def _on_IDDB_changed(self, obj, name, old, new):
        self._IDs = None


class FactorDefInput(QSArgs):
    Debug: bool = Field(default=False, title="调试环境", frozen=True)
    FDB: Dict[str, FactorDB] = Field(default={}, title="可用因子库")
    ModelArgs: Dict = Field(default={}, title="模型参数")
    DTs: List[dt.datetime] = Field(default=[], title="计算时点")
    DTRuler: List[dt.datetime] = Field(default=[], title="时点标尺")
    IDs: List[str] = Field(default=[], title="ID序列")
    SectionIDs: List[str] = Field(default=[], title="截面ID")
    TDB: Optional[WritableFactorDB] = Field(default=None, title="写入因子库")

# 因子定义对象
class FactorDef(QSArgs):
    FactorList: List[Factor] = Field(title="因子列表")
    TargetTable: str = Field(title="因子表")
    IDType: str = Field(title="ID类型")
    DefaultStartDT: dt.datetime = Field(default=dt.datetime(2002, 1, 1), title="默认起始日")
    MaxLookBack: int = Field(default=365, title="最大回溯期")
    DTType: Literal["自定义", "交易日", "自然日"] = Field(default="自定义", title="时点类型")
    Freq: str = Field(default="1d", title="时点频率")
    Author: str = Field(default="Anonymous", title="作者")
    Description: str = Field(default="", title="描述信息")

    @property
    def FactorNames(self):
        return [iFactor._QSArgs.Name for iFactor in self.FactorList]

    # 查找因子对象, def_path: 以/分割的因子查找路径, 比如 年化收益率/0/1/...， ...表示只在这层搜索，不查询该层的描述子
    def getFactor(self, factor_name: Optional[str]=None, def_path: str="...", factor_id: Optional[str]=None, only_one=True):
        if (factor_id is None) and (factor_name is None):
            raise __QS_Error__(f"入参 factor_id、factor_name 不可同时为 None")

        def _searchFactor(factors, factor_id, factor_name, recursive=True):
            Factors = []
            for iFactor in factors:
                if ((factor_id is None) or (iFactor.QSID == factor_id)) and ((factor_name is None) or (iFactor._QSArgs.Name == factor_name)):
                    Factors.append(iFactor)
                if recursive:
                    Factors += _searchFactor(iFactor.Descriptors, factor_id, factor_name)
            return Factors

        DefPath = def_path.strip().split("/")
        LastPos = DefPath[-1]
        if LastPos in ("", "..."): DefPath = DefPath[:-1]
        if DefPath:
            iFactor = self
            for i, iIdx in enumerate(DefPath):
                try:
                    iIdx = int(iIdx)
                except:
                    try:
                        iIdx = [iDep._QSArgs.Name for iDep in iFactor.Descriptors].index(iIdx)
                    except:
                        raise __QS_Error__(f"查找不到因子 path='{'/'.join(DefPath[:i+1])}': {traceback.format_exc()}")
                try:
                    iFactor = iFactor.Descriptors[iIdx]
                except:
                    raise __QS_Error__(f"查找不到因子 path='{'/'.join(DefPath[:i+2])}': {traceback.format_exc()}")
            if (LastPos not in ("", "...")) and ((factor_name is None) or (iFactor._QSArgs.Name == factor_name)) and ((factor_id is None) or (iFactor.QSID==factor_id)):
                return (iFactor if only_one else [iFactor])
            elif LastPos in ("", "..."):
                Factors = _searchFactor(factors=iFactor.Descriptors, factor_id=factor_id, factor_name=factor_name, recursive=(LastPos==""))
            else:
                raise __QS_Error__(f"查找不到因子: Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}'")
        else:
            Factors = _searchFactor(factors=self.FactorList, factor_id=factor_id, factor_name=factor_name, recursive=(LastPos==""))
        if only_one:
            if (len(Factors) == 1) or ((len(Factors) > 1) and (factor_id is not None)):
                return Factors[0]
            elif len(Factors) == 0:
                raise __QS_Error__(f"查找不到因子: Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}'")
            else:
                raise __QS_Error__(f"查找到的因子 (Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}') 不止一个!")
        else:
            return Factors


if __name__=="__main__":
    import QuantStudio.api as QS
    HDB = QS.FactorDB.HDF5DB().connect()
    Context = FactorDefContext(sys_args={})
    Context["因子库"] = {"LDB": HDB}
    Context["因子库"]["LDB"] = HDB
    print(Context)