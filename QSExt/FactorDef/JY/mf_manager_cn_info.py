# -*- coding: utf-8 -*-
"""基金经理特征因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    FT = JYDB.getTable("公募基金经理基本资料")
    Factors.append(FT.getFactor("姓名", new_name="name"))
    Factors.append(FT.getFactor("性别_R", new_name="name"))
    Factors.append(FT.getFactor("国籍_R", new_name="name"))
    Factors.append(fd.strftime(FT.getFactor("出生日期"), "%Y-%m-%d", factor_name="birthday"))
    Factors.append(FT.getFactor("最高学历_R", new_name="name"))
    Factors.append(fd.strftime(FT.getFactor("证券从业日期"), "%Y-%m-%d", factor_name="practice_date"))
    Factors.append(FT.getFactor("证券从业经历（年）", new_name="experience_time"))
    Factors.append(FT.getFactor("专业资格", new_name="professional_qualification"))
    Factors.append(FT.getFactor("背景介绍", new_name="background"))
    
    IDs = FT.getID()
    
    UpdateArgs = {
        "因子表": "mf_manager_cn_info",
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": IDs
    }
    
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
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    #DTs = DTs[-1:]# 只保留最新数据
    
    #IDs = sorted(pd.read_csv("."+os.sep+"MFIDs.csv", index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
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