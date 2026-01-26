# -*- coding: utf-8 -*-
"""A股基本信息"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools



# args:
# JYDB: 聚源因子库对象
def defFactor(args={}):
    Factors = []
    
    JYDB = args["JYDB"]
    
    # 证券特征
    FT = JYDB.getTable("A股证券主表")
    Factors.append(FT.getFactor("中文名称", new_name="name"))
    Factors.append(FT.getFactor("证券简称", new_name="abbr"))
    Factors.append(FT.getFactor("拼音证券简称", new_name="pinyin_abbr"))
    Factors.append(FT.getFactor("上市板块_R", new_name="listed_sector"))
    ListDate = FT.getFactor("上市日期")
    Factors.append(fd.strftime(ListDate, "%Y-%m-%d", factor_name="listed_date"))
    
    FT = JYDB.getTable("公司概况")
    Factors.append(FT.getFactor("省份_R", new_name="province"))
    Factors.append(FT.getFactor("地区代码_R", new_name="city"))
    
    UpdateArgs = {
        "因子表": "stock_cn_info",
        "默认起始日": dt.datetime(2002, 1, 1),
        "最长回溯期": 365,
        "IDs": "股票"
    }
    return Factors, UpdateArgs


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = JYDB.getStockID()
    
    Args = {"JYDB": JYDB}
    Factors, UpdateArgs = defFactor(args=Args)
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTs)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
        factor_db=TDB, table_name=TargetTable,
        if_exists="update", subprocess_num=4)
    
    TDB.disconnect()
    JYDB.disconnect()