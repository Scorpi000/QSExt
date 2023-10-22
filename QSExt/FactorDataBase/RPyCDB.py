# coding=utf-8
"""基于 RPyC 模块的因子库(TODO)"""
import os
import datetime as dt

import numpy as np
import pandas as pd
import rpyc
from traits.api import Range, Str, Password

from QuantStudio import __QS_Error__, __QS_ConfigPath__
from QuantStudio.FactorDataBase.FactorDB import WritableFactorDB, FactorTable
from QuantStudio.Tools.api import Panel

class _FactorTable(FactorTable):
    """RPyCDB 因子表"""
    def __init__(self, name, fdb=None, sys_args={}, config_file=None, **kwargs):
        self._FT = fdb._Conn.root.FTs[name]
        return super().__init__(name, fdb, sys_args, config_file, **kwargs)
    
    def getMetaData(self, key=None, args={}):
        return rpyc.utils.classic.obtain(self._FT.getMetaData(key=key, args=args))
    
    @property
    def FactorNames(self):
        return rpyc.utils.classic.obtain(self._FT.FactorNames)
    
    def getFactorMetaData(self, factor_names=None, key=None, args={}):
        return rpyc.utils.classic.obtain(self._FT.getFactorMetaData(factor_names=factor_names, key=key, args=args))
    
    def getID(self, ifactor_name=None, idt=None, args={}):
        return rpyc.utils.classic.obtain(self._FT.getID(ifactor_name=ifactor_name, idt=idt, args=args))
    
    def getDateTime(self, ifactor_name=None, iid=None, start_dt=None, end_dt=None, args={}):
        return rpyc.utils.classic.obtain(self._FT.getDateTime(ifactor_name=ifactor_name, iid=iid, start_dt=start_dt, end_dt=end_dt, args=args))
   
    def __QS_calcData__(self, raw_data, factor_names, ids, dts, args={}):
        Data = {iFactor: self.readFactorData(ifactor_name=iFactor, ids=ids, dts=dts, args=args) for iFactor in factor_names}
        return Panel(Data, items=factor_names, major_axis=dts, minor_axis=ids)
    
    def readFactorData(self, ifactor_name, ids, dts, args={}):
        if hasattr(self._FT, "readFactorData"):
            Data = self._FT.readFactorData(ifactor_name, ids, dts, args=args)
        else:
            Data = self._FT.readData(factor_names=[ifactor_name], ids=ids, dts=dts, args=args).iloc[0]
        return rpyc.utils.classic.obtain(Data)

# 基于 RPyC 模块的因子数据库
class RPyCDB(WritableFactorDB):
    """RPyCDB"""
    class __QS_ArgClass__(WritableFactorDB.__QS_ArgClass__):
        Name = Str("RPyCDB", arg_type="String", label="名称", order=-100)
        IPAddr = Str("localhost", arg_type="String", label="IP地址", order=2)
        Port = Range(low=0, high=65535, value=18812, arg_type="Integer", label="端口", order=3)
        User = Str("root", arg_type="String", label="用户名", order=4)
        Pwd = Password("", arg_type="String", label="密码", order=5)
        
    def __init__(self, sys_args={}, config_file=None, **kwargs):
        self._isAvailable = False
        return super().__init__(sys_args=sys_args, config_file=(__QS_ConfigPath__+os.sep+"RPyCDBConfig.json" if config_file is None else config_file), **kwargs)
    
    def connect(self):
        #self._Conn = rpyc.connect(self._QSArgs.IPAddr, port=self._QSArgs.Port)
        self._Conn = rpyc.classic.connect(self._QSArgs.IPAddr, port=self._QSArgs.Port)
        return self
    
    def disconnect(self):
        self._Conn.close()
        self._Conn = None
        self._isAvailable = False
    
    def isAvailable(self):
        return self._isAvailable
    
    # -------------------------------表的操作---------------------------------
    @property
    def TableNames(self):
        return sorted(self._Conn.root.FTs)
    
    def getTable(self, table_name, args={}):
        if table_name not in self._Conn.root.FTs: raise __QS_Error__("RPyCDB.getTable: 表 '%s' 不存在!" % table_name)
        #return self._Conn.root.FTs[table_name]
        return _FactorTable(table_name, self, sys_args=args, config_file=None)
    
    
    def renameTable(self, old_table_name, new_table_name):
        if old_table_name==new_table_name: return 0
        OldPath = self._QSArgs.MainDir+os.sep+old_table_name
        NewPath = self._QSArgs.MainDir+os.sep+new_table_name
        with self._DataLock:
            if not os.path.isdir(OldPath): raise __QS_Error__("ZarrDB.renameTable: 表: '%s' 不存在!" % old_table_name)
            if os.path.isdir(NewPath): raise __QS_Error__("ZarrDB.renameTable: 表 '"+new_table_name+"' 已存在!")
            os.rename(OldPath, NewPath)
        return 0
    def deleteTable(self, table_name):
        TablePath = self._QSArgs.MainDir+os.sep+table_name
        with self._DataLock:
            if os.path.isdir(TablePath):
                shutil.rmtree(TablePath, ignore_errors=True)
        return 0
    def setTableMetaData(self, table_name, key=None, value=None, meta_data=None):
        with self._DataLock:
            iZTable = zarr.open(self._QSArgs.MainDir+os.sep+table_name, mode="a")
            if key is not None:
                if key in iZTable.attrs:
                    del iZTable.attrs[key]
                if isinstance(value, np.ndarray):
                    iZTable.attrs[key] = {"_Type":"Array", "List":value.tolist()}
                elif isinstance(value, pd.Series):
                    iZTable.attrs[key] = {"_Type":"Series", "Json":value.to_json(index=True)}
                elif isinstance(value, pd.DataFrame):
                    iZTable.attrs[key] = {"_Type":"DataFrame", "Json":value.to_json(index=True)}
                elif value is not None:
                    iZTable.attrs[key] = value
        if meta_data is not None:
            for iKey in meta_data:
                self.setTableMetaData(table_name, key=iKey, value=meta_data[iKey], meta_data=None)
        return 0
    # ----------------------------因子操作---------------------------------
    def renameFactor(self, table_name, old_factor_name, new_factor_name):
        if old_factor_name==new_factor_name: return 0
        with self._DataLock:
            iZTable = zarr.open(self._QSArgs.MainDir+os.sep+table_name, mode="a")
            if old_factor_name not in iZTable: raise __QS_Error__("ZarrDB.renameFactor: 表 ’%s' 中不存在因子 '%s'!" % (table_name, old_factor_name))
            if new_factor_name in iZTable: raise __QS_Error__("ZarrDB.renameFactor: 表 ’%s' 中的因子 '%s' 已存在!" % (table_name, new_factor_name))
            iZTable[new_factor_name] = iZTable.pop(old_factor_name)
            DataType = iZTable.attrs.get("DataType", {})
            DataType[new_factor_name] = DataType.pop(old_factor_name)
            iZTable.attrs["DataType"] = DataType
        return 0
    def deleteFactor(self, table_name, factor_names):
        TablePath = self._QSArgs.MainDir+os.sep+table_name
        with self._DataLock:
            iZTable = zarr.open(TablePath, mode="a")
            DataType = iZTable.attrs.get("DataType", {})
            if set(DataType).issubset(set(factor_names)):
                shutil.rmtree(TablePath, ignore_errors=True)
            else:
                for iFactor in factor_names:
                    if iFactor in iZTable: del iZTable[iFactor]
                    DataType.pop(iFactor, None)
                iZTable.attrs["DataType"] = DataType
        return 0
    def setFactorMetaData(self, table_name, ifactor_name, key=None, value=None, meta_data=None):
        with self._DataLock:
            iZTable = zarr.open(self._QSArgs.MainDir+os.sep+table_name, mode="a")
            iZFactor = iZTable[ifactor_name]
            if key is not None:
                if key in iZFactor.attrs:
                    del iZFactor.attrs[key]
                if isinstance(value, np.ndarray):
                    iZFactor.attrs[key] = {"_Type":"Array", "List":value.tolist()}
                elif isinstance(value, pd.Series):
                    iZFactor.attrs[key] = {"_Type":"Series", "Json":value.to_json(index=True)}
                elif isinstance(value, pd.DataFrame):
                    iZFactor.attrs[key] = {"_Type":"DataFrame", "Json":value.to_json(index=True)}
                elif value is not None:
                    iZFactor.attrs[key] = value
        if meta_data is not None:
            for iKey in meta_data:
                self.setFactorMetaData(table_name, ifactor_name=ifactor_name, key=iKey, value=meta_data[iKey], meta_data=None)
        return 0
    def _updateFactorData(self, factor_data, table_name, ifactor_name, data_type):
        TablePath = self._QSArgs.MainDir+os.sep+table_name
        with self._DataLock:
            ZTable = zarr.open(TablePath, mode="a")
            ZFactor = ZTable[ifactor_name]
            OldDateTimes, OldIDs = ZFactor["DateTime"][:], ZFactor["ID"][:]
            NewDateTimes = factor_data.index.difference(OldDateTimes).values
            NewIDs = factor_data.columns.difference(OldIDs).values
            ZFactor["DateTime"].append(NewDateTimes, axis=0)
            ZFactor["ID"].append(NewIDs, axis=0)
            ZFactor["Data"].resize((ZFactor["DateTime"].shape[0], ZFactor["ID"].shape[0]))
            IDIndices = pd.Series(np.arange(ZFactor["ID"].shape[0]), index=np.r_[OldIDs, NewIDs]).reindex(factor_data.columns).tolist()
            DTIndices = pd.Series(np.arange(ZFactor["DateTime"].shape[0]), index=np.r_[OldDateTimes, NewDateTimes]).reindex(factor_data.index).tolist()
            if data_type!="double": factor_data = factor_data.where(pd.notnull(factor_data), None)
            else: factor_data = factor_data.astype("float")
            ZFactor["Data"].set_orthogonal_selection((DTIndices, IDIndices), factor_data.values)
        return 0
    def writeFactorData(self, factor_data, table_name, ifactor_name, if_exists="update", data_type=None, **kwargs):
        TablePath = self._QSArgs.MainDir+os.sep+table_name
        with self._DataLock:
            ZTable = zarr.open(TablePath, mode="a")
            if ifactor_name not in ZTable:
                factor_data, data_type = _identifyDataType(factor_data, data_type)
                ZFactor = ZTable.create_group(ifactor_name, overwrite=True)
                ZFactor.create_dataset("ID", shape=(factor_data.shape[1], ), data=factor_data.columns.values, dtype=object, object_codec=numcodecs.VLenUTF8(), overwrite=True)
                ZFactor.create_dataset("DateTime", shape=(factor_data.shape[0], ), data=factor_data.index.values, dtype="M8[ns]", overwrite=True)
                if data_type=="double":
                    ZFactor.create_dataset("Data", shape=factor_data.shape, data=factor_data.values, dtype="f8", fill_value=np.nan, overwrite=True)
                elif data_type=="string":
                    ZFactor.create_dataset("Data", shape=factor_data.shape, data=factor_data.values, dtype=object, object_codec=numcodecs.VLenUTF8(), overwrite=True)
                elif data_type=="object":
                    ZFactor.create_dataset("Data", shape=factor_data.shape, data=factor_data.values, dtype=object, object_codec=numcodecs.Pickle(), overwrite=True)
                ZFactor.attrs["DataType"] = data_type
                DataType = ZTable.attrs.get("DataType", {})
                DataType[ifactor_name] = data_type
                ZTable.attrs["DataType"] = DataType
                return 0
        if if_exists=="update":
            self._updateFactorData(factor_data, table_name, ifactor_name, data_type)
        else:
            OldData = self.getTable(table_name).readFactorData(ifactor_name=ifactor_name, ids=factor_data.columns.tolist(), dts=factor_data.index.tolist())
            if if_exists=="append":
                factor_data = OldData.where(pd.notnull(OldData), factor_data)
            elif if_exists=="update_notnull":
                factor_data = factor_data.where(pd.notnull(factor_data), OldData)
            else:
                Msg = ("因子库 '%s' 调用方法 writeData 错误: 不支持的写入方式 '%s'!" % (self.Name, str(if_exists)))
                self._QS_Logger.error(Msg)
                raise __QS_Error__(Msg)
            self._updateFactorData(factor_data, table_name, ifactor_name, data_type)
        return 0
    def writeData(self, data, table_name, if_exists="update", data_type={}, **kwargs):
        for i, iFactor in enumerate(data.items):
            self.writeFactorData(data.iloc[i], table_name, iFactor, if_exists=if_exists, data_type=data_type.get(iFactor, None), **kwargs)
        return 0

class FactorDBService(rpyc.core.SlaveService):
    FTs = {}
    
if __name__=="__main__1":
    from rpyc.utils.server import ThreadedServer
    
    import QuantStudio.api as QS
    
    HDB = QS.FactorDB.HDF5DB().connect()
    print(HDB.TableNames)
    
    FTs = {
        "stock_cn_day_bar": HDB.getTable("stock_cn_day_bar")
    }
    FactorDBService.FTs = FTs
    
    Server = ThreadedServer(FactorDBService, port=18812, protocol_config={'allow_all_attrs': True, "allow_pickle": True})
    Server.start()

if __name__=="__main__":
    from QuantStudio.FactorDataBase.HDF5DB import HDF5DB
    from QSExt.FactorDataBase.RPyCDB import RPyCDB
    RDB = RPyCDB().connect()
    print(RDB.TableNames)
    
    HDB = HDF5DB().connect()
    
    RFT = RDB.getTable("stock_cn_day_bar")
    LFT = HDB.getTable("stock_cn_day_bar")
    
    d = RFT.readFactorData("close", None, None)
    
    RF = RFT.getFactor("close")
    LF = LFT.getFactor("close")
    F = RF + LF
    
    Data = F.readData(None, None)
    
    print("===")