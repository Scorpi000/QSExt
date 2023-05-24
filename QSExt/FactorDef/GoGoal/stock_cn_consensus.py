# -*- coding: utf-8 -*-
"""A股一致预期"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
from QSExt.FactorDataBase.GoGoalDB import GoGoalDB
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools


def FY0Fun(df):
    iDT = df.index[0][0]
    iTargetYear = (iDT.year if iDT>= dt.datetime(iDT.year, 5, 1) else iDT.year - 1)
    df = df[df["一致预期年度"]==iTargetYear]
    if df.empty:
        return np.nan
    else:
        return float(df.iloc[0, 0])

def FY1Fun(df):
    iDT = df.index[0][0]
    iTargetYear = (iDT.year + 1 if iDT>= dt.datetime(iDT.year, 5, 1) else iDT.year)
    df = df[df["一致预期年度"]==iTargetYear]
    if df.empty:
        return np.nan
    else:
        return float(df.iloc[0, 0])

def FY2Fun(df):
    iDT = df.index[0][0]
    iTargetYear = (iDT.year + 2 if iDT>= dt.datetime(iDT.year, 5, 1) else iDT.year + 1)
    df = df[df["一致预期年度"]==iTargetYear]
    if df.empty:
        return np.nan
    else:
        return float(df.iloc[0, 0])
    
def defFactor(args={}):
    Factors = []
    
    GGDB = args["GGDB"]
    
    FT = GGDB.getTable("个股一致预期数据表", args={
        "多重映射": True,
        "附加字段": ["一致预期年度", "ASC"],
        "算子数据类型": "double"
    })
    Factors.append(FT.getFactor("一致预期净资产收益率", args={"算子": FY0Fun}, new_name="roe_fy0"))
    Factors.append(FT.getFactor("一致预期净资产收益率", args={"算子": FY1Fun}, new_name="roe_fy1"))
    Factors.append(FT.getFactor("一致预期净资产收益率", args={"算子": FY2Fun}, new_name="roe_fy2"))
    
    FT = GGDB.getTable("个股一致预期滚动数据表")
    Factors.append(FT.getFactor("一致预期净资产收益率", new_name="roe_fwd12m"))
            
    UpdateArgs = {
        "因子表": "stock_cn_consensus",
        "默认起始日": dt.datetime(2002, 1, 1),
        "最长回溯期": 365,
        "IDs": "股票",
        "时点类型": "交易日"
    }    
    
    return Factors, UpdateArgs


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    GGDB = GoGoalDB(logger=Logger).connect()
    TDB = QS.FactorDB.HDF5DB(logger=Logger).connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = GGDB.getStockID()
    
    Args = {"GGDB": GGDB, "LDB": TDB}
    Factors, UpdateArgs = defFactor(args=Args)
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTs)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
        factor_db=TDB, table_name=TargetTable,
        if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    JYDB.disconnect()