# coding=utf-8
"""商品期货月合约基本因子"""
import re
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
WDB = QS.FactorDB.WindDB2()
Factorize = QS.FactorDB.Factorize

Factors = []# 因子列表

# 证券特征
FT = WDB.getTable("中国期货基本资料")
ListDate = FT.getFactor("上市日期")
DelistDate = FT.getFactor("最后交易日期")
Factors.extend([ListDate, DelistDate])
def isListed(f, idt, iid, x, args):
    ListDate, DelistDate = x
    Listed = np.zeros_like(ListDate)
    DelistDate[pd.isnull(DelistDate)] = "99999999"
    DTs = np.array([[iDT.strftime("%Y%m%d") for iDT in idt]]).T
    Listed[(ListDate<=DTs) & (DelistDate>DTs)] = 1
    return Listed
Factors.append(QS.FactorDB.PointOperation("是否在市", [ListDate, DelistDate], {"算子":isListed, "运算时点":"多时点", "运算ID":"多ID"}))

FT = WDB.getTable("中国期货标准合约属性")
def parseDigital(f, idt, iid, x, args):
    return np.vectorize(lambda x: (re.findall("\d+\.?\d*", x)[0] if pd.notnull(x) else None))(x[0]).astype("float")
Factors.append(QS.FactorDB.PointOperation("最小变动价位", [FT.getFactor("最小变动价位")], sys_args={"算子":parseDigital, "运算时点":"多时点", "运算ID":"多ID"}))
Factors.append(FT.getFactor("交易单位(每手)", new_name="合约乘数"))


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


# 合约属性
Margin = WDB.getTable("中国期货保证金比例").getFactor("保证金比例", args={"回溯天数":9999})
Factors.append(Factorize(QS.FactorDB.FactorTools.astype(Margin, "float") / 100, factor_name="保证金比例"))
#LimitChg = WDB.getTable("中国期货合约价格波动限制变更").getFactor("涨跌停板幅度(%)", args={"回溯天数":9999})
#def LimitFun(f, idt, iid, x, args):
    #idt = idt.strftime("%Y%m%d")
    #if (idt<x[2]) or (idt>x[3]): return np.nan
    #elif pd.notnull(x[0]): return x[0] / 100
    #elif idt==x[2]: return x[1] * 2 / 100
    #else: return x[1] / 100
#Factors.append(QS.FactorDB.PointOperation("涨跌停板幅度", [LimitChg, InitLimit, ListDate, DelistDate], sys_args={"算子":LimitFun, "运算时点":"单时点", "运算ID":"单ID"}))

if __name__=="__main__":
    HDB = QS.FactorDB.HDF5DB()
    HDB.connect()
    WDB.connect()
    
    Exchanges = ["CZCE", "SHFE", "DCE"]# 需要修改
    DefaultStartDT = dt.datetime(2005, 1, 1)# 需要修改
    TargetTable = "CFElementaryFactor"# 需要修改
    EndDT = dt.datetime(2018, 12, 11)# 需要修改
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    
    CFT = QS.FactorDB.CustomFT(TargetTable)
    CFT.addFactors(factor_list=Factors)
    
    if CFT.Name in HDB.TableNames: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    else: StartDT = DefaultStartDT
    #StartDT, EndDT = dt.datetime(2018, 3, 26), dt.datetime(2018, 11, 30)# debug
    
    # 获取商品期货 ID
    FutureCodes = WDB.getFutureCode(exchange=Exchanges, date=EndDT.date(), is_current=False)
    IDs = WDB.getFutureID(future_code=FutureCodes, date=EndDT.date(), is_current=False)# 截止结束日曾经在市的 ID
    IDs1 = WDB.getFutureID(future_code=FutureCodes, date=StartDT.date(), is_current=False)# 截止起始日曾经在市的 ID
    IDs2 = WDB.getFutureID(future_code=FutureCodes, date=StartDT.date(), is_current=True)# # 起始日在市的 ID
    IDs = sorted(set(IDs).difference(set(IDs1).difference(IDs2)))
    #IDs = ["SC1809.INE", "SC1810.INE", "SC1811.INE"]# debug
    
    CalendarFT = WDB.getTable("中国期货交易日历")
    DTs = CalendarFT.getDateTime(iid="CZCE", start_dt=StartDT, end_dt=EndDT)
    DTRuler = CalendarFT.getDateTime(iid="CZCE", start_dt=StartDT-dt.timedelta(90), end_dt=EndDT)
    
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler, subprocess_num=3)
    
    HDB.disconnect()
    WDB.disconnect()