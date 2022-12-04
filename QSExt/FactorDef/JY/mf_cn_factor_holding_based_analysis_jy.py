# -*- coding: utf-8 -*-
"""公募基金持仓分析因子(聚源计算)"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    # ####################### 持股比例及其稳定性 #######################
    FT = JYDB.getTable("公募基金股票持仓平均占比", args={"公告时点字段": None, "回溯天数": np.inf, "忽略时间": True})
    Factors.append(FT.getFactor("近一年股票占比", new_name="holdings_stock_ratio_1y"))
    Factors.append(FT.getFactor("近一年标准差", new_name="holdings_stock_ratio_std_1y"))
    Factors.append(FT.getFactor("近两年股票占比", new_name="holdings_stock_ratio_2y"))
    Factors.append(FT.getFactor("近两年标准差", new_name="holdings_stock_ratio_std_2y"))
    Factors.append(FT.getFactor("近三年股票占比", new_name="holdings_stock_ratio_3y"))
    Factors.append(FT.getFactor("近三年标准差", new_name="holdings_stock_ratio_std_3y"))
    Factors.append(FT.getFactor("近五年股票占比", new_name="holdings_stock_ratio_5y"))
    Factors.append(FT.getFactor("近五年标准差", new_name="holdings_stock_ratio_std_5y"))
                                
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_holding_based_analysis_jy",
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": "公募基金"
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
    
    Args = {"JYDB": JYDB, "LDB": TDB}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
    IDs = JYDB.getMutualFundID(is_current=False)
    #IDs = ["159956.OF"]
    
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