# -*- coding: utf-8 -*-
"""A股融资融券"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools


def defFactor(args={}):
    Factors = []
    
    JYDB = args["JYDB"]
    
    FT = JYDB.getTable("融资融券标的证券")
    Factors.append(FT.getFactor("10", new_name="finance_target"))
    Factors.append(FT.getFactor("20", new_name="security_target"))
    
    FT = JYDB.getTable("股票行情表现", args={"回溯天数": np.inf})
    MarketCap = FT.getFactor("总市值(万元)") * 10000
        
    FT = JYDB.getTable("融资融券交易明细")
    FinanceValue = FT.getFactor("融资余额(元)", new_name="finance_value")
    Factors.append(FinanceValue)
    SecurityValue = FT.getFactor("融券余额(元)", new_name="security_value")
    Factors.append(SecurityValue)
    TradingValue = FT.getFactor("融资融券余额(元)", new_name="trading_value")
    Factors.append(TradingValue)
        
    Mask = (fd.notnull(FinanceValue) | fd.notnull(SecurityValue))
    FinanceSecurityDiff = fd.fillna(FinanceValue, value=0) - fd.fillna(SecurityValue, value=0)
    FinanceSecurityDiff = fd.where(FinanceSecurityDiff, Mask, np.nan, factor_name="finance_security_diff")
    
    Factors.append(Factorize(FinanceValue / MarketCap, factor_name="finance_cap_ratio"))
    Factors.append(Factorize(SecurityValue / MarketCap, factor_name="security_cap_ratio"))
    Factors.append(Factorize(TradingValue / MarketCap, factor_name="trading_cap_ratio"))
    Factors.append(Factorize(FinanceSecurityDiff / MarketCap, factor_name="finance_security_diff_cap_ratio"))
                
    UpdateArgs = {
        "因子表": "stock_cn_margin_trading",
        "默认起始日": dt.datetime(2005, 1, 1),
        "最长回溯期": 365,
        "IDs": "股票"
    }    
    
    return Factors, UpdateArgs


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB()
    JYDB.connect()
    
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = JYDB.getStockID()
    
    Args = {"JYDB": JYDB, "LDB": TDB}
    Factors, UpdateArgs = defFactor(args=Args)
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTs)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
        factor_db=TDB, table_name=TargetTable,
        if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    JYDB.disconnect()