# coding=utf-8
"""基于 ClickHouse 数据库的因子库"""
import os
import datetime as dt
from typing import List, Optional, Dict, Literal

import numpy as np
import pandas as pd
from pydantic import Field

from QuantStudio.Tools.SQLDBFun import genSQLInCondition
from QSExt.Tools.ClickHouseFun import QSClickHouseObject
from QuantStudio import __QS_ConfigPath__
from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.SQLDB import SQLDB
from QuantStudio.Factor.FactorUtils import SQL_Table, SQL_WideTable, SQL_FeatureTable, SQL_MappingTable, SQL_NarrowTable, SQL_TimeSeriesTable

def _identifyFieldType(factor_data, data_type=None):
    if (data_type is None) or (data_type=="double"):
        try:
            factor_data = factor_data.astype(float)
        except:
            FieldType = "Nullable(String)"
            factor_data = factor_data.where(pd.notnull(factor_data), None)
        else:
            FieldType = "Float64"
    else:
        FieldType = "Nullable(String)"
    return (factor_data, FieldType)

class ClickHouseDB(QSClickHouseObject, SQLDB):
    """ClickHouseDB"""

    class __QS_ArgClass__(QSClickHouseObject.__QS_ArgClass__, SQLDB.__QS_ArgClass__):
        Name: str = Field(default="ClickHouseDB", title="名称", frozen=True)
        CheckWriteData: bool = Field(default=False, title="检查写入值", frozen=False)

    def __init__(self, args={}, config_file=None, **kwargs):
        super().__init__(args=args, config_file=(__QS_ConfigPath__+os.sep+"ClickHouseDBConfig.json" if config_file is None else config_file), **kwargs)

    def _genFactorInfo(self, factor_info):
        factor_info["FieldName"] = factor_info["DBFieldName"]
        factor_info["FieldType"] = "因子"
        DataTypeStr = factor_info["DataType"].str
        DTMask = DataTypeStr.contains("date", case=False)
        factor_info.loc[DTMask, "FieldType"] = "Date"
        StrMask = (DataTypeStr.contains("str", case=False) | DataTypeStr.contains("uuid", case=False) | DataTypeStr.contains("ip", case=False))
        factor_info.loc[(factor_info["DBFieldName"].str.lower()==self._QSArgs.IDField) & StrMask, "FieldType"] = "ID"
        factor_info["Supplementary"] = None
        factor_info.loc[DTMask & (factor_info["DBFieldName"].str.lower()==self._QSArgs.DTField), "Supplementary"] = "Default"
        factor_info["Description"] = ""
        factor_info["FieldKey"] = None
        factor_info = factor_info.set_index(["TableName", "FieldName"])
        return factor_info

    def connect(self):
        QSClickHouseObject.connect(self)
        nPrefix = len(self._QSArgs.InnerPrefix)
        SQLStr = f"SELECT RIGHT(table, CHAR_LENGTH(table)-{nPrefix}) AS TableName, table AS DBTableName, name AS DBFieldName, LOWER(type) AS DataType FROM system.columns WHERE database='{self._QSArgs.DBName}' "
        SQLStr += f"AND table LIKE '{self._QSArgs.InnerPrefix}%%' "
        if len(self._QSArgs.IgnoreFields)>0:
            SQLStr += "AND name NOT IN ('"+"','".join(self._QSArgs.IgnoreFields)+"') "
        SQLStr += "ORDER BY TableName, DBFieldName"
        self._FactorInfo = pd.read_sql_query(SQLStr, self._Connection, index_col=None)
        self._TableInfo = self._FactorInfo.loc[:, ["TableName", "DBTableName"]].copy().groupby(by=["TableName"], as_index=True).last().sort_index()
        self._TableInfo["TableClass"] = "WideTable"
        self._FactorInfo.pop("DBTableName")
        self._FactorInfo = self._genFactorInfo(self._FactorInfo)
        return self

    def getTable(self, table_name, args={}):
        Args = self._initFTArgs(table_name=table_name, args=args)
        return eval("SQL_"+Args["TableType"]+"(fdb=self, args=Args, table_info=self._TableInfo.loc[table_name], factor_info=self._FactorInfo.loc[table_name], logger=self._QS_Logger)")

    def createTable(self, table_name, field_types):
        FieldTypes = field_types.copy()
        FieldTypes[self._QSArgs.DTField] = FieldTypes.pop(self._QSArgs.DTField, "DateTime")
        FieldTypes[self._QSArgs.IDField] = FieldTypes.pop(self._QSArgs.IDField, "String")
        self.createDBTable(self._QSArgs.InnerPrefix+table_name, FieldTypes, primary_keys=[self._QSArgs.IDField], index_fields=[self._QSArgs.IDField])
        self._TableInfo = pd.concat([self._TableInfo, pd.DataFrame([[self._QSArgs.InnerPrefix+table_name, "WideTable"]], columns=["DBTableName", "TableClass"], index=[table_name])])
        NewFactorInfo = pd.DataFrame(FieldTypes, index=["DataType"], columns=pd.Index(sorted(FieldTypes.keys()), name="DBFieldName")).T.reset_index()
        NewFactorInfo["TableName"] = table_name
        self._FactorInfo = pd.concat([self._FactorInfo, self._genFactorInfo(NewFactorInfo)])
        return 0

    def addFactor(self, table_name, field_types):
        if table_name not in self._TableInfo.index: return self.createTable(table_name, field_types)
        self.addField(self._QSArgs.InnerPrefix+table_name, field_types)
        NewFactorInfo = pd.DataFrame(field_types, index=["DataType"], columns=pd.Index(sorted(field_types.keys()), name="DBFieldName")).T.reset_index()
        NewFactorInfo["TableName"] = table_name
        self._FactorInfo = pd.concat([self._FactorInfo, self._genFactorInfo(NewFactorInfo)]).sort_index()
        return 0

    def deleteData(self, table_name, ids=None, dts=None, dt_ids=None):
        if table_name not in self._TableInfo.index:
            Msg = ("因子库 '%s' 调用方法 deleteData 错误: 不存在因子表 '%s'!" % (self.Name, table_name))
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        if (ids is None) and (dts is None): return self.truncateDBTable(self._QSArgs.InnerPrefix+table_name)
        DBTableName = self._QSArgs.TablePrefix+self._QSArgs.InnerPrefix+table_name
        SQLStr = "ALTER TABLE "+DBTableName+" DELETE "
        if dts is not None:
            DTs = [iDT.strftime("%Y-%m-%d %H:%M:%S") for iDT in dts]
            SQLStr += "WHERE "+genSQLInCondition(self._QSArgs.DTField, DTs, is_str=True, max_num=1000)+" "
        else:
            SQLStr += "WHERE "+self._QSArgs.DTField+" IS NOT NULL "
        if ids is not None:
            SQLStr += "AND "+genSQLInCondition(self._QSArgs.IDField, ids, is_str=True, max_num=1000)
        if dt_ids is not None:
            dt_ids = ["('"+iDTIDs[0].strftime("%Y-%m-%d %H:%M:%S")+"', '"+iDTIDs[1]+"')" for iDTIDs in dt_ids]
            SQLStr += "AND "+genSQLInCondition("("+self._QSArgs.DTField+", "+self._QSArgs.IDField+")", dt_ids, is_str=False, max_num=1000)
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 deleteData 删除表 '%s' 中数据时错误: %s" % (self.Name, table_name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        return 0

    def _adjustWriteData(self, data, table_name):
        NewData = []
        DataLen = data.applymap(lambda x: len(x) if isinstance(x, list) else 1)
        DataLenMax = DataLen.max(axis=1)
        DataLenMin = DataLen.min(axis=1)
        if (DataLenMax!=DataLenMin).sum()>0:
            self._QS_Logger.warning("'%s' 在写入因子 '%s' 时出现因子值长度不一致的情况, 将填充缺失!" % (self.Name, str(data.columns.tolist())))
        for i in range(data.shape[0]):
            iDataLen = DataLenMax.iloc[i]
            if iDataLen>0:
                iData = data.iloc[i].apply(lambda x: [None]*(iDataLen-len(x))+x if isinstance(x, list) else [x]*iDataLen).tolist()
                NewData.extend(zip(*iData))
        NewData = pd.DataFrame(NewData, dtype="O", columns=data.columns)
        factor_info = self._FactorInfo.loc[table_name]
        factor_info = factor_info.loc[data.columns[2:]]
        DataTypeStr = factor_info["DataType"].str
        NumMask = (DataTypeStr.contains("decimal") | DataTypeStr.contains("int") | DataTypeStr.contains("float") | DataTypeStr.contains("num"))
        for i, iFactorName in enumerate(factor_info.index):
            if NumMask.iloc[i]:
                NewData[iFactorName] = NewData[iFactorName].astype(float)
            else:
                NewData[iFactorName] = NewData[iFactorName].astype("O").where(pd.notnull(NewData[iFactorName]), None)
        return NewData.to_records(index=False).tolist()

    def _adjustListData(self, data, table_name):
        factor_info = self._FactorInfo.loc[table_name]
        factor_info = factor_info.loc[data.columns]
        DataTypeStr = factor_info["DataType"].str
        ListMask = (DataTypeStr.contains("array") | DataTypeStr.contains("tuple"))
        NumMask = (DataTypeStr.contains("decimal") | DataTypeStr.contains("int") | DataTypeStr.contains("float") | DataTypeStr.contains("num"))
        for i, iFactorName in enumerate(factor_info.index):
            if ListMask.iloc[i]:
                data[iFactorName] = data[iFactorName].apply(lambda x: [] if pd.isnull(x) else x)
            elif NumMask.iloc[i]:
                data[iFactorName] = data[iFactorName].astype(float)
            else:
                data[iFactorName] = data[iFactorName].astype("O").where(pd.notnull(data[iFactorName]), None)
        return data

    def writeData(self, data, table_name, if_exists="update", data_type={}, **kwargs):
        FieldTypes = {}
        for i, iFactorName in enumerate(data.items):
            data[iFactorName], FieldTypes[iFactorName] = _identifyFieldType(data[iFactorName], data_type.get(iFactorName, None))
        if table_name not in self._TableInfo.index:
            self.createTable(table_name, field_types=FieldTypes)
        else:
            NewFactorNames = data.items.difference(self._FactorInfo.loc[table_name].index).tolist()
            if NewFactorNames:
                self.addFactor(table_name, {iFactorName: FieldTypes[iFactorName] for iFactorName in NewFactorNames})
            if if_exists=="update":
                OldFactorNames = self._FactorInfo.loc[table_name].index.difference(data.items).difference({self._QSArgs.IDField, self._QSArgs.DTField}).tolist()
                if OldFactorNames:
                    if self._QSArgs.CheckWriteData:
                        OldData = self.getTable(table_name, args={"MultiMapping": True}).readData(factor_names=OldFactorNames, ids=data.minor_axis.tolist(), dts=data.major_axis.tolist())
                    else:
                        OldData = self.getTable(table_name, args={"MultiMapping": False}).readData(factor_names=OldFactorNames, ids=data.minor_axis.tolist(), dts=data.major_axis.tolist())
                    for iFactorName in OldFactorNames: data[iFactorName] = OldData[iFactorName]
            else:
                AllFactorNames = self._FactorInfo.loc[table_name].index.difference({self._QSArgs.IDField, self._QSArgs.DTField}).tolist()
                if self._QSArgs.CheckWriteData:
                    OldData = self.getTable(table_name, args={"MultiMapping": True}).readData(factor_names=AllFactorNames, ids=data.minor_axis.tolist(), dts=data.major_axis.tolist())
                else:
                    OldData = self.getTable(table_name, args={"MultiMapping": False}).readData(factor_names=AllFactorNames, ids=data.minor_axis.tolist(), dts=data.major_axis.tolist())
                if if_exists=="append":
                    for iFactorName in AllFactorNames:
                        if iFactorName in data:
                            data[iFactorName] = OldData[iFactorName].where(pd.notnull(OldData[iFactorName]), data[iFactorName])
                        else:
                            data[iFactorName] = OldData[iFactorName]
                elif if_exists=="update_notnull":
                    for iFactorName in AllFactorNames:
                        if iFactorName in data:
                            data[iFactorName] = data[iFactorName].where(pd.notnull(data[iFactorName]), OldData[iFactorName])
                        else:
                            data[iFactorName] = OldData[iFactorName]
                else:
                    Msg = ("因子库 '%s' 调用方法 writeData 错误: 不支持的写入方式 '%s'!" % (self.Name, str(if_exists)))
                    self._QS_Logger.error(Msg)
                    raise __QS_Error__(Msg)
        SQLStr = f"INSERT INTO {self._QSArgs.TablePrefix+self._QSArgs.InnerPrefix+table_name} (`{self._QSArgs.DTField}`, `{self._QSArgs.IDField}`, "
        NewData = {}
        for iFactorName in data.items:
            iData = data.loc[iFactorName].stack(future_stack=True)
            NewData[iFactorName] = iData
            SQLStr += "`"+iFactorName+"`, "
        NewData = pd.DataFrame(NewData).loc[:, data.items]
        Mask = pd.notnull(NewData).any(axis=1)
        NewData = NewData[Mask]
        if NewData.shape[0]==0: return 0
        SQLStr = SQLStr[:-2] + ") VALUES "
        self.deleteData(table_name, ids=data.minor_axis.tolist(), dts=data.major_axis.tolist())
        Cursor = self.cursor()
        if self._QSArgs.CheckWriteData:
            NewData = self._adjustWriteData(NewData.reset_index(), table_name)
        else:
            NewData = self._adjustListData(NewData, table_name).reset_index().values.tolist()
        Cursor.executemany(SQLStr, NewData)
        self._Connection.commit()
        Cursor.close()
        return 0
