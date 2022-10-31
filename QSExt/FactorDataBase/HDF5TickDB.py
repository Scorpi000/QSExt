# coding=utf-8
"""基于 HDF5 文件的 Tick 因子库"""
import os
import stat
import shutil
import pickle
import time
import datetime as dt

import numpy as np
import pandas as pd
import fasteners
import h5py
from traits.api import Directory, Float, Str

from QuantStudio import __QS_Error__, __QS_ConfigPath__
from QuantStudio.Tools.api import Panel
from QuantStudio.FactorDataBase.FactorDB import WritableFactorDB, FactorTable
from QuantStudio.Tools.FileFun import listDirDir
from QuantStudio.Tools.DataTypeFun import readNestedDictFromHDF5, writeNestedDict2HDF5

def _identifyDataType(id_data, data_type=None):
    if data_type is None: data_type = {}
    for iFactorName in id_data.columns:
        iDataType = data_type.get(iFactorName, None)
        if (iDataType is None) or (iDataType=="double"):
            try:
                id_data[iFactorName] = id_data[iFactorName].astype(float)
            except:
                iDataType = "object"
            else:
                iDataType = "double"
        elif iDataType in ("string", "object"):
            id_data[iFactorName] = id_data[iFactorName].where(pd.notnull(id_data[iFactorName]), None)
        else:
            raise __QS_Error__(f"不支持的因子数据类型: {iDataType}")
        data_type[iFactorName] = iDataType
    return (id_data, data_type)

class _FactorTable(FactorTable):
    """HDF5TickDB 因子表"""
    def __init__(self, name, fdb, sys_args={}, **kwargs):
        self._Suffix = fdb._Suffix# 文件后缀名
        return super().__init__(name=name, fdb=fdb, sys_args=sys_args, **kwargs)
    @property
    def FactorNames(self):
        TablePath = self._FactorDB.MainDir+os.sep+self._Name
        with self._FactorDB._getLock(self._Name) as DataLock:
            if not os.path.isfile(TablePath+os.sep+"_TableInfo.h5"):
                Files = os.listdir(TablePath)
                if not Files: return []
                with h5py.File(Files[0], mode="r") as iFile:
                    return sorted(iFile.attrs.get("DataType", {}))
            else:
                with h5py.File(TablePath+os.sep+"_TableInfo.h5", mode="r") as iFile:
                    return sorted(iFile.attrs.get("FactorNames", []))
    def getMetaData(self, key=None, args={}):
        with self._FactorDB._getLock(self._Name) as DataLock:
            if not os.path.isfile(self._FactorDB.MainDir+os.sep+self.Name+os.sep+"_TableInfo.h5"): return (pd.Series() if key is None else None)
            return pd.Series(readNestedDictFromHDF5(self._FactorDB.MainDir+os.sep+self.Name+os.sep+"_TableInfo.h5", "/"+("" if key is None else key)))
    def getFactorMetaData(self, factor_names=None, key=None, args={}):
        AllFactorNames = self.FactorNames
        if factor_names is None: factor_names = AllFactorNames
        elif set(factor_names).isdisjoint(AllFactorNames): return super().getFactorMetaData(factor_names=factor_names, key=key, args=args)
        with self._FactorDB._getLock(self._Name) as DataLock:
            MetaData = {}
            for iFactorName in factor_names:
                if iFactorName in AllFactorNames:
                    with self._FactorDB._openHDF5File(self._FactorDB.MainDir+os.sep+self.Name+os.sep+iFactorName+"."+self._Suffix, mode="r") as File:
                        if key is None: MetaData[iFactorName] = pd.Series(dict(File.attrs))
                        elif key in File.attrs: MetaData[iFactorName] = File.attrs[key]
        if not MetaData: return super().getFactorMetaData(factor_names=factor_names, key=key, args=args)
        if key is None: return pd.DataFrame(MetaData).T.loc[factor_names]
        else: return pd.Series(MetaData).loc[factor_names]
    def getID(self, ifactor_name=None, idt=None, args={}):
        return sorted(".".join(iFile.split(".")[:-1]) for iFile in os.listdir(self._FactorDB.MainDir+os.sep+self._Name) if iFile!="_TableInfo.h5")
    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None, args={}):# TODO
        return []
    def __QS_calcData__(self, raw_data, factor_names, ids, dts, args={}):
        Data = {iID: self.readIDData(iid=iID, factor_names=factor_names, start_dt=dts[0], end_dt=dts[-1], args=args).reindex(dts) for iID in ids}
        return Panel(Data, items=ids, major_axis=dts, minor_axis=factor_names).swapaxes(0, 2)
    def readIDData(self, iid, factor_names, start_dt, end_dt, args={}):
        FilePath = self._FactorDB.MainDir+os.sep+self.Name+os.sep+iid+"."+self._Suffix
        if not os.path.isfile(FilePath): raise __QS_Error__("因子库 '%s' 的因子表 '%s' 中不存在ID '%s'!" % (self._FactorDB.Name, self.Name, iid))
        StartTS = int(dt.datetime.combine(start_dt.date(), dt.time(0)).timestamp())
        EndTS = int((dt.datetime.combine(end_dt.date(), dt.time(0))).timestamp())
        Rslt = {iFactorName: np.array([]) for iFactorName in factor_names}
        with self._FactorDB._getLock(self._Name) as DataLock:
            with self._FactorDB._openHDF5File(FilePath, mode="r") as DataFile:
                DataType = pickle.loads(bytes(DataFile.attrs["DataType"]))
                for iTS in range(StartTS, EndTS+86400, 86400):
                    iDate = dt.datetime.fromtimestamp(iTS).strftime("%Y%m%d")
                    if iDate in DataFile:
                        iGroup = DataFile[iDate]
                        iDTs = iGroup["DateTime"][:]
                        Rslt["DateTime"] = np.r_[Rslt.get("DateTime", np.array([])), iDTs]
                        for jFactorName in factor_names:
                            if jFactorName in iGroup:
                                Rslt[jFactorName] = np.r_[Rslt[jFactorName], iGroup[jFactorName][:]]
                            elif DataType[jFactorName]=="double":
                                Rslt[jFactorName] = np.r_[Rslt[jFactorName], np.full(shape=iDTs.shape, fill_value=np.nan)]
                            else:
                                Rslt[jFactorName] = np.r_[Rslt[jFactorName], np.full(shape=iDTs.shape, fill_value=None)]
        Rslt = pd.DataFrame(Rslt).set_index(["DateTime"]).loc[:, factor_names]
        Rslt.index = [dt.datetime.fromtimestamp(iTS) for iTS in Rslt.index]
        Rslt = Rslt.loc[start_dt:end_dt]
        for jFactorName in factor_names:
            if DataType[jFactorName]=="string":
                Rslt[jFactorName] = Rslt[jFactorName].where(pd.notnull(Rslt[jFactorName]), None)
                Rslt[jFactorName] = Rslt[jFactorName].where(Rslt[jFactorName]!="", None)
            elif DataType=="object":
                Rslt[jFactorName] = Rslt[jFactorName].applymap(lambda x: pickle.loads(bytes(x)) if isinstance(x, np.ndarray) and (x.shape[0]>0) else None)
        return Rslt

# 基于 HDF5 文件的 Tick 因子数据库
# 每一张表是一个文件夹, 每个 ID 是一个 HDF5 文件
# 每个 HDF5 文件下每个 Date 是一个 Group, 每个 Group 有若干个 Dataset: DateTime, Factor1, Factor2, ....
# 表的元数据存储在表文件夹下特殊文件: _TableInfo.h5 中
# 因子的元数据存储在 HDF5 文件的 attrs 中
class HDF5TickDB(WritableFactorDB):
    """HDF5TickDB"""
    Name = Str("HDF5TickDB", arg_type="String", label="名称", order=-100)
    MainDir = Directory(label="主目录", arg_type="Directory", order=0)
    LockDir = Directory(label="锁目录", arg_type="Directory", order=1)
    FileOpenRetryNum = Float(np.inf, label="文件打开重试次数", arg_type="Float", order=2)
    def __init__(self, sys_args={}, config_file=None, **kwargs):
        self._LockFile = None# 文件锁的目标文件
        self._DataLock = None# 访问该因子库资源的锁, 防止并发访问冲突
        self._isAvailable = False
        self._Suffix = "hdf5"# 文件的后缀名
        super().__init__(sys_args=sys_args, config_file=(__QS_ConfigPath__+os.sep+"HDF5TickDBConfig.json" if config_file is None else config_file), **kwargs)
        return
    def __getstate__(self):
        state = self.__dict__.copy()
        # Remove the unpicklable entries.
        state["_DataLock"] = (True if self._DataLock is not None else False)
        return state
    def __setstate__(self, state):
        super().__setstate__(state)
        if self._DataLock:
            self._DataLock = fasteners.InterProcessLock(self._LockFile)
        else:
            self._DataLock = None
    def connect(self):
        if not os.path.isdir(self.MainDir):
            raise __QS_Error__("HDF5TickDB.connect: 不存在主目录 '%s'!" % self.MainDir)
        if not self.LockDir:
            self._LockDir = self.MainDir
        elif not os.path.isdir(self.LockDir):
            raise __QS_Error__("HDF5TickDB.connect: 不存在锁目录 '%s'!" % self.LockDir)
        else:
            self._LockDir = self.LockDir
        self._LockFile = self._LockDir+os.sep+"LockFile"
        if not os.path.isfile(self._LockFile):
            open(self._LockFile, mode="a").close()
            os.chmod(self._LockFile, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)
        self._DataLock = fasteners.InterProcessLock(self._LockFile)
        self._isAvailable = True
        return self
    def disconnect(self):
        self._LockFile = None
        self._DataLock = None
        self._isAvailable = False
    def isAvailable(self):
        return self._isAvailable
    def _getLock(self, table_name=None):
        if table_name is None:
            return self._DataLock
        TablePath = self.MainDir + os.sep + table_name
        if not os.path.isdir(TablePath):
            Msg = ("因子库 '%s' 调用 _getLock 时错误, 不存在因子表: '%s'" % (self.Name, table_name))
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        LockFile = self._LockDir + os.sep + table_name + os.sep + "LockFile"
        if not os.path.isfile(LockFile):
            with self._DataLock:
                if not os.path.isdir(self._LockDir + os.sep + table_name):
                    os.mkdir(self._LockDir + os.sep + table_name)
                if not os.path.isfile(LockFile):
                    open(LockFile, mode="a").close()
                    os.chmod(LockFile, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)
        return fasteners.InterProcessLock(LockFile)
    def _openHDF5File(self, filename, *args, **kwargs):
        i = 0
        while i<self.FileOpenRetryNum:
            try:
                f = h5py.File(filename, *args, **kwargs)
            except OSError as e:
                i += 1
                SleepTime = 0.05 + (i % 100) / 100.0
                if i % 100 == 0:
                    self._QS_Logger.warning("Can't open hdf5 file: '%s'\n %s \n try again %s seconds later!" % (filename, str(e), SleepTime))
                time.sleep(SleepTime)
            else:
                return f
        Msg = "Can't open hdf5 file: '%s' after trying %d times" % (filename, i)
        self._QS_Logger.error(Msg)
        raise __QS_Error__(Msg)
    # -------------------------------表的操作---------------------------------
    @property
    def TableNames(self):
        return sorted(listDirDir(self.MainDir))
    def getTable(self, table_name, args={}):
        if not os.path.isdir(self.MainDir+os.sep+table_name): raise __QS_Error__("HDF5TickDB.getTable: 表 '%s' 不存在!" % table_name)
        return _FactorTable(name=table_name, fdb=self, sys_args=args, logger=self._QS_Logger)
    def renameTable(self, old_table_name, new_table_name):
        if old_table_name==new_table_name: return 0
        OldPath = self.MainDir+os.sep+old_table_name
        NewPath = self.MainDir+os.sep+new_table_name
        with self._DataLock:
            if not os.path.isdir(OldPath): raise __QS_Error__("HDF5TickDB.renameTable: 表: '%s' 不存在!" % old_table_name)
            if os.path.isdir(NewPath): raise __QS_Error__("HDF5TickDB.renameTable: 表 '"+new_table_name+"' 已存在!")
            os.rename(OldPath, NewPath)
        return 0
    def deleteTable(self, table_name):
        TablePath = self.MainDir+os.sep+table_name
        with self._DataLock:
            if os.path.isdir(TablePath):
                shutil.rmtree(TablePath, ignore_errors=True)
        return 0
    def setTableMetaData(self, table_name, key=None, value=None, meta_data=None):
        if meta_data is not None:
            meta_data = dict(meta_data)
        else:
            meta_data = {}
        if key is not None:
            meta_data[key] = value
        with self._DataLock:
            writeNestedDict2HDF5(meta_data, self.MainDir+os.sep+table_name+os.sep+"_TableInfo.h5", "/")
        return 0
    # ----------------------------因子操作---------------------------------
    def renameFactor(self, table_name, old_factor_name, new_factor_name):
        if old_factor_name==new_factor_name: return 0
        FactorNames = self.getTable(table_name).FactorNames
        if old_factor_name not in FactorNames: raise __QS_Error__("HDF5TickDB.renameFactor: 表 '%s' 中不存在因子 '%s'!" % (table_name, old_factor_name))
        if new_factor_name in FactorNames: raise __QS_Error__("HDF5TickDB.renameFactor: 表 '%s' 中的因子 '%s' 已存在!" % (table_name, new_factor_name))
        TablePath = self.MainDir+os.sep+table_name
        with self._DataLock:
            for iFileName in os.listdir(TablePath):
                if iFileName=="_TableInfo.h5": continue
                with h5py.File(TablePath+os.sep+iFileName) as iFile:
                    for jDate in iFile:
                        jGroup = iFile[jDate]
                        if old_factor_name in jGroup:
                            jGroup[new_factor_name] = jGroup.pop(old_factor_name)
                    iDataType = iFile.attrs["DataType"]
                    iDataType[new_factor_name] = iDataType.pop(old_factor_name)
                    iFile.attrs["DataType"] = iDataType
        return 0
    def deleteFactor(self, table_name, factor_names):
        TablePath = self.MainDir+os.sep+table_name
        with self._DataLock:
            with h5py.File(TablePath+os.sep+"_TableInfo.h5") as iFile:
                FactorNames = set(iFile.attrs["FactorNames"])
            if FactorNames.issubset(set(factor_names)):
                shutil.rmtree(TablePath, ignore_errors=True)
            else:
                for iFileName in os.listdir(TablePath):
                    if iFileName=="_TableInfo.h5": continue
                    with h5py.File(TablePath+os.sep+iFileName) as iFile:
                        for jDate in iFile:
                            jGroup = iFile[jDate]
                            for kFactorName in factor_names:
                                jGroup.pop(kFactorName, None)
                        iDataType = iFile.attrs["DataType"]
                        for kFactorName in factor_names: iDataType.pop(kFactorName, None)
                        iFile.attrs["DataType"] = iDataType
                with h5py.File(TablePath+os.sep+"_TableInfo.h5") as iFile:
                    iFile.attrs["FactorNames"] = sorted(FactorNames.difference(factor_names))
        return 0
    def setFactorMetaData(self, table_name, ifactor_name, key=None, value=None, meta_data=None):
        if meta_data is not None:
            if key is not None: meta_data[key] = value
        elif key is not None:
            meta_data = {key: value}
        else:
            return 0
        TablePath = self.MainDir+os.sep+table_name
        with self._getLock(table_name) as DataLock:
            for iFileName in os.listdir(TablePath):
                if iFileName=="_TableInfo.h5": continue
                with self._openHDF5File(TablePath+os.sep+iFileName, mode="a") as iFile:
                    for iKey, iVal in meta_data.items():
                        if iKey in iFile.attrs:
                            del iFile.attrs[iKey]
                        if (isinstance(iVal, np.ndarray)) and (iVal.dtype==np.dtype("O")):
                            iFile.attrs.create(iKey, data=iVal, dtype=h5py.special_dtype(vlen=str))
                        elif iVal is not None:
                            iFile.attrs[iKey] = iVal
        return 0
    def writeIDData(self, id_data, table_name, iid, if_exists="replace", data_type=None, **kwargs):
        StrDataType = h5py.string_dtype(encoding="utf-8")
        if not kwargs.get("timestamp_index", False):
            DTs = id_data.index
            if pd.__version__>="0.20.0": id_data.index = [idt.to_pydatetime().timestamp() for idt in DTs]
            else: id_data.index = [idt.timestamp() for idt in DTs]
        TablePath = self.MainDir+os.sep+table_name
        if not os.path.isdir(TablePath):
            with self._DataLock:
                if not os.path.isdir(TablePath): os.mkdir(TablePath)
        StartTS = dt.datetime.combine(dt.datetime.fromtimestamp(id_data.index[0]).date(), dt.time(0)).timestamp()
        EndTS = (dt.datetime.combine(dt.datetime.fromtimestamp(id_data.index[-1]).date(), dt.time(0)) + dt.timedelta(1)).timestamp()
        FilePath = TablePath+os.sep+iid+"."+self._Suffix
        id_data, data_type = _identifyDataType(id_data, data_type)
        with self._getLock(table_name=table_name) as DataLock:
            if not os.path.isfile(FilePath):# 文件不存在
                open(FilePath, mode="a").close()# h5py 直接创建文件名包含中文的文件会报错.
                with self._openHDF5File(FilePath, mode="a") as DataFile:
                    #DataFile.attrs["DataType"] = data_type
                    DataFile.attrs.create("DataType", data=np.frombuffer(pickle.dumps(data_type), dtype=np.uint8))
                    for iTS in range(int(StartTS), int(EndTS), 86400):
                        iData = id_data.loc[iTS:iTS+86400]
                        iDate = dt.datetime.fromtimestamp(iTS).strftime("%Y%m%d")
                        iGroup = DataFile.create_group(iDate)
                        iGroup.create_dataset("DateTime", shape=(iData.shape[0],), maxshape=(None,), data=iData.index)
                        for jFactorName, jDataType in data_type.items():
                            if jDataType=="double":
                                iGroup.create_dataset(jFactorName, shape=(iData.shape[0],), maxshape=(None,), dtype=np.float, fillvalue=np.nan, data=iData[jFactorName].values)
                            elif jDataType=="string":
                                iGroup.create_dataset(jFactorName, shape=(iData.shape[0],), maxshape=(None,), dtype=StrDataType, fillvalue=None, data=iData[jFactorName].values)
                            elif jDataType=="object":
                                ijData = np.ascontiguousarray(iData[jFactorName].apply(lambda x: np.frombuffer(pickle.dumps(x), dtype=np.uint8)).values)
                                iGroup.create_dataset(jFactorName, shape=(iData.shape[0],), maxshape=(None,), dtype=h5py.vlen_dtype(np.uint8), data=ijData)
                    DataFile.flush()
            elif if_exists=="replace":
                with self._openHDF5File(FilePath, mode="a") as DataFile:
                    NewDataType = pickle.loads(bytes(DataFile.attrs["DataType"]))
                    NewDataType.update(data_type)
                    DataFile.attrs.create("DataType", data=np.frombuffer(pickle.dumps(NewDataType), dtype=np.uint8))
                    for iTS in range(int(StartTS), int(EndTS), 86400):
                        iData = id_data.loc[iTS:iTS+86400]
                        iDate = dt.datetime.fromtimestamp(iTS).strftime("%Y%m%d")
                        if iDate in DataFile: del DataFile[iDate]
                        iGroup = DataFile.create_group(iDate)
                        iGroup.create_dataset("DateTime", shape=(iData.shape[0],), maxshape=(None,), data=iData.index)
                        for jFactorName, jDataType in data_type.items():
                            if jDataType=="double":
                                iGroup.create_dataset(jFactorName, shape=(iData.shape[0],), maxshape=(None,), dtype=np.float, fillvalue=np.nan, data=iData[jFactorName].values)
                            elif jDataType=="string":
                                iGroup.create_dataset(jFactorName, shape=(iData.shape[0],), maxshape=(None,), dtype=StrDataType, fillvalue=None, data=iData[jFactorName].values)
                            elif jDataType=="object":
                                ijData = np.ascontiguousarray(iData[jFactorName].apply(lambda x: np.frombuffer(pickle.dumps(x), dtype=np.uint8)).values)
                                iGroup.create_dataset(jFactorName, shape=(iData.shape[0],), maxshape=(None,), dtype=h5py.vlen_dtype(np.uint8), data=ijData)
                    DataFile.flush()
            elif if_exists=="append":
                with self._openHDF5File(FilePath, mode="a") as DataFile:
                    NewDataType = pickle.loads(bytes(DataFile.attrs["DataType"]))
                    NewDataType.update(data_type)
                    DataFile.attrs.create("DataType", data=np.frombuffer(pickle.dumps(NewDataType), dtype=np.uint8))
                    for iTS in range(int(StartTS), int(EndTS), 86400):
                        iData = id_data.loc[iTS:iTS+86400]
                        iDate = dt.datetime.fromtimestamp(iTS).strftime("%Y%m%d")
                        if iDate not in DataFile:
                            iGroup = DataFile.create_group(iDate)
                            iGroup.create_dataset("DateTime", shape=(iData.shape[0],), maxshape=(None,), data=iData.index)
                        else:
                            nOld = iGroup["DateTime"].shape[0]
                            iGroup["DateTime"].resize((nOld+iData.shape[0],))
                            iGroup["DateTime"][nOld:] = iData.index
                        for jFactorName, jDataType in data_type.items():
                            if jFactorName not in iGroup:
                                if jDataType=="double":
                                    iGroup.create_dataset(jFactorName, shape=(iData.shape[0],), maxshape=(None,), dtype=np.float, fillvalue=np.nan, data=iData[jFactorName].values)
                                elif jDataType=="string":
                                    iGroup.create_dataset(jFactorName, shape=(iData.shape[0],), maxshape=(None,), dtype=StrDataType, fillvalue=None, data=iData[jFactorName].values)
                                elif jDataType=="object":
                                    ijData = np.ascontiguousarray(iData[jFactorName].apply(lambda x: np.frombuffer(pickle.dumps(x), dtype=np.uint8)).values)
                                    iGroup.create_dataset(jFactorName, shape=(iData.shape[0],), maxshape=(None,), dtype=h5py.vlen_dtype(np.uint8), data=ijData)
                            else:
                                nOld = iGroup[jFactorName].shape[0]
                                iGroup[jFactorName].resize((nOld+iData.shape[0],))
                                if jDataType!="object":
                                    iGroup[jFactorName][nOld:] = iData[jFactorName].values
                                else:
                                    ijData = np.ascontiguousarray(iData[jFactorName].apply(lambda x: np.frombuffer(pickle.dumps(x), dtype=np.uint8)).values)
                                    iGroup[jFactorName][nOld:] = ijData
                    DataFile.flush()
            else:
                Msg = ("因子库 '%s' 调用方法 writeIDData 错误: 不支持的写入方式 '%s'!" % (self.Name, str(if_exists)))
                self._QS_Logger.error(Msg)
                raise __QS_Error__(Msg)
        id_data.index = DTs
        return 0
    # if_exists 仅支持: replace, append
    # replace: 按天 replace
    # append: 假设已经写入的数据排好了序, 并且新写入的数据和已有数据不重叠
    def writeData(self, data, table_name, if_exists="replace", data_type={}, **kwargs):
        DTs = data.major_axis
        if pd.__version__>="0.20.0": data.index = [idt.to_pydatetime().timestamp() for idt in DTs]
        else: data.index = [idt.timestamp() for idt in DTs]
        for i, iID in enumerate(data.minor_axis):
            self.writeIDData(data.iloc[:, :, i], table_name, iID, if_exists=if_exists, data_type=data_type, timestamp_index=True, **kwargs)
        data.major_axis = DTs
        return 0

if __name__=="__main__":
    FDB = HDF5TickDB(sys_args={"主目录": r"D:\HST\Data\HDF5TickData"})
    FDB.connect()
    
    #TickData = pd.read_csv(r"D:\HST\Data\TXTData\DZH-SH201212-TXT\20121212\600519_20121212.txt", header=0, index_col=None, encoding="gb2312")
    #DateField, TimeField = TickData.columns[0], TickData.columns[1]
    #TickData.index = (TickData.pop(DateField)+"T"+TickData.pop(TimeField)).apply(lambda d: dt.datetime.strptime(d, "%Y-%m-%dT%H:%M:%S"))
    #FDB.writeIDData(TickData, "test", "600519.SH")
    
    TargetDir = r"D:\HST\Data\TXTData\DZH-SH201212-TXT"
    for iDir in os.listdir(TargetDir):
        for jFile in os.listdir(TargetDir+os.sep+iDir):
            jID = jFile.split("_")[0]
            if (not jID) or (jID[0]!="6"): continue
            jID = jID + ".SH"
            TickData = pd.read_csv(TargetDir+os.sep+iDir+os.sep+jFile, header=0, index_col=None, encoding="gb2312")
            DateField, TimeField = TickData.columns[0], TickData.columns[1]
            TickData.index = (TickData.pop(DateField)+"T"+TickData.pop(TimeField)).apply(lambda d: dt.datetime.strptime(d, "%Y-%m-%dT%H:%M:%S"))
            FDB.writeIDData(TickData, "test", jID)
        print(iDir)
    
    #FT = FDB.getTable("test")
    #Data = FT.readIDData("600519.SH", ["B1价", "S1价", "成交价"], start_dt=dt.datetime(2012, 12, 12), end_dt=dt.datetime(2012, 12, 13))
    
    print("===")