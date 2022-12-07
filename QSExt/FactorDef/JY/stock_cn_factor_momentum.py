# coding=utf-8
"""动量因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_factor_momentum",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def MomentumFun(f,idt,iid,x,args):
    FirstClose = x[0][0,:]
    LastClose = x[0][-1,:]
    IfTrading = x[1]
    Len = IfTrading.shape[0]
    Mask = (np.sum(IfTrading==1, axis=0)/Len<args['非空率'])
    FirstClose[(FirstClose==0) | Mask] = np.nan
    return LastClose/FirstClose-1

def defFactor(args={}):
    Factors = []

    LDB = args["LDB"]
    
    # ### 日行情因子 #############################################################################
    FT = LDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    AdjClose = FT.getFactor("close")
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    IfTrading = FT.getFactor("if_trading")
    FT = LDB.getTable("stock_cn_info")
    IfListed = FT.getFactor("if_listed")
    Mask = ((IfListed==1) & (IfTrading==1))

    #计算RTN_1D
    RTN_1D = QS.FactorDB.TimeOperation('rtn_1d', [AdjClose, Mask], {'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[2-1,2-1],"运算ID":"多ID"})
    Factors.append(RTN_1D)
    
    #计算RTN_5D
    RTN_5D = QS.FactorDB.TimeOperation('rtn_5d', [AdjClose, Mask], {'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[6-1,6-1],"运算ID":"多ID"})
    Factors.append(RTN_5D)
    
    #计算RTN_20D
    RTN_20D = QS.FactorDB.TimeOperation('rtn_20d', [AdjClose, Mask], {'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[21-1,21-1],"运算ID":"多ID"})
    Factors.append(RTN_20D)

    #计算RTN_60D
    RTN_60D = QS.FactorDB.TimeOperation('rtn_60d', [AdjClose, Mask], {'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[61-1,61-1],"运算ID":"多ID"})
    Factors.append(RTN_60D)
    
    #计算RTN_120D
    RTN_120D = QS.FactorDB.TimeOperation('rtn_120d', [AdjClose, Mask], {'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[121-1,121-1],"运算ID":"多ID"})
    Factors.append(RTN_120D)
    
    #计算RTN_180D
    RTN_180D = QS.FactorDB.TimeOperation('rtn_180d', [AdjClose, Mask], {'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[181-1,181-1],"运算ID":"多ID"})
    Factors.append(RTN_180D)
    
    #计算RTN_240D
    RTN_240D = QS.FactorDB.TimeOperation('rtn_240d', [AdjClose, Mask], {'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[241-1,241-1],"运算ID":"多ID"})
    Factors.append(RTN_240D)

    #计算RTN_720D
    RTN_720D = QS.FactorDB.TimeOperation('rtn_720d', [AdjClose, Mask], {'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[721-1,721-1],"运算ID":"多ID"})
    Factors.append(RTN_720D)
    
    #计算RTN_1200D
    RTN_1200D = QS.FactorDB.TimeOperation('rtn_1200d', [AdjClose, Mask], {'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[1201-1,1201-1],"运算ID":"多ID"})
    Factors.append(RTN_1200D)
    
    return Factors


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.WindDB2()
    JYDB.connect()
    
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = JYDB.getStockID(is_current=False)
    
    Args = {"JYDB": JYDB}
    Factors = defFactor(args=Args)
    
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