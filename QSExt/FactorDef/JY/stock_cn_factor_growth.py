# -*- coding: utf-8 -*-
"""成长因子"""
import datetime as dt

import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.BasicOperator import rename
from QuantStudio.Core.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


# 以回归的方式计算增速
@FactorOperatorized(operator_type="Point", args={"Arity": None, "ModelArgs": {'非空率': 0.4}, "IDMode": "单ID", "DTMode": "单时点"})
def calcRegressionGrowth(f, idt, iid, x, args):
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
@FactorOperatorized(operator_type="Point", args={"Arity": 8, "ModelArgs": {'非空率': 0.4}, "IDMode": "单ID", "DTMode": "单时点"})
def calcACC(f, idt, iid, x, args):
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

def defFactor(fdi: FactorDefInput):
    Factors = []

    JYDB = fdi.FDB["JYDB"]
    
    # ### 利润表因子 #############################################################################
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "TTM", "ReportDate": "所有"})
    Sales_TTM = FT.getFactor("营业收入")
    OperNetProfit_TTM = FT.getFactor("营业利润")
    NetProfit_TTM = FT.getFactor("归属于母公司所有者的净利润")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "TTM", "ReportDate": "所有", "YearLookBack": 1})
    Sales_L1 = FT.getFactor("营业收入")
    OperNetProfit_L1 = FT.getFactor("营业利润")
    NetProfit_L1 = FT.getFactor("归属于母公司所有者的净利润")
    
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报", "YearLookBack": 0})
    Sales_Y0 = FT.getFactor("营业收入")
    NetProfit_Y0 = FT.getFactor("归属于母公司所有者的净利润")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报", "YearLookBack": 1})
    Sales_Y1 = FT.getFactor("营业收入")
    NetProfit_Y1 = FT.getFactor("归属于母公司所有者的净利润")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报", "YearLookBack": 2})
    Sales_Y2 = FT.getFactor("营业收入")
    NetProfit_Y2 = FT.getFactor("归属于母公司所有者的净利润")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报", "YearLookBack": 3})
    Sales_Y3 = FT.getFactor("营业收入")
    NetProfit_Y3 = FT.getFactor("归属于母公司所有者的净利润")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报", "YearLookBack": 4})
    Sales_Y4 = FT.getFactor("营业收入")
    NetProfit_Y4 = FT.getFactor("归属于母公司所有者的净利润")

    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 0})
    OperNetProfit_SQ0P = FT.getFactor("营业利润")
    NetProfit_SQ0P = FT.getFactor("归属于母公司所有者的净利润")
    Sales_SQ0P = FT.getFactor("营业收入")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 1})
    OperNetProfit_SQ1P = FT.getFactor("营业利润")
    NetProfit_SQ1P = FT.getFactor("归属于母公司所有者的净利润")
    Sales_SQ1P = FT.getFactor("营业收入")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 2})
    NetProfit_SQ2P = FT.getFactor("归属于母公司所有者的净利润")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 3})
    NetProfit_SQ3P = FT.getFactor("归属于母公司所有者的净利润")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 4})
    OperNetProfit_SQ4P = FT.getFactor("营业利润")
    NetProfit_SQ4P = FT.getFactor("归属于母公司所有者的净利润")
    Sales_SQ4P = FT.getFactor("营业收入")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 5})
    OperNetProfit_SQ5P = FT.getFactor("营业利润")
    NetProfit_SQ5P = FT.getFactor("归属于母公司所有者的净利润")
    Sales_SQ5P = FT.getFactor("营业收入")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 6})
    NetProfit_SQ6P = FT.getFactor("归属于母公司所有者的净利润")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 7})
    NetProfit_SQ7P = FT.getFactor("归属于母公司所有者的净利润")
    
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "TTM", "ReportDate": "所有"})
    NetProfit_TTM_Deducted = FT.getFactor("扣除非经常性损益后的净利润")
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "TTM", "ReportDate": "所有", "YearLookBack": 1})
    NetProfit_TTM_Deducted_L1 = FT.getFactor("扣除非经常性损益后的净利润")
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 0})
    NetProfit_Deducted_SQ0P = FT.getFactor("扣除非经常性损益后的净利润")
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 1})
    NetProfit_Deducted_SQ1P = FT.getFactor("扣除非经常性损益后的净利润")
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 4})
    NetProfit_Deducted_SQ4P = FT.getFactor("扣除非经常性损益后的净利润")
    
    # ### 现金流量表因子 #############################################################################
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报", "YearLookBack": 0})
    OCF_Y0 = FT.getFactor("经营活动产生的现金流量净额")
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报", "YearLookBack": 1})
    OCF_Y1 = FT.getFactor("经营活动产生的现金流量净额")
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报", "YearLookBack": 2})
    OCF_Y2 = FT.getFactor("经营活动产生的现金流量净额")
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报", "YearLookBack": 3})
    OCF_Y3 = FT.getFactor("经营活动产生的现金流量净额")
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报", "YearLookBack": 4})
    OCF_Y4 = FT.getFactor("经营活动产生的现金流量净额")
    
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 0})
    OCF_SQ0P = FT.getFactor("经营活动产生的现金流量净额")
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 1})
    OCF_SQ1P = FT.getFactor("经营活动产生的现金流量净额")
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 4})
    OCF_SQ4P = FT.getFactor("经营活动产生的现金流量净额")
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 5})
    OCF_SQ5P = FT.getFactor("经营活动产生的现金流量净额")
    
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "TTM", "ReportDate": "所有"})
    OCF_TTM = FT.getFactor("经营活动产生的现金流量净额")
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "TTM", "ReportDate": "所有", "YearLookBack": 1})
    OCF_TTM_L1 = FT.getFactor("经营活动产生的现金流量净额")

    # ### 资产负债表 #############################################################################
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "最新", "ReportDate": "所有"})
    Asset = FT.getFactor("资产总计")
    Equity = FT.getFactor("归属母公司股东权益合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "最新", "ReportDate": "所有", "YearLookBack": 1})
    Asset_L1 = FT.getFactor("资产总计")
    Equity_L1 = FT.getFactor("归属母公司股东权益合计")
    
    # ### 一致预期因子 #############################################################################
    FT = JYDB.getTable("股票盈利综合预测表(新)", args={"AdditionalConditon": {"ForeYearLevel": "t"}})
    NetProfitAvg_FY0 = FT.getFactor("预测净利润平均值(元)")
    FT = JYDB.getTable("股票盈利综合预测表(新)", args={"AdditionalConditon": {"ForeYearLevel": "t+1"}})
    NetProfitAvg_FY1 = FT.getFactor("预测净利润平均值(元)")
    
    # #### 五年增速: 回归方式计算 ########################################################################
    Factors.append(calcRegressionGrowth(Sales_Y4, Sales_Y3, Sales_Y2, Sales_Y1, Sales_Y0, factor_args={"Name": "revenue_5y_gr"}))
    Factors.append(calcRegressionGrowth(NetProfit_Y4, NetProfit_Y3, NetProfit_Y2, NetProfit_Y1, NetProfit_Y0, factor_args={"Name": "net_profit_5y_gr"}))
    Factors.append(calcRegressionGrowth(OCF_Y4, OCF_Y3, OCF_Y2, OCF_Y1, OCF_Y0, factor_args={"Name": "ocf_5y_gr"}))
    
    # #### 三年增速: 回归方式计算 #########################################################################
    Factors.append(calcRegressionGrowth(Sales_Y2, Sales_Y1, Sales_Y0, factor_args={"Name": "revenue_3y_gr"}))
    Factors.append(calcRegressionGrowth(NetProfit_Y2, NetProfit_Y1, NetProfit_Y0, factor_args={"Name": "net_profit_3y_gr"}))
    Factors.append(calcRegressionGrowth(OCF_Y2, OCF_Y1, OCF_Y0, factor_args={"Name": "ocf_3y_gr"}))

    # #### 一年增速: 同比 #########################################################################
    Factors.append(rename((Sales_Y0 - Sales_Y1) / abs(Sales_Y1), factor_name="revenue_lyr_yoy"))
    Factors.append(rename((NetProfit_Y0 - NetProfit_Y1) / abs(NetProfit_Y1), factor_name="net_profit_lyr_yoy"))
    Factors.append(rename((OCF_Y0 - OCF_Y1) / abs(OCF_Y1), factor_name="ocf_lyr_yoy"))
    Factors.append(rename(NetProfit_TTM / NetProfit_L1 - 1, factor_name="net_profit_ttm_yoy"))
    Factors.append(rename(OperNetProfit_TTM / OperNetProfit_L1 - 1, factor_name="oper_profit_ttm_yoy"))
    Factors.append(rename(Sales_TTM / Sales_L1 - 1, factor_name="net_profit_ttm_yoy"))

    Factors.append(rename(NetProfit_TTM_Deducted / NetProfit_TTM_Deducted_L1 - 1, factor_name="net_profit_deducted_ttm_yoy"))#--扣非净利润TTM同比变动 新添加
    Factors.append(rename(OCF_TTM / OCF_TTM_L1 - 1, factor_name="ocf_ttm_yoy"))
    Factors.append(rename(Asset / Asset_L1 - 1, factor_name="asset_lr_yoy"))
    Factors.append(rename(Equity / Equity_L1 - 1, factor_name="equity_lr_yoy"))

    # #### 季度增速: 同比 #########################################################################
    Revenue_SQ_YoY = rename((Sales_SQ0P - Sales_SQ4P) / abs(Sales_SQ4P), factor_name="revenue_sq_yoy")
    NetProfit_SQ_YoY = rename((NetProfit_SQ0P - NetProfit_SQ4P) / abs(NetProfit_SQ4P), factor_name="net_profit_sq_yoy")
    OperProfit_SQ_YoY = rename((OperNetProfit_SQ0P - OperNetProfit_SQ4P) / abs(OperNetProfit_SQ4P), factor_name="oper_profit_sq_yoy")
    NetProfitDeducted_SQ_YoY = rename((NetProfit_Deducted_SQ0P - NetProfit_Deducted_SQ4P) / abs(NetProfit_Deducted_SQ4P), factor_name="net_profit_deducted_sq_yoy")
    OCF_SQ_YoY = rename((OCF_SQ0P - OCF_SQ4P) / abs(OCF_SQ4P), factor_name="ocf_sq_yoy")
    Factors.extend([Revenue_SQ_YoY, NetProfit_SQ_YoY, OperProfit_SQ_YoY, NetProfitDeducted_SQ_YoY, OCF_SQ_YoY])
    
    # #### 季度增速: 环比 #########################################################################
    Revenue_SQ_QoQ = rename(Sales_SQ0P / Sales_SQ1P - 1, factor_name="revenue_sq_qoq")
    OperProfit_SQ_QoQ= rename(OperNetProfit_SQ0P / OperNetProfit_SQ1P - 1, factor_name="oper_profit_sq_qoq")
    NetProfit_SQ_QoQ = rename(NetProfit_SQ0P / NetProfit_SQ1P - 1, factor_name="net_profit_sq_qoq")
    NetProfitDeducted_SQ_QoQ= rename(NetProfit_Deducted_SQ0P / NetProfit_Deducted_SQ1P - 1, factor_name="net_profit_deducted_sq_qoq")
    OCF_SQ_QoQ= rename(OCF_SQ0P / OCF_SQ1P - 1, factor_name="ocf_sql_qoq")
    Factors.extend([OCF_SQ_QoQ, NetProfitDeducted_SQ_QoQ, OperProfit_SQ_QoQ, Revenue_SQ_QoQ, NetProfit_SQ_QoQ])

    # #### 季度增速的增量 #######################################################################
    Factors.append(rename(Revenue_SQ_YoY - ((Sales_SQ1P - Sales_SQ5P) / abs(Sales_SQ5P)), factor_name="revenue_sq_acc"))
    Factors.append(rename(NetProfit_SQ_YoY - ((NetProfit_SQ1P - NetProfit_SQ5P) / abs(NetProfit_SQ5P)), factor_name="net_profit_sq_acc"))
    Factors.append(rename(OperProfit_SQ_YoY - ((OperNetProfit_SQ1P - OperNetProfit_SQ5P) / abs(OperNetProfit_SQ5P)), factor_name="oper_profit_sq_acc"))
    Factors.append(rename(OCF_SQ_YoY - ((OCF_SQ1P - OCF_SQ5P) / abs(OCF_SQ5P)), factor_name="ocf_sq_acc"))

    # #### 预期增长 ###############################################################################
    Factors.append(rename((NetProfitAvg_FY0 - NetProfit_Y0) / abs(NetProfit_Y0), factor_name='net_profit_fy0_yoy'))
    Factors.append(rename(((NetProfitAvg_FY1 - NetProfit_Y0) / abs(NetProfit_Y0) + 1)**0.5 - 1, factor_name='net_profit_fy1_gr'))

    # #### 成长加速度计算 ###############################################################################
    # 20180527-光大证券-多因子系列报告之十二：成长因子重构与优化，稳健加速为王 系列一
    # 过去8个季度的净利润相对于时间（T,以及T^2）的回归
    NetProft_8Q_Acc = calcACC(NetProfit_SQ0P, NetProfit_SQ1P, NetProfit_SQ2P, NetProfit_SQ3P, NetProfit_SQ4P, NetProfit_SQ5P, NetProfit_SQ6P, NetProfit_SQ7P, factor_args={"Name": "net_profit_8q_acc"})
    Factors.append(NetProft_8Q_Acc)

    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_factor_growth",
        MaxLookBack=365, 
        IDType="A股",
        Author="麦冬"
    )
