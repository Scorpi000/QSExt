# coding=utf-8
"""基于 QLib 的因子库"""
import os
import re
import stat
import shutil
import datetime as dt
from pathlib import Path
from functools import wraps
from typing import Optional, Self, Any, Dict, Literal, List, Union, Set

import numpy as np
import pandas as pd
import fasteners
import qlib
from qlib.data import D
from qlib.constant import REG_CN
from multiprocess import Lock
from pydantic import Field, DirectoryPath

from QuantStudio import __QS_ConfigPath__
from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.QSObject import Panel, QSFileLock
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorDB import WritableFactorDB
from QuantStudio.Factor.FactorTable import FactorTable
from QuantStudio.Tools.FileFun import listDirFile
from QuantStudio.Tools.DataTypeFun import readNestedDictFromHDF5, writeNestedDict2HDF5


def QLibInit(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._FactorDB._getLock(self._QSArgs.Name) as DataLock:
            qlib.init(provider_uri=self._FactorDB._QSArgs.MainDir / self._QSArgs.Name, region=self._QSArgs.Region)
            return method(self, *args, **kwargs)
    return wrapper

def _parseField(field:str) -> Set[str]:
    chinese_punctuation_regex = r"\u3001\uff1a\uff08\uff09"
    FieldList = []
    for pattern in [rf"\$\$([\w{chinese_punctuation_regex}]+)", rf"\$([\w{chinese_punctuation_regex}]+)", r"(\w+\s*)\("]:
        FieldList += re.findall(pattern, field)
        field = re.sub(pattern, "", field)
    return set(FieldList)

class QLibFactorTable(FactorTable):
    """QLibDB 库中因子表"""

    class __QS_ArgClass__(FactorTable.__QS_ArgClass__):
        Market: str = Field(default="all", title="证券范围", frozen=True)
        Region: str = Field(default=REG_CN, title="所在地区", frozen=True)
        Freq: str = Field(default="day", title="时间频率", frozen=True)
        Suffix: str = Field(default="bin", title="文件后缀", frozen=True)
        DiskCache: Optional[int] = Field(default=None, title="硬盘缓存", frozen=True, description="whether to skip(0)/use(1)/replace(2) disk_cache")

    def __init__(self, fdb: "QLibDB", args:dict={}, config_file:Optional[str]=None, **kwargs):
        return super().__init__(fdb=fdb, args=args, config_file=config_file, **kwargs)

    @property
    def FactorNames(self) -> List[str]:
        DataDir = self._FactorDB._QSArgs.MainDir / self.Name / self._FactorDB.FeaturesDirName
        for iDir in os.listdir(path=DataDir):
            iDir = os.path.join(DataDir, iDir)
            if os.path.isdir(iDir):
                Freq = "." + self._QSArgs.Freq
                SuffixLen = len(Freq)
                return sorted("$" + (iFactorName[:-SuffixLen] if iFactorName.endswith(Freq) else iFactorName) for iFactorName in listDirFile(str(iDir), suffix=self._QSArgs.Suffix))
        return []
    
    def getFactor(self, ifactor_name:str, args:dict={}) -> Factor:
        FieldSet = _parseField(ifactor_name)
        FactorNames = {iFactorName.replace("$", "") for iFactorName in self.FactorNames}
        if not FieldSet.issubset(FactorNames):
            raise __QS_Error__(f"因子表中不存在因子: {["$"+iField for iField in FieldSet.difference(FactorNames)]}")
        return Factor(ft=self, args={"CacheEnabled": False} | args | {"Name": ifactor_name}, logger=self._QS_Logger)

    def getMetaData(self, key:Optional[str]=None) -> Union[Any, pd.Series]:
        with self._FactorDB._getLock(self._QSArgs.Name) as DataLock:
            if not os.path.isfile(self._FactorDB._QSArgs.MainDir / self._QSArgs.Name / "_TableInfo.h5"):
                return (pd.Series() if key is None else None)
            if key is None:
                return pd.Series(readNestedDictFromHDF5(self._FactorDB._QSArgs.MainDir / self._QSArgs.Name / "_TableInfo.h5", "/"))
            else:
                return readNestedDictFromHDF5(self._FactorDB._QSArgs.MainDir / self._QSArgs.Name / "_TableInfo.h5", f"/{key}")

    def getFactorMetaData(self, factor_names:Optional[List[str]]=None, key:Optional[str]=None) -> Union[pd.DataFrame, pd.Series]:
        if factor_names is None: factor_names = self.FactorNames
        with self._FactorDB._getLock(self._QSArgs.Name) as DataLock:
            MetaData = {}
            for iFactorName in factor_names:
                if not os.path.isfile(self._FactorDB._QSArgs.MainDir / self._QSArgs.Name / "_FactorInfo.h5"):
                    MetaData[iFactorName] = (pd.Series() if key is None else None)
                if key is None:
                    MetaData[iFactorName] = pd.Series(readNestedDictFromHDF5(self._FactorDB._QSArgs.MainDir / self._QSArgs.Name / "_FactorInfo.h5", f"/{iFactorName}"))
                else:
                    MetaData[iFactorName] = readNestedDictFromHDF5(self._FactorDB._QSArgs.MainDir / self._QSArgs.Name / "_FactorInfo.h5", f"/{iFactorName}/{key}")
        if key is None: return pd.DataFrame(MetaData).T
        else: return pd.Series(MetaData)

    @QLibInit
    def getID(self, ifactor_name:Optional[str]=None, idt:Optional[dt.datetime]=None) -> List[str]:
        Instruments = D.instruments(market=self._QSArgs.Market)
        IDs = D.list_instruments(instruments=Instruments, start_time=idt, end_time=idt, as_list=True)
        if self._QSArgs.Region==REG_CN:
            return sorted(f"{iID[2:]}.{iID[:2]}" for iID in IDs)
        else:
            return sorted(IDs)

    @QLibInit
    def getDateTime(self, ifactor_name:Optional[str]=None, iid:Optional[str]=None, start_dt:Optional[dt.datetime]=None, end_dt:Optional[dt.datetime]=None) -> List[dt.datetime]:
        return sorted(D.calendar(start_time=start_dt, end_time=end_dt, freq=self._QSArgs.Freq, future=False))

    @QLibInit
    def __QS_calcData__(self, raw_data, factor_names, ids, dts):
        if self._QSArgs.Region == REG_CN:
            Instruments = ["".join(reversed(iID.split("."))) for iID in ids]
        else:
            Instruments = ids
        Fields = factor_names
        Data = D.features(Instruments, Fields, start_time=dts[0], end_time=dts[-1], freq=self._QSArgs.Freq, disk_cache=self._QSArgs.DiskCache)
        Data = Panel({iFactorName: Data[iFactorName].unstack().T.reindex(index=dts, columns=Instruments) for iFactorName in Data}, items=factor_names, major_axis=dts, minor_axis=Instruments)
        Data.minor_axis = ids
        return Data


class QLibDB(WritableFactorDB):
    """基于 QLib 的因子库"""

    class __QS_ArgClass__(WritableFactorDB.__QS_ArgClass__):
        Name: str = Field(default="QLibDB", title="名称", frozen=True)
        MainDir: DirectoryPath = Field(default=Path(os.path.expanduser("~/.qlib/qlib_data")), title="主目录", frozen=True, description="存放数据的主目录")
        LockDir: Optional[DirectoryPath] = Field(default=None, title="锁目录", frozen=True, description="存放锁文件的目录, 默认 None 表示和主目录相同")
        ProcessLock: bool = Field(default=True, title="进程锁", frozen=True, description="是否添加进程锁用于防止多进程间读写冲突")
        Suffix: str = Field(default="bin", title="文件后缀", frozen=True)
        CalendarsDirName: str = Field(default="calendars", title="时点目录", frozen=True)
        FeaturesDirName: str = Field(default="features", title="特征目录", frozen=True)
        InstrumentsDirName: str = Field(default="instruments", title="证券目录", frozen=True)
        DailyFormt: str = Field(default="%Y-%m-%d", title="日期格式", frozen=True)
        HighFreqFormat: str = Field(default="%Y-%m-%d %H:%M:%S", title="高频时间格式", frozen=True)
        InstrumentsSep: str = Field(default="\t", title="证券分隔符", frozen=True)
        InstrumentsFileName: str = Field(default="all.txt", title="证券文件", frozen=True)

    def __init__(self, args:dict={}, config_file:Optional[str]=None, **kwargs):
        """初始化 QLibDB

        Args:
            args: 指定的对象参数集
            config_file: 配置文件路径, 默认配置文件为 "~/QuantStudioConfig/QLibDBConfig.json"
        """
        self._LockFile = None  # 文件锁的目标文件
        self._DataLock = None  # 访问该因子库资源的文件锁, 防止并发访问冲突
        self._TableLock = None  # 访问该因子表资源的临时文件锁, 防止并发访问冲突
        self._ProcLock = None  # 访问该因子库资源的进程锁, 防止并发访问冲突
        return super().__init__(args=args, config_file=(__QS_ConfigPath__ + os.sep + "QLibDBConfig.json" if config_file is None else config_file), **kwargs)

    def __getstate__(self):
        state = self.__dict__.copy()
        # Remove the unpicklable entries.
        state["_DataLock"] = (True if self._DataLock is not None else False)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        if self._DataLock:
            self._DataLock = fasteners.InterProcessLock(self._LockFile)
        else:
            self._DataLock = None

    def _getLock(self, table_name=None):
        if table_name is None:
            return QSFileLock(self._DataLock, proc_lock=self._ProcLock)
        TablePath = self._QSArgs.MainDir / table_name
        if not os.path.isdir(TablePath):
            Msg = ("因子库 '%s' 调用 _getLock 时错误, 不存在因子表: '%s'" % (self.Name, table_name))
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        LockFile = self._LockDir / table_name / "LockFile"
        if not os.path.isfile(LockFile):
            with QSFileLock(self._DataLock, proc_lock=self._ProcLock) as FileLock:
                if not os.path.isdir(self._LockDir / table_name):
                    os.mkdir(self._LockDir / table_name)
                if not os.path.isfile(LockFile):
                    open(LockFile, mode="a").close()
                    os.chmod(LockFile, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)
        return QSFileLock(LockFile, self._ProcLock)

    def connect(self) -> Self:
        if not os.path.isdir(self._QSArgs.MainDir):
            raise __QS_Error__("QLibDB.connect: 不存在主目录 '%s'!" % self._QSArgs.MainDir)
        if not self._QSArgs.LockDir:
            self._LockDir = self._QSArgs.MainDir
        elif not os.path.isdir(self._QSArgs.LockDir):
            raise __QS_Error__("QLibDB.connect: 不存在锁目录 '%s'!" % self._QSArgs.LockDir)
        else:
            self._LockDir = self._QSArgs.LockDir
        self._LockFile = self._LockDir / "LockFile"
        if not os.path.isfile(self._LockFile):
            open(self._LockFile, mode="a").close()
            os.chmod(self._LockFile, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)
        self._DataLock = fasteners.InterProcessLock(self._LockFile)
        if self._QSArgs.ProcessLock: self._ProcLock = Lock()
        return self

    def disconnect(self):
        self._LockFile = None
        self._DataLock = None
        self._ProcLock = None

    @property
    def TableNames(self) -> List[str]:
        TableList = []
        for iDir in os.listdir(self._QSArgs.MainDir):
            iTablePath = self._QSArgs.MainDir / iDir
            if os.path.isdir(iTablePath) and os.path.isdir(iTablePath / self._QSArgs.FeaturesDirName) and os.path.isdir(iTablePath / self._QSArgs.CalendarsDirName) and os.path.isdir(iTablePath / self._QSArgs.InstrumentsDirName):
                TableList.append(iDir)
        return sorted(TableList)

    def _getTableFreq(self, table_name: str, suffix: str) -> str:
        for iDir in os.listdir(self._QSArgs.MainDir / table_name / self._QSArgs.FeaturesDirName):
            iPath = self._QSArgs.MainDir / table_name / self._QSArgs.FeaturesDirName / iDir
            if os.path.isdir(iPath):
                for iFile in os.listdir(iPath):
                    if iFile.endswith(f".{suffix}"):
                        Freq = iFile.split(".")[-2]
                        return Freq
        return None
    
    def getTable(self, table_name:str, args:dict={}) -> QLibFactorTable:
        iTablePath = self._QSArgs.MainDir / table_name
        if (not os.path.isdir(iTablePath)) or (not os.path.isdir(iTablePath / self._QSArgs.FeaturesDirName)) or (not os.path.isdir(iTablePath / self._QSArgs.CalendarsDirName)) or (not os.path.isdir(iTablePath / self._QSArgs.InstrumentsDirName)):
            raise __QS_Error__("QLibDB.getTable: 表 '%s' 不存在!" % table_name)
        Suffix = args.get("Suffix", self._QSArgs.Suffix)
        if "Freq" in args:
            return QLibFactorTable(fdb=self, args={"Suffix": Suffix} | args | {"Name": table_name}, logger=self._QS_Logger)
        else:
            Freq = self._getTableFreq(table_name=table_name, suffix=Suffix)
            if Freq is None: raise __QS_Error__("QLibDB.getTable: 无法判断表 '%s' 的时间频率" % table_name)
            return QLibFactorTable(fdb=self, args={"Suffix": Suffix} | args | {"Name": table_name, "Freq": Freq}, logger=self._QS_Logger)

    def renameTable(self, old_table_name:str, new_table_name:str):
        if old_table_name == new_table_name: return 0
        OldPath = self._QSArgs.MainDir / old_table_name
        NewPath = self._QSArgs.MainDir / new_table_name
        with self._DataLock:
            if not os.path.isdir(OldPath): raise __QS_Error__("QLibDB.renameTable: 表: '%s' 不存在!" % old_table_name)
            if os.path.isdir(NewPath): raise __QS_Error__("QLibDB.renameTable: 表 '" + new_table_name + "' 已存在!")
            os.rename(OldPath, NewPath)
        return 0

    def deleteTable(self, table_name:str):
        TablePath = self._QSArgs.MainDir / table_name
        with self._DataLock:
            if os.path.isdir(TablePath):
                shutil.rmtree(TablePath, ignore_errors=True)
        return 0

    def setTableMetaData(self, table_name:str, key:Optional[str]=None, value:Any=None, meta_data:Optional[dict]=None):
        if meta_data is not None:
            meta_data = dict(meta_data)
        else:
            meta_data = {}
        if key is not None:
            meta_data[key] = value
        with self._DataLock:
            writeNestedDict2HDF5(meta_data, self._QSArgs.MainDir / table_name / "_TableInfo.h5", "/")
        return 0

    def renameFactor(self, table_name:str, old_factor_name:str, new_factor_name:str):
        if old_factor_name == new_factor_name: return
        old_factor_name = old_factor_name.replace("$", "")
        new_factor_name = new_factor_name.replace("$", "")
        TablePath = self._QSArgs.MainDir / table_name / self._QSArgs.FeaturesDirName
        with self._DataLock:
            for iDir in os.listdir(path=TablePath):
                if not os.path.isdir(TablePath / iDir): continue
                for iFile in os.listdir(path=TablePath / iDir):
                    if iFile.startswith(f"{old_factor_name}.") and (not os.path.isdir(TablePath / iDir / iFile)):
                        os.rename(TablePath / iDir / iFile, TablePath / iDir / iFile.replace(old_factor_name, new_factor_name))

    def deleteFactor(self, table_name:str, factor_names:List[str]):
        TablePath = self._QSArgs.MainDir / table_name / self._QSArgs.FeaturesDirName
        with self._DataLock:
            for jFactorName in factor_names:
                jFactorName = jFactorName.replace("$", "")
                for iDir in os.listdir(path=TablePath):
                    if not os.path.isdir(TablePath / iDir): continue
                    for iFile in os.listdir(path=TablePath / iDir):
                        if iFile.startswith(f"{jFactorName}.") and (not os.path.isdir(TablePath / iDir / iFile)):
                            os.remove(TablePath / iDir / iFile)
                            break

    def setFactorMetaData(self, table_name:str, ifactor_name:str, key:Optional[str]=None, value:Any=None, meta_data:Optional[dict]=None):
        if meta_data is not None:
            meta_data = dict(meta_data)
        else:
            meta_data = {}
        if key is not None:
            meta_data[key] = value
        with self._DataLock:
            writeNestedDict2HDF5(meta_data, self._QSArgs.MainDir / table_name / "_FactorInfo.h5", f"/{ifactor_name}")
        return 0

    # TODO
    def writeData(self, data:Panel, table_name:str, if_exists:Literal["update", "replace", "append"]="update", data_type:Dict[str, Literal["double", "string", "object"]]={}, **kwargs):
        raise NotImplementedError
