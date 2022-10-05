# coding=utf-8
"""Wind 一致预期因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

import UpdateDate
Factors = []

WDB = QS.FactorDB.WindDB2()


def DetailProspectFun(f, idt, iid, x, args):
    EPS_Avg_FY = []
    EPS_Std_FY = []
    EPS_Num_FY = []
    Earnings_FY = []
    ReportDate = []
    for i in range(3):
        iData = x[i]
        iData.iloc[:,4:] = iData.iloc[:,4:].astype('float')# 将Decimal类型数据转为float
        if iData.shape[0]==0:
            EPS_Avg_FY.append(np.nan)
            EPS_Std_FY.append(np.nan)
            EPS_Num_FY.append(0.0)
            Earnings_FY.append(np.nan)
            ReportDate.append(None)
            continue
        ReportDate.append(iData['预测报告期'].iloc[0])
        Earnings_FY.append(iData["预测净利润(万元)"].mean())
        iMask = (iData['预测每股收益(摊薄)(元)'].isnull()) & (iData['预测净利润(万元)'].notnull())
        if iMask.sum()>0:
            iData.ix[iMask,'预测每股收益(摊薄)(元)'] = iData[iMask]['预测净利润(万元)']/iData[iMask]['预测基准股本(万股)']
        iData = iData[iData['预测每股收益(摊薄)(元)'].notnull()]
        EPS_Avg_FY.append(iData['预测每股收益(摊薄)(元)'].mean())
        EPS_Std_FY.append(iData['预测每股收益(摊薄)(元)'].std())
        EPS_Num_FY.append(iData['预测每股收益(摊薄)(元)'].shape[0])
    TargetDate1 = str(idt.year)+'1231'
    TargetDate2 = str(int(idt.year)+1)+'1231'
    if (TargetDate1 not in ReportDate) or (TargetDate2 not in ReportDate):
        EPS_Fwd12M = np.nan
        Earnings_Fwd12M = np.nan
    else:
        Weight1 = (dt.date(int(TargetDate1[0:4]),12,31)-idt.date()).days / 365
        EPS_Fwd12M = Weight1 * EPS_Avg_FY[ReportDate.index(TargetDate1)] + (1-Weight1) * EPS_Avg_FY[ReportDate.index(TargetDate2)]
        Earnings_Fwd12M = Weight1 * Earnings_FY[ReportDate.index(TargetDate1)] + (1-Weight1) * Earnings_FY[ReportDate.index(TargetDate2)]
    return tuple(EPS_Avg_FY) + tuple(EPS_Std_FY) + tuple(EPS_Num_FY) + tuple(Earnings_FY) + (EPS_Fwd12M, Earnings_Fwd12M)

DetailProspect = WDB.getTable("中国A股盈利预测明细").getFactor("预测每股收益(摊薄)(元)", args={"算子":DetailProspectFun, "附加字段":["预测净利润(万元)"], 
                                                                                             "向前年数":[0,1,2], "周期":180, "数据类型":"string"})

Factors.append(Factorize(fd.fetch(DetailProspect, 0), "WEST_EPSAvg_FY0"))
Factors.append(Factorize(fd.fetch(DetailProspect, 1), "WEST_EPSAvg_FY1"))
Factors.append(Factorize(fd.fetch(DetailProspect, 2), "WEST_EPSAvg_FY2"))
Factors.append(Factorize(fd.fetch(DetailProspect, 3), "WEST_EPSStd_FY0"))
Factors.append(Factorize(fd.fetch(DetailProspect, 4), "WEST_EPSStd_FY1"))
Factors.append(Factorize(fd.fetch(DetailProspect, 5), "WEST_EPSStd_FY2"))
Factors.append(Factorize(fd.fetch(DetailProspect, 6), "WEST_EPSNum_FY0"))
Factors.append(Factorize(fd.fetch(DetailProspect, 7), "WEST_EPSNum_FY1"))
Factors.append(Factorize(fd.fetch(DetailProspect, 8), "WEST_EPSNum_FY2"))
Factors.append(Factorize(fd.fetch(DetailProspect, 9), "WEST_EarningsAvg_FY0"))
Factors.append(Factorize(fd.fetch(DetailProspect, 10), "WEST_EarningsAvg_FY1"))
Factors.append(Factorize(fd.fetch(DetailProspect, 11), "WEST_EarningsAvg_FY2"))
Factors.append(Factorize(fd.fetch(DetailProspect, 12), "WEST_EPSFwd_12M"))
Factors.append(Factorize(fd.fetch(DetailProspect, 13), "WEST_EarningsFwd_12M"))


if __name__=="__main__":
    HDB = QS.FactorDB.HDF5DB()
    HDB.connect()    
    WDB.connect()
    
    CFT = QS.FactorDB.CustomFT("WindConsensusFactor")
    CFT.addFactors(factor_list=Factors)
    
    IDs = WDB.getStockID(index_id="全体A股", is_current=False)
    #IDs = ["000001.SZ", "000003.SZ", "603297.SH"]# debug
    
    #if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2018, 8, 31, 23, 59, 59, 999999)
    #else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    #EndDT = dt.datetime(2018, 10, 31, 23, 59, 59, 999999)
    StartDT, EndDT = UpdateDate.StartDT, UpdateDate.EndDT
    
    DTs = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT-dt.timedelta(365), end_dt=EndDT)
    
    TargetTable = "WindConsensusFactor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler)
    
    HDB.disconnect()
    WDB.disconnect()