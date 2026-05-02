# -*- coding: utf-8 -*-
"""公募基金风险调整因子(聚源计算, 周频)"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    # ####################### 夏普比率 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金夏普比率", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 101, "6m": 102, "1y": 103, "2y": 104, "3y": 105, "5y": 106, "10y": 107}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"sharpe_ratio_{iLookBack}"))
    
    # ####################### 特雷诺比率 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金特雷诺比率", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 108, "6m": 109, "1y": 110, "2y": 111, "3y": 112, "5y": 113, "10y": 114}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"treynor_ratio_{iLookBack}"))
    
    # ####################### 索提诺比率 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金索提诺比率", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 115, "6m": 116, "1y": 117, "2y": 118, "3y": 119, "5y": 120, "10y": 121}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"sortino_ratio_{iLookBack}"))
    
    # ####################### 詹森指数 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金詹森指数", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 156, "6m": 157, "1y": 158, "2y": 159, "3y": 160, "5y": 161, "10y": 162}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"jensen_alpha_{iLookBack}"))
    
    # ####################### 信息比率 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金信息比率", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 165, "6m": 170, "1y": 171, "2y": 166, "3y": 167, "5y": 168, "10y": 169}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"information_ratio_{iLookBack}"))
    
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_risk_adjusted_w_jy",
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