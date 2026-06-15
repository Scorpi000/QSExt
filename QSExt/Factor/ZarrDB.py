# coding=utf-8
"""基于 zarr 模块的因子库"""
import os
import shutil
import datetime as dt
from io import StringIO
from typing import Optional, Any, Dict, Literal, List, Union

import numpy as np
import pandas as pd
import numcodecs
import zarr
from filelock import FileLock
from pydantic import Field, DirectoryPath

from QuantStudio import __QS_ConfigPath__
from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.QSObject import Panel
from QuantStudio.Factor.FactorDB import WritableFactorDB
from QuantStudio.Factor.FactorTable import FactorTable
from QuantStudio.Factor.FactorUtils import adjustDataDTID


def _identifyDataType(factor_data, data_type=None):
    if (data_type is None) or (data_type == "double"):
        try:
            factor_data = factor_data.astype(float)
        except:
            data_type = "object"
        else:
            data_type = "double"
    return (factor_data, data_type)


class ZarrFactorTable(FactorTable):
    """ZarrDB 库中因子表"""

    class __QS_ArgClass__(FactorTable.__QS_ArgClass__):
        LookBack: int = Field(default=0, title="回溯天数", ge=0, frozen=True, description="缺失填充回溯的天数")
        OnlyStartLookBack: bool = Field(default=False, title="只起始日回溯", frozen=True, description="如果为 True, 表示只对提取数据的第一个时点进行缺失填充, 之后的时点不填充")
        OnlyLookBackNontarget: bool = Field(default=False, title="只回溯非目标日", frozen=True, description="如果为 True, 表示只用不在提取时点序列中的数据进行缺失填充")
        OnlyLookBackDT: bool = Field(default=False, title="只回溯时点", frozen=True, description="如果为 True, 表示所有 ID 统一沿着时点字段进行回溯填充, 不单独填充")
        TargetDT: Optional[dt.datetime] = Field(default=None, title="目标时点", frozen=True, description="非 None 表示只取该时点的值返回")

    @property
    def FactorNames(self) -> List[str]:
        ZTable = zarr.open(str(self._FactorDB._QSArgs.MainDir / self.Name), mode="r")
        DataType = ZTable.attrs.get("DataType", {})
        return sorted(DataType)

    def getMetaData(self, key: Optional[str] = None) -> Union[Any, pd.Series]:
        ZTable = zarr.open(str(self._FactorDB._QSArgs.MainDir / self.Name), mode="r")
        if key is not None:
            if key not in ZTable.attrs:
                return None
            MetaData = ZTable.attrs[key]
            if isinstance(MetaData, dict):
                Type = MetaData.get("_Type")
                if Type == "Array":
                    return np.array(MetaData["List"])
                elif Type == "Series":
                    return pd.read_json(StringIO(MetaData["Json"]), typ="series")
                elif Type == "DataFrame":
                    return pd.read_json(StringIO(MetaData["Json"]), typ="frame")
                else:
                    return MetaData
            else:
                return MetaData
        MetaData = {}
        for iKey in ZTable.attrs:
            MetaData[iKey] = self.getMetaData(key=iKey)
        return pd.Series(MetaData)

    def getFactorMetaData(self, factor_names: Optional[List[str]] = None, key: Optional[str] = None) -> Union[pd.DataFrame, pd.Series]:
        AllFactorNames = self.FactorNames
        if factor_names is None:
            factor_names = AllFactorNames
        elif set(factor_names).isdisjoint(AllFactorNames):
            return super().getFactorMetaData(factor_names=factor_names, key=key)
        MetaData = {}
        ZTable = zarr.open(str(self._FactorDB._QSArgs.MainDir / self.Name), mode="r")
        for iFactorName in factor_names:
            if iFactorName in AllFactorNames:
                iZFactor = ZTable[iFactorName]
                if key is None:
                    MetaData[iFactorName] = pd.Series(dict(iZFactor.attrs))
                elif key in iZFactor.attrs:
                    MetaData[iFactorName] = iZFactor.attrs[key]
        if not MetaData:
            return super().getFactorMetaData(factor_names=factor_names, key=key)
        if key is None:
            return pd.DataFrame(MetaData).T.reindex(index=factor_names)
        else:
            return pd.Series(MetaData).reindex(index=factor_names)

    def getID(self, ifactor_name: Optional[str] = None, idt: Optional[dt.datetime] = None) -> List[str]:
        if ifactor_name is None:
            ifactor_name = self.FactorNames[0]
        ZTable = zarr.open(str(self._FactorDB._QSArgs.MainDir / self.Name), mode="r")
        ZFactor = ZTable[ifactor_name]
        IDs = sorted(ZFactor["ID"][:])
        if idt is not None:
            Data = self.readFactorData(ifactor_name, ids=IDs, dts=[idt]).iloc[0]
            return Data[pd.notnull(Data)].index.tolist()
        else:
            return IDs

    def getDateTime(self, ifactor_name: Optional[str] = None, iid: Optional[str] = None, start_dt: Optional[dt.datetime] = None, end_dt: Optional[dt.datetime] = None) -> List[dt.datetime]:
        if ifactor_name is None:
            ifactor_name = self.FactorNames[0]
        ZTable = zarr.open(str(self._FactorDB._QSArgs.MainDir / self.Name), mode="r")
        ZFactor = ZTable[ifactor_name]
        Timestamps = pd.DatetimeIndex(ZFactor["DateTime"][:])
        if start_dt is not None:
            Timestamps = Timestamps[Timestamps >= pd.Timestamp(start_dt)]
        if end_dt is not None:
            Timestamps = Timestamps[Timestamps <= pd.Timestamp(end_dt)]
        DTs = sorted(t.to_pydatetime() for t in Timestamps)
        if iid is not None:
            Data = self.readFactorData(ifactor_name, ids=[iid], dts=DTs).iloc[:, 0]
            return Data[pd.notnull(Data)].index.tolist()
        else:
            return DTs

    def __QS_calcData__(self, raw_data, factor_names, ids, dts):
        Data = {iFactor: self.readFactorData(ifactor_name=iFactor, ids=ids, dts=dts) for iFactor in factor_names}
        return Panel(Data, items=factor_names, major_axis=dts, minor_axis=ids)

    def _readFactorData(self, ifactor_name, ids, dts):
        ZTable = zarr.open(str(self._FactorDB._QSArgs.MainDir / self.Name), mode="r")
        if ifactor_name not in ZTable:
            raise __QS_Error__("因子库 '%s' 的因子表 '%s' 中不存在因子 '%s'!" % (self._FactorDB.Name, self.Name, ifactor_name))
        ZFactor = ZTable[ifactor_name]
        DataType = ZFactor.attrs["DataType"]
        DateTimes = pd.DatetimeIndex(ZFactor["DateTime"][:])
        IDs = ZFactor["ID"][:]

        if ids is not None:
            IDIndices = pd.Series(np.arange(0, IDs.shape[0]), index=IDs)
            IDIndices = IDIndices[IDIndices.index.intersection(ids)].astype('int')
        else:
            IDIndices = slice(None)

        if dts is not None:
            DTIndices = pd.Series(np.arange(0, DateTimes.shape[0]), index=DateTimes)
            DTIndices = DTIndices[DTIndices.index.intersection(dts)].astype('int')
        else:
            DTIndices = slice(None)

        Rslt = pd.DataFrame(
            ZFactor["Data"].get_orthogonal_selection((DTIndices, IDIndices)),
            index=DateTimes[DTIndices],
            columns=IDs[IDIndices]
        )

        if ids is not None:
            if Rslt.shape[1] > 0:
                Rslt = Rslt.reindex(columns=ids)
            else:
                Rslt = pd.DataFrame(index=Rslt.index, columns=ids)
        else:
            Rslt = Rslt.sort_index(axis=1)

        if dts is not None:
            if Rslt.shape[0] > 0:
                Rslt = Rslt.reindex(index=dts)
            else:
                Rslt = pd.DataFrame(index=dts, columns=Rslt.columns)
        else:
            Rslt = Rslt.sort_index(axis=0)

        if DataType == "string":
            Rslt = Rslt.where(pd.notnull(Rslt), None)
            Rslt = Rslt.where(Rslt != "", None)

        return Rslt

    def readFactorData(self, ifactor_name: str, ids: List[str], dts: List[dt.datetime]) -> pd.DataFrame:
        TargetDT = self._QSArgs.TargetDT
        if TargetDT:
            Data = self.new(args={"TargetDT": None}).readFactorData(ifactor_name=ifactor_name, ids=ids, dts=[TargetDT])
            if dts is None:
                dts = self.getDateTime(ifactor_name=ifactor_name)
            if ids is None:
                ids = self.getID(ifactor_name=ifactor_name)
            return pd.DataFrame(Data.values.repeat(repeats=len(dts), axis=0), index=dts, columns=ids)
        LookBack = self._QSArgs.LookBack
        if LookBack == 0:
            return self._readFactorData(ifactor_name, ids, dts)
        if np.isinf(LookBack):
            RawData = self._readFactorData(ifactor_name, ids, None)
        else:
            if dts is not None:
                StartDT = dts[0] - dt.timedelta(LookBack)
                iDTs = self.getDateTime(ifactor_name=ifactor_name, start_dt=StartDT, end_dt=dts[-1])
            else:
                iDTs = None
            RawData = self._readFactorData(ifactor_name, ids, iDTs)
        if not self._QSArgs.OnlyLookBackDT:
            RawData = Panel({ifactor_name: RawData})
            return adjustDataDTID(RawData, LookBack, [ifactor_name], ids, dts, self._QSArgs.OnlyStartLookBack, self._QSArgs.OnlyLookBackNontarget, logger=self._QS_Logger).iloc[0]
        RawData = RawData.dropna(axis=0, how="all").dropna(axis=1, how="all")
        RowIdxMask = pd.isnull(RawData)
        if RowIdxMask.shape[1] == 0:
            return pd.DataFrame(index=dts, columns=ids)
        RawIDs = RowIdxMask.columns
        RowIdx = pd.DataFrame(
            np.arange(RowIdxMask.shape[0]).reshape((RowIdxMask.shape[0], 1)).repeat(RowIdxMask.shape[1], axis=1),
            index=RowIdxMask.index, columns=RawIDs)
        RowIdx[RowIdxMask] = np.nan
        RowIdx = adjustDataDTID(Panel({"RowIdx": RowIdx}), LookBack, ["RowIdx"], RawIDs.tolist(), dts, self._QSArgs.OnlyStartLookBack, self._QSArgs.OnlyLookBackNontarget, logger=self._QS_Logger).iloc[0].values
        RowIdx[pd.isnull(RowIdx)] = -1
        RowIdx = RowIdx.astype(int)
        ColIdx = np.arange(RowIdx.shape[1]).reshape((1, RowIdx.shape[1])).repeat(RowIdx.shape[0], axis=0)
        RowIdxMask = (RowIdx == -1)
        RawData = RawData.values[RowIdx, ColIdx]
        RawData[RowIdxMask] = None
        return pd.DataFrame(RawData, index=dts, columns=RawIDs).reindex(columns=ids)


class ZarrDB(WritableFactorDB):
    """基于 Zarr 文件的因子库

    主目录下的每个文件夹表示一张因子表, 每张表是一个 zarr 根 group。
    每个因子是表下的一个子 group, 包含三个 Dataset: DateTime, ID, Data。
    表的元数据存储在根 group 的 attrs 中。
    因子的元数据存储在因子 group 的 attrs 中。
    """

    class __QS_ArgClass__(WritableFactorDB.__QS_ArgClass__):
        Name: str = Field(default="ZarrDB", title="名称", frozen=True)
        MainDir: DirectoryPath = Field(title="主目录", frozen=True, description="存放数据的主目录")

    def connect(self):
        if not os.path.isdir(self._QSArgs.MainDir):
            raise __QS_Error__("ZarrDB.connect: 不存在主目录 '%s'!" % self._QSArgs.MainDir)
        return self

    def _getLock(self, table_name=None):
        if table_name is None:
            return FileLock(self._QSArgs.MainDir / "_FDB.lock")
        TablePath = self._QSArgs.MainDir / table_name
        if not os.path.isdir(TablePath):
            Msg = ("因子库 '%s' 调用 _getLock 时错误, 不存在因子表: '%s'" % (self.Name, table_name))
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        return FileLock(TablePath / "_Table.lock")

    @property
    def TableNames(self) -> List[str]:
        MainDir = self._QSArgs.MainDir
        return sorted(iDir for iDir in os.listdir(MainDir) if os.path.isdir(MainDir / iDir))

    def getTable(self, table_name: str, args: dict = {}) -> ZarrFactorTable:
        if not os.path.isdir(self._QSArgs.MainDir / table_name):
            raise __QS_Error__("ZarrDB.getTable: 表 '%s' 不存在!" % table_name)
        return ZarrFactorTable(fdb=self, args=args | {"Name": table_name}, logger=self._QS_Logger)

    def renameTable(self, old_table_name: str, new_table_name: str):
        if old_table_name == new_table_name:
            return 0
        OldPath = self._QSArgs.MainDir / old_table_name
        NewPath = self._QSArgs.MainDir / new_table_name
        with self._getLock() as DataLock:
            if not os.path.isdir(OldPath):
                raise __QS_Error__("ZarrDB.renameTable: 表: '%s' 不存在!" % old_table_name)
            if os.path.isdir(NewPath):
                raise __QS_Error__("ZarrDB.renameTable: 表 '" + new_table_name + "' 已存在!")
            os.rename(OldPath, NewPath)
        return 0

    def deleteTable(self, table_name: str):
        TablePath = self._QSArgs.MainDir / table_name
        with self._getLock() as DataLock:
            if os.path.isdir(TablePath):
                shutil.rmtree(TablePath, ignore_errors=True)
        return 0

    def setTableMetaData(self, table_name: str, key: Optional[str] = None, value: Any = None, meta_data: Optional[dict] = None):
        if meta_data is not None:
            meta_data = dict(meta_data)
        else:
            meta_data = {}
        if key is not None:
            meta_data[key] = value
        with self._getLock(table_name=table_name) as DataLock:
            iZTable = zarr.open(str(self._QSArgs.MainDir / table_name), mode="a")
            for iKey, iValue in meta_data.items():
                if iKey in iZTable.attrs:
                    del iZTable.attrs[iKey]
                if isinstance(iValue, np.ndarray):
                    iZTable.attrs[iKey] = {"_Type": "Array", "List": iValue.tolist()}
                elif isinstance(iValue, pd.Series):
                    iZTable.attrs[iKey] = {"_Type": "Series", "Json": iValue.to_json(index=True)}
                elif isinstance(iValue, pd.DataFrame):
                    iZTable.attrs[iKey] = {"_Type": "DataFrame", "Json": iValue.to_json(index=True)}
                elif iValue is not None:
                    iZTable.attrs[iKey] = iValue
        return 0

    def renameFactor(self, table_name: str, old_factor_name: str, new_factor_name: str):
        if old_factor_name == new_factor_name:
            return 0
        with self._getLock() as DataLock:
            iZTable = zarr.open(str(self._QSArgs.MainDir / table_name), mode="a")
            if old_factor_name not in iZTable:
                raise __QS_Error__("ZarrDB.renameFactor: 表 '%s' 中不存在因子 '%s'!" % (table_name, old_factor_name))
            if new_factor_name in iZTable:
                raise __QS_Error__("ZarrDB.renameFactor: 表 '%s' 中的因子 '%s' 已存在!" % (table_name, new_factor_name))
            iZTable[new_factor_name] = iZTable.pop(old_factor_name)
            DataType = iZTable.attrs.get("DataType", {})
            DataType[new_factor_name] = DataType.pop(old_factor_name)
            iZTable.attrs["DataType"] = DataType
        return 0

    def deleteFactor(self, table_name: str, factor_names: List[str]):
        TablePath = self._QSArgs.MainDir / table_name
        with self._getLock() as DataLock:
            iZTable = zarr.open(str(TablePath), mode="a")
            DataType = iZTable.attrs.get("DataType", {})
            if set(DataType).issubset(set(factor_names)):
                shutil.rmtree(TablePath, ignore_errors=True)
            else:
                for iFactor in factor_names:
                    if iFactor in iZTable:
                        del iZTable[iFactor]
                    DataType.pop(iFactor, None)
                iZTable.attrs["DataType"] = DataType
        return 0

    def setFactorMetaData(self, table_name: str, ifactor_name: str, key: Optional[str] = None, value: Any = None, meta_data: Optional[dict] = None):
        with self._getLock(table_name=table_name) as DataLock:
            iZTable = zarr.open(str(self._QSArgs.MainDir / table_name), mode="a")
            iZFactor = iZTable[ifactor_name]
            if key is not None:
                if key in iZFactor.attrs:
                    del iZFactor.attrs[key]
                if isinstance(value, np.ndarray):
                    iZFactor.attrs[key] = {"_Type": "Array", "List": value.tolist()}
                elif isinstance(value, pd.Series):
                    iZFactor.attrs[key] = {"_Type": "Series", "Json": value.to_json(index=True)}
                elif isinstance(value, pd.DataFrame):
                    iZFactor.attrs[key] = {"_Type": "DataFrame", "Json": value.to_json(index=True)}
                elif value is not None:
                    iZFactor.attrs[key] = value
        if meta_data is not None:
            for iKey in meta_data.keys():
                self.setFactorMetaData(table_name, ifactor_name=ifactor_name, key=iKey, value=meta_data[iKey], meta_data=None)
        return 0

    def _updateFactorData(self, factor_data, table_name, ifactor_name, data_type):
        TablePath = self._QSArgs.MainDir / table_name
        with self._getLock(table_name=table_name) as DataLock:
            ZTable = zarr.open(str(TablePath), mode="a")
            ZFactor = ZTable[ifactor_name]
            OldDateTimes = pd.DatetimeIndex(ZFactor["DateTime"][:])
            OldIDs = ZFactor["ID"][:]
            NewDateTimes = factor_data.index.difference(OldDateTimes).values
            NewIDs = factor_data.columns.difference(OldIDs).values
            ZFactor["DateTime"].append(NewDateTimes, axis=0)
            ZFactor["ID"].append(NewIDs, axis=0)
            ZFactor["Data"].resize((ZFactor["DateTime"].shape[0], ZFactor["ID"].shape[0]))
            AllDateTimes = OldDateTimes.append(pd.DatetimeIndex(NewDateTimes))
            IDIndices = pd.Series(np.arange(ZFactor["ID"].shape[0]), index=np.r_[OldIDs, NewIDs]).reindex(factor_data.columns).values.tolist()
            DTIndices = pd.Series(np.arange(ZFactor["DateTime"].shape[0]), index=AllDateTimes).reindex(factor_data.index).values.tolist()
            IDIndices = [int(i) for i in IDIndices]
            DTIndices = [int(i) for i in DTIndices]
            if data_type != "double":
                factor_data = factor_data.where(pd.notnull(factor_data), None)
            else:
                factor_data = factor_data.astype("float")
            ZFactor["Data"].set_orthogonal_selection((DTIndices, IDIndices), factor_data.values)
        return 0

    def writeFactorData(self, factor_data: pd.DataFrame, table_name: str, ifactor_name: str, if_exists: Literal["update", "replace", "append"] = "update", data_type: Optional[Literal["double", "string", "object"]] = None, **kwargs):
        DTs = factor_data.index
        TablePath = self._QSArgs.MainDir / table_name
        if not os.path.isdir(TablePath):
            with self._getLock() as DataLock:
                if not os.path.isdir(TablePath):
                    os.mkdir(TablePath)
        with self._getLock(table_name=table_name) as DataLock:
            ZTable = zarr.open(str(TablePath), mode="a")
            if ifactor_name not in ZTable:
                factor_data, data_type = _identifyDataType(factor_data, data_type)
                ZFactor = ZTable.create_group(ifactor_name, overwrite=True)
                ZFactor.create_dataset("ID", shape=(factor_data.shape[1],), data=factor_data.columns.values, dtype=object, object_codec=numcodecs.VLenUTF8(), overwrite=True)
                ZFactor.create_dataset("DateTime", shape=(factor_data.shape[0],), data=factor_data.index.values, dtype="M8[ns]", overwrite=True)
                if data_type == "double":
                    ZFactor.create_dataset("Data", shape=factor_data.shape, data=factor_data.values, dtype="f8", fill_value=np.nan, overwrite=True)
                elif data_type == "string":
                    ZFactor.create_dataset("Data", shape=factor_data.shape, data=factor_data.values, dtype=object, object_codec=numcodecs.VLenUTF8(), overwrite=True)
                elif data_type == "object":
                    ZFactor.create_dataset("Data", shape=factor_data.shape, data=factor_data.values, dtype=object, object_codec=numcodecs.Pickle(), overwrite=True)
                ZFactor.attrs["DataType"] = data_type
                DataType = ZTable.attrs.get("DataType", {})
                DataType[ifactor_name] = data_type
                ZTable.attrs["DataType"] = DataType
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

    def writeData(self, data: Panel, table_name: str, if_exists: Literal["update", "replace", "append"] = "update", data_type: Dict[str, Literal["double", "string", "object"]] = {}, **kwargs):
        for i, iFactor in enumerate(data.items):
            self.writeFactorData(data.iloc[i], table_name, iFactor, if_exists=if_exists, data_type=data_type.get(iFactor, None), **kwargs)
        return 0
