# -*- coding: utf-8 -*-
"""基金经理选券择时因子(聚源计算)"""
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
    
    # ####################### Brinson 模型 #######################
    FT = JYDB.getTable("公募基金衍生指标_基金经理Brinson业绩归因", args={"回溯天数": 0})
    look_back_period = {"6m": 6, "1y": 12, "2y": 24, "3y": 36, "5y": 60, "10y": 120}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("资产配置", args={"指标周期": str(iLookBackPeriod)}, new_name=f"brinson_aa_{iLookBack}"))
        Factors.append(FT.getFactor("个股选择", args={"指标周期": str(iLookBackPeriod)}, new_name=f"brinson_ss_{iLookBack}"))
        Factors.append(FT.getFactor("交互作用", args={"指标周期": str(iLookBackPeriod)}, new_name=f"brinson_in_{iLookBack}"))
        Factors.append(FT.getFactor("总主动作用", args={"指标周期": str(iLookBackPeriod)}, new_name=f"brinson_ta_{iLookBack}"))
                                
    UpdateArgs = {
        "因子表": "mf_manager_cn_factor_selection_timing_jy",
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