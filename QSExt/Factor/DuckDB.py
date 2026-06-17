# coding=utf-8
"""基于 DuckDB 数据库的因子库"""
import os
import datetime as dt
from pathlib import Path
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


def _quote(name: str) -> str:
    """DuckDB 使用双引号引用标识符"""
    return '"' + name + '"'


def _identifyDataType(dtypes):
    if np.dtype("O") in dtypes.values:
        return "VARCHAR"
    else:
        return "DOUBLE"


class DuckDB(WritableFactorDB):
    """基于 DuckDB 的因子库"""

    class __QS_ArgClass__(WritableFactorDB.__QS_ArgClass__):
        Name: str = Field(default="DuckDB", title="名称", frozen=True)
        DBFile: str = Field(default=":memory:", title="DuckDB文件", frozen=True)
        InnerPrefix: str = Field(default="qs_", title="内部前缀", frozen=True)
        DTField: str = Field(default="datetime", title="时点字段", frozen=True)
        IDField: str = Field(default="code", title="ID字段", frozen=True)
        DTFmt: str = Field(default="%Y-%m-%d %H:%M:%S", title="时点格式", frozen=True)
        IgnoreFields: List[str] = Field(default=[], title="忽略字段", frozen=True)
        FTArgs: dict = Field(default={}, title="因子表参数", frozen=True)
        TablePrefix: str = Field(default="", title="表名前缀", frozen=True)
        CheckWriteData: bool = Field(default=False, title="检查写入值", frozen=False)
        CheckNullable: bool = Field(default=False, title="检查缺失容许", frozen=False)
        ParquetDir: str = Field(default="", title="Parquet目录", frozen=True, description="Parquet 文件根目录，设置后将自动注册各 data_class 子目录为 DuckDB 视图")

    def __init__(self, args={}, config_file=None, **kwargs):
        self._Connection = None
        self._TableInfo = pd.DataFrame()
        self._FactorInfo = pd.DataFrame()
        self._ParquetTables = set()
        self._SQLFun = {"toDate": "CAST(%s AS DATE)", "toString": "CAST(%s AS VARCHAR)"}
        super().__init__(args=args, config_file=(__QS_ConfigPath__+os.sep+"DuckDBConfig.json" if config_file is None else config_file), **kwargs)

    # -------------------- Parquet 外部数据源 --------------------
    def _registerParquetViews(self, parquet_dir: str):
        """扫描 Parquet 目录，为每个 data_class 创建 DuckDB 视图"""
        root = Path(parquet_dir)
        if not root.is_dir():
            self._QS_Logger.warning(f"'{self.Name}' Parquet 目录不存在: {parquet_dir}")
            return
        for dc_dir in sorted(root.iterdir()):
            if not dc_dir.is_dir() or dc_dir.name == "exceptions":
                continue
            dc_name = dc_dir.name
            view_name = self._QSArgs.InnerPrefix + dc_name
            # 如果已有同名原生表则跳过
            if dc_name in self._TableInfo.index:
                continue
            glob_pattern = str(dc_dir / "**" / "*.parquet").replace("\\", "/")
            try:
                self._Connection.execute(
                    f"CREATE OR REPLACE VIEW \"{view_name}\" AS "
                    f"SELECT * FROM read_parquet('{glob_pattern}', hive_partitioning=true)"
                )
            except Exception as e:
                self._QS_Logger.warning(f"'{self.Name}' 创建 Parquet 视图 '{dc_name}' 失败: {e}")
                continue
            iFactorInfo = self._Connection.execute(f"PRAGMA table_info('{view_name}')").fetchall()
            if not iFactorInfo:
                continue
            iFactorInfo = pd.DataFrame(iFactorInfo, columns=["cid", "DBFieldName", "DataType", "Nullable", "DefaultValue", "FieldKey"])
            iFactorInfo = iFactorInfo[~iFactorInfo["DBFieldName"].isin(self._QSArgs.IgnoreFields)]
            if iFactorInfo.shape[0] == 0:
                continue
            iFactorInfo["TableName"] = dc_name
            self._TableInfo = pd.concat([
                self._TableInfo,
                pd.DataFrame([[view_name, "", "WideTable"]], columns=["DBTableName", "Description", "TableClass"], index=[dc_name])
            ])
            self._FactorInfo = pd.concat([self._FactorInfo, self._genFactorInfo(iFactorInfo)])
            self._ParquetTables.add(dc_name)
            self._QS_Logger.info(f"'{self.Name}' 已注册 Parquet 视图: {dc_name} ({iFactorInfo.shape[0]} 个字段)")

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
        self._Connection.execute(sql_str)

    def fetchall(self, sql_str: str):
        if self._Connection is None:
            Msg = f"'{self.Name}' 执行 SQL 查询失败: 数据库尚未连接!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        return self._Connection.execute(sql_str).fetchall()

    def connect(self):
        import duckdb
        self._Connection = duckdb.connect(self._QSArgs.DBFile)
        nPrefix = len(self._QSArgs.InnerPrefix)
        SQLStr = f"SELECT table_name AS DBTableName FROM information_schema.tables WHERE table_name LIKE '{self._QSArgs.InnerPrefix}%' ORDER BY table_name"
        Result = self._Connection.execute(SQLStr).df()
        if Result.shape[0] == 0:
            self._TableInfo = pd.DataFrame(columns=["DBTableName", "Description", "TableClass"])
            self._FactorInfo = pd.DataFrame(columns=["DBFieldName", "DataType", "FieldType", "Supplementary", "Description", "Nullable", "FieldKey"])
            self._FactorInfo.index = pd.MultiIndex.from_tuples([], names=["TableName", "FieldName"])
        else:
            self._TableInfo = Result
            self._TableInfo["TableName"] = self._TableInfo["DBTableName"].apply(lambda x: x[nPrefix:])
            self._TableInfo["Description"] = ""
            self._TableInfo["TableClass"] = "WideTable"
            self._TableInfo = self._TableInfo.set_index(["TableName"])

            FactorInfoList = []
            for iTableName in self._TableInfo.index:
                iDBTableName = self._QSArgs.InnerPrefix + iTableName
                iFactorInfo = self._Connection.execute(f"PRAGMA table_info('{iDBTableName}')").fetchall()
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

        # 注册 Parquet 外部数据源
        ParquetDir = self._QSArgs.ParquetDir
        if ParquetDir:
            self._registerParquetViews(ParquetDir)

        return self

    def disconnect(self):
        if self._Connection is not None:
            self._Connection.close()
            self._Connection = None
            self._ParquetTables.clear()
        return 0

    # -------------------- 元数据整理 --------------------
    def _genFactorInfo(self, factor_info):
        factor_info["FieldName"] = factor_info["DBFieldName"]
        factor_info["FieldType"] = "因子"
        StrMask = factor_info["DataType"].str.contains("varchar|text|char|string", case=False)
        DateMask = StrMask | factor_info["DataType"].str.contains("timestamp|datetime|date", case=False)
        factor_info.loc[DateMask, "FieldType"] = "Date"
        factor_info.loc[(factor_info["DBFieldName"].str.lower() == self._QSArgs.IDField) & StrMask, "FieldType"] = "ID"
        factor_info["Supplementary"] = None
        factor_info.loc[DateMask & (factor_info["DBFieldName"].str.lower() == self._QSArgs.DTField), "Supplementary"] = "Default"
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
    def _checkNotParquet(self, table_name: str, method_name: str):
        if table_name in self._ParquetTables:
            Msg = f"'{self.Name}' 调用方法 {method_name} 错误: Parquet 视图 '{table_name}' 为只读!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)

    def createDBTable(self, table_name: str, field_types: Dict[str, str], primary_keys: List[str] = [], index_fields: List[str] = []):
        qt = _quote
        SQLStr = f"CREATE TABLE IF NOT EXISTS {qt(self._QSArgs.TablePrefix + table_name)} ("
        for iField, iDataType in field_types.items():
            SQLStr += f"{qt(iField)} {iDataType}, "
        SQLStr = SQLStr[:-2] + ")"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = f"'{self.Name}' 调用方法 createDBTable 在数据库中创建表 '{table_name}' 时错误: {e}"
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info(f"'{self.Name}' 调用方法 createDBTable 在数据库中创建表 '{table_name}'")

    def deleteDBTable(self, table_name: str):
        SQLStr = f"DROP TABLE IF EXISTS {_quote(self._QSArgs.TablePrefix + table_name)}"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = f"'{self.Name}' 调用方法 deleteDBTable 从数据库中删除表 '{table_name}' 时错误: {e}"
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info(f"'{self.Name}' 调用方法 deleteDBTable 从数据库中删除表 '{table_name}'")

    def renameDBTable(self, old_table_name: str, new_table_name: str):
        SQLStr = f"ALTER TABLE {_quote(self._QSArgs.TablePrefix + old_table_name)} RENAME TO {_quote(self._QSArgs.TablePrefix + new_table_name)}"
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
            SQLStr = f"ALTER TABLE {_quote(self._QSArgs.TablePrefix + table_name)} ADD COLUMN {_quote(iField)} {iDataType}"
            try:
                self.execute(SQLStr)
            except Exception as e:
                Msg = f"'{self.Name}' 调用方法 addField 为表 '{table_name}' 添加字段 '{iField}' 时错误: {e}"
                self._QS_Logger.error(Msg)
                raise e
            else:
                self._QS_Logger.info(f"'{self.Name}' 调用方法 addField 为表 '{table_name}' 添加字段 '{iField}'")

    def renameField(self, table_name: str, old_field_name: str, new_field_name: str):
        SQLStr = f"ALTER TABLE {_quote(self._QSArgs.TablePrefix + table_name)} RENAME COLUMN {_quote(old_field_name)} TO {_quote(new_field_name)}"
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
        for iField in field_names:
            try:
                self.execute(f"ALTER TABLE {_quote(self._QSArgs.TablePrefix + table_name)} DROP COLUMN {_quote(iField)}")
            except Exception as e:
                # DuckDB 在有索引时不允许 DROP COLUMN，尝试先删除所有索引
                try:
                    indexes = self._Connection.execute(f"SELECT index_name FROM duckdb_indexes WHERE table_name = '{self._QSArgs.TablePrefix + table_name}'").fetchall()
                    for idx in indexes:
                        self.execute(f"DROP INDEX IF EXISTS {idx[0]}")
                    self.execute(f"ALTER TABLE {_quote(self._QSArgs.TablePrefix + table_name)} DROP COLUMN {_quote(iField)}")
                except Exception as e2:
                    Msg = f"'{self.Name}' 调用方法 deleteField 删除表 '{table_name}' 中的字段 '{iField}' 时错误: {e2}"
                    self._QS_Logger.error(Msg)
                    raise e2
            else:
                self._QS_Logger.info(f"'{self.Name}' 调用方法 deleteField 删除表 '{table_name}' 中的字段 '{iField}'")

    def truncateDBTable(self, table_name: str):
        SQLStr = f"DELETE FROM {_quote(self._QSArgs.TablePrefix + table_name)}"
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
        self._checkNotParquet(old_table_name, "renameTable")
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
        self._checkNotParquet(table_name, "createTable")
        FieldTypes = field_types.copy()
        FieldTypes[self._QSArgs.DTField] = FieldTypes.pop(self._QSArgs.DTField, "VARCHAR NOT NULL")
        FieldTypes[self._QSArgs.IDField] = FieldTypes.pop(self._QSArgs.IDField, "VARCHAR NOT NULL")
        self.createDBTable(self._QSArgs.InnerPrefix + table_name, FieldTypes, primary_keys=[self._QSArgs.DTField, self._QSArgs.IDField], index_fields=[self._QSArgs.IDField])
        self._TableInfo = pd.concat([self._TableInfo, pd.DataFrame([[self._QSArgs.InnerPrefix + table_name, "", "WideTable"]], columns=["DBTableName", "Description", "TableClass"], index=[table_name])])
        NewFactorInfo = pd.DataFrame(FieldTypes, index=["DataType"], columns=pd.Index(sorted(FieldTypes.keys()), name="DBFieldName")).T.reset_index()
        NewFactorInfo["TableName"] = table_name
        self._FactorInfo = pd.concat([self._FactorInfo, self._genFactorInfo(NewFactorInfo)])

    def deleteTable(self, table_name: str):
        if table_name not in self._TableInfo.index:
            return
        if table_name in self._ParquetTables:
            SQLStr = f"DROP VIEW IF EXISTS {_quote(self._QSArgs.TablePrefix + self._QSArgs.InnerPrefix + table_name)}"
            self.execute(SQLStr)
            self._ParquetTables.discard(table_name)
            self._QS_Logger.info(f"'{self.Name}' 调用方法 deleteTable 删除 Parquet 视图 '{table_name}'")
        else:
            self.deleteDBTable(self._QSArgs.InnerPrefix + table_name)
        TableNames = self._TableInfo.index.tolist()
        TableNames.remove(table_name)
        self._TableInfo = self._TableInfo.loc[TableNames]
        self._FactorInfo = self._FactorInfo.loc[TableNames]

    # -------------------- 因子管理 --------------------
    def addFactor(self, table_name: str, field_types: Dict[str, str]):
        self._checkNotParquet(table_name, "addFactor")
        if table_name not in self._TableInfo.index:
            return self.createTable(table_name, field_types)
        self.addField(self._QSArgs.InnerPrefix + table_name, field_types)
        NewFactorInfo = pd.DataFrame(field_types, index=["DataType"], columns=pd.Index(sorted(field_types.keys()), name="DBFieldName")).T.reset_index()
        NewFactorInfo["TableName"] = table_name
        self._FactorInfo = pd.concat([self._FactorInfo, self._genFactorInfo(NewFactorInfo)]).sort_index()

    def renameFactor(self, table_name: str, old_factor_name: str, new_factor_name: str):
        self._checkNotParquet(table_name, "renameFactor")
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
        self._checkNotParquet(table_name, "deleteFactor")
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

    # -------------------- 元数据操作 --------------------
    def setTableMetaData(self, table_name: str, key: Optional[str] = None, value: Any = None, meta_data: Optional[dict] = None):
        if meta_data is not None:
            for k, v in meta_data.items():
                self._TableInfo.loc[table_name, k] = v
        elif key is not None:
            self._TableInfo.loc[table_name, key] = value

    def setFactorMetaData(self, table_name: str, ifactor_name: str, key: Optional[str] = None, value: Any = None, meta_data: Optional[dict] = None):
        if meta_data is not None:
            for k, v in meta_data.items():
                self._FactorInfo.loc[(table_name, ifactor_name), k] = v
        elif key is not None:
            self._FactorInfo.loc[(table_name, ifactor_name), key] = value

    # -------------------- 数据操作 --------------------
    def deleteData(self, table_name: str, ids: Optional[List[str]] = None, dts: Optional[List[dt.datetime]] = None, dt_ids: Optional[List[Tuple[dt.datetime, str]]] = None):
        self._checkNotParquet(table_name, "deleteData")
        if table_name not in self._TableInfo.index:
            Msg = f"因子库 '{self.Name}' 调用方法 deleteData 错误: 不存在因子表 '{table_name}'!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        if (ids is None) and (dts is None):
            return self.truncateDBTable(self._QSArgs.InnerPrefix + table_name)
        DBTableName = self._QSArgs.TablePrefix + self._QSArgs.InnerPrefix + table_name
        qtn = _quote(DBTableName)
        IDField = f"{qtn}.{_quote(self._QSArgs.IDField)}"
        DTField = f"{qtn}.{_quote(self._QSArgs.DTField)}"
        SQLStr = f"DELETE FROM {qtn} "
        if dts is not None:
            DTs = [iDT.strftime(self._QSArgs.DTFmt) for iDT in dts]
            SQLStr += f"WHERE ({genSQLInCondition(DTField, DTs, is_str=True, max_num=1000)}) "
        else:
            SQLStr += f"WHERE {DTField} IS NOT NULL "
        if ids is not None:
            SQLStr += f"AND ({genSQLInCondition(IDField, ids, is_str=True, max_num=1000)}) "
        if dt_ids is not None:
            dt_ids = ["('" + iDTIDs[0].strftime(self._QSArgs.DTFmt) + "', '" + iDTIDs[1] + "')" for iDTIDs in dt_ids]
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
        DTFmt = self._QSArgs.DTFmt
        iDataType = self._FactorInfo["DataType"].loc[table_name]
        StrftimeFun = lambda d: d.strftime(DTFmt) if isinstance(d, dt.datetime) else (d.strftime("%Y-%m-%d") if isinstance(d, dt.date) else None)
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
        if table_name in self._ParquetTables:
            Msg = f"'{self.Name}' 调用方法 writeData 错误: 不支持写入 Parquet 视图 '{table_name}'，请使用原生 DuckDB 表!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
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
        data.major_axis = [iDT.strftime(self._QSArgs.DTFmt) if isinstance(iDT, (dt.datetime, dt.date)) else str(iDT) for iDT in DTs]
        NewData = {}
        for iFactorName in data.items:
            iData = data.loc[iFactorName].stack(future_stack=True)
            NewData[iFactorName] = iData
        NewData = pd.DataFrame(NewData).loc[:, data.items]
        Mask = pd.notnull(NewData).any(axis=1)
        NewData = NewData[Mask]
        if NewData.shape[0] == 0:
            return

        DimFields = [self._QSArgs.DTField, self._QSArgs.IDField]
        Fields = DimFields + list(data.items)
        Placeholders = ", ".join(["?"] * len(Fields))
        FullTableName = self._QSArgs.TablePrefix + self._QSArgs.InnerPrefix + table_name
        SQLStr = f"INSERT INTO {_quote(FullTableName)} ({_quote(Fields[0])}"
        for f in Fields[1:]:
            SQLStr += f", {_quote(f)}"
        SQLStr += f") VALUES ({Placeholders})"

        # 先删除冲突的数据（dt, code 复合键）
        self.deleteData(table_name, ids=data.minor_axis.tolist(), dts=DTs.tolist())
        if self._QSArgs.CheckWriteData:
            NewData = self._adjustWriteData(NewData.reset_index(), table_name)
            self._Connection.executemany(SQLStr, NewData)
        else:
            NewData = NewData.astype("O").where(pd.notnull(NewData), None)
            if self._QSArgs.CheckNullable:
                NewData = self._dropWriteDataNa(NewData, table_name)
            DTFmt = self._QSArgs.DTFmt
            iDataType = self._FactorInfo["DataType"].loc[table_name]
            StrftimeFun = lambda d: d.strftime(DTFmt) if isinstance(d, dt.datetime) else (d.strftime("%Y-%m-%d") if isinstance(d, dt.date) else None)
            for iFactorName in iDataType[iDataType.str.contains("date")].index:
                NewData[iFactorName] = NewData[iFactorName].apply(StrftimeFun)
            self._Connection.executemany(SQLStr, NewData.reset_index().values.tolist())


if __name__ == "__main__":
    import datetime as dt

    DDB = DuckDB()
    DDB.connect()

    # 测试写入
    print("=== 测试写入数据 ===")
    DTs = [dt.datetime(2024, 1, 15), dt.datetime(2024, 1, 16), dt.datetime(2024, 1, 17)]
    IDs = ["000001.SZ", "000002.SZ", "000004.SZ"]

    Data = pd.DataFrame([
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
        [7.0, 8.0, 9.0],
    ], index=DTs, columns=IDs)
    FactorData = Panel({"factor1": Data, "factor2": Data * 2})

    DDB.writeData(FactorData, "test_table", if_exists="replace")
    print("写入完成，表列表:", DDB.TableNames)

    # 测试读取
    print("\n=== 测试读取数据 ===")
    FT = DDB.getTable("test_table")
    print("因子列表:", FT.FactorNames)
    print("ID 列表:", FT.getID())
    print("时点列表:", FT.getDateTime(start_dt=dt.datetime(2024, 1, 1), end_dt=dt.datetime(2024, 2, 1)))

    ReadData = FT.readData(factor_names=["factor1", "factor2"], ids=IDs, dts=DTs)
    print("\n读取的数据:")
    print(ReadData)

    # 测试追加
    print("\n=== 测试追加因子 ===")
    DDB.addFactor("test_table", {"factor3": "DOUBLE"})
    FT = DDB.getTable("test_table")
    print("追加后因子列表:", FT.FactorNames)

    # 测试删除因子
    print("\n=== 测试删除因子 ===")
    DDB.deleteFactor("test_table", ["factor3"])
    FT = DDB.getTable("test_table")
    print("删除后因子列表:", FT.FactorNames)

    # 测试重命名
    print("\n=== 测试重命名 ===")
    DDB.renameTable("test_table", "renamed_table")
    print("重命名后表列表:", DDB.TableNames)

    # 测试删除表
    print("\n=== 测试删除表 ===")
    DDB.deleteTable("renamed_table")
    print("删除后表列表:", DDB.TableNames)

    DDB.disconnect()
    print("\n所有测试完成!")

    # 测试 Parquet 外部数据源
    print("\n\n=== 测试 Parquet 外部数据源 ===")
    import tempfile, pyarrow.parquet as pq, pyarrow as pa

    with tempfile.TemporaryDirectory() as tmpdir:
        # 模拟 DataScrapy 的 Hive 分区 Parquet 目录结构
        parquet_dir = os.path.join(tmpdir, "parquet_data")
        table_dir = os.path.join(parquet_dir, "stock_cn_minute_bar")
        for day in ["2026-06-01", "2026-06-02"]:
            dt_dir = os.path.join(table_dir, f"dt={day}")
            os.makedirs(dt_dir, exist_ok=True)
            pq.write_table(
                pa.table({
                    "source": ["test"] * 4,
                    "code": ["000001.SZ", "000002.SZ", "000001.SZ", "000002.SZ"],
                    "datetime": [f"{day} 09:30:00", f"{day} 09:30:00",
                                 f"{day} 10:00:00", f"{day} 10:00:00"],
                    "open": [10.5, 20.3, 10.7, 20.1],
                    "high": [10.8, 20.9, 10.9, 20.5],
                    "low": [10.4, 20.1, 10.6, 20.0],
                    "close": [10.6, 20.5, 10.8, 20.3],
                    "volume": [10000.0, 20000.0, 15000.0, 18000.0],
                    "amount": [106000.0, 410000.0, 162000.0, 365400.0],
                }),
                os.path.join(dt_dir, "part-0.parquet"),
                compression="zstd",
            )

        PDDB = DuckDB(args={"ParquetDir": parquet_dir})
        PDDB.connect()
        print("Parquet 表列表:", PDDB.TableNames)

        FT = PDDB.getTable("stock_cn_minute_bar")
        print("因子列表:", [f for f in FT.FactorNames if f not in ("code", "datetime")])
        print("时点字段:", FT._QSArgs.DTField)
        print("ID 字段:", FT._QSArgs.IDField)

        DTs = FT.getDateTime(start_dt=dt.datetime(2026, 6, 1), end_dt=dt.datetime(2026, 6, 3))
        IDs = FT.getID()
        print("时点列表:", DTs)
        print("ID 列表:", IDs)

        ReadData = FT.readData(
            factor_names=["open", "high", "low", "close"],
            ids=["000001.SZ"],
            dts=DTs,
        )
        print("读取数据 shape:", ReadData.shape)
        print(ReadData)

        # 测试写入被拒绝
        try:
            PDDB.writeData(FactorData, "stock_cn_minute_bar", if_exists="replace")
            print("错误: 应该抛出异常!")
        except __QS_Error__ as e:
            print(f"写入被正确拒绝: {e}")

        # 测试 deleteTable 对 Parquet 视图
        PDDB.deleteTable("stock_cn_minute_bar")
        print("删除后表列表:", PDDB.TableNames)
        PDDB.disconnect()
        print("Parquet 测试完成!")
