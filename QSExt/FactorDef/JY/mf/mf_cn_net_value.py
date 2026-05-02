# -*- coding: utf-8 -*-
"""公募基金净值因子"""
import os
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# args 应该包含的参数
# JYDB: 聚源因子库对象
def defFactor(args={}, debug=False):
    Factors = []

    JYDB = args["JYDB"]

    FT = JYDB.getTable("公募基金净值", args={"回溯天数":0, "公告时点字段":None})
    Factors.append(FT.getFactor("单位净值(元)", new_name="unit_net_value"))
    Factors.append(FT.getFactor("单位累计净值(元)", new_name="unit_net_value_cum"))
    Factors.append(FT.getFactor("净资产值(元)", new_name="net_value"))
    
    FT = JYDB.getTable("公募基金复权净值", args={"回溯天数":0})
    Factors.append(FT.getFactor("复权单位净值", new_name="unit_net_value_adj"))
    Factors.append(Factorize(FT.getFactor("复权单位净值日增长率") / 100, factor_name="daily_growth_unit_net_value_adj"))
    
    UpdateArgs = {"因子表": "mf_cn_net_value",
                  "默认起始日": dt.datetime(2002,1,1),
                  "最长回溯期": 3650,
                  "IDs": "公募基金"}
    
    return (Factors, UpdateArgs)


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Args = {"JYDB": JYDB}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2020, 3, 1), dt.datetime(2020, 9, 25)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
    #IDs = sorted(pd.read_csv("."+os.sep+"MFIDs.csv", index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
    IDs = JYDB.getMutualFundID(is_current=False)
    
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