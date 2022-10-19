# coding=utf-8
"""Wind 一致预期因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

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

def defFactor(args={}):
    Factors = []

    WDB = args["WDB"]

    DetailProspect = WDB.getTable("中国A股盈利预测明细").getFactor("预测每股收益(摊薄)(元)", 
        args={"算子":DetailProspectFun, "附加字段":["预测净利润(万元)"], 
            "向前年数":[0,1,2], "周期":180, "数据类型":"object"})

    Factors.append(fd.fetch(DetailProspect, 0, factor_name="WEST_EPSAvg_FY0"))
    Factors.append(fd.fetch(DetailProspect, 1, factor_name="WEST_EPSAvg_FY1"))
    Factors.append(fd.fetch(DetailProspect, 2, factor_name="WEST_EPSAvg_FY2"))
    Factors.append(fd.fetch(DetailProspect, 3, factor_name="WEST_EPSStd_FY0"))
    Factors.append(fd.fetch(DetailProspect, 4, factor_name="WEST_EPSStd_FY1"))
    Factors.append(fd.fetch(DetailProspect, 5, factor_name="WEST_EPSStd_FY2"))
    Factors.append(fd.fetch(DetailProspect, 6, factor_name="WEST_EPSNum_FY0"))
    Factors.append(fd.fetch(DetailProspect, 7, factor_name="WEST_EPSNum_FY1"))
    Factors.append(fd.fetch(DetailProspect, 8, factor_name="WEST_EPSNum_FY2"))
    Factors.append(fd.fetch(DetailProspect, 9, factor_name="WEST_EarningsAvg_FY0"))
    Factors.append(fd.fetch(DetailProspect, 10, factor_name="WEST_EarningsAvg_FY1"))
    Factors.append(fd.fetch(DetailProspect, 11, factor_name="WEST_EarningsAvg_FY2"))
    Factors.append(fd.fetch(DetailProspect, 12, factor_name="WEST_EPSFwd_12M"))
    Factors.append(fd.fetch(DetailProspect, 13, factor_name="WEST_EarningsFwd_12M"))

    return Factors


if __name__=="__main__":
    pass