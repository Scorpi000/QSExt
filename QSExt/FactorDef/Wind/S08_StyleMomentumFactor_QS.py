# coding=utf-8
"""动量因子"""
import datetime as dt
import UpdateDate
import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

Factors = []

WDB = QS.FactorDB.WindDB2()
HDB = QS.FactorDB.HDF5DB()
HDB.connect()


# ### 日行情因子 #############################################################################
FT = HDB.getTable("ElementaryFactor")
AdjClose = FT.getFactor("复权收盘价")
DayReturn = FT.getFactor("日收益率")
Close = FT.getFactor("收盘价")
Low = FT.getFactor("最低价")
TradeStatus = FT.getFactor("交易状态")





def MomentumFun(f,idt,iid,x,args):
    FirstClose = x[0][0,:]
    LastClose = x[0][-1,:]
    TradeStatus = x[1]
    Len = TradeStatus.shape[0]
    Mask = (np.sum((TradeStatus!="停牌") & pd.notnull(TradeStatus), axis=0)/Len<args['非空率'])
    FirstClose[(FirstClose==0) | Mask] = np.nan
    return LastClose/FirstClose-1

#计算RTN_1D
RTN_1D = QS.FactorDB.TimeOperation('RTN_1D',[AdjClose,TradeStatus],{'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[2-1,2-1],"运算ID":"多ID"})
Factors.append(RTN_1D)

#计算RTN_5D
RTN_5D = QS.FactorDB.TimeOperation('RTN_5D',[AdjClose,TradeStatus],{'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[6-1,6-1],"运算ID":"多ID"})
Factors.append(RTN_5D)

#计算RTN_20D
RTN_20D = QS.FactorDB.TimeOperation('RTN_20D',[AdjClose,TradeStatus],{'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[21-1,21-1],"运算ID":"多ID"})
Factors.append(RTN_20D)

#计算RTN_60D
RTN_60D = QS.FactorDB.TimeOperation('RTN_60D',[AdjClose,TradeStatus],{'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[61-1,61-1],"运算ID":"多ID"})
Factors.append(RTN_60D)

#计算RTN_120D
RTN_120D = QS.FactorDB.TimeOperation('RTN_120D',[AdjClose,TradeStatus],{'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[121-1,121-1],"运算ID":"多ID"})
Factors.append(RTN_120D)

#计算RTN_180D
RTN_180D = QS.FactorDB.TimeOperation('RTN_180D',[AdjClose,TradeStatus],{'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[181-1,181-1],"运算ID":"多ID"})
Factors.append(RTN_180D)

#计算RTN_240D
RTN_240D = QS.FactorDB.TimeOperation('RTN_240D',[AdjClose,TradeStatus],{'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[241-1,241-1],"运算ID":"多ID"})
Factors.append(RTN_240D)

#计算RTN_720D
RTN_720D = QS.FactorDB.TimeOperation('RTN_720D',[AdjClose,TradeStatus],{'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[721-1,721-1],"运算ID":"多ID"})
Factors.append(RTN_720D)

#计算RTN_1200D
RTN_1200D = QS.FactorDB.TimeOperation('RTN_1200D',[AdjClose,TradeStatus],{'算子':MomentumFun,'参数':{"非空率":0.8},'回溯期数':[1201-1,1201-1],"运算ID":"多ID"})
Factors.append(RTN_1200D)


if __name__=="__main__":
    WDB.connect()
    CFT = QS.FactorDB.CustomFT("StyleMomentumFactor")
    CFT.addFactors(factor_list=Factors)
    
    IDs = WDB.getStockID(index_id="全体A股", is_current=False)
    #IDs = ["000001.SZ", "000003.SZ", "603297.SH"]# debug
    
    # if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2018, 8, 31, 23, 59, 59, 999999)
    # else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    # EndDT = dt.datetime(2018, 10, 31, 23, 59, 59, 999999)
    StartDT, EndDT = UpdateDate.StartDT, UpdateDate.EndDT
    
    DTs = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT-dt.timedelta(int(5*365+183)), end_dt=EndDT)

    TargetTable = "StyleMomentumFactor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler)
    
    HDB.disconnect()
    WDB.disconnect()