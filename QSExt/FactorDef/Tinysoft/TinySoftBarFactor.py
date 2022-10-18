# -*- coding: utf-8 -*-
"""来自于 TinySoft 的 Bar 数据"""
import datetime as dt

import QuantStudio.api as QS
from QuantStudio.FactorDataBase.TinySoftDB import TinySoftDB
from QuantStudio.FactorDataBase.ArcticDB import ArcticDB

ADB = ArcticDB()
ADB.connect()

TSDB = TinySoftDB()
TSDB.connect()

FT = TSDB.getTable("分时和日线数据", args={"周期":60, "周期单位":"s"})# 1 分钟 Bar 数据
#FT = TSDB.getTable("分时和日线数据", args={"周期":300, "周期单位":"s"})# 5 分钟 Bar 数据
#FT = TSDB.getTable("分时和日线数据", args={"周期":1800, "周期单位":"s"})# 30 分钟 Bar 数据
FactorNames = ['最新价', '开盘价', '最高价', '最低价', '成交量', '成交金额','买一价','买一量','卖一价','卖一量']

#TableName = QS.Tools.genAvailableName("TestTable", ADB.TableNames)# debug
TableName = "MinuteBar"
#TableName = "Minute5Bar"
#TableName = "Minute30Bar"

## 指数, 最早从 2005-4-8 开始
#StartDate, EndDate = dt.date(2018, 11, 26), dt.date(2018, 11, 30)
#IDs = ["000300.SH", "000905.SH", "000016.SH"]
#Data = FT.readDayData(factor_names=FactorNames, ids=IDs, start_date=StartDate, end_date=EndDate)
#ADB.writeData(Data, TableName, if_exists="update")

## 股指期货, 最早从 2010-4-16 开始
#StartDate, EndDate = dt.date(2018, 11, 26), dt.date(2018, 11, 30)
#if (StartDate<=EndDate) and (StartDate<=dt.date(2015, 4, 15)):
    #iEndDate = min(EndDate, dt.date(2015, 4, 15))
    #IDs = ["IF00","IF01","IF02","IF03","IF04"]
    #Data = FT.readDayData(factor_names=FactorNames, ids=IDs, start_date=StartDate, end_date=iEndDate)
    #ADB.writeData(Data, TableName, if_exists="update")
    #StartDate = dt.date(2015, 4, 16)
#if StartDate<=EndDate:
    #IDs = ["IF00","IF01","IF02","IF03","IF04","IC00","IC01","IC02","IC03","IC04","IH00","IH01","IH02","IH03","IH04"]
    #Data = FT.readDayData(factor_names=FactorNames, ids=IDs, start_date=StartDate, end_date=EndDate)
    #ADB.writeData(Data, TableName, if_exists="update")

# 原油期货, 最早从 2018-3-26 开始
StartDate, EndDate = dt.date(2018, 3, 26), dt.date(2018, 3, 31)
IDs = ["ZL000050", "LXSC00","LXSC01","LXSC02","LXSC03","LXSC04"]
Data = FT.readDayData(factor_names=FactorNames, ids=IDs, start_date=StartDate, end_date=EndDate)
ADB.writeData(Data, TableName, if_exists="update")

ADB.disconnect()
TSDB.disconnect()