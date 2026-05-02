# -*- coding: utf-8 -*-
"""基金经理风险因子(聚源计算)"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"].connect()
    
    FT = JYDB.getTable("公募基金经理(新)(基金经理ID)", args={"多重映射": True})
    IDs = FT.getID()
    
    # ####################### 最大回撤 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金经理最大回撤", args={"因子表类型": "WideTable", "回溯天数": 0})
    TypeMap = {
        "全部基金": {"999": "all"}, 
        "证监会基金分类": {
            "1101": "csrc_stock_type", 
            "1103": "csrc_hybrid_type", 
            "1105": "csrc_bond_type", 
            "1110": "csrc_qdii_type"
        },
        "聚源二级分类": {
            "1102": "jy_stock_index_type",
            "1304": "jy_bond_index_type"
        }
    }
    look_back_period = {"3m": 17, "6m": 18, "1y": 19, "2y": 20, "3y": 21, "5y": 22, "10y": 23, "this_year": 75}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        for jType in TypeMap:
            for kSubType, kSuffix in TypeMap[jType].items():
                Factors.append(FT.getFactor("指标值", args={"基金分类口径描述": jType, "基金类别代码": kSubType, "筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"max_drawdown_rate_{iLookBack}_{kSuffix}"))
    look_back_period = {"3m": 25, "6m": 26, "1y": 27, "2y": 28, "3y": 29, "5y": 30, "10y": 31, "this_year": 76}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        for jType in TypeMap:
            for kSubType, kSuffix in TypeMap[jType].items():
                Factors.append(FT.getFactor("指标值", args={"基金分类口径描述": jType, "基金类别代码": kSubType, "筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"active_drawdown_rate_{iLookBack}_{kSuffix}"))
        
    # ####################### 跟踪误差 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金经理相对基准收益标准差", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"3m": 82, "6m": 66, "1y": 67, "2y": 68, "3y": 69, "5y": 70, "10y": 71, "this_year": 81}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("指标值", args={"筛选条件": "{Table}.IndexCode="+str(iLookBackPeriod)}, new_name=f"active_volatility_{iLookBack}"))
    
    UpdateArgs = {
        "因子表": "mf_manager_cn_factor_risk_jy",
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
    
    Args = {"JYDB": JYDB, "LDB": TDB}
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