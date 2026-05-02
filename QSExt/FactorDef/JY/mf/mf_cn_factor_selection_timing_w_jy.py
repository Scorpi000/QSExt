# -*- coding: utf-8 -*-
"""公募基金选券择时因子(聚源计算, 周频)"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    # ####################### TMFF 选股择时 #######################
    FT = JYDB.getTable("公募基金衍生指标_TMFF选股择时能力分析", args={"因子表类型": "WideTable", "回溯天数": 0})
    look_back_period = {"6m": 6, "1y": 12, "2y": 24, "3y": 36, "5y": 60, "10y": 120}# 回溯期
    for iLookBack, iLookBackPeriod in look_back_period.items():
        Factors.append(FT.getFactor("选股能力", args={"指标周期": str(iLookBackPeriod)}, new_name=f"tmff_selection_ability_{iLookBack}"))
        Factors.append(FT.getFactor("选股能力P值", args={"指标周期": str(iLookBackPeriod)}, new_name=f"tmff_selection_pvalue_{iLookBack}"))
        Factors.append(FT.getFactor("择时能力", args={"指标周期": str(iLookBackPeriod)}, new_name=f"tmff_timing_ability_{iLookBack}"))
        Factors.append(FT.getFactor("择时能力P值", args={"指标周期": str(iLookBackPeriod)}, new_name=f"tmff_timing_pvalue_{iLookBack}"))
        Factors.append(FT.getFactor("市场系数", args={"指标周期": str(iLookBackPeriod)}, new_name=f"tmff_market_coef_{iLookBack}"))
        Factors.append(FT.getFactor("市场P值", args={"指标周期": str(iLookBackPeriod)}, new_name=f"tmff_market_pvalue_{iLookBack}"))
        Factors.append(FT.getFactor("规模系数", args={"指标周期": str(iLookBackPeriod)}, new_name=f"tmff_smb_coef_{iLookBack}"))
        Factors.append(FT.getFactor("规模P值", args={"指标周期": str(iLookBackPeriod)}, new_name=f"tmff_smb_pvalue_{iLookBack}"))
        Factors.append(FT.getFactor("价值系数", args={"指标周期": str(iLookBackPeriod)}, new_name=f"tmff_hml_coef_{iLookBack}"))
        Factors.append(FT.getFactor("价值P值", args={"指标周期": str(iLookBackPeriod)}, new_name=f"tmff_hml_pvalue_{iLookBack}"))                                                                        
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_selection_timing_w_jy",
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