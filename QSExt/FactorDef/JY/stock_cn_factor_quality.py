# -*- coding: utf-8 -*-
"""质量因子"""
import datetime as dt

import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_consensus_expectation import defFactor as defStockConsensus


# 20180806_光大证券_金融工程深度：创新基本面因子：财务数据间线性关系初窥——多因子系列报告之十四_ws 系列二
# 营业收入营业成本的线性关系推算
@FactorOperatorized(operator_type="Point", args={"Arity": 16, "ModelArgs": {'非空率': 0.4}, "DataType": "double", "DTMode": "单时点", "IDMode": "单ID"})
def calcRROC(f, idt, iid, x, args):
    Y = np.array(x[0:8])
    Mask = (~np.isnan(Y))
    L = Y.shape[0]
    X = np.array(x[8:])
    Mask_y = (~np.isnan(Y))
    Mask_x = (~np.isnan(X))
    Mask_len = min(np.sum(Mask_y), np.sum(Mask_x))
    if Mask_len == np.sum(Mask_y):
        Mask = Mask_y
    else:
        Mask = Mask_x
    Y = Y[Mask]
    X = X[Mask]
    if np.sum(Mask) / L < args['非空率']: return np.nan
    x = (X - np.nanmean(X)) / np.nanstd(X)
    y = (Y - np.nanmean(Y)) / np.nanstd(Y)
    x = np.nan_to_num(x)
    y = np.nan_to_num(y)
    x = sm.add_constant(x)
    est = sm.OLS(y, x)
    para = est.fit().params
    residual = y - np.sum(para * x, axis=1)
    return residual[-1]

# 20180909_光大证券_金融工程深度：创新基本面因子：提纯净利数据中的选股信息——多因子系列报告之十五_ws 系列三
# 财务因子的提纯
@FactorOperatorized(operator_type="Point", args={"Arity": 24, "ModelArgs": {'非空率': 0.4}, "DataType": "double", "DTMode": "单时点", "IDMode": "单ID"})
def calcLPNP(f, idt, iid, x, args):
    Y = np.array(x[0:8])
    Mask_y = (~np.isnan(Y))

    L = Y.shape[0]
    Emp_pay = np.array(x[8:16])
    Non_Inc = np.array(x[16:])
    Mask_x1 = (~np.isnan(Emp_pay))
    Mask_x2 = (~np.isnan(Non_Inc))
    Mask_len = min(np.sum(Mask_y), np.sum(Mask_x1), np.sum(Mask_x2))
    if Mask_len == np.sum(Mask_y):
        Mask = Mask_y
    elif Mask_len == np.sum(Mask_x1):
        Mask = Mask_x1
    else:
        Mask = Mask_x2
    if np.sum(Mask) / L < args['非空率']: return np.nan
    Y = Y[Mask]
    Emp_pay = Emp_pay[Mask]
    Non_Inc = Non_Inc[Mask]
    Emp_pay = (Emp_pay - np.nanmean(Emp_pay)) / np.nanstd(Emp_pay)
    Non_Inc = (Non_Inc - np.nanmean(Non_Inc)) / np.nanstd(Non_Inc)

    y = (Y - np.nanmean(Y)) / np.nanstd(Y)
    x = np.array([Emp_pay, Non_Inc]).T
    x = np.nan_to_num(x)
    y = np.nan_to_num(y)

    x = sm.add_constant(x)
    est = sm.OLS(y, x)
    para = est.fit().params
    residual = y - np.sum(para * x, axis=1)
    return residual[-1]

# 20181101_光大证券_金融工程深度：创新基本面因子：捕捉产能利用率中的讯号——多因子系列报告之十六_ws 系列四
# 用固定资产与营业成本捕捉产能利用率
@FactorOperatorized(operator_type="Point", args={"Arity": 16, "ModelArgs": {'非空率': 0.4}, "DataType": "object", "DTMode": "单时点", "IDMode": "单ID"})
def calcOCFA(f, idt, iid, x, args):
    Y = np.array(x[0:8])
    X = np.array(x[8:])
    L = Y.shape[0]
    Mask_y = (~np.isnan(Y))
    Mask_x = (~np.isnan(X))
    Mask_len = min(np.sum(Mask_y), np.sum(Mask_x))
    if Mask_len == np.sum(Mask_y):
        Mask = Mask_y
    else:
        Mask = Mask_x
    if np.sum(Mask) / L < args['非空率']:
        return (np.nan, np.nan)
    Y = Y[Mask]
    X = X[Mask]

    x = (X - np.nanmean(X)) / np.nanstd(X)
    y = (Y - np.nanmean(Y)) / np.nanstd(Y)
    x = np.nan_to_num(x)
    y = np.nan_to_num(y)
    x = sm.add_constant(x)
    est = sm.OLS(y, x)
    para = est.fit().params
    residual = y - np.sum(para * x, axis=1)
    return (residual[-1], para[-1])


def defFactor(fdi: FactorDefInput):
    Factors = []

    JYDB = fdi.FDB["JYDB"]

    # ### 利润表因子 #############################################################################
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "TTM", "ReportDate": "所有"})
    NetProfit_TTM = FT.getFactor("归属于母公司所有者的净利润")
    Sales_TTM = FT.getFactor("营业收入")
    Cost_TTM = FT.getFactor("营业成本")
    OpNetProfit_TTM = FT.getFactor("营业利润")
    SalesExpenses_TTM = FT.getFactor("销售费用")
    ManagementExpenses_TTM = FT.getFactor("管理费用")
    FinancialExpenses_TTM = FT.getFactor("财务费用")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "TTM", "ReportDate": "所有", "YearLookBack": 1})
    NetProfit_TTM_L1 = FT.getFactor("归属于母公司所有者的净利润")
    Sales_L1 = FT.getFactor("营业收入")
    Cost_L1 = FT.getFactor("营业成本")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "TTM", "ReportDate": "所有", "YearLookBack": 2})
    NetProfit_TTM_L2 = FT.getFactor("归属于母公司所有者的净利润")
    Sales_L2 = FT.getFactor("营业收入")
    Cost_L2 = FT.getFactor("营业成本")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "TTM", "ReportDate": "所有", "YearLookBack": 3})
    NetProfit_TTM_L3 = FT.getFactor("归属于母公司所有者的净利润")
    Sales_L3 = FT.getFactor("营业收入")
    Cost_L3 = FT.getFactor("营业成本")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "TTM", "ReportDate": "所有", "YearLookBack": 4})
    NetProfit_TTM_L4 = FT.getFactor("归属于母公司所有者的净利润")
    Sales_L4 = FT.getFactor("营业收入")
    Cost_L4 = FT.getFactor("营业成本")
    
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 0})
    NetProfit_SQ0P = FT.getFactor("归属于母公司所有者的净利润")
    Non_Inc_SQ0P = FT.getFactor("加-营业外收入")
    Sales_SQ0P = FT.getFactor("营业收入")
    Cost_SQ0P = FT.getFactor("营业成本")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 1})
    NetProfit_SQ1P = FT.getFactor("归属于母公司所有者的净利润")
    Non_Inc_SQ1P = FT.getFactor("加-营业外收入")
    Sales_SQ1P = FT.getFactor("营业收入")
    Cost_SQ1P = FT.getFactor("营业成本")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 2})
    NetProfit_SQ2P = FT.getFactor("归属于母公司所有者的净利润")
    Non_Inc_SQ2P = FT.getFactor("加-营业外收入")
    Sales_SQ2P = FT.getFactor("营业收入")
    Cost_SQ2P = FT.getFactor("营业成本")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 3})
    NetProfit_SQ3P = FT.getFactor("归属于母公司所有者的净利润")
    Non_Inc_SQ3P = FT.getFactor("加-营业外收入")
    Sales_SQ3P = FT.getFactor("营业收入")
    Cost_SQ3P = FT.getFactor("营业成本")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 4})
    NetProfit_SQ4P = FT.getFactor("归属于母公司所有者的净利润")
    Non_Inc_SQ4P = FT.getFactor("加-营业外收入")
    Sales_SQ4P = FT.getFactor("营业收入")
    Cost_SQ4P = FT.getFactor("营业成本")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 5})
    NetProfit_SQ5P = FT.getFactor("归属于母公司所有者的净利润")
    Non_Inc_SQ5P = FT.getFactor("加-营业外收入")
    Sales_SQ5P = FT.getFactor("营业收入")
    Cost_SQ5P = FT.getFactor("营业成本")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 6})
    NetProfit_SQ6P = FT.getFactor("归属于母公司所有者的净利润")
    Non_Inc_SQ6P = FT.getFactor("加-营业外收入")
    Sales_SQ6P = FT.getFactor("营业收入")
    Cost_SQ6P = FT.getFactor("营业成本")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 7})
    NetProfit_SQ7P = FT.getFactor("归属于母公司所有者的净利润")
    Non_Inc_SQ7P = FT.getFactor("加-营业外收入")
    Sales_SQ7P = FT.getFactor("营业收入")
    Cost_SQ7P = FT.getFactor("营业成本")
    
    # ### 资产负债表因子 #############################################################################
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "最新", "ReportDate": "所有"})
    CurDebt = FT.getFactor("流动负债合计")
    CurAsset = FT.getFactor("流动资产合计")
    FixAsset = FT.getFactor("固定资产合计")
    Asset = FT.getFactor("资产总计")
    Equity = FT.getFactor("归属母公司股东权益合计")
    AR = FT.getFactor("应收账款")
    Debt = FT.getFactor("负债合计")
    LTDebt = FT.getFactor("非流动负债合计")
    Inventory = FT.getFactor("存货")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "最新", "ReportDate": "所有", "YearLookBack": 1})
    CurDebt_L1 = FT.getFactor("流动负债合计")
    CurAsset_L1 = FT.getFactor("流动资产合计")
    FixAsset_L1 = FT.getFactor("固定资产合计")
    Asset_L1 = FT.getFactor("资产总计")
    Equity_L1 = FT.getFactor("归属母公司股东权益合计")
    AR_L1 = FT.getFactor("应收账款")
    Debt_L1 = FT.getFactor("负债合计")
    LTDebt_L1 = FT.getFactor("非流动负债合计")
    Inventory_L1 = FT.getFactor("存货")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "最新", "ReportDate": "所有", "YearLookBack": 2})
    Asset_L2 = FT.getFactor("资产总计")
    Equity_L2 = FT.getFactor("归属母公司股东权益合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "最新", "ReportDate": "所有", "YearLookBack": 3})
    Asset_L3 = FT.getFactor("资产总计")
    Equity_L3 = FT.getFactor("归属母公司股东权益合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "最新", "ReportDate": "所有", "YearLookBack": 4})
    Asset_L4 = FT.getFactor("资产总计")
    Equity_L4 = FT.getFactor("归属母公司股东权益合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "最新", "ReportDate": "所有", "YearLookBack": 5})
    Asset_L5 = FT.getFactor("资产总计")
    Equity_L5 = FT.getFactor("归属母公司股东权益合计")
    
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 0})
    Empl_Pay_SQ0P = FT.getFactor("应付职工薪酬")
    FixAsset_SQ0P = FT.getFactor("固定资产合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 1})
    Empl_Pay_SQ1P = FT.getFactor("应付职工薪酬")
    FixAsset_SQ1P = FT.getFactor("固定资产合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 2})
    Empl_Pay_SQ2P = FT.getFactor("应付职工薪酬")
    FixAsset_SQ2P = FT.getFactor("固定资产合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 3})
    Empl_Pay_SQ3P = FT.getFactor("应付职工薪酬")
    FixAsset_SQ3P = FT.getFactor("固定资产合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 4})
    Empl_Pay_SQ4P = FT.getFactor("应付职工薪酬")
    FixAsset_SQ4P = FT.getFactor("固定资产合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 5})
    Empl_Pay_SQ5P = FT.getFactor("应付职工薪酬")
    FixAsset_SQ5P = FT.getFactor("固定资产合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 6})
    Empl_Pay_SQ6P = FT.getFactor("应付职工薪酬")
    FixAsset_SQ6P = FT.getFactor("固定资产合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "单季度", "ReportDate": "所有", "PeriodLookBack": 7})
    Empl_Pay_SQ7P = FT.getFactor("应付职工薪酬")
    FixAsset_SQ7P = FT.getFactor("固定资产合计")

    # ### 衍生报表数据 #############################################################################
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "最新", "ReportDate": "所有"})
    CurDebt_NonInterset = FT.getFactor("无息流动负债")
    NonCurDebt_NonInterset = FT.getFactor("无息非流动负债")
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "TTM", "ReportDate": "所有"})
    NetProfit_TTM_Deducted = FT.getFactor("扣除非经常性损益后的归母净利润")
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "TTM", "ReportDate": "所有", "YearLookBack": 1})
    NetProfit_TTM_Deducted_L1 = FT.getFactor("扣除非经常性损益后的归母净利润")

    FT = JYDB.getTable("公司报告期主要会计数据_新会计准则", args={"CalcType": "最新", "ReportDate": "所有"})
    TotalStock = FT.getFactor("总股本(股)")
    FT = JYDB.getTable("公司报告期主要会计数据_新会计准则", args={"CalcType": "最新", "ReportDate": "所有", "YearLookBack": 1})
    TotalStock_L1 = FT.getFactor("总股本(股)")
    
    # ### 现金流量表因子 #############################################################################
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "TTM", "ReportDate": "所有"})
    OCF_TTM = FT.getFactor("经营活动产生的现金流量净额")
    Capex_TTM = FT.getFactor("购建固定资产、无形资产和其他长期资产支付的现金")
    
    # ### 一致预期因子 #############################################################################
    StockConsensusDef = defStockConsensus(fdi=fdi)
    NetProfitAvg_FY0 = StockConsensusDef.getFactor(factor_name="net_profit_fy0")
    NetProfitAvg_Fwd12M = StockConsensusDef.getFactor(factor_name="net_profit_fwd12m")
    
    # ### 盈利能力 ################################################################################
    ROE_FY0 = rename(NetProfitAvg_FY0 / Equity, factor_name="roe_fy0")
    Factors.append(ROE_FY0)

    ROE_Fwd12M = rename(NetProfitAvg_Fwd12M / Equity, factor_name="roe_fwd12m")
    Factors.append(ROE_Fwd12M)

    ROE_TTM = rename(2 * NetProfit_TTM / (Equity + Equity_L1), factor_name='roe_ttm')
    Factors.append(ROE_TTM)

    ROA_TTM = rename(2 * NetProfit_TTM / (Asset + Asset_L1), factor_name='roa_ttm')
    Factors.append(ROA_TTM)

    InvestCapital_All = Equity + Debt - CurDebt_NonInterset - NonCurDebt_NonInterset
    ROIC_TTM = rename(NetProfit_TTM / InvestCapital_All, factor_name="roic_ttm")
    Factors.append(ROIC_TTM)

    CFROE_TTM = rename(2 * OCF_TTM / (Equity + Equity_L1), factor_name="cfroe_ttm")
    Factors.append(CFROE_TTM)

    CFROA_TTM = rename(2 * OCF_TTM / (Asset + Asset_L1), factor_name="cfroa_ttm")
    Factors.append(CFROA_TTM)
    
    Revenue2Asset = rename(2 * Sales_TTM / (Asset + Asset_L1), factor_name="revenue2asset")
    Factors.append(Revenue2Asset)

    GrossMargin_TTM = rename((Sales_TTM - Cost_TTM) / Sales_TTM, factor_name="gross_margin_ttm")
    Factors.append(GrossMargin_TTM)

    GrossProfit2SalesExpenses_TTM = rename((Sales_TTM - Cost_TTM) / SalesExpenses_TTM, factor_name="gross_profit2sales_expenses_ttm")
    Factors.append(GrossProfit2SalesExpenses_TTM)

    OperProfitMargin_TTM = rename(OpNetProfit_TTM / Sales_TTM, factor_name="oper_profit_margin_ttm")
    Factors.append(OperProfitMargin_TTM)

    NetProfitMargin_TTM = rename(NetProfit_TTM / Sales_TTM, factor_name="net_profit_margin_ttm")
    Factors.append(NetProfitMargin_TTM)

    OCF2OperProfit_TTM = rename(OCF_TTM / OpNetProfit_TTM, factor_name="ocf2oper_profit_ttm")
    Factors.append(OCF2OperProfit_TTM)

    ThreeCosts_TTM = SalesExpenses_TTM + ManagementExpenses_TTM + FinancialExpenses_TTM
    ThreeCosts2Revenue_TTM = rename(ThreeCosts_TTM / Sales_TTM, factor_name="three_costs2revenue_ttm")
    Factors.append(ThreeCosts2Revenue_TTM)


    # ### 盈利能力变动与稳定性 ######################################################################
    ROE_TTM_L1 = 2 * NetProfit_TTM_L1 / (Equity_L1 + Equity_L2)
    ROE_TTM_L2 = 2 * NetProfit_TTM_L2 / (Equity_L2 + Equity_L3)
    ROE_TTM_L3 = 2 * NetProfit_TTM_L3 / (Equity_L3 + Equity_L4)
    ROE_TTM_L4 = 2 * NetProfit_TTM_L4 / (Equity_L4 + Equity_L5)

    ROE_mean = fo.Mean()(ROE_TTM, ROE_TTM_L1, ROE_TTM_L2, ROE_TTM_L3, ROE_TTM_L4)
    ROE_std = fo.Std(ddof=0.0)(ROE_TTM, ROE_TTM_L1, ROE_TTM_L2, ROE_TTM_L3, ROE_TTM_L4)
    ROE_TTM_CV = rename(ROE_std / abs(ROE_mean), factor_name='roe_ttm_cv')
    Factors.append(ROE_TTM_CV)

    ROE_TTM_YoY = rename(ROE_TTM / ROE_TTM_L1 - 1, factor_name='roe_ttm_yoy')
    Factors.append(ROE_TTM_YoY)

    ROA_TTM_L1 = 2 * NetProfit_TTM_L1 / (Asset_L1 + Asset_L2)
    ROA_TTM_L2 = 2 * NetProfit_TTM_L2 / (Asset_L2 + Asset_L3)
    ROA_TTM_L3 = 2 * NetProfit_TTM_L3 / (Asset_L3 + Asset_L4)
    ROA_TTM_L4 = 2 * NetProfit_TTM_L4 / (Asset_L4 + Asset_L5)

    ROA_mean = fo.Mean()(ROA_TTM, ROA_TTM_L1, ROA_TTM_L2, ROA_TTM_L3, ROA_TTM_L4)
    ROA_std = fo.Std(ddof=0.0)(ROA_TTM, ROA_TTM_L1, ROA_TTM_L2, ROA_TTM_L3, ROA_TTM_L4)
    ROA_TTM_CV = rename(ROA_std / abs(ROA_mean), factor_name='roa_ttm_yoy')
    Factors.append(ROA_TTM_CV)

    ROA_TTM_YoY = rename(ROA_TTM / ROA_TTM_L1 - 1, factor_name='roa_ttm_cv')
    Factors.append(ROA_TTM_YoY)

    GrossMargin_L1 = (Sales_L1 - Cost_L1) / Sales_L1
    GrossMargin_L2 = (Sales_L2 - Cost_L2) / Sales_L2
    GrossMargin_L3 = (Sales_L3 - Cost_L3) / Sales_L3
    GrossMargin_L4 = (Sales_L4 - Cost_L4) / Sales_L4

    GrossMargin_mean = fo.Mean()(GrossMargin_TTM, GrossMargin_L1, GrossMargin_L2, GrossMargin_L3, GrossMargin_L4)
    GrossMargin_std = fo.Std(ddof=0.0)(GrossMargin_TTM, GrossMargin_L1, GrossMargin_L2, GrossMargin_L3, GrossMargin_L4)
    GrossMargin_TTM_CV = rename(GrossMargin_std / abs(GrossMargin_mean), factor_name='gross_margin_ttm_cv')
    Factors.append(GrossMargin_TTM_CV)

    GrossMargin_TTM_YoY = rename((GrossMargin_TTM - GrossMargin_L1) / abs(GrossMargin_L1), factor_name='gross_margin_ttm_yoy')
    Factors.append(GrossMargin_TTM_YoY)


    # ### 财务杠杆 ###################################################################################
    CurrentRatio_L1 = CurAsset_L1 / CurDebt_L1
    CurrentRatio_LR = rename(CurAsset / CurDebt, factor_name="current_ratio_lr")
    Factors.append(CurrentRatio_LR)

    QuickRatio_LR = rename((CurAsset - Inventory) / CurDebt, factor_name="quick_ratio_lr")
    Factors.append(QuickRatio_LR)

    InventoryTurnover = rename(2 * Sales_TTM / (Inventory + Inventory_L1), factor_name="inventory_turnover")
    Factors.append(InventoryTurnover)

    ReceivablesTurnover = rename(2 * Sales_TTM / (AR + AR_L1), factor_name="receivables_turnover")
    Factors.append(ReceivablesTurnover)

    LTDebt2Equity_LR = rename(LTDebt / Equity, factor_name="lt_debt2equity_lr")
    Factors.append(LTDebt2Equity_LR)

    LTDebt2Equity_L1 = LTDebt_L1 / Equity_L1
    LTDebt2Equity_LR_YoY = rename((LTDebt2Equity_LR - LTDebt2Equity_L1) / abs(LTDebt2Equity_L1), factor_name="lt_debt2equity_lr_yoy")
    Factors.append(LTDebt2Equity_LR_YoY)

    OCF2CurDebt = rename(2 * OCF_TTM / (CurDebt + CurDebt_L1), factor_name='ocf2cur_debt')
    Factors.append(OCF2CurDebt)


    # ### 资本利用程度 ###################################################################################
    CurAsset_LR_Gr = rename((CurAsset - CurAsset_L1) / abs(CurAsset_L1), factor_name="cur_asset_lr_gr")
    Factors.append(CurAsset_LR_Gr)

    FixAsset_LR_Gr = rename((FixAsset - FixAsset_L1) / abs(FixAsset_L1), factor_name="fix_asset_lr_gr")
    Factors.append(FixAsset_LR_Gr)

    CurDebt_LR_Gr = rename((CurDebt - CurDebt_L1) / abs(CurDebt_L1), factor_name="cur_debt_lr_gr")
    Factors.append(CurDebt_LR_Gr)

    Debt_LR_Gr = rename((Debt - Debt_L1) / abs(Debt_L1), factor_name="debt_lr_gr")
    Factors.append(Debt_LR_Gr)

    Equity_LR_Gr = rename((Equity - Equity_L1) / abs(Equity_L1), factor_name="equity_lr_gr")
    Factors.append(Equity_LR_Gr)

    Asset_LR_Gr = rename((Asset - Asset_L1) / abs(Asset_L1), factor_name="asset_lr_gr")
    Factors.append(Asset_LR_Gr)

    Factors.append(rename(Capex_TTM / Sales_TTM, factor_name="capex2revenue"))

    # ### 其他 ##############################################################################################
    Revenue2Asset_L1 = 2 * Sales_L1 / (Asset_L1 + Asset_L2)
    Piotroski_F_Score = fo.Sum(all_nan=np.nan)(
        NetProfit_TTM_Deducted > 0,
        OCF_TTM > 0,
        NetProfit_TTM_Deducted > NetProfit_TTM_Deducted_L1,
        OCF_TTM > NetProfit_TTM_Deducted,
        LTDebt2Equity_LR <= LTDebt2Equity_L1,
        CurrentRatio_LR > CurrentRatio_L1,
        TotalStock <= TotalStock_L1,
        GrossMargin_TTM > GrossMargin_L1,
        Revenue2Asset > Revenue2Asset_L1,
        factor_args={"Name": "piotroski_f_score"}
    )
    Factors.append(Piotroski_F_Score)
    
    ## ### 股利支付率 ##############################################################################################
    ##--股利支付率+留存收益率=1
    ##--股利包括现金分红加上股票股利；我们通常所说的股息率等是现金部分，正推不太好算
    ##--留存收益率实际上是所有者权益/净利润，所以我们可以反推
    ##Dividend_Pay_Ratio=Factors.append(rename(1-Equity_Cur/NetProfit_LYR,"Dividend_Pay_Ratio"))#--股利支付率

    # # #### 股利支付率#############################################################################
    # FT = JYDB.getTable("中国A股分红")
    # CashDvdPerShare, BaseShare = FT.getFactor("每股派息(税前)"), FT.getFactor("基准股本")
    # Dividend_Pay_Ratio=Factors.append(rename(1-(CashDvdPerShare*BaseShare)/NetProfit_LYR,"Dividend_Pay_Ratio"))#--股利支付率

    # 20180806_光大证券_金融工程深度：创新基本面因子：财务数据间线性关系初窥——多因子系列报告之十四_ws 系列二
    # 营业收入营业成本的线性关系推算
    PROC = calcRROC(
        Sales_SQ7P, Sales_SQ6P, Sales_SQ5P, Sales_SQ4P, Sales_SQ3P, Sales_SQ2P, Sales_SQ1P, Sales_SQ0P,
        Cost_SQ7P, Cost_SQ6P, Cost_SQ5P, Cost_SQ4P, Cost_SQ3P, Cost_SQ2P, Cost_SQ1P, Cost_SQ0P, 
    factor_args={"Name": "proc"})
    Factors.append(PROC)
    
    # 20180909_光大证券_金融工程深度：创新基本面因子：提纯净利数据中的选股信息——多因子系列报告之十五_ws 系列三
    # 财务因子的提纯
    LPNP = calcLPNP(
        NetProfit_SQ7P, NetProfit_SQ6P, NetProfit_SQ5P, NetProfit_SQ4P, NetProfit_SQ3P, NetProfit_SQ2P, NetProfit_SQ1P, NetProfit_SQ0P,
        Empl_Pay_SQ7P, Empl_Pay_SQ6P, Empl_Pay_SQ5P, Empl_Pay_SQ4P, Empl_Pay_SQ3P, Empl_Pay_SQ2P, Empl_Pay_SQ1P, Empl_Pay_SQ0P,
        Non_Inc_SQ7P, Non_Inc_SQ6P, Non_Inc_SQ5P, Non_Inc_SQ4P, Non_Inc_SQ3P, Non_Inc_SQ2P, Non_Inc_SQ1P, Non_Inc_SQ0P, 
    factor_args={"Name": "lpnp"})
    Factors.append(LPNP)

    # 20181101_光大证券_金融工程深度：创新基本面因子：捕捉产能利用率中的讯号——多因子系列报告之十六_ws 系列四
    # 用固定资产与营业成本捕捉产能利用率
    OCFA_val = calcOCFA(
        Cost_SQ7P, Cost_SQ6P, Cost_SQ5P, Cost_SQ4P, Cost_SQ3P, Cost_SQ2P, Cost_SQ1P, Cost_SQ0P,
        FixAsset_SQ7P, FixAsset_SQ6P, FixAsset_SQ5P, FixAsset_SQ4P, FixAsset_SQ3P, FixAsset_SQ2P, FixAsset_SQ1P, FixAsset_SQ0P, 
    factor_args={"Name": "ocfa_val"})
    Factors.append(fo.Fetch(pos=0, dtype="double")(OCFA_val, factor_args={"Name": "ocfa_resid"}))
    Factors.append(fo.Fetch(pos=1, dtype="double")(OCFA_val, factor_args={"Name": "ocfa_para"}))

    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_factor_quality",
        MaxLookBack=max(365, StockConsensusDef.MaxLookBack),
        IDType="A股",
        Author="麦冬"
    )