# -*- coding: utf-8 -*-
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_day_bar_adj_backward_nafilled",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

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

def defFactor(args={}):
    Factors = []
    
    WDB = args["WDB"]
    
    FT = WDB.getTable("中国A股日行情")
    AdjFactor = FT.getFactor("复权因子", new_name="adj_factor")
    Factors.append(AdjFactor)
    PreClose = Factorize(FT.getFactor("昨收盘价(元)") * AdjFactor, factor_name="pre_close")
    Factors.append(PreClose)
    Factors.append(Factorize(FT.getFactor("开盘价(元)") * AdjFactor, factor_name="open"))
    Factors.append(Factorize(FT.getFactor("最高价(元)") * AdjFactor, factor_name="high"))
    Factors.append(Factorize(FT.getFactor("最低价(元)") * AdjFactor, factor_name="low"))
    Close = Factorize(FT.getFactor("收盘价(元)") * AdjFactor, factor_name="close")
    Factors.append(Close)
    Factors.append(Factorize(FT.getFactor("均价(VWAP)") * AdjFactor, factor_name="avg_price"))
    Factors.append(FT.getFactor("成交量(手)", new_name="volume"))
    Factors.append(FT.getFactor("成交金额(千元)", new_name="amount"))
    Factors.append(Factorize(Close / PreClose - 1, factor_name="chg_rate"))
    
    Factors.append(QS.FactorDB.TimeOperation("week_return", [Close, PreClose], {"算子":WeekRetFun, "回溯期数":[1-1, 8-1], "运算ID":"多ID"}))
    Factors.append(QS.FactorDB.TimeOperation("month_return", [Close, PreClose], {"算子":MonthRetFun, "回溯期数":[1-1, 31-1], "运算ID":"多ID"}))

    return Factors


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    WDB = QS.FactorDB.WindDB2()
    WDB.connect()
    
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = WDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = WDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = WDB.getStockID(is_current=False)
    
    Args = {"WDB": WDB}
    Factors = defFactor(args=Args)
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTs)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
        factor_db=TDB, table_name=TargetTable,
        if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    WDB.disconnect()