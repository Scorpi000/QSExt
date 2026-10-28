# coding=utf-8
"""基于 DuckDB 数据库的因子库"""
import os
import json
import datetime as dt
import threading
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Literal, Any

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from QuantStudio import __QS_ConfigPath__
from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.QSObject import Panel
from QuantStudio.Factor.FactorDB import WritableFactorDB
from QuantStudio.Factor.FactorUtils import SQL_WideTable, SQL_FeatureTable, SQL_MappingTable, SQL_NarrowTable, SQL_TimeSeriesTable, SQL_ConstituentTable, SQL_FinancialTable, SQL_Table
from QuantStudio.Tools.SQLDBFun import genSQLInCondition
from QSExt.Factor._DuckDBCoordination import CoordinatedDB, TABLE_CLASSES, _SessionCursor, coordinated


def _quote(name: str) -> str:
    """DuckDB 使用双引号引用标识符"""
    return '"' + name.replace('"', '""') + '"'


def _identifyDataType(dtypes):
    if np.dtype("O") in dtypes.values:
        return "VARCHAR"
    else:
        return "DOUBLE"


class DuckDB(CoordinatedDB, WritableFactorDB):
    """基于 DuckDB 的因子库"""

    class __QS_ArgClass__(WritableFactorDB.__QS_ArgClass__):
        Name: str = Field(default="DuckDB", title="名称", frozen=True)
        DBFile: str = Field(default=":memory:", title="DuckDB文件", frozen=True, description="未显式指定时优先使用 ParquetDir 内已有的 _metadata.duckdb，否则使用内存库")
        CoordinatedAccess: bool = Field(default=False, title="跨进程协调访问", frozen=True, exclude=True)
        LockTimeout: float = Field(default=30, ge=0, allow_inf_nan=False, title="协调锁超时秒数", frozen=True, exclude=True)
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

        @model_validator(mode="before")
        @classmethod
        def _resolveDBFile(cls, data):
            """未指定 DBFile 时自动使用 Parquet 根目录内已有的元信息库。"""
            if isinstance(data, dict) and "DBFile" not in data and isinstance(data.get("ParquetDir"), str):
                if data["ParquetDir"]:
                    MetaFile = Path(data["ParquetDir"]) / "_metadata.duckdb"
                    if MetaFile.is_file():
                        return data | {"DBFile": str(MetaFile.resolve())}
            return data

    def __init__(self, args={}, config_file=None, **kwargs):
        self._Connection = None
        self._TableInfo = pd.DataFrame()
        self._FactorInfo = pd.DataFrame()
        self._ParquetTables = set()
        self._SQLFun = {"toDate": "CAST(%s AS DATE)", "toString": "CAST(%s AS VARCHAR)"}
        super().__init__(args=args, config_file=(__QS_ConfigPath__+os.sep+"DuckDBConfig.json" if config_file is None else config_file), **kwargs)
        self._initCoordination()

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
            view_name = self._QSArgs.TablePrefix + self._QSArgs.InnerPrefix + dc_name
            # 如果已有同名原生表则跳过
            if dc_name in self._TableInfo.index:
                continue
            glob_pattern = str(dc_dir / "**" / "*.parquet").replace("\\", "/").replace("'", "''")
            try:
                self._Connection.execute(
                    f"CREATE OR REPLACE VIEW {_quote(view_name)} AS "
                    f"SELECT * FROM read_parquet('{glob_pattern}', hive_partitioning=true)"
                )
            except Exception as e:
                self._QS_Logger.warning(f"'{self.Name}' 创建 Parquet 视图 '{dc_name}' 失败: {e}")
                continue
            iFactorInfo = self._getDBFieldInfo(view_name)
            if not iFactorInfo:
                continue
            iFactorInfo = pd.DataFrame(iFactorInfo, columns=["cid", "DBFieldName", "DataType", "Nullable", "DefaultValue", "FieldKey"])
            iFactorInfo = iFactorInfo[~iFactorInfo["DBFieldName"].isin(self._QSArgs.IgnoreFields)]
            if iFactorInfo.shape[0] == 0:
                continue
            iFactorInfo["TableName"] = dc_name
            self._TableInfo = pd.concat([
                self._TableInfo,
                pd.DataFrame([[view_name, "", "WideTable", {}]], columns=["DBTableName", "Description", "TableClass", "FTArgs"], index=[dc_name])
            ])
            self._FactorInfo = pd.concat([self._FactorInfo, self._genFactorInfo(iFactorInfo)])
            self._ParquetTables.add(dc_name)
            self._QS_Logger.info(f"'{self.Name}' 已注册 Parquet 视图: {dc_name} ({iFactorInfo.shape[0]} 个字段)")

    # -------------------- 连接管理 --------------------
    @property
    def Connection(self):
        if self.Args.CoordinatedAccess:
            if self._SessionOwner != threading.get_ident():
                return None
            self._CatalogDirty = True
        return self._Connection

    def cursor(self):
        if self.Args.CoordinatedAccess:
            if self.Connection is None:
                raise __QS_Error__("协调模式下 cursor() 只能在 with db.session(): 内使用")
            return _SessionCursor(self)
        if self._Connection is None:
            Msg = f"'{self.Name}' 获取 cursor 失败: 数据库尚未连接!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        return self._Connection.cursor()

    @coordinated
    def execute(self, sql_str: str):
        if self._Connection is None:
            Msg = f"'{self.Name}' 执行 SQL 命令失败: 数据库尚未连接!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        self._Connection.execute(sql_str)

    @coordinated
    def fetchall(self, sql_str: str):
        if self.Args.CoordinatedAccess:
            import duckdb
            if any(stmt.type != duckdb.StatementType.SELECT for stmt in duckdb.extract_statements(sql_str)):
                self._CatalogDirty = True
        if self._Connection is None:
            Msg = f"'{self.Name}' 执行 SQL 查询失败: 数据库尚未连接!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        return self._Connection.execute(sql_str).fetchall()

    @coordinated
    def _getDBFieldInfo(self, table_name):
        """读取实际字段结构，兼容名称中含引号的表和视图。"""
        Fields = self._Connection.execute(f"DESCRIBE {_quote(table_name)}").fetchall()
        return [(i, Name, Type, Nullable == "NO", Default, Key == "PRI")
                for i, (Name, Type, Nullable, Key, Default, Extra) in enumerate(Fields)]

    def connect(self):
        if self.Args.CoordinatedAccess:
            with self._coordinationThread():
                if self._SessionDepth:
                    return self
                self._LogicalConnected = True
                self._CatalogStamp = None
                try:
                    with self.session():
                        pass
                except BaseException:
                    self._LogicalConnected = False
                    raise
            return self
        import duckdb
        if self._Connection is not None:
            self.disconnect()
        self._Connection = duckdb.connect(self._QSArgs.DBFile)
        self._loadCatalog()
        return self

    def _loadCatalog(self):
        """在持有真实连接时重新读取结构和持久化元信息。"""
        Prefix = self._QSArgs.TablePrefix + self._QSArgs.InnerPrefix
        nPrefix = len(Prefix)
        SQLStr = """SELECT table_name AS DBTableName, table_type FROM information_schema.tables
                    WHERE table_catalog = current_database() AND table_schema = 'main'
                    AND starts_with(table_name, ?) ORDER BY table_name"""
        Result = self._Connection.execute(SQLStr, [Prefix]).df()
        # 磁盘数据库中的 Parquet 视图会随库文件保留，重连后仍需恢复只读标记。
        self._ParquetTables = {name[nPrefix:] for name, kind in Result.itertuples(index=False, name=None) if kind == "VIEW"}
        Result = Result.drop(columns="table_type")
        if Result.shape[0] == 0:
            self._TableInfo = pd.DataFrame(columns=["DBTableName", "Description", "TableClass", "FTArgs"])
            self._FactorInfo = pd.DataFrame(columns=["DBFieldName", "DataType", "FieldType", "Supplementary", "Description", "Nullable", "FieldKey"])
            self._FactorInfo.index = pd.MultiIndex.from_tuples([], names=["TableName", "FieldName"])
        else:
            self._TableInfo = Result
            self._TableInfo["TableName"] = self._TableInfo["DBTableName"].apply(lambda x: x[nPrefix:])
            self._TableInfo["Description"] = ""
            self._TableInfo["TableClass"] = "WideTable"
            self._TableInfo["FTArgs"] = [{} for _ in self._TableInfo.index]
            self._TableInfo = self._TableInfo.set_index(["TableName"])

            FactorInfoList = []
            for iTableName in self._TableInfo.index:
                iDBTableName = self._TableInfo.loc[iTableName, "DBTableName"]
                iFactorInfo = self._getDBFieldInfo(iDBTableName)
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
        ParquetDir = self._ParquetPath if self.Args.CoordinatedAccess else self._QSArgs.ParquetDir
        if ParquetDir:
            self._registerParquetViews(ParquetDir)

        self._loadMetaData()
        return self

    def disconnect(self):
        if self.Args.CoordinatedAccess:
            with self._coordinationThread():
                if self._SessionDepth:
                    raise __QS_Error__("不能在活动的 DuckDB session 内 disconnect")
                self._LogicalConnected = False
                self._CatalogStamp = None
                self._ParquetTables.clear()
            return 0
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
    @coordinated
    def TableNames(self) -> List[str]:
        return sorted(self._TableInfo.index)

    def _initFTArgs(self, table_name: str, args: dict) -> dict:
        if table_name not in self._TableInfo.index:
            Msg = f"因子库 '{self.Name}' 调用方法 getTable 错误: 不存在因子表: '{table_name}'!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        Args = self._QSArgs.FTArgs.copy()
        # 表级参数覆盖库级默认值，调用参数优先；复制容器以隔离各次初始化。
        Args.update(deepcopy(self._TableInfo.at[table_name, "FTArgs"]))
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

    @coordinated
    def getTable(self, table_name: str, args: dict = {}) -> SQL_Table:
        """按库级默认参数、表级 FTArgs、本次 args 的顺序合并并初始化因子表。

        Args:
            table_name: 因子表名称。
            args: 本次初始化参数，覆盖同名的库级和表级参数。

        Returns:
            使用合并参数初始化的因子表对象。
        """
        return self._makeTable(table_name, args, coordinated=self.Args.CoordinatedAccess)

    def _makeTable(self, table_name, args, coordinated):
        """使用当前结构构造原生表或协调表，调用方负责持有会话。"""
        Args = self._initFTArgs(table_name=table_name, args=args)
        cls = TABLE_CLASSES[Args["TableType"]] if coordinated else globals()["SQL_" + Args["TableType"]]
        return cls(fdb=self, args=Args, table_info=self._TableInfo.loc[table_name], factor_info=self._FactorInfo.loc[table_name], logger=self._QS_Logger)

    # -------------------- 底层表操作 --------------------
    def _checkNotParquet(self, table_name: str, method_name: str):
        if table_name in self._ParquetTables:
            Msg = f"'{self.Name}' 调用方法 {method_name} 错误: Parquet 视图 '{table_name}' 为只读!"
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)

    @coordinated
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

    @coordinated
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

    @coordinated
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

    @coordinated
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

    @coordinated
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

    @coordinated
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

    @coordinated
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
    @coordinated
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
        if new_table_name == old_table_name:
            return
        OldDBTable = self._TableInfo.at[old_table_name, "DBTableName"]
        NewDBTable = self._QSArgs.TablePrefix + self._QSArgs.InnerPrefix + new_table_name
        NewTableInfo = self._TableInfo.rename(index={old_table_name: new_table_name})
        NewTableInfo.at[new_table_name, "DBTableName"] = NewDBTable
        NewFactorInfo = self._FactorInfo.rename(index={old_table_name: new_table_name}, level=0)
        with self._transaction():
            self.renameDBTable(self._QSArgs.InnerPrefix + old_table_name, self._QSArgs.InnerPrefix + new_table_name)
            for Table in ("table_metadata", "factor_metadata"):
                if self._hasMetaDataTable(Table):
                    self._Connection.execute(
                        f"UPDATE qs_meta.{Table} SET db_table = ? WHERE db_schema = 'main' AND db_table = ?",
                        [NewDBTable, OldDBTable]
                    )
        self._TableInfo, self._FactorInfo = NewTableInfo, NewFactorInfo

    @coordinated
    def createTable(self, table_name: str, field_types: Dict[str, str]):
        self._checkNotParquet(table_name, "createTable")
        FieldTypes = field_types.copy()
        FieldTypes[self._QSArgs.DTField] = FieldTypes.pop(self._QSArgs.DTField, "VARCHAR NOT NULL")
        FieldTypes[self._QSArgs.IDField] = FieldTypes.pop(self._QSArgs.IDField, "VARCHAR NOT NULL")
        self.createDBTable(self._QSArgs.InnerPrefix + table_name, FieldTypes, primary_keys=[self._QSArgs.DTField, self._QSArgs.IDField], index_fields=[self._QSArgs.IDField])
        self._TableInfo = pd.concat([self._TableInfo, pd.DataFrame([[self._QSArgs.TablePrefix + self._QSArgs.InnerPrefix + table_name, "", "WideTable", {}]], columns=["DBTableName", "Description", "TableClass", "FTArgs"], index=[table_name])])
        NewFactorInfo = pd.DataFrame(FieldTypes, index=["DataType"], columns=pd.Index(sorted(FieldTypes.keys()), name="DBFieldName")).T.reset_index()
        NewFactorInfo["TableName"] = table_name
        self._FactorInfo = pd.concat([self._FactorInfo, self._genFactorInfo(NewFactorInfo)])

    @coordinated
    def deleteTable(self, table_name: str):
        if table_name not in self._TableInfo.index:
            return
        DBTable = self._TableInfo.at[table_name, "DBTableName"]
        with self._transaction():
            if table_name in self._ParquetTables:
                self.execute(f"DROP VIEW IF EXISTS {_quote(DBTable)}")
            else:
                self.deleteDBTable(self._QSArgs.InnerPrefix + table_name)
            for Table in ("table_metadata", "factor_metadata"):
                if self._hasMetaDataTable(Table):
                    self._Connection.execute(
                        f"DELETE FROM qs_meta.{Table} WHERE db_schema = 'main' AND db_table = ?", [DBTable]
                    )
        self._ParquetTables.discard(table_name)
        TableNames = self._TableInfo.index.tolist()
        TableNames.remove(table_name)
        self._TableInfo = self._TableInfo.loc[TableNames]
        self._FactorInfo = self._FactorInfo.loc[TableNames]

    # -------------------- 因子管理 --------------------
    @coordinated
    def addFactor(self, table_name: str, field_types: Dict[str, str]):
        self._checkNotParquet(table_name, "addFactor")
        if table_name not in self._TableInfo.index:
            return self.createTable(table_name, field_types)
        self.addField(self._QSArgs.InnerPrefix + table_name, field_types)
        NewFactorInfo = pd.DataFrame(field_types, index=["DataType"], columns=pd.Index(sorted(field_types.keys()), name="DBFieldName")).T.reset_index()
        NewFactorInfo["TableName"] = table_name
        self._FactorInfo = pd.concat([self._FactorInfo, self._genFactorInfo(NewFactorInfo)]).sort_index()

    @coordinated
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
        if new_factor_name == old_factor_name:
            return
        TableNames = self._TableInfo.index.tolist()
        TableNames.remove(table_name)
        NewFactorInfo = pd.concat([self._FactorInfo.loc[TableNames], self._FactorInfo.loc[[table_name]].rename(index={old_factor_name: new_factor_name}, level=1)])
        NewFactorInfo.at[(table_name, new_factor_name), "DBFieldName"] = new_factor_name
        with self._transaction():
            self.renameField(self._QSArgs.InnerPrefix + table_name, old_factor_name, new_factor_name)
            if self._hasMetaDataTable("factor_metadata"):
                self._Connection.execute(
                    """UPDATE qs_meta.factor_metadata SET field_name = ?
                       WHERE db_schema = 'main' AND db_table = ? AND field_name = ?""",
                    [new_factor_name, self._TableInfo.at[table_name, "DBTableName"], old_factor_name]
                )
        self._FactorInfo = NewFactorInfo

    @coordinated
    def deleteFactor(self, table_name: str, factor_names: List[str]):
        self._checkNotParquet(table_name, "deleteFactor")
        if (not factor_names) or (table_name not in self._TableInfo.index):
            return 0
        FactorIndex = self._FactorInfo.loc[table_name].index.difference(factor_names).tolist()
        if not FactorIndex:
            return self.deleteTable(table_name)
        TableNames = self._TableInfo.index.tolist()
        TableNames.remove(table_name)
        Remaining = self._FactorInfo.loc[table_name].loc[FactorIndex]
        Remaining.index = pd.MultiIndex.from_product([[table_name], Remaining.index], names=["TableName", "FieldName"])
        NewFactorInfo = pd.concat([self._FactorInfo.loc[TableNames], Remaining])
        with self._transaction():
            self.deleteField(self._QSArgs.InnerPrefix + table_name, factor_names)
            if self._hasMetaDataTable("factor_metadata"):
                self._Connection.executemany(
                    "DELETE FROM qs_meta.factor_metadata WHERE db_schema = 'main' AND db_table = ? AND field_name = ?",
                    [[self._TableInfo.at[table_name, "DBTableName"], Name] for Name in factor_names]
                )
        self._FactorInfo = NewFactorInfo

    # -------------------- 元数据操作 --------------------
    @contextmanager
    def _transaction(self):
        """在同一事务内维护数据库结构与元信息，失败时回滚。"""
        if self.Args.CoordinatedAccess:
            with self.session():
                yield
            return
        self._Connection.begin()
        try:
            yield
            self._Connection.commit()
        except Exception:
            self._Connection.rollback()
            raise

    @coordinated
    def _hasMetaDataTable(self, table_name):
        """检查元信息表是否存在，不对旧数据库执行写操作。"""
        if self._QSArgs.DBFile == ":memory:":
            return False
        return self._Connection.execute(
            """SELECT 1 FROM information_schema.tables WHERE table_catalog = current_database()
               AND table_schema = 'qs_meta' AND table_name = ?""", [table_name]
        ).fetchone() is not None

    def _ensureMetaDataTables(self):
        """首次设置磁盘库元信息时创建专用存储表。"""
        self._Connection.execute("CREATE SCHEMA IF NOT EXISTS qs_meta")
        for Table, Field in (("table_metadata", ""), ("factor_metadata", "field_name VARCHAR, ")):
            Keys = "db_schema, db_table, " + ("field_name, " if Field else "") + "meta_key"
            self._Connection.execute(
                f"CREATE TABLE IF NOT EXISTS qs_meta.{Table} ("
                f"db_schema VARCHAR, db_table VARCHAR, {Field}meta_key VARCHAR, "
                f"meta_value JSON NOT NULL, PRIMARY KEY ({Keys}))"
            )

    @staticmethod
    def _assignMetaData(info, index, values):
        """按单元格保存元信息，保留列表、字典与显式空值。"""
        for Key, Value in values.items():
            if Key not in info.columns:
                info[Key] = pd.Series(index=info.index, dtype=object)
            elif info[Key].dtype != object:
                info[Key] = info[Key].astype(object)
            info.at[index, Key] = Value

    def _loadMetaData(self):
        """将已存在表和字段的持久化元信息覆盖到结构推导结果。"""
        TableNames = dict(zip(self._TableInfo["DBTableName"], self._TableInfo.index))
        for Table, IsFactor in (("table_metadata", False), ("factor_metadata", True)):
            if not self._hasMetaDataTable(Table):
                continue
            Fields = "db_table, " + ("field_name, " if IsFactor else "") + "meta_key, meta_value"
            Rows = self._Connection.execute(f"SELECT {Fields} FROM qs_meta.{Table} WHERE db_schema = 'main'").fetchall()
            for Row in Rows:
                TableName = TableNames.get(Row[0])
                if TableName is None:
                    continue
                Info = self._FactorInfo if IsFactor else self._TableInfo
                Index = (TableName, Row[1]) if IsFactor else TableName
                if Index in Info.index:
                    Value = json.loads(Row[-1])
                    if not IsFactor and Row[-2] == "FTArgs" and not isinstance(Value, dict):
                        raise TypeError("表级元信息 'FTArgs' 必须是字典")
                    self._assignMetaData(Info, Index, {Row[-2]: Value})

    def _metaDataTarget(self, table_name, factor_name=None):
        """校验元信息目标，防止无效名称创建虚假的表或字段。"""
        if self._Connection is None:
            raise __QS_Error__("数据库尚未连接，不能修改元信息")
        if table_name not in self._TableInfo.index:
            raise __QS_Error__(f"不存在因子表: '{table_name}'")
        Info = self._TableInfo if factor_name is None else self._FactorInfo
        Index = table_name if factor_name is None else (table_name, factor_name)
        if Index not in Info.index:
            raise __QS_Error__(f"因子表 '{table_name}' 中不存在因子: '{factor_name}'")
        return Info, Index, self._TableInfo.at[table_name, "DBTableName"]

    @staticmethod
    def _validateMetaData(values):
        """校验键及 JSON 值，拒绝会在往返序列化时改变类型的对象。"""
        def CheckValue(value):
            if type(value) in (str, int, float, bool, type(None)):
                return
            if type(value) is list:
                for Item in value:
                    CheckValue(Item)
                return
            if type(value) is dict and all(isinstance(Key, str) for Key in value):
                for Item in value.values():
                    CheckValue(Item)
                return
            raise TypeError("元信息值仅支持字符串、数字、布尔值、列表、字符串键字典和 None")

        Structural = {"DBTableName", "DBFieldName", "DataType", "Nullable", "FieldKey", "TableName", "FieldName"}
        for Key, Value in values.items():
            if not isinstance(Key, str):
                raise TypeError("元信息键必须是字符串")
            if Key in Structural:
                raise __QS_Error__(f"'{Key}' 来自数据库实际结构，不能通过元信息接口修改")
            CheckValue(Value)
        return {Key: json.dumps(Value, ensure_ascii=False, allow_nan=False) for Key, Value in values.items()}

    def _setMetaData(self, table_name, factor_name, key, value, meta_data):
        """先准备缓存副本，事务提交成功后再替换内存缓存。"""
        Info, Index, DBTable = self._metaDataTarget(table_name, factor_name)
        Values = meta_data if meta_data is not None else ({key: value} if key is not None else {})
        if factor_name is None and "FTArgs" in Values and not isinstance(Values["FTArgs"], dict):
            raise TypeError("表级元信息 'FTArgs' 必须是字典")
        Encoded = self._validateMetaData(Values)
        if not Encoded:
            return
        NewInfo = Info.copy(deep=True)
        self._assignMetaData(NewInfo, Index, {Key: json.loads(Value) for Key, Value in Encoded.items()})
        if self._QSArgs.DBFile != ":memory:":
            Table = "table_metadata" if factor_name is None else "factor_metadata"
            Identity = ["main", DBTable] + ([] if factor_name is None else [factor_name])
            Rows = [Identity + [Key, Value] for Key, Value in Encoded.items()]
            Placeholders = ", ".join("?" for _ in Rows[0])
            with self._transaction():
                self._ensureMetaDataTables()
                self._Connection.executemany(
                    f"INSERT INTO qs_meta.{Table} VALUES ({Placeholders}) "
                    "ON CONFLICT DO UPDATE SET meta_value = excluded.meta_value", Rows
                )
        if factor_name is None:
            self._TableInfo = NewInfo
        else:
            self._FactorInfo = NewInfo

    @coordinated
    def setTableMetaData(self, table_name: str, key: Optional[str] = None, value: Any = None, meta_data: Optional[dict] = None):
        """设置表元信息，磁盘库立即持久化，None 表示显式空值。

        Args:
            table_name: 因子表名称。
            key: 元信息键，不允许修改数据库结构字段。
            value: JSON 支持的元信息值；FTArgs 必须为字典，用于初始化因子表参数。
            meta_data: 批量设置的键值对，提供时优先于 key 和 value。
        """
        self._setMetaData(table_name, None, key, value, meta_data)

    @coordinated
    def setFactorMetaData(self, table_name: str, ifactor_name: str, key: Optional[str] = None, value: Any = None, meta_data: Optional[dict] = None):
        """设置因子元信息，磁盘库立即持久化，None 表示显式空值。

        Args:
            table_name: 因子表名称。
            ifactor_name: 因子名称。
            key: 元信息键，不允许修改数据库结构字段。
            value: JSON 支持的元信息值。
            meta_data: 批量设置的键值对，提供时优先于 key 和 value。
        """
        self._setMetaData(table_name, ifactor_name, key, value, meta_data)

    def _deleteMetaData(self, table_name, factor_name, key):
        """删除一个覆盖值，并恢复当前数据库结构推导的默认值。"""
        self._validateMetaData({key: None})
        Info, Index, DBTable = self._metaDataTarget(table_name, factor_name)
        if factor_name is None:
            Default = {"Description": "", "TableClass": "WideTable", "FTArgs": {}}.get(key)
        else:
            Fields = self._getDBFieldInfo(DBTable)
            Defaults = pd.DataFrame(Fields, columns=["cid", "DBFieldName", "DataType", "Nullable", "DefaultValue", "FieldKey"])
            Defaults["TableName"] = table_name
            Default = self._genFactorInfo(Defaults).loc[Index].get(key)
        NewInfo = Info.copy(deep=True)
        if key in NewInfo.columns:
            self._assignMetaData(NewInfo, Index, {key: Default})
        Table = "table_metadata" if factor_name is None else "factor_metadata"
        if self._hasMetaDataTable(Table):
            SQLStr = f"DELETE FROM qs_meta.{Table} WHERE db_schema = 'main' AND db_table = ? AND meta_key = ?"
            Params = [DBTable, key]
            if factor_name is not None:
                SQLStr += " AND field_name = ?"
                Params.append(factor_name)
            with self._transaction():
                self._Connection.execute(SQLStr, Params)
        if factor_name is None:
            self._TableInfo = NewInfo
        else:
            self._FactorInfo = NewInfo

    @coordinated
    def deleteTableMetaData(self, table_name: str, key: str):
        """删除表元信息覆盖，恢复默认值。

        Args:
            table_name: 因子表名称。
            key: 待删除的元信息键。
        """
        self._deleteMetaData(table_name, None, key)

    @coordinated
    def deleteFactorMetaData(self, table_name: str, ifactor_name: str, key: str):
        """删除因子元信息覆盖，恢复当前结构推导值。

        Args:
            table_name: 因子表名称。
            ifactor_name: 因子名称。
            key: 待删除的元信息键。
        """
        self._deleteMetaData(table_name, ifactor_name, key)

    # -------------------- 数据操作 --------------------
    @coordinated
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

    @coordinated
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
