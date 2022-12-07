# -*- coding: utf-8 -*-
"""成长因子"""
import datetime as dt

import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_factor_growth",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

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

def defFactor(args={}):
    Factors = []

    JYDB = args["JYDB"]
    LDB = args["LDB"]

    # ### 利润表因子 #############################################################################
    FT = JYDB.getTable("利润分配表_新会计准则")
    Sales_TTM = FT.getFactor("营业收入", args={"计算方法":"TTM"})
    Sales_L1 = FT.getFactor("营业收入", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})

    Sales_Y0 = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":0})
    Sales_Y1 = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":1})
    Sales_Y2 = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":2})
    Sales_Y3 = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":3})
    Sales_Y4 = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":4})

    NetProfit_Y0 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"最新", "报告期":"年报", "回溯年数":0})
    NetProfit_Y1 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"最新", "报告期":"年报", "回溯年数":1})
    NetProfit_Y2 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"最新", "报告期":"年报", "回溯年数":2})
    NetProfit_Y3 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"最新", "报告期":"年报", "回溯年数":3})
    NetProfit_Y4 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"最新", "报告期":"年报", "回溯年数":4})

    OperNetProfit_TTM = FT.getFactor("营业利润", args={"计算方法":"TTM"})
    OperNetProfit_L1 = FT.getFactor("营业利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})

    OperNetProfit_SQ0P = FT.getFactor("营业利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
    OperNetProfit_SQ1P = FT.getFactor("营业利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
    OperNetProfit_SQ4P = FT.getFactor("营业利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
    OperNetProfit_SQ5P = FT.getFactor("营业利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})

    NetProfit_TTM = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"TTM"})
    NetProfit_L1 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})

    NetProfit_SQ0P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
    NetProfit_SQ1P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
    NetProfit_SQ2P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":2})
    NetProfit_SQ3P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":3})
    NetProfit_SQ4P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
    NetProfit_SQ5P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})
    NetProfit_SQ6P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":6})
    NetProfit_SQ7P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":7})
    
    Sales_SQ0P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
    Sales_SQ1P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
    Sales_SQ4P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
    Sales_SQ5P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})
    
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)")
    NetProfit_TTM_Deducted = FT.getFactor("扣除非经常性损益后的净利润", args={"计算方法":"TTM"})
    NetProfit_TTM_Deducted_L1 = FT.getFactor("扣除非经常性损益后的净利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})
    NetProfit_Deducted_SQ0P = FT.getFactor("扣除非经常性损益后的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
    NetProfit_Deducted_SQ1P = FT.getFactor("扣除非经常性损益后的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
    NetProfit_Deducted_SQ4P = FT.getFactor("扣除非经常性损益后的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
    
    # ### 现金流量表因子 #############################################################################
    FT = JYDB.getTable("现金流量表_新会计准则")
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
    FT = JYDB.getTable("资产负债表_新会计准则")
    Asset = FT.getFactor("资产总计",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    Asset_L1 = FT.getFactor("资产总计",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})
    Equity = FT.getFactor("归属母公司股东权益合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    Equity_L1 = FT.getFactor("归属母公司股东权益合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})


    # ### 一致预期因子 #############################################################################
    FT = LDB.getTable("stock_cn_consensus")
    NetProfitAvg_FY0 = FT.getFactor("net_profit_fy0")# 单位: 万元
    NetProfitAvg_FY1 = FT.getFactor("net_profit_fy1")# 单位: 万元

    # #### 五年增速: 回归方式计算 ########################################################################
    Factors.append(QS.FactorDB.PointOperation("revenue_5y_gr",[Sales_Y4,Sales_Y3,Sales_Y2,Sales_Y1,Sales_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))
    Factors.append(QS.FactorDB.PointOperation("net_profit_5y_gr",[NetProfit_Y4,NetProfit_Y3,NetProfit_Y2,NetProfit_Y1,NetProfit_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))
    Factors.append(QS.FactorDB.PointOperation("ocf_5y_gr",[OCF_Y4,OCF_Y3,OCF_Y2,OCF_Y1,OCF_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))

    # #### 三年增速: 回归方式计算 #########################################################################
    Factors.append(QS.FactorDB.PointOperation('revenue_3y_gr',[Sales_Y2,Sales_Y1,Sales_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))
    Factors.append(QS.FactorDB.PointOperation('net_profit_3y_gr',[NetProfit_Y2,NetProfit_Y1,NetProfit_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))
    Factors.append(QS.FactorDB.PointOperation('ocf_3y_gr',[OCF_Y2,OCF_Y1,OCF_Y0],{'算子':RegressionFun,"参数":{'非空率':0.4}}))

    # #### 一年增速: 同比 #########################################################################
    Factors.append(Factorize((Sales_Y0-Sales_Y1)/abs(Sales_Y1),"revenue_lyr_yoy"))
    Factors.append(Factorize((NetProfit_Y0-NetProfit_Y1)/abs(NetProfit_Y1),"net_profit_lyr_yoy"))
    Factors.append(Factorize((OCF_Y0-OCF_Y1)/abs(OCF_Y1),"ocf_lyr_yoy"))
    Factors.append(Factorize(NetProfit_TTM/NetProfit_L1-1,"net_profit_ttm_yoy"))
    Factors.append(Factorize(OperNetProfit_TTM/OperNetProfit_L1-1,"oper_profit_ttm_yoy"))
    Factors.append(Factorize(Sales_TTM/Sales_L1-1,"net_profit_ttm_yoy"))

    Factors.append(Factorize(NetProfit_TTM_Deducted/NetProfit_TTM_Deducted_L1-1,"net_profit_deducted_ttm_yoy"))#--扣非净利润TTM同比变动 新添加
    Factors.append(Factorize(OCF_TTM/OCF_TTM_L1-1,"ocf_ttm_yoy"))
    Factors.append(Factorize(Asset/Asset_L1-1,"asset_lr_yoy"))
    Factors.append(Factorize(Equity/Equity_L1-1,"equity_lr_yoy"))

    # #### 季度增速: 同比 #########################################################################
    Revenue_SQ_YoY = Factorize((Sales_SQ0P-Sales_SQ4P)/abs(Sales_SQ4P),"revenue_sq_yoy")
    NetProfit_SQ_YoY = Factorize((NetProfit_SQ0P-NetProfit_SQ4P)/abs(NetProfit_SQ4P),"net_profit_sq_yoy")
    OperProfit_SQ_YoY = Factorize((OperNetProfit_SQ0P-OperNetProfit_SQ4P)/abs(OperNetProfit_SQ4P),"oper_profit_sq_yoy")
    NetProfitDeducted_SQ_YoY = Factorize((NetProfit_Deducted_SQ0P-NetProfit_Deducted_SQ4P)/abs(NetProfit_Deducted_SQ4P),"net_profit_deducted_sq_yoy")
    OCF_SQ_YoY = Factorize((OCF_SQ0P-OCF_SQ4P)/abs(OCF_SQ4P),"ocf_sq_yoy")
    Factors.extend([Revenue_SQ_YoY, NetProfit_SQ_YoY, OperProfit_SQ_YoY,NetProfitDeducted_SQ_YoY, OCF_SQ_YoY])
    
    # #### 季度增速: 环比 #########################################################################
    Revenue_SQ_QoQ = Factorize(Sales_SQ0P/Sales_SQ1P,"revenue_sq_qoq")
    OperProfit_SQ_QoQ= Factorize(OperNetProfit_SQ0P/OperNetProfit_SQ1P,"oper_profit_sq_qoq")
    NetProfit_SQ_QoQ = Factorize(NetProfit_SQ0P/NetProfit_SQ1P,"net_profit_sq_qoq")
    NetProfitDeducted_SQ_QoQ= Factorize(NetProfit_Deducted_SQ0P/NetProfit_Deducted_SQ1P,"net_profit_deducted_sq_qoq")
    OCF_SQ_QoQ= Factorize(OCF_SQ0P/OCF_SQ1P,"ocf_sql_qoq")
    Factors.extend([OCF_SQ_QoQ,NetProfitDeducted_SQ_QoQ,OperProfit_SQ_QoQ,Revenue_SQ_QoQ,NetProfit_SQ_QoQ])

    # #### 季度增速的增量 #######################################################################
    Factors.append(Factorize((Revenue_SQ_YoY-((Sales_SQ1P-Sales_SQ5P)/abs(Sales_SQ5P))),"revenue_sq_acc"))
    Factors.append(Factorize((NetProfit_SQ_YoY-((NetProfit_SQ1P-NetProfit_SQ5P)/abs(NetProfit_SQ5P))),"net_profit_sq_acc"))
    Factors.append(Factorize((OperProfit_SQ_YoY-((OperNetProfit_SQ1P-OperNetProfit_SQ5P)/abs(OperNetProfit_SQ5P))),"oper_profit_sq_acc"))
    Factors.append(Factorize((OCF_SQ_YoY-((OCF_SQ1P-OCF_SQ5P)/abs(OCF_SQ5P))),"ocf_sq_acc"))

    # #### 预期增长 ###############################################################################
    Factors.append(Factorize((NetProfitAvg_FY0*10000-NetProfit_Y0)/abs(NetProfit_Y0),'net_profit_fy0_yoy'))
    Factors.append(Factorize(((NetProfitAvg_FY1*10000-NetProfit_Y0)/abs(NetProfit_Y0)+1)**0.5-1,'net_profit_fy1_gr'))

    # #### 成长加速度计算 ###############################################################################
    # 20180527-光大证券-多因子系列报告之十二：成长因子重构与优化，稳健加速为王 系列一
    # 过去8个季度的净利润相对于时间（T,以及T^2）的回归
    NetProft_8Q_Acc=QS.FactorDB.PointOperation("net_profit_8q_acc",[NetProfit_SQ0P,NetProfit_SQ1P,NetProfit_SQ3P,NetProfit_SQ3P,NetProfit_SQ4P,NetProfit_SQ5P,NetProfit_SQ6P,NetProfit_SQ7P],{'算子':ACC_Fun,"参数":{'非空率':0.4}})
    Factors.append(NetProft_8Q_Acc)

    return Factors

if __name__=="__main__":
    pass