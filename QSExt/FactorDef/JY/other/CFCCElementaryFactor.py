# coding=utf-8
"""商品期货连续合约基本因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
WDB = QS.FactorDB.WindDB2()
Factorize = QS.FactorDB.Factorize

Factors = []# 因子列表

# 证券特征
FT = WDB.getTable("中国期货基本资料")
Factors.append(FT.getFactor("证券中文简称", new_name="证券名称"))

FT = WDB.getTable("中国期货连续(主力)合约和月合约映射表")
Factors.append(FT.getFactor("映射月合约Wind代码", new_name="月合约"))

# 市场行情
FT = WDB.getTable("中国商品期货日行情")
Settle, PreSettle = FT.getFactor("结算价(元)", new_name="结算价"), FT.getFactor("前结算价(元)", new_name="前结算价")
Factors.extend([PreSettle, FT.getFactor("开盘价(元)", new_name="开盘价"), FT.getFactor("最高价(元)", new_name="最高价"), 
                FT.getFactor("最低价(元)", new_name="最低价"), FT.getFactor("收盘价(元)", new_name="收盘价"), Settle, 
                FT.getFactor("成交量(手)", new_name="成交量"), FT.getFactor("成交金额(万元)", new_name="成交金额"), 
                FT.getFactor("持仓量(手)", new_name="持仓量"), FT.getFactor("持仓量变化")])

DayReturn = Factorize(Settle / PreSettle - 1, "日收益率")
Factors.append(DayReturn)

def WeekReturnFun(f, idt, iid, x, args):
    CurDate = idt[-1].date()
    CurWeekDay = CurDate.weekday()
    for i in range(1, 8):
        iDT = idt[-i-1]
        if iDT is None: return np.full(shape=(x[0].shape[1], ), fill_value=np.nan)
        iPreDate = iDT.date()
        iPreWeekDay = iPreDate.weekday()
        if (CurWeekDay-iPreWeekDay)!=(CurDate-iPreDate).days: break
    DayReturns = x[0][-i:]
    return np.nanprod(1+DayReturns, axis=0) - 1
Factors.append(QS.FactorDB.TimeOperation("周收益率", [DayReturn], {"算子":WeekReturnFun, "回溯期数":[8-1], "运算ID":"多ID"}))

def MonthReturnFun(f, idt, iid, x, args):
    CurDate = idt[-1].strftime("%Y%m%d")
    for i in range(1, 31):
        iDT = idt[-i-1]
        if iDT is None: return np.full(shape=(x[0].shape[1], ), fill_value=np.nan)
        iPreDate = iDT.strftime("%Y%m%d")
        if (iPreDate[:6]!=CurDate[:6]): break
    DayReturns = x[0][-i:]
    return np.nanprod(1+DayReturns, axis=0) - 1
Factors.append(QS.FactorDB.TimeOperation("月收益率", [DayReturn], {"算子":MonthReturnFun, "回溯期数":[31-1], "运算ID":"多ID"}))

if __name__=="__main__":
    HDB = QS.FactorDB.HDF5DB()
    HDB.connect()
    WDB.connect()
    
    Exchanges = ["CZCE", "SHFE", "DCE"]# 需要修改
    DefaultStartDT = dt.datetime(2005, 1, 1)# 需要修改
    TargetTable = "CFCCElementaryFactor"# 需要修改
    EndDT = dt.datetime(2018, 12, 11)# 需要修改
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    
    CFT = QS.FactorDB.CustomFT(TargetTable)
    CFT.addFactors(factor_list=Factors)
    
    if CFT.Name in HDB.TableNames: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    else: StartDT = DefaultStartDT
    #StartDT, EndDT = dt.datetime(2018, 3, 26), dt.datetime(2018, 11, 30)# debug
    
    FutureCodes = WDB.getFutureCode(exchange=Exchanges, date=EndDT.date(), is_current=False)
    IDs = WDB.getFutureID(future_code=FutureCodes, date=EndDT.date(), is_current=False, contract_type="连续合约")
    #IDs = ["SC.INE", "SC_S.INE", "SC00.INE", "SC01M.INE"]# debug
    
    CalendarFT = WDB.getTable("中国期货交易日历")
    DTs = CalendarFT.getDateTime(iid="CZCE", start_dt=StartDT, end_dt=EndDT)
    DTRuler = CalendarFT.getDateTime(iid="CZCE", start_dt=StartDT-dt.timedelta(90), end_dt=EndDT)
    
    if CFT.Name in HDB.TableNames: InitPrice = HDB.getTable(CFT.Name).readData(factor_names=["净值"], ids=IDs, dts=[StartDT-dt.timedelta(1)]).iloc[0]
    else: InitPrice = None
    CFT.addFactors(factor_list=[QS.FactorDB.FactorTools.nav(DayReturn, init=InitPrice, factor_name="净值")])
    
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler, subprocess_num=3)
    
    HDB.disconnect()
    WDB.disconnect()