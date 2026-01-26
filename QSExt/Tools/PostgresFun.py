# -*- coding: utf-8 -*-
import os

import numpy as np
import pandas as pd
from traits.api import Enum, Str

from QuantStudio import __QS_Error__
from QuantStudio.FactorDataBase.FactorDB import FactorDB
from QuantStudio.Tools.QSObjects import QSSQLObject


class QSPostgresObject(QSSQLObject):
    """PostgresDB"""
    class __QS_ArgClass__(QSSQLObject.__QS_ArgClass__, FactorDB.__QS_ArgClass__):
        Name = Str("PGDB", arg_type="String", label="名称", order=-100)
        DBType = Enum("Postgres", arg_type="SingleOption", label="数据库类型", order=0)
        Connector = Enum("default", "psycopg", arg_type="SingleOption", label="连接器", order=7)

    def _connect(self):
        self._Connection = None
        if (self._QSArgs.Connector=="psycopg") or (self._QSArgs.Connector=="default"):
            try:
                import psycopg
                self._Connection = psycopg.connect(user=self._QSArgs.User, password=self._QSArgs.Pwd, host=self._QSArgs.IPAddr, port=self._QSArgs.Port, dbname=self._QSArgs.DBName)
            except Exception as e:
                Msg = ("'%s' 尝试使用 psycopg 连接(%s@%s:%d)数据库 '%s' 失败: %s" % (self._QSArgs.Name, self._QSArgs.User, self._QSArgs.IPAddr, self._QSArgs.Port, self._QSArgs.DBName, str(e)))
                self._QS_Logger.error(Msg)
                if self._QSArgs.Connector!="default": raise e
            else:
                self._Connector = "psycopg"
        self._PID = os.getpid()
        return 0

    def connect(self):
        self._connect()
        if not self._QSArgs.AdjustTableName:
            self._AllTables = []
        else:
            self._AllTables = self.getDBTable()
        # 设置特异性参数
        # 设置 SQL 相关特异性函数
        self._SQLFun = {"toDate": "CAST(%s AS DATE)"}
        return self

    def renameDBTable(self, old_table_name, new_table_name):
        SQLStr = "ALTER TABLE "+self.TablePrefix+old_table_name+" RENAME TO "+self.TablePrefix+new_table_name
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 renameDBTable 将表 '%s' 重命名为 '%s' 时错误: %s" % (self._QSArgs.Name, old_table_name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info("'%s' 调用方法 renameDBTable 将表 '%s' 重命名为 '%s'" % (self._QSArgs.Name, old_table_name, new_table_name))
        return 0

    def createDBTable(self, table_name, field_types, primary_keys=[], index_fields=[]):
        SQLStr = "CREATE TABLE IF NOT EXISTS %s (" % (self._QSArgs.TablePrefix + table_name)
        for iField, iDataType in field_types.items(): SQLStr += "`%s` %s, " % (iField, iDataType)
        if primary_keys:
            SQLStr += "PRIMARY KEY (`" + "`,`".join(primary_keys) + "`))"
        else:
            SQLStr = SQLStr[:-2] + ")"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 createDBTable 在数据库中创建表 '%s' 时错误: %s" % (self._QSArgs.Name, table_name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info("'%s' 调用方法 createDBTable 在数据库中创建表 '%s'" % (self._QSArgs.Name, table_name))
        if not index_fields: return 0
        try:
            self.addIndex(table_name+"_index", table_name, fields=index_fields)
        except Exception as e:
            self._QS_Logger.warning("'%s' 调用方法 createDBTable 在数据库中创建表 '%s' 时错误: %s" % (self._QSArgs.Name, table_name, str(e)))
        return 0

    def getDBTable(self):
        try:
            SQLStr = "SELECT * FROM pg_tables WHERE schemaname = 'public';"
            AllTables = self.fetchall(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 getDBTable 时错误: %s" % (self._QSArgs.Name, str(e)))
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        else:
            return [rslt[0] for rslt in AllTables]

    def addIndex(self, index_name, table_name, fields):
        SQLStr = "CREATE INDEX "+index_name+" ON "+self._QSArgs.TablePrefix+table_name+"("+", ".join(fields)+")"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 addIndex 为表 '%s' 添加索引时错误: %s" % (self._QSArgs.Name, table_name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info("'%s' 调用方法 addIndex 为表 '%s' 添加索引 '%s'" % (self._QSArgs.Name, table_name, index_name))
        return 0

    def getFieldDataType(self, table_format=None, ignore_fields=[]):
        try:
            SQLStr = "SELECT table_name, column_name, data_type FROM information_schema.columns"
            TableField, ColField = "table_name", "column_name"
            if isinstance(table_format, str) and table_format:
                SQLStr += ("AND %s LIKE '%s' " % (TableField, table_format))
            if ignore_fields:
                SQLStr += "AND "+ColField+" NOT IN ('"+"', '".join(ignore_fields)+"') "
            SQLStr += ("ORDER BY %s, %s" % (TableField, ColField))
            Rslt = self.fetchall(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 getFieldDataType 获取字段数据类型信息时错误: %s" % (self._QSArgs.Name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        return pd.DataFrame(Rslt, columns=["Table", "Field", "DataType"])

    def addField(self, table_name, field_types):
        SQLStr = "ALTER TABLE %s " % (self._QSArgs.TablePrefix+table_name)
        for iField in field_types:
            SQLStr += " ADD COLUMN %s %s, " % (iField, field_types[iField])
        SQLStr = SQLStr[:-2]+")"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 addField 为表 '%s' 添加字段时错误: %s" % (self._QSArgs.Name, table_name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info("'%s' 调用方法 addField 为表 '%s' 添加字段 ’%s'" % (self._QSArgs.Name, table_name, str(list(field_types.keys()))))
        return 0

    def renameField(self, table_name, old_field_name, new_field_name):
        DataType = self.getFieldDataType(table_format=table_name)
        try:
            # 添加新列
            AddSQL = f"""ALTER TABLE {self._QSArgs.TablePrefix + table_name} ADD COLUMN {new_field_name} {DataType[old_field_name]}"""
            self.execute(AddSQL)
            # 复制数据
            UpdateSQL = f"""UPDATE {self._QSArgs.TablePrefix + table_name} SET {new_field_name} = {old_field_name}"""
            self.execute(UpdateSQL)
            # 删除旧列
            DelSQL = f"""ALTER TABLE {self._QSArgs.TablePrefix + table_name} DROP COLUMN {old_field_name}"""
            self.execute(DelSQL)
        except Exception as e:
            Msg = ("'%s' 调用方法 renameField 将表 '%s' 中的字段 '%s' 重命名为 '%s' 时错误: %s" % (self._QSArgs.Name, table_name, old_field_name, new_field_name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info("'%s' 调用方法 renameField 在将表 '%s' 中的字段 '%s' 重命名为 '%s'" % (self._QSArgs.Name, table_name, old_field_name, new_field_name))
        return 0

if __name__=="__main__":
    PGDB = QSPostgresObject(sys_args={"IP地址": "127.0.0.1", "端口": 5432, "数据库名": "qsakb", "用户名": "hst", "密码": "shuntai11"}).connect()
    print(PGDB.getDBTable())

    print("===")