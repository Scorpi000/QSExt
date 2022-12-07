# -*- coding: utf-8 -*-
"""ETF 基金行情"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"].connect()
    
    SQLStr = "SELECT CONCAT(SecuCode, '.OF') AS ID FROM secumain WHERE InnerCode IN (SELECT DISTINCT InnerCode FROM mf_etfprlist) ORDER BY ID"
    IDs = pd.read_sql(SQLStr, JYDB.Connection, index_col=None).iloc[:, 0].tolist()
    
    FT = JYDB.getTable("公募基金日行情表")
    AdjClose = FT.getFactor("昨收盘(元)", new_name="close")    
    
    FT = JYDB.getTable("公募基金日行情表")
    Close = FT.getFactor("收盘价(元)")
    AdjFactor = AdjClose / Close
    AdjFactor = fd.where(AdjFactor, fd.notnull(AdjFactor), 1)
    AdjFactor = fd.where(AdjFactor, fd.notnull(Close), np.nan, factor_name="adj_factor")
    Factors.append(AdjFactor)
    PreClose = FT.getFactor("昨收盘(元)")
    Factors.append(Factorize(PreClose * AdjFactor, factor_name="pre_close"))
    Factors.append(Factorize(FT.getFactor("今开盘(元)") * AdjFactor, factor_name="open"))
    Factors.append(Factorize(FT.getFactor("最高价(元)") * AdjFactor, factor_name="high"))
    Factors.append(Factorize(FT.getFactor("最低价(元)") * AdjFactor, factor_name="low"))
    Factors.append(Factorize(Close * AdjFactor, factor_name="close"))
    
    Amount, Volume = FT.getFactor("成交金额(元)", new_name="amount"), FT.getFactor("成交量(股)")
    Factors.append(Factorize(Volume / 10000, factor_name="volume"))
    Factors.append(Amount)
    Factors.append(Factorize(Amount / Volume * AdjFactor, factor_name="avg"))
    Factors.append(Factorize(Close / PreClose - 1, factor_name="chg"))
    
    UpdateArgs = {
        "因子表": "mf_etf_cn_day_bar_adj_backward",
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": IDs
    }
    return Factors, UpdateArgs

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Args = {"JYDB": JYDB, "LDB": TDB, "industry_index_ids": sorted(pd.read_csv("../conf/citic_industry.csv", index_col=0, header=0, encoding="utf-8", encoding="python")["index_code"])}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
    IDs = UpdateArgs["IDs"]
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTRuler)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, 
                  factor_db=TDB, table_name=TargetTable, 
                  if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    JYDB.disconnect()