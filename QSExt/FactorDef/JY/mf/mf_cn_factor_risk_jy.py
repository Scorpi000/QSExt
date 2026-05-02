# -*- coding: utf-8 -*-
"""公募基金风险因子(聚源计算)"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    # ####################### 最大回撤 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金最大回撤", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 1, "6m": 2, "1y": 3, "2y": 4, "3y": 5, "5y": 6, "10y": 7, "establish": 8, "this_year": 73}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"max_drawdown_rate_{iLookBack}"))
    
    FT = JYDB.getTable("公募基金衍生指标_基金最大回撤修复天数", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 212, "6m": 213, "1y": 214, "2y": 215, "3y": 216, "5y": 217, "10y": 218, "this_year": 219, "establish": 220}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("回撤后修复天数", args={"指标内码": str(iLookBackPeriod)}, new_name=f"max_drawdown_restore_days_{iLookBack}"))
        Factors.append(FT.getFactor("回撤前高点日期", args={"指标内码": str(iLookBackPeriod)}, new_name=f"max_drawdown_start_{iLookBack}"))
        Factors.append(FT.getFactor("最大回撤日期", args={"指标内码": str(iLookBackPeriod)}, new_name=f"max_drawdown_end_{iLookBack}"))
        Factors.append(FT.getFactor("回撤后修复日期", args={"指标内码": str(iLookBackPeriod)}, new_name=f"max_drawdown_restore_date_{iLookBack}"))
    
    # ####################### 波动率 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金收益标准差", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 92, "6m": 93, "1y": 94, "2y": 95, "3y": 96, "5y": 97, "10y": 98, "establish": 100, "this_year": 99}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"volatility_{iLookBack}"))
    
    # ####################### 下行风险 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金下行标准差", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 122, "6m": 123, "1y": 124, "2y": 125, "3y": 126, "5y": 127, "10y": 128, "establish": 130, "this_year": 129}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"down_volatility_{iLookBack}"))
    
    # ####################### 跟踪误差 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金相对基准收益标准差", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 49, "6m": 50, "1y": 51, "2y": 52, "3y": 53, "5y": 54, "10y": 55, "establish": 56, "this_year": 79}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"active_volatility_{iLookBack}"))
    
    # ####################### beta #######################
    FT = JYDB.getTable("公募基金衍生指标_基金贝塔系数", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 83, "6m": 84, "1y": 85, "2y": 86, "3y": 87, "5y": 88, "10y": 89, "establish": 91, "this_year": 90}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"beta_{iLookBack}"))
    
    # ####################### 大盘相关系数 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金相关系数", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 131, "6m": 132, "1y": 133, "2y": 134, "3y": 135, "5y": 136, "10y": 137, "establish": 139, "this_year": 138}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"correlation_{iLookBack}"))
    
    # ####################### 可决系数 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金可决系数", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 140, "6m": 141, "1y": 142, "2y": 143, "3y": 144, "5y": 145, "10y": 146, "establish": 148, "this_year": 147}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"determ_{iLookBack}"))
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_risk_jy",
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