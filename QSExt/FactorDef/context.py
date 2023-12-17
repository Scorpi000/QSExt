# -*- coding: utf-8 -*-
import re
import datetime as dt

import numpy as np
import pandas as pd
from traits.api import Str, Int, Dict, List, ListStr, Enum, Datetime, Either, Callable, Instance, on_trait_change

import QuantStudio.api as QS
from QSExt.FactorDef.updateFactorData import getLogger
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize
from QuantStudio import QSArgs, __QS_Error__

Today = dt.datetime.combine(dt.date.today(), dt.time(0))

class _RunArgs(QSArgs):
    """运行参数"""
    UpdateMethod = Enum("update", "update_notnull", "append", arg_type="SingleOption", label="更新方式", order=0, option_range=["update", "update_notnull", "append"])
    SubprocessNum = Int(0, arg_type="Integer", label="子进程数", order=1)

# 因子运行时环境
class FactorDefContext(QSArgs):
    Debug = Enum(True, False, label="调试环境", order=0, arg_type="Bool")
    FDB = Dict(label="因子库", order=1, arg_type="Dict")
    # DTDB = Enum(label="时点因子库", order=2, arg_type="SingleOption")
    # DTType = Enum("交易日", "自然日", "自定义", label="时点类型", arg_type="SingleOption", order=3, option_range=("自定义", "交易日", "自然日"))
    StartDT = Datetime(Today-dt.timedelta(30), label="开始时点", arg_type="DateTime", order=4)
    EndDT = Datetime(Today, label="结束时点", arg_type="DateTime", order=5)
    Freq = Either(Str("1d"), Callable(), label="时点频率", arg_type="String", order=6)
    LastDTIncluded = Enum(True, False, label="包含结束时点", order=7, arg_type="Bool")
    DTs = List(dt.datetime, arg_type="DateTimeList", label="计算时点", order=8)
    DTRuler = List(dt.datetime, arg_type="DateTimeList", label="时点标尺", order=9)
    # IDDB = Enum(label="ID因子库", order=10, arg_type="SingleOption")
    # IDType = Enum("私募基金", "自定义", "A股", "公募基金", label="ID类型", arg_type="SingleOption", order=11, option_range=("私募基金", "自定义", "股票", "公募基金"))
    IDs = ListStr(arg_type="IDList", label="截面ID", order=12)
    TargetTable = Str(label="目标因子表", arg_type="String", order=13)
    MdlArgs = Dict(label="模型参数", arg_type="Dict", order=14)
    RunArgs = Instance(_RunArgs, label="运行参数", arg_type="QSObject", order=15)
    def __init__(self, sys_args={}, config_file=None, **kwargs):
        if "logger" not in kwargs:
            kwargs["logger"] = getLogger(log_dir=None, log_level="INFO")
        super().__init__(owner=None, sys_args=sys_args, config_file=config_file, **kwargs)
        self._DTs = None
        self._DTRuler = None
        self._IDs = None
        self._setDTAttr()
        self._setIDAttr()
        self._checkDT()

    def __QS_initArgs__(self):
        super().__QS_initArgs__()
        DBNames = sorted(self.FDB.keys())
        DBEmpty, DBNames = bool(DBNames), ([None] if not DBNames else DBNames)
        self.add_trait("DTDB", Enum(*DBNames, arg_type="SingleOption", label="时点因子库", order=2, option_range=DBNames, visible=DBEmpty))
        DTTypeList = self.SupportedDTType
        self.add_trait("DTType", Enum(*DTTypeList, label="时点类型", arg_type="SingleOption", order=3, option_range=DTTypeList))
        IDTypeList = self.SupportedIDType
        self.add_trait("IDType", Enum(*IDTypeList, label="ID类型", arg_type="SingleOption", order=11, option_range=IDTypeList))
        self.add_trait("IDDB", Enum(*DBNames, arg_type="SingleOption", label="ID因子库", order=10, option_range=DBNames, visible=DBEmpty))
        self.RunArgs = _RunArgs(logger=self._QS_Logger)

    @property
    def Author(self) -> str:
        raise NotImplementedError

    @property
    def Info(self) -> str:
        return ""

    @property
    def SupportedDTType(self):
        return ("自定义", "自然日", "交易日")

    @property
    def SupportedFreq(self):
        return ("d", "w", "m", "y", "自定义")

    @property
    def SupportedIDType(self):
        return ("自定义", )

    @property
    def IndispensableModelArgs(self):
        return ()

    # 运行时参数是否合适
    def ifProper(self, raise_error=True):
        Proper = True
        if self.DTType not in self.SupportedDTType:
            self._QS_Logger.error(f"时点类型 '{self.DTType}' 不支持, 可取的时点类型为: {self.SupportedDTType}")
            Proper = False
        if self.DTType!="自定义":
            if isinstance(self.Freq, str):
                iFreq, iFreqType = int(re.findall("\d+", self.Freq)[0]), re.findall("\D+", self.Freq)[0].lower()
            else:
                iFreqType = "自定义"
            if iFreqType not in self.SupportedFreq:
                self._QS_Logger.error(f"时点频率 '{iFreqType}' 不支持, 可取的时点频率为: {self.SupportedFreq}")
                Proper = False
        if self.IDType not in self.SupportedIDType:
            self._QS_Logger.error(f"ID类型 '{self.IDType}' 不支持, 可取的ID类型为: {self.SupportedFreq}")
            Proper = False
        MissingArgs = set(self.IndispensableModelArgs).difference(self.MdlArgs.keys())
        if MissingArgs:
            self._QS_Logger.error(f"缺失模型参数: {MissingArgs}")
            Proper = False
        Proper = (Proper and self._checkDT())
        if raise_error and (not Proper):
            raise __QS_Error__("参数不合适!")
        return Proper

    def getID(self):
        if self._IDs is None:
            if self.IDType=="自定义":
                self._IDs = self.IDs
            else:
                self._IDs = self._genIDs()
        return self._IDs

    def getDateTime(self):
        if self._DTs is None:
            if self.DTType=="自定义":
                self._DTs, self._DTRuler = self.DTs, self.DTRuler
            else:
                self._DTs, self._DTRuler = self._genDTs()
        return self._DTs

    def getDTRuler(self):
        if self._DTRuler is None:
            if self.DTType == "自定义":
                self._DTs, self._DTRuler = self.DTs, self.DTRuler
            else:
                self._DTs, self._DTRuler = self._genDTs()
        return self._DTRuler

    @property
    def ObservedArgs(self):
        return super().ObservedArgs + ("调试环境", "时点类型", "开始时点", "结束时点", "时点频率", "包含结束时点", "ID类型")

    @on_trait_change("Debug")
    def _on_Debug_changed(self, obj, name, old, new):
        for iDB in self.FDB:
            if "因子表参数" in iDB.Args:
                iDB.Args["因子表参数"]["预筛选ID"] = new

    @on_trait_change("FDB_items")
    def _on_FDB_changed(self, obj, name, new):
        if (self.DTDB not in self.FDB) and (self.DTType=="交易日"):
            self._QS_Logger.warning(f"时点因子库 '{self.DTDB}' 不存在, 所有因子库: {sorted(self.FDB)}")
        if (self.IDDB not in self.FDB) and (self.IDType!="自定义"):
            self._QS_Logger.warning(f"ID因子库 '{self.IDDB}' 不存在, 所有因子库: {sorted(self.FDB)}")

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
        DTDB = self.FDB[self.DTDB]
        if self.DTType == "交易日":
            DTs = DTDB.getTradeDay(start_date=self.StartDT, end_date=self.EndDT, output_type="datetime")
            DTRuler = DTDB.getTradeDay(start_date=dt.datetime(1990,1,1), end_date=self.EndDT, output_type="datetime")
        elif self.DTType == "自然日":
            DTs = QS.Tools.DateTime.getDateTimeSeries(start_dt=self.StartDT, end_dt=self.EndDT, timedelta=dt.timedelta(1))
            DTRuler = QS.Tools.DateTime.getDateTimeSeries(start_dt=dt.datetime(1990,1,1), end_dt=self.EndDT, timedelta=dt.timedelta(1))
        else:
            return None, None
        if isinstance(self.Freq, str):
            iFreq, iFreqType = int(re.findall("\d+", self.Freq)[0]), re.findall("\D+", self.Freq)[0].lower()
            if iFreqType == "y":
                DTs = QS.Tools.DateTime.getYearLastDateTime(DTs)
                DTRuler = QS.Tools.DateTime.getYearLastDateTime(DTRuler)
            elif iFreqType == "q":
                DTs = QS.Tools.DateTime.getQuarterLastDateTime(DTs)
                DTRuler = QS.Tools.DateTime.getQuarterLastDateTime(DTRuler)
            elif iFreqType == "m":
                DTs = QS.Tools.DateTime.getMonthLastDateTime(DTs)
                DTRuler = QS.Tools.DateTime.getMonthLastDateTime(DTRuler)
            elif iFreqType == "w":
                DTs = QS.Tools.DateTime.getWeekLastDateTime(DTs)
                DTRuler = QS.Tools.DateTime.getWeekLastDateTime(DTRuler)
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
            self._QS_setArgVisible("开始时点", visible=False)
            self._QS_setArgVisible("结束时点", visible=False)
            self._QS_setArgVisible("时点频率", visible=False)
            self._QS_setArgVisible("包含结束时点", visible=False)
            self._QS_setArgVisible("计算时点", visible=True)
            self._QS_setArgVisible("时点标尺", visible=True)
        else:
            self._QS_setArgVisible("时点因子库", visible=(self.DTType=="交易日"))
            self._QS_setArgVisible("开始时点", visible=True)
            self._QS_setArgVisible("结束时点", visible=True)
            self._QS_setArgVisible("时点频率", visible=True)
            self._QS_setArgVisible("包含结束时点", visible=True)
            self._QS_setArgVisible("计算时点", visible=False)
            self._QS_setArgVisible("时点标尺", visible=False)

    @on_trait_change("DTType")
    def _on_DTType_changed(self, obj, name, old, new):
        self._setDTAttr()
        self._DTs, self._DTRuler = None, None

    @on_trait_change("DTDB")
    def _on_DTDB_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    @on_trait_change("StartDT")
    def _on_StartDT_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    @on_trait_change("EndDT")
    def _on_EndDT_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    @on_trait_change("Freq")
    def _on_Freq_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    @on_trait_change("LastDTIncluded")
    def _on_LastDTIncluded_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    @on_trait_change("DTs[]")
    def _on_DTs_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    @on_trait_change("DTRuler[]")
    def _on_DTRuler_changed(self, obj, name, old, new):
        self._DTs, self._DTRuler = None, None

    def _genIDs(self):
        IDDB = self.FDB[self.IDDB]
        if self.IDType == "A股":
            IDs = IDDB.getStockID(is_current=False)
        elif self.IDType == "债券":
            IDs = IDDB.getBondID(is_current=False)
        elif self.IDType == "公募基金":
            IDs = IDDB.getMutualFundID(is_current=False)
        elif self.IDType == "私募基金":
            IDs = IDDB.getPrivateFundID(is_current=False)
        return IDs

    def _setIDAttr(self):
        if self.IDType == "自定义":
            self._QS_setArgVisible("截面ID", visible=True)
            self._QS_setArgVisible("ID因子库", visible=False)
        else:
            self._QS_setArgVisible("截面ID", visible=False)
            self._QS_setArgVisible("ID因子库", visible=True)

    @on_trait_change("IDType")
    def _on_IDType_changed(self, obj, name, old, new):
        self._setIDAttr()
        self._IDs = None

    @on_trait_change("IDDB")
    def _on_IDDB_changed(self, obj, name, old, new):
        self._IDs = None

if __name__=="__main__":
    HDB = QS.FactorDB.HDF5DB().connect()
    Context = FactorDefContext(sys_args={})
    # Context["因子库"] = {"LDB": HDB}
    Context["因子库"]["LDB"] = HDB
    print(Context)