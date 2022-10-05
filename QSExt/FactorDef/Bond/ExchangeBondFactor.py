# -*- coding: utf-8 -*-
"""交易所债券因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS

Factors = []

WDB = QS.FactorDB.WindDB2()

# 市场行情因子
FT = WDB.getTable("中国债券交易所债券行情")
Factors.append(FT.getFactor("开盘价(元)", new_name="开盘价"))
Factors.append(FT.getFactor("最高价(元)", new_name="最高价"))
Factors.append(FT.getFactor("最低价(元)", new_name="最低价"))
Close = FT.getFactor("收盘价(元)", new_name="收盘价")
Factors.append(Close)
PreClose = FT.getFactor("昨收盘价(元)", new_name="前收盘价")
Factors.append(PreClose)
Factors.append(FT.getFactor("成交量(手)", new_name="成交量"))
Factors.append(QS.FactorDB.Factorize(FT.getFactor("成交金额(千元)") * 1000, factor_name="成交金额"))
Factors.append(FT.getFactor("均价(VWAP)", new_name="均价"))
AIFT = WDB.getTable("中国债券应计利息")
AI = AIFT.getFactor("应计利息")
Factors.append(AI)
Factors.append(AIFT.getFactor("已计息时间"))
AIFT = WDB.getTable("中国债券付息和兑付")
Factors.append(QS.FactorDB.Factorize(AIFT.getFactor("每手付息数", args={"日期字段":"债权登记日"}) / 10, factor_name="付息"))
Factors.append(QS.FactorDB.Factorize(AIFT.getFactor("每手兑付本金数", args={"日期字段":"债权登记日"}) / 10, factor_name="兑付本金"))
Factors.append(QS.FactorDB.Factorize(AIFT.getFactor("税后每手付息数", args={"日期字段":"债权登记日"}) / 10, factor_name="税后付息"))
Factors.append(AIFT.getFactor("除息日", args={"日期字段":"债权登记日"}))
Factors.append(AIFT.getFactor("付息日", args={"日期字段":"债权登记日"}))

def DayReturnFun(f, idt, iid, x, args):
    Denominator = x[1][0] + x[2][0]
    Denominator[Denominator==0] = np.nan
    Interest = x[3][0]/10
    Interest[np.isnan(Interest)] = 0
    Principal = x[4][0]/10
    Principal[np.isnan(Principal)] = 0
    Numerator = x[0][0] + x[2][1] + Interest + Principal
    return Numerator / Denominator - 1
Interest = AIFT.getFactor("每手付息数", args={"日期字段":"除息日"})
Principal = AIFT.getFactor("每手兑付本金数", args={"日期字段":"除息日"})
Factors.append(QS.FactorDB.TimeOperation("日收益率", [Close, PreClose, AI, Interest, Principal], {"算子":DayReturnFun, "回溯期数":[1-1, 1-1, 2-1, 1-1, 1-1], "运算ID":"多ID"}))

if __name__=="__main__":
    HDB = QS.FactorDB.HDF5DB()
    HDB.connect()
    WDB.connect()
    
    CFT = QS.FactorDB.CustomFT("ExchangeBondFactor")
    CFT.addFactors(factor_list=Factors)
    
    SQLStr = "SELECT DISTINCT s_info_windcode FROM CBondDescription WHERE b_info_issuertype='财政部' AND s_info_exchmarket IN ('SSE', 'SZSE') ORDER BY s_info_windcode"
    IDs = np.array(WDB.fetchall(SQLStr)).flatten().tolist()# 所有的交易所交易国债
    #IDs = ["010303.SH"]# debug
    
    if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2005, 1, 1)
    else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    EndDT = dt.datetime.today()
    #StartDT, EndDT = dt.datetime(2018, 9, 1), dt.datetime(2018, 9, 30)# debug
    
    DTs = FT.getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = FT.getDateTime(start_dt=dt.datetime(2017, 6, 1), end_dt=dt.datetime(2018, 8, 20))
    
    TargetTable = "ExchangeBondFactor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=QS.Tools.genAvailableName("TestTable", HDB.TableNames), if_exists="update")
    
    HDB.disconnect()
    WDB.disconnect()