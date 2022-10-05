# -*- coding: utf-8 -*-
"""成长因子"""
import datetime as dt
import UpdateDate
import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize

Factors = []

WDB = QS.FactorDB.WindDB2()
HDB = QS.FactorDB.HDF5DB()
HDB.connect()

# ### 利润表因子 #############################################################################
FT = WDB.getTable("中国A股利润表")
Sales_TTM = FT.getFactor("营业收入", args={"计算方法":"TTM"})
Sales_L1 = FT.getFactor("营业收入", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})

Sales_Y0 = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":0})
Sales_Y1 = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":1})
Sales_Y2 = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":2})
Sales_Y3 = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":3})
Sales_Y4 = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":4})

Earnings_Y0 = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"最新", "报告期":"年报", "回溯年数":0})
Earnings_Y1 = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"最新", "报告期":"年报", "回溯年数":1})
Earnings_Y2 = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"最新", "报告期":"年报", "回溯年数":2})
Earnings_Y3 = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"最新", "报告期":"年报", "回溯年数":3})
Earnings_Y4 = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"最新", "报告期":"年报", "回溯年数":4})

OperEarnings_TTM = FT.getFactor("营业利润", args={"计算方法":"TTM"})
OperEarnings_L1 = FT.getFactor("营业利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})

OperEarnings_SQ0P = FT.getFactor("营业利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
OperEarnings_SQ1P = FT.getFactor("营业利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
OperEarnings_SQ4P = FT.getFactor("营业利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
OperEarnings_SQ5P = FT.getFactor("营业利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})


Earnings_TTM = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"TTM"})
Earnings_L1 = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})


Earnings_SQ0P = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
Earnings_SQ1P = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
Earnings_SQ2P = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":2})
Earnings_SQ3P = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":3})
Earnings_SQ4P = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
Earnings_SQ5P = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})
Earnings_SQ6P = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":6})
Earnings_SQ7P = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":7})
Earnings_TTM_Deducted = FT.getFactor("扣除非经常性损益后净利润", args={"计算方法":"TTM"})
Earnings_TTM_Deducted_L1 = FT.getFactor("扣除非经常性损益后净利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})
 

Sales_SQ0P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
Sales_SQ1P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
Sales_SQ4P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
Sales_SQ5P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})


Earnings_Deducted_SQ0P = FT.getFactor("扣除非经常性损益后净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
Earnings_Deducted_SQ1P = FT.getFactor("扣除非经常性损益后净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
Earnings_Deducted_SQ4P = FT.getFactor("扣除非经常性损益后净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
# ### 现金流量表因子 #############################################################################
FT = WDB.getTable("中国A股现金流量表")
OCF_Y0 = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"最新", "报告期":"年报", "回溯年数":0})
OCF_Y1 = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"最新", "报告期":"年报", "回溯年数":1})
OCF_Y2 = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"最新", "报告期":"年报", "回溯年数":2})
OCF_Y3 = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"最新", "报告期":"年报", "回溯年数":3})
OCF_Y4 = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"最新", "报告期":"年报", "回溯年数":4})

OCF_SQ0P = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
OCF_SQ1P = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
OCF_SQ4P = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
OCF_SQ5P = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})

OCF_TTM = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"TTM"})
OCF_TTM_L1 = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})

# ### 资产负债表 #############################################################################
FT = WDB.getTable("中国A股资产负债表")
Asset = FT.getFactor("资产总计",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
Asset_L1 = FT.getFactor("资产总计",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})
Equity = FT.getFactor("股东权益合计(不含少数股东权益)",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
Equity_L1 = FT.getFactor("股东权益合计(不含少数股东权益)",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})


# ### 一致预期因子 #############################################################################
FT = HDB.getTable("WindConsensusFactor")
EarningsAvg_FY0 = FT.getFactor("WEST_EarningsAvg_FY0")# 单位: 万元
EarningsAvg_FY1 = FT.getFactor("WEST_EarningsAvg_FY1")# 单位: 万元


# 以回归的方式计算增速
def RegressionFun(f, idt, iid, x, args):
    Y = np.array(x)
    Mask = (~np.isnan(Y))
    L = Y.shape[0]
    if np.sum(Mask)/L<args['非空率']: return np.nan
    X = np.array(range(L), dtype='float')[Mask]
    Y = Y[Mask]
    x = X-np.nanmean(X)
    y = Y-np.nanmean(Y)
    Numerator = np.nansum(x*y) / np.nansum(x*x)
    Denominator = np.abs(np.nanmean(Y))
    if Denominator==0: return np.sign(Numerator)
    else: return Numerator / Denominator
# 20180527-光大证券-多因子系列报告之十二：成长因子重构与优化，稳健加速为王 系列一
# 过去8个季度的净利润相对于时间（T,以及T^2）的回归
def getQuarterLastDateTime(dts):
    dts = [x for x in dts if x != None]
    dts = sorted(dts)
    TargetDTs = [dts[0]]
    for iDT in dts:
        if (iDT.year != TargetDTs[-1].year):
            TargetDTs.append(iDT)
        elif (iDT.month - 1) // 3 != (TargetDTs[-1].month - 1) // 3:
            TargetDTs.append(iDT)
        else:
            TargetDTs[-1] = iDT
    return TargetDTs

# 20180527-光大证券-多因子系列报告之十二：成长因子重构与优化，稳健加速为王 系列一
# 过去8个季度的净利润相对于时间（T,以及T^2）的回归
def ACC_Fun(f, idt, iid, x, args):
    Y = np.array(x)
    Mask = (~np.isnan(Y))
    L = Y.shape[0]
    tmp = [1, 2, 3, 4, 5, 6, 7, 8]
    tmp_sq = (list(map(lambda num: num * num, tmp)))
    X = np.array([tmp, tmp_sq]).T
    Y = Y[Mask]
    X = X[Mask]
    if np.sum(Mask) / L < args['非空率']: return np.nan

    x = X - np.nanmean(X, axis=0)
    y = Y - np.nanmean(Y)
    x = sm.add_constant(x)
    est = sm.OLS(y, x)
    est = est.fit()
    return est.params[-1]


# #### 五年增速: 回归方式计算 ########################################################################
Factors.append(QS.FactorDB.PointOperation("Revenue_5Y_Gr",[Sales_Y4,Sales_Y3,Sales_Y2,Sales_Y1,Sales_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))
Factors.append(QS.FactorDB.PointOperation('NetProfit_5Y_Gr',[Earnings_Y4,Earnings_Y3,Earnings_Y2,Earnings_Y1,Earnings_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))
Factors.append(QS.FactorDB.PointOperation('OCF_5Y_Gr',[OCF_Y4,OCF_Y3,OCF_Y2,OCF_Y1,OCF_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))


# #### 三年增速: 回归方式计算 #########################################################################
Factors.append(QS.FactorDB.PointOperation('Revenue_3Y_Gr',[Sales_Y2,Sales_Y1,Sales_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))
Factors.append(QS.FactorDB.PointOperation('NetProfit_3Y_Gr',[Earnings_Y2,Earnings_Y1,Earnings_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))
Factors.append(QS.FactorDB.PointOperation('OCF_3Y_Gr',[OCF_Y2,OCF_Y1,OCF_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))


# #### 一年增速: 同比 #########################################################################
Factors.append(Factorize((Sales_Y0-Sales_Y1)/abs(Sales_Y1),"Revenue_LYR_YoY"))
Factors.append(Factorize((Earnings_Y0-Earnings_Y1)/abs(Earnings_Y1),"NetProfit_LYR_YoY"))
Factors.append(Factorize((OCF_Y0-OCF_Y1)/abs(OCF_Y1),"OCF_LYR_YoY"))
Factors.append(Factorize(Earnings_TTM/Earnings_L1-1,"Revenue_TTM_YoY"))#--营业收入的TTM同比变动 新添加
Factors.append(Factorize(OperEarnings_TTM/OperEarnings_L1-1,"OperProfit_TTM_YoY"))#--营业利润的TTM同比变动 新添加
Factors.append(Factorize(Sales_TTM/Sales_L1-1,"NetProfit_TTM_YoY"))#--净利润的TTM同比变动 新添加

Factors.append(Factorize(Earnings_TTM_Deducted/Earnings_TTM_Deducted_L1-1,"NetProfitDeducted_TTM_YoY"))#--扣非净利润TTM同比变动 新添加
Factors.append(Factorize(OCF_TTM/OCF_TTM_L1-1,"OCF_TTM_YoY"))#--经营活动现金流_TTM同比变动 新添加
Factors.append(Factorize(Asset/Asset_L1-1,"Asset_LR_YoY"))#--总资产同比变动 新添加
Factors.append(Factorize(Equity/Equity_L1-1,"Equity_LR_YoY"))#--净资产（股东权益）同比变动 新添加
  
  
# #### 季度增速: 同比 #########################################################################
Revenue_SQ_YoY = Factorize((Sales_SQ0P-Sales_SQ4P)/abs(Sales_SQ4P),"Revenue_SQ_YoY")
NetProfit_SQ_YoY = Factorize((Earnings_SQ0P-Earnings_SQ4P)/abs(Earnings_SQ4P),"NetProfit_SQ_YoY")
OperProfit_SQ_YoY = Factorize((OperEarnings_SQ0P-OperEarnings_SQ4P)/abs(OperEarnings_SQ4P),"OperProfit_SQ_YoY")
NetProfitDeducted_SQ_YoY = Factorize((Earnings_Deducted_SQ0P-Earnings_Deducted_SQ4P)/abs(Earnings_Deducted_SQ4P),"NetProfitDeducted_SQ_YoY")
OCF_SQ_YoY = Factorize((OCF_SQ0P-OCF_SQ4P)/abs(OCF_SQ4P),"OCF_SQ_YoY")
Factors.extend([Revenue_SQ_YoY, NetProfit_SQ_YoY, OperProfit_SQ_YoY,NetProfitDeducted_SQ_YoY, OCF_SQ_YoY])
# #### 季度增速: 环比 #########################################################################
Revenue_SQ_QoQ = Factorize(Sales_SQ0P/Sales_SQ1P,"Revenue_SQ_QoQ")#--新添加
OperProfit_SQ_QoQ= Factorize(OperEarnings_SQ0P/OperEarnings_SQ1P,"OperProfit_SQ_QoQ")#--新添加
NetProfit_SQ_QoQ = Factorize(Earnings_SQ0P/Earnings_SQ1P,"NetProfit_SQ_QoQ")#--新添加



NetProfitDeducted_SQ_QoQ= Factorize(Earnings_Deducted_SQ0P/Earnings_Deducted_SQ1P,"NetProfitDeducted_SQ_QoQ")#--新添加
OCF_SQ_QoQ= Factorize(OCF_SQ0P/OCF_SQ1P,"OCF_SQ_QoQ")#--新添加
Factors.extend([OCF_SQ_QoQ,NetProfitDeducted_SQ_QoQ,OperProfit_SQ_QoQ,Revenue_SQ_QoQ,NetProfit_SQ_QoQ])

# #### 季度增速的增量 #######################################################################
Factors.append(Factorize((Revenue_SQ_YoY-((Sales_SQ1P-Sales_SQ5P)/abs(Sales_SQ5P))),"Revenue_SQ_Acc"))
Factors.append(Factorize((NetProfit_SQ_YoY-((Earnings_SQ1P-Earnings_SQ5P)/abs(Earnings_SQ5P))),"NetProfit_SQ_Acc"))
Factors.append(Factorize((OperProfit_SQ_YoY-((OperEarnings_SQ1P-OperEarnings_SQ5P)/abs(OperEarnings_SQ5P))),"OperProfit_SQ_Acc"))
Factors.append(Factorize((OCF_SQ_YoY-((OCF_SQ1P-OCF_SQ5P)/abs(OCF_SQ5P))),"OCF_SQ_Acc"))


# #### 预期增长 ###############################################################################
Factors.append(Factorize((EarningsAvg_FY0*10000-Earnings_Y0)/abs(Earnings_Y0),'NetProfit_FY0_YoY'))
Factors.append(Factorize(((EarningsAvg_FY1*10000-Earnings_Y0)/abs(Earnings_Y0)+1)**0.5-1,'NetProfit_FY1_Gr'))


# #### 成长加速度计算 ###############################################################################
# 20180527-光大证券-多因子系列报告之十二：成长因子重构与优化，稳健加速为王 系列一
# 过去8个季度的净利润相对于时间（T,以及T^2）的回归

NetProft_8Q_Acc=QS.FactorDB.PointOperation("NetProft_8Q_Acc",[Earnings_SQ0P,Earnings_SQ1P,Earnings_SQ3P,Earnings_SQ3P,Earnings_SQ4P,Earnings_SQ5P,Earnings_SQ6P,Earnings_SQ7P],{'算子':ACC_Fun,"参数":{'非空率':0.4}})
Factors.append(NetProft_8Q_Acc)



if __name__=="__main__":
    WDB.connect()
    CFT = QS.FactorDB.CustomFT("StyleGrowthFactor")
    CFT.addFactors(factor_list=Factors)
    
    IDs = WDB.getStockID(index_id="全体A股", is_current=False)
    StartDT, EndDT = UpdateDate.StartDT, UpdateDate.EndDT
    
    DTs = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT-dt.timedelta(365), end_dt=EndDT)
    
    TargetTable = "StyleGrowthFactor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler)

    
    HDB.disconnect()
    WDB.disconnect()