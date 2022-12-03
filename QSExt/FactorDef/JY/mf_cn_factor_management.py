# -*- coding: utf-8 -*-
"""公募基金管理因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def max_list(f, idt, iid, x, args):
    x = x[0]
    if isinstance(x, list) and x:
        return np.nanmax([(idt - ix).days for ix in x])
    else:
        return np.nan

def avg_list(f, idt, iid, x, args):
    x = x[0]
    if isinstance(x, list) and x:
        return np.nanmean([(idt - ix).days for ix in x])
    else:
        return np.nan

def calc_practice_days(f, idt, iid, x, args):
    pass

def calc_longest_practice_days(f, idt, iid, x, args):
    pass

def calc_average_practice_days(f, idt, iid, x, args):
    pass
    

def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    # 基金经理信息
    ManagerInfoFT = JYDB.getTable("公募基金经理基本资料")
    ManagerIDs = ManagerInfoFT.getID()
    
    MFManagerFT = JYDB.getTable("公募基金经理(新)", args={"多重映射": True})
    
    # ####################### 基金经理变更次数 #######################
    ManagerCode = MFManagerFT.getFactor("所属人员代码", args={"只填起始日": True})
    look_back_period = {"1y": 12, "3y": 36, "5y": 60}
    for iLookBack, iLookBackPeriods in look_back_period.items():
        ManagerChgNum = fd.rolling_sum(
            fd.notnull(ManagerCode),
            window=iLookBackPeriods,
            min_periods=iLookBackPeriods,
            factor_name=f"manager_chg_num_{iLookBack}"
        )
        Factors.append(ManagerChgNum)
    
    # ####################### 基金经理最长/平均任职年限 #######################
    AccessionDate = MFManagerFT.getFactor("到人日期", args={"只填起始日": False})
    LongestAccessionDays = QS.FactorDB.PointOperation(
        "longest_accession_days",
        [AccessionDate],
        sys_args={
            "算子": max_list,
            "运算时点": "单时点",
            "运算ID": "单ID"
        }
    )
    Factors.append(LongestAccessionDays)
    AvgAccessionDays = QS.FactorDB.PointOperation(
        "average_accession_days",
        [AccessionDate],
        sys_args={
            "算子": avg_list,
            "运算时点": "单时点",
            "运算ID": "单ID"
        }
    )
    Factors.append(AvgAccessionDays)
    
    # ####################### 基金经理最长/平均从业年限 #######################
    ManagerCode = MFManagerFT.getFactor("所属人员代码", args={"只填起始日": False})
    PracticeDate = MFManagerFT.getFactor("证券从业日期")
    PracticeDays = QS.FactorDB.PointOperation(
        "practice_days",
        [PracticeDate],
        sys_args={
            "算子": calc_practice_days,
            "运算时点": "多时点",
            "运算ID": "多ID",
        }
    )
    
    LongestPracticeDays = QS.FactorDB.SectionOperation(
        "longest_practice_days",
        [PracticeDays, ManagerCode],
        sys_args={
            "算子": calc_longest_practice_days,
            "运算时点": "单时点",
            "输出形式": "全截面",
            "描述子截面": [ManagerIDs, None]
        }
    )
    Factors.append(LongestPracticeDays)
    AvgPracticeDays = QS.FactorDB.SectionOperation(
        "average_practice_days",
        [PracticeDays, ManagerCode],
        sys_args={
            "算子": calc_average_practice_days,
            "运算时点": "单时点",
            "输出形式": "全截面",
            "描述子截面": [ManagerIDs, None]
        }
    )
    Factors.append(AvgPracticeDays)
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_management",
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