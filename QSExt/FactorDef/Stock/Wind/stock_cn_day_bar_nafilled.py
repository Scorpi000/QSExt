# -*- coding: utf-8 -*-
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_day_bar_nafilled",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}


def defFactor(args={}):
    Factors = []
    
    WDB = args["WDB"]
    
    FT = WDB.getTable("中国A股日行情")
    Factors.append(FT.getFactor("交易状态", new_name="if_trading"))
    PreClose = FT.getFactor("昨收盘价(元)", new_name="pre_close")
    Factors.append(PreClose)
    Factors.append(FT.getFactor("开盘价(元)", new_name="open"))
    Factors.append(FT.getFactor("最高价(元)", new_name="high"))
    Factors.append(FT.getFactor("最低价(元)", new_name="low"))
    Close = FT.getFactor("收盘价(元)", new_name="close")
    Factors.append(Close)
    Factors.append(FT.getFactor("均价(VWAP)", new_name="avg_price"))
    Factors.append(FT.getFactor("成交量(手)", new_name="volume"))
    Factors.append(FT.getFactor("成交金额(千元)", new_name="amount"))
    Factors.append(Factorize(Close / PreClose - 1, factor_name="chg_rate"))
    
    FT = WDB.getTable("中国A股日行情估值指标")
    Factors.append(FT.getFactor("换手率", new_name="turnover"))
    Factors.append(FT.getFactor("当日总市值", new_name="total_cap"))
    Factors.append(FT.getFactor("当日流通市值", new_name="float_cap"))
    Factors.append(FT.getFactor("涨跌停状态", new_name="limit"))

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