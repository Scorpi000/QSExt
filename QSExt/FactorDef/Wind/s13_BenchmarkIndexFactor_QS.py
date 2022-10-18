# coding=utf-8
"""股票基准指数因子"""
import datetime as dt
import UpdateDate
import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize

Factors = []

WDB = QS.FactorDB.WindDB2()

FT = WDB.getTable("中国A股指数日行情")
PreClose, Open, High, Low = FT.getFactor("昨收盘价(点)", new_name="昨收盘价"), FT.getFactor("开盘价(点)", new_name="开盘价"), FT.getFactor("最高价(点)", new_name="最高价"), FT.getFactor("最低价(点)", new_name="最低价")
Close, Volume, Amount = FT.getFactor("收盘价(点)", new_name="收盘价"), FT.getFactor("成交量(手)", new_name="成交量"), FT.getFactor("成交金额(千元)", new_name="成交金额")

Factors.extend([PreClose, Open, High, Low, Close, Volume, Amount])

RawName = WDB.getTable("中国A股指数基本资料").getFactor("证券简称")
def NameFun(f, idt, iid, x, args):
    Data = pd.DataFrame(x[0])
    Data = Data.applymap(lambda x:str.replace(x,'指数','') if pd.notnull(x) else None)
    return Data.values
Factors.append(QS.FactorDB.PointOperation("指数名称", [RawName], {"算子":NameFun, "运算ID":"多ID", "运算时点":"多时点", "数据类型":"string"}))

Factors.append(Factorize(Close/PreClose-1,"日收益率"))

def WeekRetFun(f, idt, iid, x, args):
    CurDate = idt[-1].date()
    CurWeekDay = CurDate.weekday()
    for i in range(1, 8):
        iDT = idt[-i-1]
        if iDT is None: return np.full(shape=(x[0].shape[1],), fill_value=np.nan)
        iPreDate = iDT.date()
        iPreWeekDay = iPreDate.weekday()
        if (CurWeekDay-iPreWeekDay)!=(CurDate-iPreDate).days: break
    Denominator = x[1][-i]
    Denominator[Denominator==0] = np.nan
    return x[0][0] / Denominator - 1
Factors.append(QS.FactorDB.TimeOperation('周收益率', [Close, PreClose], {"算子":WeekRetFun, "回溯期数":[1-1, 8-1], "运算ID":"多ID"}))

def MonthRetFun(f, idt, iid, x, args):
    CurDate = idt[-1].strftime("%Y%m%d")
    for i in range(1, 31):
        iDT = idt[-i-1]
        if iDT is None: return np.full(shape=(x[0].shape[1],), fill_value=np.nan)
        iPreDate = iDT.strftime("%Y%m%d")
        if (iPreDate[:6]!=CurDate[:6]): break
    Denominator = x[1][-i]
    Denominator[Denominator==0] = np.nan
    return x[0][0] / Denominator - 1
Factors.append(QS.FactorDB.TimeOperation('月收益率', [Close, PreClose], {"算子":MonthRetFun, "回溯期数":[1-1, 31-1], "运算ID":"多ID"}))

if __name__=="__main__":
    HDB = QS.FactorDB.HDF5DB()
    HDB.connect()
    WDB.connect()
    
    CFT = QS.FactorDB.CustomFT("BenchmarkIndexFactor")
    CFT.addFactors(factor_list=Factors)
    
    IDs = ['000001.SH','000010.SH','000016.SH','000300.SH','000852.SH','000905.SH','000906.SH','399001.SZ','399005.SZ','399006.SZ','399311.SZ']
    #if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2018, 8, 31, 23, 59, 59, 999999)
    #else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    #EndDT = dt.datetime(2018, 10, 31, 23, 59, 59, 999999)
    StartDT, EndDT = UpdateDate.StartDT, UpdateDate.EndDT
    
    DTs = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT-dt.timedelta(183), end_dt=EndDT)
    
    TargetTable = "BenchmarkIndexFactor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler, subprocess_num=0)
    
    HDB.disconnect()
    WDB.disconnect()