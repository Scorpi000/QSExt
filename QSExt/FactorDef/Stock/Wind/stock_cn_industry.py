# -*- coding: utf-8 -*-
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_industry",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def defFactor(args={}):
    Factors = []
    
    WDB = args["WDB"]
    
    Factors.append(WDB.getTable("中国A股Wind行业分类").getFactor("行业名称", args={"分类级别":1}, new_name="wind_level1"))
    Factors.append(WDB.getTable("中国A股中信行业分类").getFactor("行业名称", args={"分类级别":1}, new_name="citic_level1"))
    
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