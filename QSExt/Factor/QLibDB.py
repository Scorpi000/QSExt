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
        DataDir = self._FactorDB._QSArgs.MainDir / self.Name / "features"
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
        return Factor(ft=self, args=args | {"Name": ifactor_name}, logger=self._QS_Logger)

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
        MainDir: DirectoryPath = Field(default=Path("~/.qlib/qlib_data"), title="主目录", frozen=True, description="存放数据的主目录")
        LockDir: Optional[DirectoryPath] = Field(default=None, title="锁目录", frozen=True, description="存放锁文件的目录, 默认 None 表示和主目录相同")
        ProcessLock: bool = Field(default=True, title="进程锁", frozen=True, description="是否添加进程锁用于防止多进程间读写冲突")

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
        MainDir = self._QSArgs.MainDir
        return sorted(iDir for iDir in os.listdir(MainDir) if os.path.isdir(MainDir / iDir))

    def getTable(self, table_name:str, args:dict={}) -> QLibFactorTable:
        if not os.path.isdir(self._QSArgs.MainDir / table_name):
            raise __QS_Error__("QLibDB.getTable: 表 '%s' 不存在!" % table_name)
        return QLibFactorTable(fdb=self, args=args | {"Name": table_name}, logger=self._QS_Logger)

    def renameTable(self, old_table_name:str, new_table_name:str):
        if old_table_name == new_table_name: return 0
        OldPath = self._QSArgs.MainDir / old_table_name
        NewPath = self._QSArgs.MainDir / new_table_name
        with self._DataLock:
            if not os.path.isdir(OldPath): raise __QS_Error__("HDF5DB.renameTable: 表: '%s' 不存在!" % old_table_name)
            if os.path.isdir(NewPath): raise __QS_Error__("HDF5DB.renameTable: 表 '" + new_table_name + "' 已存在!")
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
        if old_factor_name == new_factor_name: return 0
        OldPath = self._QSArgs.MainDir / table_name / (old_factor_name + "." + self._Suffix)
        NewPath = self._QSArgs.MainDir / table_name / (new_factor_name + "." + self._Suffix)
        with self._DataLock:
            if not os.path.isfile(OldPath): raise __QS_Error__("HDF5DB.renameFactor: 表 '%s' 中不存在因子 '%s'!" % (table_name, old_factor_name))
            if os.path.isfile(NewPath): raise __QS_Error__("HDF5DB.renameFactor: 表 '%s' 中的因子 '%s' 已存在!" % (table_name, new_factor_name))
            os.rename(OldPath, NewPath)
        return 0

    def deleteFactor(self, table_name:str, factor_names:List[str]):
        TablePath = self._QSArgs.MainDir / table_name
        FactorNames = set(listDirFile(str(TablePath), suffix=self._Suffix))
        with self._DataLock:
            if FactorNames.issubset(set(factor_names)):
                shutil.rmtree(TablePath, ignore_errors=True)
            else:
                for iFactor in factor_names:
                    iFilePath = TablePath / (iFactor + "." + self._Suffix)
                    if os.path.isfile(iFilePath):
                        os.remove(iFilePath)
        return 0

    def setFactorMetaData(self, table_name:str, ifactor_name:str, key:Optional[str]=None, value:Any=None, meta_data:Optional[dict]=None):
        with self._getLock(table_name=table_name) as DataLock:
            with self._openHDF5File(self._QSArgs.MainDir / table_name / (ifactor_name + "." + self._Suffix), mode="a") as File:
                if key is not None:
                    if key in File.attrs:
                        del File.attrs[key]
                    if (isinstance(value, np.ndarray)) and (value.dtype == np.dtype("O")):
                        File.attrs.create(key, data=value, dtype=h5py.special_dtype(vlen=str))
                    elif value is not None:
                        File.attrs[key] = value
        if meta_data is not None:
            for iKey in meta_data.keys():
                self.setFactorMetaData(table_name, ifactor_name=ifactor_name, key=iKey, value=meta_data[iKey], meta_data=None)
        return 0

    def _updateFactorData(self, factor_data, table_name, ifactor_name, data_type):
        FilePath = self._QSArgs.MainDir / table_name / (ifactor_name + "." + self._Suffix)
        with self._getLock(table_name=table_name) as DataLock:
            with self._openHDF5File(FilePath, mode="a") as DataFile:
                OldDataType = DataFile.attrs["DataType"]
                if data_type is None: data_type = OldDataType
                factor_data, data_type = _identifyDataType(factor_data, data_type)
                if OldDataType != data_type:
                    raise __QS_Error__("HDF5DB.writeFactorData: 表 '%s' 中因子 '%s' 的新数据无法转换成已有数据的数据类型 '%s'!" % (table_name, ifactor_name, OldDataType))
                nOldDT, OldDateTimes = DataFile["DateTime"].shape[0], DataFile["DateTime"][...]
                NewDateTimes = factor_data.index.difference(OldDateTimes).values
                if h5py.version.version < "3.0.0":
                    OldIDs = DataFile["ID"][...]
                else:
                    OldIDs = DataFile["ID"].asstr(encoding="utf-8")[...]
                NewIDs = factor_data.columns.difference(OldIDs).values
                DataFile["DateTime"].resize((nOldDT + NewDateTimes.shape[0],))
                DataFile["DateTime"][nOldDT:] = NewDateTimes
                DataFile["ID"].resize((OldIDs.shape[0] + NewIDs.shape[0],))
                DataFile["ID"][OldIDs.shape[0]:] = NewIDs
                DataFile["Data"].resize((DataFile["DateTime"].shape[0], DataFile["ID"].shape[0]))
                if NewDateTimes.shape[0] > 0:
                    DataFile["Data"][nOldDT:, :] = _adjustData(factor_data.reindex(index=NewDateTimes, columns=np.r_[OldIDs, NewIDs]), data_type)
                CrossedDateTimes = factor_data.index.intersection(OldDateTimes).values
                if CrossedDateTimes.shape[0] == 0:
                    DataFile.flush()
                    return 0
                if len(CrossedDateTimes) == len(OldDateTimes):
                    if NewIDs.shape[0] > 0:
                        DataFile["Data"][:nOldDT, OldIDs.shape[0]:] = _adjustData(factor_data.reindex(index=OldDateTimes, columns=NewIDs), data_type)
                    CrossedIDs = factor_data.columns.intersection(OldIDs)
                    if CrossedIDs.shape[0] > 0:
                        OldIDs = OldIDs.tolist()
                        CrossedIDPos = [OldIDs.index(iID) for iID in CrossedIDs]
                        CrossedIDs = CrossedIDs[np.argsort(CrossedIDPos)]
                        CrossedIDPos.sort()
                        DataFile["Data"][:nOldDT, CrossedIDPos] = _adjustData(factor_data.reindex(index=OldDateTimes, columns=CrossedIDs), data_type)
                    DataFile.flush()
                    return 0
                Sorter = np.argsort(OldDateTimes)
                CrossedDateTimePos = Sorter[np.searchsorted(OldDateTimes, CrossedDateTimes, sorter=Sorter)]
                CrossedDateTimes = CrossedDateTimes[np.argsort(CrossedDateTimePos)]
                CrossedDateTimePos.sort()
                if NewIDs.shape[0] > 0:
                    DataFile["Data"][CrossedDateTimePos, OldIDs.shape[0]:] = _adjustData(factor_data.reindex(index=CrossedDateTimes, columns=NewIDs), data_type)
                CrossedIDs = factor_data.columns.intersection(OldIDs).values
                if CrossedIDs.shape[0] > 0:
                    Sorter = np.argsort(OldIDs)
                    CrossedIDPos = Sorter[np.searchsorted(OldIDs, CrossedIDs, sorter=Sorter)]
                    CrossedIDs = CrossedIDs[np.argsort(CrossedIDPos)]
                    CrossedIDPos.sort()
                    NewData = _adjustData(factor_data.reindex(index=CrossedDateTimes, columns=CrossedIDs), data_type, order="F")
                    CrossedIDSep = np.arange(CrossedIDPos.shape[0])[np.r_[True, np.diff(CrossedIDPos) > 1]]
                    for i, iSep in enumerate(CrossedIDSep):
                        if i < CrossedIDSep.shape[0] - 1:
                            iCrossedStartIdx, iCrossedEndIdx = iSep, CrossedIDSep[i + 1]
                            iStartIdx, iEndIdx = CrossedIDPos[iSep], CrossedIDPos[CrossedIDSep[i + 1] - 1] + 1
                        else:
                            iCrossedStartIdx, iCrossedEndIdx = iSep, CrossedIDPos.shape[0]
                            iStartIdx, iEndIdx = CrossedIDPos[iSep], CrossedIDPos[-1] + 1
                        if data_type == "object":
                            DataFile["Data"][CrossedDateTimePos, iStartIdx:iEndIdx] = np.ascontiguousarray(NewData[:, iCrossedStartIdx:iCrossedEndIdx])
                        else:
                            DataFile["Data"][CrossedDateTimePos, iStartIdx:iEndIdx] = NewData[:, iCrossedStartIdx:iCrossedEndIdx]
                DataFile.flush()
        return 0

    def writeFactorData(self, factor_data:pd.DataFrame, table_name:str, ifactor_name:str, if_exists:Literal["update", "replace", "append"]="update", data_type:Optional[Literal["double", "string", "object"]]=None, **kwargs):
        DTs = factor_data.index
        if pd.__version__ >= "0.20.0":
            factor_data.index = [idt.to_pydatetime().timestamp() for idt in factor_data.index]
        else:
            factor_data.index = [idt.timestamp() for idt in factor_data.index]
        TablePath = self._QSArgs.MainDir / table_name
        FilePath = TablePath / (ifactor_name + "." + self._Suffix)
        if not os.path.isdir(TablePath):
            with self._DataLock:
                if not os.path.isdir(TablePath): os.mkdir(TablePath)
        with self._getLock(table_name=table_name) as DataLock:
            if not os.path.isfile(FilePath):
                factor_data, data_type = _identifyDataType(factor_data, data_type)
                NewData = _adjustData(factor_data, data_type)
                open(FilePath, mode="a").close()# h5py 直接创建文件名包含中文的文件会报错.
                # StrDataType = h5py.special_dtype(vlen=str)
                StrDataType = h5py.string_dtype(encoding="utf-8")
                with self._openHDF5File(FilePath, mode="a") as DataFile:
                    DataFile.attrs["DataType"] = data_type
                    DataFile.create_dataset("ID", shape=(factor_data.shape[1],), maxshape=(None,), dtype=StrDataType, data=factor_data.columns)
                    DataFile.create_dataset("DateTime", shape=(factor_data.shape[0],), maxshape=(None,), data=factor_data.index)
                    if data_type == "double":
                        DataFile.create_dataset("Data", shape=factor_data.shape, maxshape=(None, None), dtype=float, fillvalue=np.nan, data=NewData)
                    elif data_type == "string":
                        DataFile.create_dataset("Data", shape=factor_data.shape, maxshape=(None, None), dtype=StrDataType, fillvalue=None, data=NewData)
                    elif data_type == "object":
                        DataFile.create_dataset("Data", shape=factor_data.shape, maxshape=(None, None), dtype=h5py.vlen_dtype(np.uint8), data=NewData)
                    DataFile.flush()
                factor_data.index = DTs
                return 0
        if if_exists == "update":
            self._updateFactorData(factor_data, table_name, ifactor_name, data_type)
        else:
            OldData = self.getTable(table_name).readFactorData(ifactor_name=ifactor_name, ids=factor_data.columns.tolist(), dts=DTs.tolist())
            OldData.index = factor_data.index
            if if_exists == "append":
                factor_data = OldData.where(pd.notnull(OldData), factor_data)
            elif if_exists == "update_notnull":
                factor_data = factor_data.where(pd.notnull(factor_data), OldData)
            else:
                Msg = ("因子库 '%s' 调用方法 writeData 错误: 不支持的写入方式 '%s'!" % (self.Name, str(if_exists)))
                self._QS_Logger.error(Msg)
                raise __QS_Error__(Msg)
            self._updateFactorData(factor_data, table_name, ifactor_name, data_type)
        factor_data.index = DTs
        return 0

    def writeData(self, data:Panel, table_name:str, if_exists:Literal["update", "replace", "append"]="update", data_type:Dict[str, Literal["double", "string", "object"]]={}, **kwargs):
        for i, iFactor in enumerate(data.items):
            self.writeFactorData(data.iloc[i], table_name, iFactor, if_exists=if_exists, data_type=data_type.get(iFactor, None), **kwargs)
        return 0

    def optimizeData(self, table_name, factor_names):
        for iFactorName in factor_names:
            iFilePath = self._QSArgs.MainDir / table_name / (iFactorName + "." + self._Suffix)
            with self._DataLock:
                with self._openHDF5File(iFilePath, mode="a") as DataFile:
                    DTs = DataFile["DateTime"][...]
                    if np.any(np.diff(DTs) < 0):
                        iData = pd.DataFrame(DataFile["Data"][...], index=DTs).sort_index()
                        DataFile["Data"][:, :] = iData.values
                        DataFile["DateTime"][:] = iData.index.values
                        self._QS_Logger.info("因子 '%s' : ’%s' 数据存储完成优化!" % (table_name, iFactorName))
                    else:
                        self._QS_Logger.info("因子 '%s' : ’%s' 数据存储不需要优化!" % (table_name, iFactorName))
        return 0

    def fixData(self, table_name, factor_names):
        for iFactorName in factor_names:
            iFilePath = self._QSArgs.MainDir / table_name / (iFactorName + "." + self._Suffix)
            FixMask = np.full(shape=(4,), fill_value=True, dtype=bool)
            with self._DataLock:
                with self._openHDF5File(iFilePath, mode="a") as DataFile:
                    # 修复 ID 长度和数据长度不符
                    if DataFile["ID"].shape[0] > DataFile["Data"].shape[1]:
                        DataFile["ID"].resize((DataFile["Data"].shape[1],))
                    elif DataFile["ID"].shape[0] < DataFile["Data"].shape[1]:
                        DataFile["Data"].resize((DataFile["Data"].shape[0], DataFile["ID"].shape[0]))
                    else:
                        FixMask[0] = False
                    # 修复 DT 长度和数据长度不符
                    if DataFile["DateTime"].shape[0] > DataFile["Data"].shape[0]:
                        DataFile["DateTime"].resize((DataFile["Data"].shape[0],))
                    elif DataFile["DateTime"].shape[0] < DataFile["Data"].shape[0]:
                        DataFile["Data"].resize((DataFile["DateTime"].shape[0], DataFile["Data"].shape[1]))
                    else:
                        FixMask[1] = False
                    # 修复 ID 重复值
                    if h5py.version.version < "3.0.0":
                        IDs = pd.Series(np.arange(DataFile["ID"].shape[0]), index=DataFile["ID"][...])
                    else:
                        IDs = pd.Series(np.arange(DataFile["ID"].shape[0]), index=DataFile["ID"].asstr(encoding="utf-8")[...])
                    DuplicatedMask = IDs.index.duplicated()
                    if np.any(DuplicatedMask):
                        iData = DataFile["Data"][...]
                        for jID in set(IDs.index[DuplicatedMask]):
                            jIdx = IDs[jID].tolist()
                            iData[:, jIdx[0]] = pd.DataFrame(iData[:, jIdx].T).fillna(method="bfill").values[0, :]  # TODO: h5py.version.version>=3.0.0 and data_type=string
                        nID = DuplicatedMask.shape[0] - np.sum(DuplicatedMask)
                        DataFile["ID"].resize((nID,))
                        DataFile["ID"][:] = IDs.index.values[~DuplicatedMask]
                        DataFile["Data"].resize((DataFile["Data"].shape[0], nID))
                        DataFile["Data"][:, :] = iData[:, ~DuplicatedMask]
                    else:
                        FixMask[2] = False
                    # 修复 DT 重复值
                    DTs = pd.Series(np.arange(DataFile["DateTime"].shape[0]), index=DataFile["DateTime"][...])
                    DuplicatedMask = DTs.index.duplicated()
                    if np.any(DuplicatedMask):
                        iData = DataFile["Data"][...]
                        for jDT in set(DTs.index[DuplicatedMask]):
                            jIdx = DTs[jDT].tolist()
                            iData[jIdx[0], :] = pd.DataFrame(iData[jIdx, :]).fillna(method="bfill").values[0, :]  # TODO: h5py.version.version>=3.0.0 and data_type=string
                        nDT = DuplicatedMask.shape[0] - np.sum(DuplicatedMask)
                        DataFile["DateTime"].resize((nDT,))
                        DataFile["DateTime"][:] = DTs.index.values[~DuplicatedMask]
                        DataFile["Data"].resize((nDT, DataFile["Data"].shape[1]))
                        DataFile["Data"][:, :] = iData[~DuplicatedMask, :]
                    else:
                        FixMask[3] = False
                    if np.any(FixMask):
                        self._QS_Logger.info("因子 '%s' : '%s' 数据修复完成!" % (table_name, iFactorName))
        return 0
