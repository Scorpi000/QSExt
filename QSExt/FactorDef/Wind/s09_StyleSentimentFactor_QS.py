# -*- coding: utf-8 -*-
"""情绪因子""" 
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

# ### 行情因子 #############################################################################
Close = HDB.getTable("ElementaryFactor").getFactor("收盘价")


# ### 一致预期因子 #########################################################################
FT = HDB.getTable("WindConsensusFactor")
EPSAvg_FY0 = FT.getFactor("WEST_EPSAvg_FY0")
EPSAvg_Fwd12M = FT.getFactor("WEST_EPSFwd_12M")
EarningsAvg_FY0 = FT.getFactor("WEST_EarningsAvg_FY0")
EarningsAvg_Fwd12M = FT.getFactor("WEST_EarningsFwd_12M")
EPSStd_FY0 = FT.getFactor("WEST_EPSStd_FY0")

FT = WDB.getTable("中国A股投资评级汇总")
Rating = FT.getFactor("综合评级", args={"回溯天数":180, "周期":"263003000"}, new_name="Rating")
TargetPrice = FT.getFactor("一致预测目标价", args={"回溯天数":180, "周期":"263003000"})


# ### 资产负债表因子 #########################################################################
Equity = WDB.getTable("中国A股资产负债表").getFactor("股东权益合计(不含少数股东权益)", args={"计算方法":"最新", "报告期":"所有"})


# ### EPS 预测变化 #########################################################################
EPS_FY0_R1M = Factorize(fd.rolling_change_rate(EPSAvg_FY0,window=20+1),"EPS_FY0_R1M")
Factors.append(EPS_FY0_R1M)

EPS_FY0_R3M = Factorize(fd.rolling_change_rate(EPSAvg_FY0,window=60+1),"EPS_FY0_R3M")
Factors.append(EPS_FY0_R3M)

EPS_Fwd12M_R1M = Factorize(fd.rolling_change_rate(EPSAvg_Fwd12M,window=20+1),"EPS_Fwd12M_R1M")
Factors.append(EPS_Fwd12M_R1M)

EPS_Fwd12M_R3M = Factorize(fd.rolling_change_rate(EPSAvg_Fwd12M,window=60+1),"EPS_Fwd12M_R3M")
Factors.append(EPS_Fwd12M_R3M)


# ### ROE 预测变化 #########################################################################
ROE_FY0 = EarningsAvg_FY0/Equity
ROE_FY0_R1M = Factorize(fd.rolling_change_rate(ROE_FY0,window=20+1),"ROE_FY0_R1M")
Factors.append(ROE_FY0_R1M)

ROE_FY0_R3M = Factorize(fd.rolling_change_rate(ROE_FY0,window=60+1),"ROE_FY0_R3M")
Factors.append(ROE_FY0_R3M)

ROE_Fwd12M = EarningsAvg_Fwd12M/Equity
ROE_Fwd12M_R1M = Factorize(fd.rolling_change_rate(ROE_Fwd12M,window=20+1),"ROE_Fwd12M_R1M")
Factors.append(ROE_Fwd12M_R1M)

ROE_Fwd12M_R3M = Factorize(fd.rolling_change_rate(ROE_Fwd12M,window=60+1),"ROE_Fwd12M_R3M")
Factors.append(ROE_Fwd12M_R3M)


# ### 分析师评级 #########################################################################
Factors.append(Rating)

Rating_R1M = fd.rolling_change_rate(Rating,window=20+1,factor_name="Rating_R1M")
Factors.append(Rating_R1M)

Rating_R3M = fd.rolling_change_rate(Rating,window=20*3+1,factor_name="Rating_R3M")
Factors.append(Rating_R3M)


# ### 分析师预测目标收益率 #########################################################################
TargetReturn = Factorize(TargetPrice/Close-1,"TargetReturn")
Factors.append(TargetReturn)
#--从质量里面而来
EPS_FY0_CV = Factorize(EPSStd_FY0/abs(EPSAvg_FY0),"EPS_FY0_CV")
Factors.append(EPS_FY0_CV)


if __name__=="__main__":
    WDB.connect()
    CFT = QS.FactorDB.CustomFT("StyleSentimentFactor")
    CFT.addFactors(factor_list=Factors)
    
    IDs = WDB.getStockID(index_id="全体A股", is_current=False)
    #IDs = ["000001.SZ", "000003.SZ", "603297.SH"]# debug
    
    # if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2018, 8, 31, 23, 59, 59, 999999)
    # else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    # EndDT = dt.datetime(2018, 10, 31, 23, 59, 59, 999999)
    StartDT, EndDT = UpdateDate.StartDT, UpdateDate.EndDT
    
    DTs = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT-dt.timedelta(365), end_dt=EndDT)

    TargetTable = "StyleSentimentFactor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler)
    
    HDB.disconnect()
    WDB.disconnect()