# -*- coding: utf-8 -*-
"""A股日行情"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools
from QSExt.FactorDataBase.AKShareDB import AKShareDB

UpdateArgs = {
    "因子表": "stock_cn_day_bar",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

# args:
# AKSDB: AKShare 因子库对象
def defFactor(args={}):
    Factors = []
    
    AKSDB = args["AKSDB"]
    
    # 市场行情
    FT = AKSDB.getTable("历史行情数据-东财")
    Factors.append(FT.getFactor("开盘", new_name="open"))
    Factors.append(FT.getFactor("收盘", new_name="close"))
    Factors.append(FT.getFactor("最高", new_name="high"))
    Factors.append(FT.getFactor("最低", new_name="low"))
    Factors.append(FT.getFactor("成交量", new_name="volume"))
    Factors.append(FT.getFactor("成交额", new_name="amount"))
    Factors.append(FT.getFactor("涨跌幅", new_name="chg_rate"))
    Factors.append(FT.getFactor("涨跌额", new_name="chg"))
    Factors.append(FT.getFactor("换手率", new_name="turnover_rate"))
    Factors.append(FT.getFactor("振幅", new_name="amplitude"))
    
    #FT = AKSDB.getTable("历史行情数据-新浪")
    #Factors.append(FT.getFactor("outstanding_share", new_name="float_share"))
    
    #FT = AKSDB.getTable("历史行情数据-网易")
    #Factors.append(FT.getFactor("总市值", new_name="total_cap"))
    #Factors.append(FT.getFactor("流通市值", new_name="float_cap"))
    
    FT = AKSDB.getTable("两市停复牌")
    SuspendRange = FT.getFactor("停牌期限")
    IfTrading = fd.where(1, fd.isnull(SuspendRange) | (SuspendRange=="盘中停牌"), 0, factor_name="if_trading")
    Factors.append(IfTrading)
    
    return Factors


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    AKSDB = AKShareDB()
    AKSDB.connect()
    
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = AKSDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = AKSDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    #IDs = AKSDB.getStockID()
    IDs = ["000001.SZ"]
    
    Args = {"AKSDB": AKSDB}
    Factors = defFactor(args=Args)
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTs)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
        factor_db=TDB, table_name=TargetTable,
        if_exists="update", subprocess_num=0)
    
    TDB.disconnect()
    AKSDB.disconnect()