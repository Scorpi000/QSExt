# coding=utf-8
"""基于 SQLite3 数据库的因子库"""
import os
import datetime as dt
from typing import List, Optional, Dict, Tuple, Literal, Any

import numpy as np
import pandas as pd
from pydantic import Field

from QuantStudio import __QS_ConfigPath__
from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.QSObject import Panel
from QuantStudio.Factor.FactorDB import WritableFactorDB
from QuantStudio.Factor.FactorUtils import SQL_WideTable, SQL_FeatureTable, SQL_MappingTable, SQL_NarrowTable, SQL_TimeSeriesTable, SQL_ConstituentTable, SQL_FinancialTable, SQL_Table
from QuantStudio.Tools.SQLDBFun import genSQLInCondition


def _identifyDataType(dtypes):
    if np.dtype("O") in dtypes.values:
        return "text"
    else:
        return "real"


class SQLite3DB(WritableFactorDB):
    """基于SQLite3的因子库"""

    class __QS_ArgClass__(WritableFactorDB.__QS_ArgClass__):
        Name: str = Field(default="SQLite3DB", title="名称", frozen=True)
        DBFile: str = Field(default="", title="SQLite3文件", frozen=True)
        InnerPrefix: str = Field(default="qs_", title="内部前缀", frozen=True)
        DTField: str = Field(default="datetime", title="时点字段", frozen=True)
        IDField: str = Field(default="code", title="ID字段", frozen=True)
        DTFmt: str = Field(default="%Y-%m-%d %H:%M:%S", title="时点格式", frozen=True)
        IgnoreFields: List[str] = Field(default=[], title="忽略字段", frozen=True)
        FTArgs: dict = Field(default={}, title="因子表参数", frozen=True)
        TablePrefix: str = Field(default="", title="表名前缀", frozen=True)
        CheckWriteData: bool = Field(default=False, title="检查写入值", frozen=False)
        CheckNullable: bool = Field(default=False, title="检查缺失容许", frozen=False)

    def __init__(self, args={}, config_file=None, **kwargs):
        self._Connection = None
        self._TableInfo = pd.DataFrame()
        self._FactorInfo = pd.DataFrame()
        super().__init__(args=args, config_file=(__QS_ConfigPath__+os.sep+"SQLite3DBConfig.json" if config_file is None else config_file), **kwargs)

    # -------------------- 连接管理 --------------------
    @property
    def Connection(self):
        return self._Connection

    def cursor(self):
        if self._Connection is None:
            Msg = f"'{self.Name}' 获取 cursor 失败: 数据库尚未连接!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        return self._Connection.cursor()

    def execute(self, sql_str: str):
        if self._Connection is None:
            Msg = f"'{self.Name}' 执行 SQL 命令失败: 数据库尚未连接!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        Cursor = self._Connection.cursor()
        Cursor.execute(sql_str)
        self._Connection.commit()
        Cursor.close()

    def fetchall(self, sql_str: str):
        if self._Connection is None:
            Msg = f"'{self.Name}' 执行 SQL 查询失败: 数据库尚未连接!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        Cursor = self._Connection.cursor()
        Cursor.execute(sql_str)
        Data = Cursor.fetchall()
        Cursor.close()
        return Data

    def connect(self):
        import sqlite3
        self._Connection = sqlite3.connect(self._QSArgs.DBFile)
        nPrefix = len(self._QSArgs.InnerPrefix)
        SQLStr = f"SELECT name AS DBTableName FROM sqlite_master WHERE type='table' AND name LIKE '{self._QSArgs.InnerPrefix}%' ORDER BY name"
        Result = pd.read_sql_query(SQLStr, self._Connection)
        if Result.shape[0] == 0:
            self._TableInfo = pd.DataFrame(columns=["DBTableName", "Description", "TableClass"])
            self._FactorInfo = pd.DataFrame(columns=["DBFieldName", "DataType", "FieldType", "Supplementary", "Description", "Nullable", "FieldKey"])
            self._FactorInfo.index = pd.MultiIndex.from_tuples([], names=["TableName", "FieldName"])
            return self

        self._TableInfo = Result
        self._TableInfo["TableName"] = self._TableInfo["DBTableName"].apply(lambda x: x[nPrefix:])
        self._TableInfo["Description"] = ""
        self._TableInfo["TableClass"] = "WideTable"
        self._TableInfo = self._TableInfo.set_index(["TableName"])

        Cursor = self._Connection.cursor()
        FactorInfoList = []
        for iTableName in self._TableInfo.index:
            Cursor.execute(f"PRAGMA table_info([{self._QSArgs.InnerPrefix+iTableName}])")
            iFactorInfo = Cursor.fetchall()
            if iFactorInfo:
                iFactorInfo = pd.DataFrame(iFactorInfo, columns=["cid", "DBFieldName", "DataType", "Nullable", "DefaultValue", "FieldKey"])
                iFactorInfo = iFactorInfo[~iFactorInfo["DBFieldName"].isin(self._QSArgs.IgnoreFields)]
                if iFactorInfo.shape[0] > 0:
                    iFactorInfo["TableName"] = iTableName
                    FactorInfoList.append(iFactorInfo[["TableName", "DBFieldName", "DataType", "Nullable", "FieldKey"]])

        if FactorInfoList:
            self._FactorInfo = pd.concat(FactorInfoList, ignore_index=True)
            self._FactorInfo = self._genFactorInfo(self._FactorInfo)
        else:
            self._FactorInfo = pd.DataFrame(columns=["DBFieldName", "DataType", "FieldType", "Supplementary", "Description", "Nullable", "FieldKey"])
            self._FactorInfo.index = pd.MultiIndex.from_tuples([], names=["TableName", "FieldName"])

        return self

    def disconnect(self):
        if self._Connection is not None:
            self._Connection.close()
            self._Connection = None
        return 0

    # -------------------- 元数据整理 --------------------
    def _genFactorInfo(self, factor_info):
        factor_info["FieldName"] = factor_info["DBFieldName"]
        factor_info["FieldType"] = "因子"
        StrMask = factor_info["DataType"].str.contains("text|char", case=False)
        factor_info.loc[StrMask, "FieldType"] = "Date"
        factor_info.loc[(factor_info["DBFieldName"].str.lower() == self._QSArgs.IDField) & StrMask, "FieldType"] = "ID"
        factor_info["Supplementary"] = None
        factor_info.loc[StrMask & (factor_info["DBFieldName"].str.lower() == self._QSArgs.DTField), "Supplementary"] = "Default"
        factor_info["Description"] = ""
        if "Nullable" in factor_info.columns:
            factor_info["Nullable"] = np.where(factor_info["Nullable"].values == 1, "NO", "YES")
        if "FieldKey" in factor_info.columns:
            factor_info["FieldKey"] = np.where(factor_info["FieldKey"].values.astype(int) > 0, "PRI", None)
        factor_info = factor_info.set_index(["TableName", "FieldName"])
        return factor_info

    # -------------------- 因子表访问 --------------------
    @property
    def TableNames(self) -> List[str]:
        return sorted(self._TableInfo.index)

    def _initFTArgs(self, table_name: str, args: dict) -> dict:
        if table_name not in self._TableInfo.index:
            Msg = f"因子库 '{self.Name}' 调用方法 getTable 错误: 不存在因子表: '{table_name}'!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        Args = self._QSArgs.FTArgs.copy()
        Args.update(args)
        iFactorInfo = self._FactorInfo.loc[table_name]
        # 确定时点字段
        if "DTField" in Args:
            DTField = Args["DTField"]
        else:
            Mask = (iFactorInfo["FieldType"] == "Date")
            DTField = iFactorInfo.index[Mask & (iFactorInfo["Supplementary"] == "Default")]
            DTField = (DTField[0] if DTField.shape[0] > 0 else (iFactorInfo.index[Mask][0] if Mask.any() else None))
        # 确定 ID 字段
        if "IDField" in Args:
            IDField = Args["IDField"]
        else:
            Mask = (iFactorInfo["FieldType"] == "ID")
            IDField = (iFactorInfo.index[Mask][0] if Mask.any() else None)
        # 确定因子表类型
        if "TableType" in Args:
            TableClass = Args["TableType"]
        elif ((DTField is not None) and (IDField is not None)) or ((DTField is None) and (IDField is None)):
            TableClass = self._TableInfo.loc[table_name, "TableClass"]
        elif DTField is None:
            TableClass = "FeatureTable"
        elif IDField is None:
            TableClass = "TimeSeriesTable"
        Args["TableType"] = TableClass
        # 多重映射
        PrimaryKeys = iFactorInfo[iFactorInfo["FieldKey"] == "PRI"].index
        Args.setdefault("MultiMapping", (PrimaryKeys.difference({DTField, IDField}).shape[0] > 0))
        Args["DTFmt"] = Args.get("DTFmt", self._QSArgs.DTFmt)
        Args["Name"] = table_name
        return Args

    def getTable(self, table_name: str, args: dict = {}) -> SQL_Table:
        Args = self._initFTArgs(table_name=table_name, args=args)
        return eval(f"SQL_{Args['TableType']}(fdb=self, args=Args, table_info=self._TableInfo.loc[table_name], factor_info=self._FactorInfo.loc[table_name], logger=self._QS_Logger)")

    # -------------------- 底层表操作 --------------------
    def createDBTable(self, table_name: str, field_types: Dict[str, str], primary_keys: List[str] = [], index_fields: List[str] = []):
        SQLStr = f"CREATE TABLE IF NOT EXISTS [{self._QSArgs.TablePrefix}{table_name}] ("
        for iField, iDataType in field_types.items():
            SQLStr += f"[{iField}] {iDataType}, "
        if primary_keys:
            SQLStr += "PRIMARY KEY (" + ", ".join(f"[{k}]" for k in primary_keys) + "))"
        else:
            SQLStr = SQLStr[:-2] + ")"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = f"'{self.Name}' 调用方法 createDBTable 在数据库中创建表 '{table_name}' 时错误: {e}"
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info(f"'{self.Name}' 调用方法 createDBTable 在数据库中创建表 '{table_name}'")
        if index_fields:
            for iField in index_fields:
                try:
                    self.execute(f"CREATE INDEX IF NOT EXISTS [idx_{table_name}_{iField}] ON [{self._QSArgs.TablePrefix}{table_name}]([{iField}])")
                except Exception as e:
                    self._QS_Logger.warning(f"'{self.Name}' 调用方法 createDBTable 创建索引时错误: {e}")

    def deleteDBTable(self, table_name: str):
        SQLStr = f"DROP TABLE IF EXISTS [{self._QSArgs.TablePrefix}{table_name}]"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = f"'{self.Name}' 调用方法 deleteDBTable 从数据库中删除表 '{table_name}' 时错误: {e}"
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info(f"'{self.Name}' 调用方法 deleteDBTable 从数据库中删除表 '{table_name}'")

    def renameDBTable(self, old_table_name: str, new_table_name: str):
        SQLStr = f"ALTER TABLE [{self._QSArgs.TablePrefix}{old_table_name}] RENAME TO [{self._QSArgs.TablePrefix}{new_table_name}]"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = f"'{self.Name}' 调用方法 renameDBTable 将表 '{old_table_name}' 重命名为 '{new_table_name}' 时错误: {e}"
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info(f"'{self.Name}' 调用方法 renameDBTable 将表 '{old_table_name}' 重命名为 '{new_table_name}'")

    def addField(self, table_name: str, field_types: Dict[str, str]):
        for iField, iDataType in field_types.items():
            SQLStr = f"ALTER TABLE [{self._QSArgs.TablePrefix}{table_name}] ADD COLUMN [{iField}] {iDataType}"
            try:
                self.execute(SQLStr)
            except Exception as e:
                Msg = f"'{self.Name}' 调用方法 addField 为表 '{table_name}' 添加字段 '{iField}' 时错误: {e}"
                self._QS_Logger.error(Msg)
                raise e
            else:
                self._QS_Logger.info(f"'{self.Name}' 调用方法 addField 为表 '{table_name}' 添加字段 '{iField}'")

    def renameField(self, table_name: str, old_field_name: str, new_field_name: str):
        # SQLite3 3.25.0+ 支持 RENAME COLUMN
        SQLStr = f"ALTER TABLE [{self._QSArgs.TablePrefix}{table_name}] RENAME COLUMN [{old_field_name}] TO [{new_field_name}]"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = f"'{self.Name}' 调用方法 renameField 将表 '{table_name}' 中的字段 '{old_field_name}' 重命名为 '{new_field_name}' 时错误: {e}"
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info(f"'{self.Name}' 调用方法 renameField 将表 '{table_name}' 中的字段 '{old_field_name}' 重命名为 '{new_field_name}'")

    def deleteField(self, table_name: str, field_names: List[str]):
        if not field_names:
            return 0
        # SQLite3 3.35.0+ 支持 DROP COLUMN，逐列删除
        for iField in field_names:
            try:
                self.execute(f"ALTER TABLE [{self._QSArgs.TablePrefix}{table_name}] DROP COLUMN [{iField}]")
            except Exception as e:
                Msg = f"'{self.Name}' 调用方法 deleteField 删除表 '{table_name}' 中的字段 '{iField}' 时错误: {e}"
                self._QS_Logger.error(Msg)
                raise e
            else:
                self._QS_Logger.info(f"'{self.Name}' 调用方法 deleteField 删除表 '{table_name}' 中的字段 '{iField}'")

    def truncateDBTable(self, table_name: str):
        SQLStr = f"DELETE FROM [{self._QSArgs.TablePrefix}{table_name}]"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = f"'{self.Name}' 调用方法 truncateDBTable 清空数据库中的表 '{table_name}' 时错误: {e}"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        else:
            self._QS_Logger.info(f"'{self.Name}' 调用方法 truncateDBTable 清空数据库中的表 '{table_name}'")

    # -------------------- 因子表管理 --------------------
    def renameTable(self, old_table_name: str, new_table_name: str):
        if old_table_name not in self._TableInfo.index:
            Msg = f"因子库 '{self.Name}' 调用方法 renameTable 错误: 不存在因子表 '{old_table_name}'!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        if (new_table_name != old_table_name) and (new_table_name in self._TableInfo.index):
            Msg = f"因子库 '{self.Name}' 调用方法 renameTable 错误: 新因子表名 '{new_table_name}' 已经存在于库中!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        self.renameDBTable(self._QSArgs.InnerPrefix + old_table_name, self._QSArgs.InnerPrefix + new_table_name)
        self._TableInfo = self._TableInfo.rename(index={old_table_name: new_table_name})
        self._FactorInfo = self._FactorInfo.rename(index={old_table_name: new_table_name}, level=0)

    def createTable(self, table_name: str, field_types: Dict[str, str]):
        FieldTypes = field_types.copy()
        FieldTypes[self._QSArgs.DTField] = FieldTypes.pop(self._QSArgs.DTField, "text NOT NULL")
        FieldTypes[self._QSArgs.IDField] = FieldTypes.pop(self._QSArgs.IDField, "text NOT NULL")
        self.createDBTable(self._QSArgs.InnerPrefix + table_name, FieldTypes, primary_keys=[self._QSArgs.DTField, self._QSArgs.IDField], index_fields=[self._QSArgs.IDField])
        self._TableInfo = pd.concat([self._TableInfo, pd.DataFrame([[self._QSArgs.InnerPrefix + table_name, "", "WideTable"]], columns=["DBTableName", "Description", "TableClass"], index=[table_name])])
        NewFactorInfo = pd.DataFrame(FieldTypes, index=["DataType"], columns=pd.Index(sorted(FieldTypes.keys()), name="DBFieldName")).T.reset_index()
        NewFactorInfo["TableName"] = table_name
        self._FactorInfo = pd.concat([self._FactorInfo, self._genFactorInfo(NewFactorInfo)])

    def deleteTable(self, table_name: str):
        if table_name not in self._TableInfo.index:
            return
        self.deleteDBTable(self._QSArgs.InnerPrefix + table_name)
        TableNames = self._TableInfo.index.tolist()
        TableNames.remove(table_name)
        self._TableInfo = self._TableInfo.loc[TableNames]
        self._FactorInfo = self._FactorInfo.loc[TableNames]

    # -------------------- 因子管理 --------------------
    def addFactor(self, table_name: str, field_types: Dict[str, str]):
        if table_name not in self._TableInfo.index:
            return self.createTable(table_name, field_types)
        self.addField(self._QSArgs.InnerPrefix + table_name, field_types)
        NewFactorInfo = pd.DataFrame(field_types, index=["DataType"], columns=pd.Index(sorted(field_types.keys()), name="DBFieldName")).T.reset_index()
        NewFactorInfo["TableName"] = table_name
        self._FactorInfo = pd.concat([self._FactorInfo, self._genFactorInfo(NewFactorInfo)]).sort_index()

    def renameFactor(self, table_name: str, old_factor_name: str, new_factor_name: str):
        if old_factor_name not in self._FactorInfo.loc[table_name].index:
            Msg = f"因子库 '{self.Name}' 调用方法 renameFactor 错误: 因子表 '{table_name}' 中不存在因子 '{old_factor_name}'!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        if (new_factor_name != old_factor_name) and (new_factor_name in self._FactorInfo.loc[table_name].index):
            Msg = f"因子库 '{self.Name}' 调用方法 renameFactor 错误: 新因子名 '{new_factor_name}' 已经存在于因子表 '{table_name}' 中!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        self.renameField(self._QSArgs.InnerPrefix + table_name, old_factor_name, new_factor_name)
        TableNames = self._TableInfo.index.tolist()
        TableNames.remove(table_name)
        self._FactorInfo = pd.concat([self._FactorInfo.loc[TableNames], self._FactorInfo.loc[[table_name]].rename(index={old_factor_name: new_factor_name}, level=1)])

    def deleteFactor(self, table_name: str, factor_names: List[str]):
        if (not factor_names) or (table_name not in self._TableInfo.index):
            return 0
        FactorIndex = self._FactorInfo.loc[table_name].index.difference(factor_names).tolist()
        if not FactorIndex:
            return self.deleteTable(table_name)
        self.deleteField(self._QSArgs.InnerPrefix + table_name, factor_names)
        TableNames = self._TableInfo.index.tolist()
        TableNames.remove(table_name)
        Remaining = self._FactorInfo.loc[table_name].loc[FactorIndex]
        Remaining.index = pd.MultiIndex.from_product([[table_name], Remaining.index], names=["TableName", "FieldName"])
        self._FactorInfo = pd.concat([self._FactorInfo.loc[TableNames], Remaining])

    # -------------------- 数据操作 --------------------
    def deleteData(self, table_name: str, ids: Optional[List[str]] = None, dts: Optional[List[dt.datetime]] = None, dt_ids: Optional[List[Tuple[dt.datetime, str]]] = None):
        if table_name not in self._TableInfo.index:
            Msg = f"因子库 '{self.Name}' 调用方法 deleteData 错误: 不存在因子表 '{table_name}'!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        if (ids is None) and (dts is None):
            return self.truncateDBTable(self._QSArgs.InnerPrefix + table_name)
        DBTableName = self._QSArgs.TablePrefix + self._QSArgs.InnerPrefix + table_name
        IDField = f"[{DBTableName}].[{self._QSArgs.IDField}]"
        DTField = f"[{DBTableName}].[{self._QSArgs.DTField}]"
        SQLStr = f"DELETE FROM [{DBTableName}] "
        if dts is not None:
            DTs = [iDT.strftime("%Y-%m-%d %H:%M:%S.%f") for iDT in dts]
            SQLStr += f"WHERE ({genSQLInCondition(DTField, DTs, is_str=True, max_num=1000)}) "
        else:
            SQLStr += f"WHERE {DTField} IS NOT NULL "
        if ids is not None:
            SQLStr += f"AND ({genSQLInCondition(IDField, ids, is_str=True, max_num=1000)}) "
        if dt_ids is not None:
            dt_ids = ["('" + iDTIDs[0].strftime("%Y-%m-%d %H:%M:%S.%f") + "', '" + iDTIDs[1] + "')" for iDTIDs in dt_ids]
            SQLStr += f"AND ({genSQLInCondition(f'({DTField}, {IDField})', dt_ids, is_str=False, max_num=1000)})"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = f"'{self.Name}' 调用方法 deleteData 删除表 '{table_name}' 中数据时错误: {e}"
            self._QS_Logger.error(Msg)
            raise e

    def _adjustWriteData(self, data, table_name):
        NewData = []
        DataLen = data.applymap(lambda x: max(1, len(x)) if isinstance(x, list) else 1)
        DataLenMax = DataLen.iloc[:, 2:].max(axis=1)
        DataLenMin = DataLen.iloc[:, 2:].min(axis=1)
        if (DataLenMax != DataLenMin).sum() > 0:
            self._QS_Logger.warning(f"'{self.Name}' 在写入因子 '{str(data.columns.tolist())}' 时出现因子值长度不一致的情况, 将填充缺失!")
        for i in range(data.shape[0]):
            iDataLen = DataLenMax.iloc[i]
            if iDataLen > 0:
                iData = data.iloc[i].apply(lambda x: [None] * (iDataLen - len(x)) + x if isinstance(x, list) else [x] * iDataLen).tolist()
                NewData.extend(zip(*iData))
        NewData = pd.DataFrame(NewData, columns=data.columns, dtype="O")
        if self._QSArgs.CheckNullable:
            NewData = self._dropWriteDataNa(NewData, table_name)
        iDataType = self._FactorInfo["DataType"].loc[table_name]
        StrftimeFun = lambda d: d.strftime("%Y-%m-%d %H:%M:%S.%f") if isinstance(d, dt.datetime) else (d.strftime("%Y-%m-%d") if isinstance(d, dt.date) else None)
        for iFactorName in iDataType[iDataType.str.contains("date")].index:
            NewData[iFactorName] = NewData[iFactorName].apply(StrftimeFun)
        return NewData.where(pd.notnull(NewData), None).to_records(index=False).tolist()

    def _dropWriteDataNa(self, data, table_name):
        DropNaFields = self._FactorInfo["Nullable"].loc[table_name].loc[data.columns]
        DropNaFields = DropNaFields[DropNaFields == "NO"].index.tolist()
        if DropNaFields:
            OldRowNum = data.shape[0]
            data = data.dropna(subset=DropNaFields)
            if data.shape[0] < OldRowNum:
                self._QS_Logger.warning(f"因子库 {self.Name} 中的因子表 {table_name} 中的字段 {DropNaFields} 不允许 NULL, 但写入数据中出现 NULL, 删除相应行后执行写入!")
        return data

    def writeData(self, data: Panel, table_name: str, if_exists: Literal["update", "replace", "append"] = "update", data_type: Dict[str, Literal["double", "string", "object"]] = {}, **kwargs):
        if table_name not in self._TableInfo.index:
            FieldTypes = {iFactorName: _identifyDataType(data.iloc[i].dtypes) for i, iFactorName in enumerate(data.items)}
            try:
                self.createTable(table_name, field_types=FieldTypes)
            except Exception as e:
                self.connect()
                if table_name not in self._TableInfo.index:
                    raise e
        else:
            NewFactorNames = data.items.difference(self._FactorInfo.loc[table_name].index).tolist()
            if NewFactorNames:
                FieldTypes = {iFactorName: _identifyDataType(data.iloc[i].dtypes) for i, iFactorName in enumerate(NewFactorNames)}
                try:
                    self.addFactor(table_name, FieldTypes)
                except Exception as e:
                    self.connect()
                    if data.items.difference(self._FactorInfo.loc[table_name].index).shape[0] > 0:
                        raise e
            if if_exists == "update":
                OldFactorNames = self._FactorInfo.loc[table_name].index.difference(data.items).difference({self._QSArgs.IDField, self._QSArgs.DTField}).tolist()
                if OldFactorNames:
                    if self._QSArgs.CheckWriteData:
                        OldData = self.getTable(table_name, args={"MultiMapping": True}).readData(factor_names=OldFactorNames, ids=data.minor_axis.tolist(), dts=data.major_axis.tolist())
                    else:
                        OldData = self.getTable(table_name, args={"MultiMapping": False}).readData(factor_names=OldFactorNames, ids=data.minor_axis.tolist(), dts=data.major_axis.tolist())
                    for iFactorName in OldFactorNames:
                        data[iFactorName] = OldData[iFactorName]
            else:
                AllFactorNames = self._FactorInfo.loc[table_name].index.difference({self._QSArgs.IDField, self._QSArgs.DTField}).tolist()
                if self._QSArgs.CheckWriteData:
                    OldData = self.getTable(table_name, args={"MultiMapping": True}).readData(factor_names=AllFactorNames, ids=data.minor_axis.tolist(), dts=data.major_axis.tolist())
                else:
                    OldData = self.getTable(table_name, args={"MultiMapping": False}).readData(factor_names=AllFactorNames, ids=data.minor_axis.tolist(), dts=data.major_axis.tolist())
                if if_exists == "append":
                    for iFactorName in AllFactorNames:
                        if iFactorName in data:
                            data[iFactorName] = OldData[iFactorName].where(pd.notnull(OldData[iFactorName]), data[iFactorName])
                        else:
                            data[iFactorName] = OldData[iFactorName]
                elif if_exists == "update_notnull":
                    for iFactorName in AllFactorNames:
                        if iFactorName in data:
                            data[iFactorName] = data[iFactorName].where(pd.notnull(data[iFactorName]), OldData[iFactorName])
                        else:
                            data[iFactorName] = OldData[iFactorName]
                else:
                    Msg = f"因子库 '{self.Name}' 调用方法 writeData 错误: 不支持的写入方式 '{if_exists}'!"
                    self._QS_Logger.error(Msg)
                    raise __QS_Error__(Msg)

        DTs = data.major_axis
        data.major_axis = DTs.astype(str)
        NewData = {}
        for iFactorName in data.items:
            iData = data.loc[iFactorName].stack(dropna=False)
            NewData[iFactorName] = iData
        NewData = pd.DataFrame(NewData).loc[:, data.items]
        Mask = pd.notnull(NewData).any(axis=1)
        NewData = NewData[Mask]
        if NewData.shape[0] == 0:
            return

        DimFields = [self._QSArgs.DTField, self._QSArgs.IDField]
        Fields = DimFields + list(data.items)
        Placeholders = ", ".join(["?"] * len(Fields))
        SQLStr = f"INSERT OR REPLACE INTO [{self._QSArgs.TablePrefix}{self._QSArgs.InnerPrefix}{table_name}] ([{'], ['.join(Fields)}]) VALUES ({Placeholders})"

        Cursor = self.cursor()
        if self._QSArgs.CheckWriteData:
            NewData = self._adjustWriteData(NewData.reset_index(), table_name)
            self.deleteData(table_name, ids=data.minor_axis.tolist(), dts=DTs.tolist())
            Cursor.executemany(SQLStr, NewData)
        else:
            NewData = NewData.astype("O").where(pd.notnull(NewData), None)
            if self._QSArgs.CheckNullable:
                NewData = self._dropWriteDataNa(NewData, table_name)
            iDataType = self._FactorInfo["DataType"].loc[table_name]
            StrftimeFun = lambda d: d.strftime("%Y-%m-%d %H:%M:%S.%f") if isinstance(d, dt.datetime) else (d.strftime("%Y-%m-%d") if isinstance(d, dt.date) else None)
            for iFactorName in iDataType[iDataType.str.contains("date")].index:
                NewData[iFactorName] = NewData[iFactorName].apply(StrftimeFun)
            Cursor.executemany(SQLStr, NewData.reset_index().values.tolist())
        self._Connection.commit()
        Cursor.close()


if __name__ == "__main__":
    SDB = SQLite3DB(args={
        "DBFile": "D:/Project/Research/QSDemo/Data/SQLite3/TestData.sqlite3",
        "InnerPrefix": "",
        "DTField": "datetime",
        "IDField": "code",
        "DTFmt": "%Y-%m-%d",
        "FTArgs": {"IgnoreTime": True},
    })
    SDB.connect()

    TargetTable = "test_FinancialTable1"
    SQLStr = f"SELECT * FROM [{TargetTable}]"
    print("库原始数据 : ")
    print(pd.read_sql_query(SQLStr, SDB.Connection))

    DTs = [dt.datetime(2022, 1, 17), dt.datetime(2022, 1, 18)]
    IDs = ["000001.SZ"]

    Args = {
        "TableType": "FinancialTable",
        "DTField": "report_date",
        "公告时点字段": "ann_dt",
        "报告期": "年报",
        "计算方法": "最新",
        "回溯年数": 1,
        "回溯期数": 0,
    }
    FT = SDB.getTable(TargetTable, args=Args)
    print("参数 : ")
    print(Args)
    print("数据 : ")
    print(FT.readData(factor_names=["factor1", "factor2"], ids=IDs, dts=DTs).iloc[:, :, 0])
