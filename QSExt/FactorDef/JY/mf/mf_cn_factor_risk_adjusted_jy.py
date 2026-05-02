# -*- coding: utf-8 -*-
"""公募基金风险调整因子(聚源计算)"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    # ####################### 卡玛比率 #######################
    FT = JYDB.getTable("公募基金衍生指标_卡玛比率", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 33, "6m": 34, "1y": 35, "2y": 36, "3y": 37, "5y": 38, "10y": 39, "establish": 40}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"calmar_ratio_{iLookBack}"))
    
    # 超基准卡玛比率
    look_back_period = {"3m": 41, "6m": 42, "1y": 43, "2y": 44, "3y": 45, "5y": 46, "10y": 47, "establish": 48}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"active_calmar_ratio_{iLookBack}"))
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_risk_adjusted_jy",
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