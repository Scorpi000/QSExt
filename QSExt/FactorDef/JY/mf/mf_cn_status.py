# -*- coding: utf-8 -*-
"""公募基金状态因子"""
import os
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

def ifExist(f, idt, iid, x, args):
    EstablishDate, ExpireDate = x
    Exist = np.ones(EstablishDate.shape)
    DTs = np.array([idt]).T.repeat(EstablishDate.shape[1], axis=1).astype("datetime64")
    Mask = pd.isnull(EstablishDate)
    EstablishDate[Mask] = (DTs + np.timedelta64(1, "D"))[Mask]
    Mask = pd.isnull(ExpireDate)
    ExpireDate[Mask] = DTs[Mask]
    Exist[(EstablishDate>DTs) | (ExpireDate<DTs)] = 0
    return Exist

# args 应该包含的参数
# JYDB: 聚源因子库对象
def defFactor(args={}, debug=False):
    Factors = []

    JYDB = args["JYDB"]

    FT = JYDB.getTable("公募基金概况")
    EstablishDate = FT.getFactor("设立日期")
    ExpireDate = FT.getFactor("存续期截止日")
    Factors.append(QS.FactorDB.PointOperation("if_exist", [EstablishDate, ExpireDate], {"算子":ifExist, "运算时点":"多时点", "运算ID":"多ID"}))
    
    FT = JYDB.getTable("公募基金状态(TA类型)", args={"回溯天数": np.inf})
    Factors.append(FT.getFactor("申赎状态_R", new_name="status_ta"))
    FT = JYDB.getTable("公募基金申赎状态", args={"回溯天数": np.inf})
    Factors.append(FT.getFactor("申购状态", new_name="status_applying"))
    Factors.append(FT.getFactor("赎回状态", new_name="status_redeem"))
    Factors.append(FT.getFactor("基金大额申购上限(元)", new_name="max_applying"))
    
    UpdateArgs = {"因子表": "mf_cn_status",
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
    
    StartDT, EndDT = dt.datetime(2020, 6, 1), dt.datetime(2020, 9, 25)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    #DTs = DTs[-1:]# 只保留最新数据
    
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