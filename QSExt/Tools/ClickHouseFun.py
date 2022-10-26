# -*- coding: utf-8 -*-
import os
import re
import mmap
import uuid
from multiprocessing import Queue, Lock
from collections import OrderedDict
import pickle

import numpy as np
import pandas as pd
from traits.api import Enum, Str, Range, Password, File, Bool, Either

from QuantStudio import __QS_Error__
from QuantStudio.Tools.QSObjects import QSSQLObject
from QuantStudio.Tools.AuxiliaryFun import genAvailableName


class QSClickHouseObject(QSSQLObject):
    """ClickHouseDB"""
    DBType = Enum("ClickHouse", arg_type="SingleOption", label="数据库类型", order=0)
    Connector = Enum("default", "clickhouse-driver", arg_type="SingleOption", label="连接器", order=7)
    def _connect(self):
        self._Connection = None
        if (self.Connector=="clickhouse-driver") or (self.Connector=="default"):
            try:
                import clickhouse_driver
                if self.DSN:
                    self._Connection = clickhouse_driver.connect(dsn=self.DSN, password=self.Pwd)
                else:
                    self._Connection = clickhouse_driver.connect(user=self.User, password=self.Pwd, host=self.IPAddr, port=self.Port, database=self.DBName)
            except Exception as e:
                Msg = ("'%s' 尝试使用 clickhouse-driver 连接(%s@%s:%d)数据库 '%s' 失败: %s" % (self.Name, self.User, self.IPAddr, self.Port, self.DBName, str(e)))
                self._QS_Logger.error(Msg)
                if self.Connector!="default": raise e
            else:
                self._Connector = "clickhouse-driver"
        self._PID = os.getpid()
        return 0
    def connect(self):
        self._connect()
        if not self.AdjustTableName:
            self._AllTables = []
        else:
            self._AllTables = self.getDBTable()
        # 设置特异性参数
        # 设置 SQL 相关特异性函数
        self._SQLFun = {"toDate": "DATE(%s)"}
        return 0
    def renameDBTable(self, old_table_name, new_table_name):
        SQLStr = "RENAME TABLE "+self.TablePrefix+old_table_name+" TO "+self.TablePrefix+new_table_name
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 renameDBTable 将表 '%s' 重命名为 '%s' 时错误: %s" % (self.Name, old_table_name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info("'%s' 调用方法 renameDBTable 将表 '%s' 重命名为 '%s'" % (self.Name, old_table_name, new_table_name))
        return 0
    def createDBTable(self, table_name, field_types, primary_keys=[], index_fields=[]):
        SQLStr = "CREATE TABLE IF NOT EXISTS %s (" % (self.TablePrefix+table_name)
        for iField in field_types: SQLStr += "`%s` %s, " % (iField, field_types[iField])
        SQLStr = SQLStr[:-2]+")"
        SQLStr += " ENGINE=MergeTree()"
        if primary_keys:
            SQLStr += " ORDER BY (`"+"`,`".join(primary_keys)+"`)"
        try:
            self.execute(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 createDBTable 在数据库中创建表 '%s' 时错误: %s" % (self.Name, table_name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info("'%s' 调用方法 createDBTable 在数据库中创建表 '%s'" % (self.Name, table_name))
        return 0
    def getDBTable(self):
        try:
            SQLStr = "SELECT name FROM system.tables WHERE database='"+self.DBName+"'"
            AllTables = self.fetchall(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 getDBTable 时错误: %s" % (self.Name, str(e)))
            self._QS_Logger.error(Msg)
            raise __QS_Error__(Msg)
        else:
            return [rslt[0] for rslt in AllTables]
    def getFieldDataType(self, table_format=None, ignore_fields=[]):
        try:
            SQLStr = ("SELECT table, name, type FROM system.columns WHERE database='%s' " % self.DBName)
            TableField, ColField = "table", "name"
            if isinstance(table_format, str) and table_format:
                SQLStr += ("AND %s LIKE '%s' " % (TableField, table_format))
            if ignore_fields:
                SQLStr += "AND "+ColField+" NOT IN ('"+"', '".join(ignore_fields)+"') "
            SQLStr += ("ORDER BY %s, %s" % (TableField, ColField))
            Rslt = self.fetchall(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 getFieldDataType 获取字段数据类型信息时错误: %s" % (self.Name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        return pd.DataFrame(Rslt, columns=["Table", "Field", "DataType"])
    def addField(self, table_name, field_types):
        SQLStr = "ALTER TABLE %s " % (self.TablePrefix+table_name)
        SQLStr += "ADD COLUMN %s %s"
        try:
            for iField in field_types:
                self.execute(SQLStr % (iField, field_types[iField]))
        except Exception as e:
            Msg = ("'%s' 调用方法 addField 为表 '%s' 添加字段时错误: %s" % (self.Name, table_name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info("'%s' 调用方法 addField 为表 '%s' 添加字段 ’%s'" % (self.Name, table_name, str(list(field_types.keys()))))
        return 0
    def renameField(self, table_name, old_field_name, new_field_name):
        try:
            SQLStr = "ALTER TABLE "+self.TablePrefix+table_name
            SQLStr += " RENAME COLUMN `"+old_field_name+"` TO `"+new_field_name+"`"
            self.execute(SQLStr)
        except Exception as e:
            Msg = ("'%s' 调用方法 renameField 将表 '%s' 中的字段 '%s' 重命名为 '%s' 时错误: %s" % (self.Name, table_name, old_field_name, new_field_name, str(e)))
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info("'%s' 调用方法 renameField 在将表 '%s' 中的字段 '%s' 重命名为 '%s'" % (self.Name, table_name, old_field_name, new_field_name))
        return 0
    def deleteField(self, table_name, field_names):
        if not field_names: return 0
        try:
                SQLStr = "ALTER TABLE "+self.TablePrefix+table_name
                for iField in field_names: SQLStr += " DROP COLUMN `"+iField+"`,"
                self.execute(SQLStr[:-1])
        except Exception as e:
            Msg = ("'%s' 调用方法 deleteField 删除表 '%s' 中的字段 '%s' 时错误: %s" % (self.Name, table_name, str(field_names), str(e)))
            self._QS_Logger.error(Msg)
            raise e
        else:
            self._QS_Logger.info("'%s' 调用方法 deleteField 删除表 '%s' 中的字段 '%s'" % (self.Name, table_name, str(field_names)))
        return 0
