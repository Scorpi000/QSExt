# -*- coding: utf-8 -*-
"""质量因子"""
import datetime as dt

import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_factor_quality",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

# 20180806_光大证券_金融工程深度：创新基本面因子：财务数据间线性关系初窥——多因子系列报告之十四_ws 系列二
# 营业收入营业成本的线性关系推算
def RROC_Fun(f, idt, iid, x, args):
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
def LPNP_Fun(f, idt, iid, x, args):
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
def OCFA_Fun(f, idt, iid, x, args):
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
    if np.sum(Mask) / L < args['非空率']: return (np.nan, np.nan)
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

def defFactor(args={}):
    Factors = []

    JYDB = args["JYDB"]
    LDB = args["LDB"]

    # ### 利润表因子 #############################################################################
    FT = JYDB.getTable("利润分配表_新会计准则")
    NetProfit_TTM = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":0})
    NetProfit_TTM_L1 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})
    NetProfit_TTM_L2 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":2})
    NetProfit_TTM_L3 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":3})
    NetProfit_TTM_L4 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":4})
    
    NetProfit_SQ0P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
    NetProfit_SQ1P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
    NetProfit_SQ2P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":2})
    NetProfit_SQ3P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":3})
    NetProfit_SQ4P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
    NetProfit_SQ5P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})
    NetProfit_SQ6P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":6})
    NetProfit_SQ7P = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":7})
    
    Non_Inc_SQ0P = FT.getFactor("加-营业外收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
    Non_Inc_SQ1P = FT.getFactor("加-营业外收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
    Non_Inc_SQ2P = FT.getFactor("加-营业外收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":2})
    Non_Inc_SQ3P = FT.getFactor("加-营业外收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":3})
    Non_Inc_SQ4P = FT.getFactor("加-营业外收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
    Non_Inc_SQ5P = FT.getFactor("加-营业外收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})
    Non_Inc_SQ6P = FT.getFactor("加-营业外收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":6})
    Non_Inc_SQ7P = FT.getFactor("加-营业外收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":7})
    
    Sales_TTM = FT.getFactor("营业收入", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":0})
    Sales_L1 = FT.getFactor("营业收入", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})
    Sales_L2 = FT.getFactor("营业收入", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":2})
    Sales_L3 = FT.getFactor("营业收入", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":3})
    Sales_L4 = FT.getFactor("营业收入", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":4})

    Cost_TTM = FT.getFactor("营业成本", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":0})
    Cost_L1 = FT.getFactor("营业成本", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})
    Cost_L2 = FT.getFactor("营业成本", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":2})
    Cost_L3 = FT.getFactor("营业成本", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":3})
    Cost_L4 = FT.getFactor("营业成本", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":4})

    OpNetProfit_TTM = FT.getFactor("营业利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":0})
    SalesExpenses_TTM = FT.getFactor("销售费用", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":0})
    ManagementExpenses_TTM = FT.getFactor("管理费用", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":0})
    FinancialExpenses_TTM = FT.getFactor("财务费用", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":0})

    Sales_SQ0P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
    Sales_SQ1P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
    Sales_SQ2P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":2})
    Sales_SQ3P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":3})
    Sales_SQ4P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
    Sales_SQ5P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})
    Sales_SQ6P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":6})
    Sales_SQ7P = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":7})

    Cost_SQ0P = FT.getFactor("营业成本", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
    Cost_SQ1P = FT.getFactor("营业成本", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
    Cost_SQ2P = FT.getFactor("营业成本", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":2})
    Cost_SQ3P = FT.getFactor("营业成本", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":3})
    Cost_SQ4P = FT.getFactor("营业成本", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
    Cost_SQ5P = FT.getFactor("营业成本", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})
    Cost_SQ6P = FT.getFactor("营业成本", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":6})
    Cost_SQ7P = FT.getFactor("营业成本", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":7})
    
    # ### 资产负债表因子 #############################################################################
    FT = JYDB.getTable("资产负债表_新会计准则")
    CurDebt = FT.getFactor("流动负债合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    CurDebt_L1 = FT.getFactor("流动负债合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})

    CurAsset = FT.getFactor("流动资产合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    CurAsset_L1 = FT.getFactor("流动资产合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})

    FixAsset = FT.getFactor("固定资产",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    FixAsset_L1 = FT.getFactor("固定资产",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})

    Asset = FT.getFactor("资产总计",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    Asset_L1 = FT.getFactor("资产总计",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})
    Asset_L2 = FT.getFactor("资产总计",{"计算方法":"最新", "报告期":"所有", "回溯年数":2})
    Asset_L3 = FT.getFactor("资产总计",{"计算方法":"最新", "报告期":"所有", "回溯年数":3})
    Asset_L4 = FT.getFactor("资产总计",{"计算方法":"最新", "报告期":"所有", "回溯年数":4})
    Asset_L5 = FT.getFactor("资产总计",{"计算方法":"最新", "报告期":"所有", "回溯年数":5})

    Equity = FT.getFactor("归属母公司股东权益合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    Equity_L1 = FT.getFactor("归属母公司股东权益合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})
    Equity_L2 = FT.getFactor("归属母公司股东权益合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":2})
    Equity_L3 = FT.getFactor("归属母公司股东权益合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":3})
    Equity_L4 = FT.getFactor("归属母公司股东权益合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":4})
    Equity_L5 = FT.getFactor("归属母公司股东权益合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":5})
    
    AR = FT.getFactor("应收账款",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    AR_L1 = FT.getFactor("应收账款",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})

    Debt = FT.getFactor("负债合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    Debt_L1 = FT.getFactor("负债合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})

    LTDebt = FT.getFactor("非流动负债合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    LTDebt_L1 = FT.getFactor("非流动负债合计",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})

    Inventory = FT.getFactor("存货",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    Inventory_L1 = FT.getFactor("存货",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})

    Empl_Pay_SQ0P = FT.getFactor("应付职工薪酬", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
    Empl_Pay_SQ1P = FT.getFactor("应付职工薪酬", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
    Empl_Pay_SQ2P = FT.getFactor("应付职工薪酬", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":2})
    Empl_Pay_SQ3P = FT.getFactor("应付职工薪酬", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":3})
    Empl_Pay_SQ4P = FT.getFactor("应付职工薪酬", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
    Empl_Pay_SQ5P = FT.getFactor("应付职工薪酬", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})
    Empl_Pay_SQ6P = FT.getFactor("应付职工薪酬", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":6})
    Empl_Pay_SQ7P = FT.getFactor("应付职工薪酬", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":7})
    
    FixAsset_SQ0P = FT.getFactor("固定资产", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":0})
    FixAsset_SQ1P = FT.getFactor("固定资产", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":1})
    FixAsset_SQ2P = FT.getFactor("固定资产", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":2})
    FixAsset_SQ3P = FT.getFactor("固定资产", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":3})
    FixAsset_SQ4P = FT.getFactor("固定资产", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":4})
    FixAsset_SQ5P = FT.getFactor("固定资产", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":5})
    FixAsset_SQ6P = FT.getFactor("固定资产", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":6})
    FixAsset_SQ7P = FT.getFactor("固定资产", args={"计算方法":"单季度", "报告期":"所有", "回溯期数":7})

    # ### 衍生报表数据 #############################################################################
    FT = JYDB.getTable("中国A股财务指标")
    CurDebt_NonInterset = FT.getFactor("无息流动负债",{"计算方法":"最新", "报告期":"所有"})
    NonCurDebt_NonInterset = FT.getFactor("无息非流动负债",{"计算方法":"最新", "报告期":"所有"})
    
    NetProfit_TTM_Deducted = FT.getFactor("扣除非经常性损益后的净利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":0})
    NetProfit_TTM_Deducted_L1 = FT.getFactor("扣除非经常性损益后的净利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})    
    
    #TotalStock = FT.getFactor("期末总股本",{"计算方法":"最新", "报告期":"所有", "回溯年数":0})
    #TotalStock_L1 = FT.getFactor("期末总股本",{"计算方法":"最新", "报告期":"所有", "回溯年数":1})
    
    # ### 现金流量表因子 #############################################################################
    FT = JYDB.getTable("现金流量表_新会计准则")
    OCF_TTM = FT.getFactor("经营活动产生的现金流量净额",{"计算方法":"TTM", "报告期":"所有"})
    #Capex_TTM = FT.getFactor("购建固定资产、无形资产和其他长期资产支付的现金", args={"计算方法":"TTM"})
    
    # ### 一致预期因子 #############################################################################
    FT = LDB.getTable("stock_cn_consensus")
    NetProfitAvg_FY0 = FT.getFactor("net_profit_fy0")# 万元
    NetProfitAvg_Fwd12M = FT.getFactor("net_profit_fwd12m")# 万元

    # ### 盈利能力 ################################################################################
    ROE_FY0 = Factorize(NetProfitAvg_FY0*10000/Equity,"roe_fy0")
    Factors.append(ROE_FY0)

    ROE_Fwd12M = Factorize(NetProfitAvg_Fwd12M*10000/Equity,"roe_fwd12m")
    Factors.append(ROE_Fwd12M)

    ROE_TTM = Factorize(2*NetProfit_TTM/(Equity+Equity_L1),'roe_ttm')
    Factors.append(ROE_TTM)

    ROA_TTM = Factorize(2*NetProfit_TTM/(Asset+Asset_L1),'roa_ttm')
    Factors.append(ROA_TTM)

    InvestCapital_All = Equity+Debt-CurDebt_NonInterset-NonCurDebt_NonInterset
    ROIC_TTM = Factorize(NetProfit_TTM/InvestCapital_All,"roic_ttm")
    Factors.append(ROIC_TTM)

    CFROE_TTM = Factorize(2*OCF_TTM/(Equity+Equity_L1),"cfroe_ttm")
    Factors.append(CFROE_TTM)

    CFROA_TTM = Factorize(2*OCF_TTM/(Asset+Asset_L1),"cfroa_ttm")
    Factors.append(CFROA_TTM)

    Sale2Asset_L1 = 2*Sales_L1/(Asset_L1+Asset_L2)
    Revenue2Asset = Factorize(2*Sales_TTM/(Asset+Asset_L1),"revenue2asset")
    Factors.append(Revenue2Asset)

    GrossMargin_TTM = Factorize((Sales_TTM-Cost_TTM)/Sales_TTM,"gross_margin_ttm")
    Factors.append(GrossMargin_TTM)

    GrossProfit2SalesExpenses_TTM = Factorize((Sales_TTM-Cost_TTM)/SalesExpenses_TTM,"gross_profit2sales_expenses_ttm")
    Factors.append(GrossProfit2SalesExpenses_TTM)

    OperProfitMargin_TTM = Factorize(OpNetProfit_TTM/Sales_TTM,"oper_profit_margin_ttm")
    Factors.append(OperProfitMargin_TTM)

    NetProfitMargin_TTM = Factorize(NetProfit_TTM/Sales_TTM,"net_profit_margin_ttm")
    Factors.append(NetProfitMargin_TTM)

    OCF2OperProfit_TTM = Factorize(OCF_TTM/OpNetProfit_TTM,"ocf2oper_profit_ttm")
    Factors.append(OCF2OperProfit_TTM)

    ThreeCosts_TTM = SalesExpenses_TTM+ManagementExpenses_TTM+FinancialExpenses_TTM
    ThreeCosts2Revenue_TTM = Factorize(ThreeCosts_TTM/Sales_TTM,"three_costs2revenue_ttm")
    Factors.append(ThreeCosts2Revenue_TTM)


    # ### 盈利能力变动与稳定性 ######################################################################
    ROE_TTM_L1 = 2*NetProfit_TTM_L1/(Equity_L1+Equity_L2)
    ROE_TTM_L2 = 2*NetProfit_TTM_L2/(Equity_L2+Equity_L3)
    ROE_TTM_L3 = 2*NetProfit_TTM_L3/(Equity_L3+Equity_L4)
    ROE_TTM_L4 = 2*NetProfit_TTM_L4/(Equity_L4+Equity_L5)

    ROE_mean = fd.nanmean(ROE_TTM,ROE_TTM_L1,ROE_TTM_L2,ROE_TTM_L3,ROE_TTM_L4)
    ROE_std = fd.nanstd(ROE_TTM,ROE_TTM_L1,ROE_TTM_L2,ROE_TTM_L3,ROE_TTM_L4,ddof=0.0)
    ROE_TTM_CV = Factorize(ROE_std/abs(ROE_mean),'roe_ttm_cv')
    Factors.append(ROE_TTM_CV)

    ROE_TTM_YoY = Factorize(ROE_TTM/ROE_TTM_L1-1,'rot_ttm_yoy')
    Factors.append(ROE_TTM_YoY)

    ROA_TTM_L1 = 2*NetProfit_TTM_L1/(Asset_L1+Asset_L2)
    ROA_TTM_L2 = 2*NetProfit_TTM_L2/(Asset_L2+Asset_L3)
    ROA_TTM_L3 = 2*NetProfit_TTM_L3/(Asset_L3+Asset_L4)
    ROA_TTM_L4 = 2*NetProfit_TTM_L4/(Asset_L4+Asset_L5)

    ROA_mean = fd.nanmean(ROA_TTM,ROA_TTM_L1,ROA_TTM_L2,ROA_TTM_L3,ROA_TTM_L4)
    ROA_std = fd.nanstd(ROA_TTM,ROA_TTM_L1,ROA_TTM_L2,ROA_TTM_L3,ROA_TTM_L4,ddof=0.0)
    ROA_TTM_CV = Factorize(ROA_std/abs(ROA_mean),'roa_ttm_yoy')
    Factors.append(ROA_TTM_CV)

    ROA_TTM_YoY = Factorize(ROA_TTM/ROA_TTM_L1-1,'roa_ttm_cv')
    Factors.append(ROA_TTM_YoY)

    GrossMargin_L1 = (Sales_L1-Cost_L1)/Sales_L1
    GrossMargin_L2 = (Sales_L2-Cost_L2)/Sales_L2
    GrossMargin_L3 = (Sales_L3-Cost_L3)/Sales_L3
    GrossMargin_L4 = (Sales_L4-Cost_L4)/Sales_L4

    GrossMargin_mean = fd.nanmean(GrossMargin_TTM,GrossMargin_L1,GrossMargin_L2,GrossMargin_L3,GrossMargin_L4)
    GrossMargin_std = fd.nanstd(GrossMargin_TTM,GrossMargin_L1,GrossMargin_L2,GrossMargin_L3,GrossMargin_L4,ddof=0.0)
    GrossMargin_TTM_CV = Factorize(GrossMargin_std/abs(GrossMargin_mean),'gross_margin_ttm_cv')
    Factors.append(GrossMargin_TTM_CV)

    GrossMargin_TTM_YoY = Factorize((GrossMargin_TTM-GrossMargin_L1)/abs(GrossMargin_L1),'gross_margin_ttm_yoy')
    Factors.append(GrossMargin_TTM_YoY)


    # ### 财务杠杆 ###################################################################################
    CurrentRatio_L1 = CurAsset_L1/CurDebt_L1
    CurrentRatio_LR = Factorize(CurAsset/CurDebt,"current_ratio_lr")
    Factors.append(CurrentRatio_LR)

    QuickRatio_LR = Factorize((CurAsset-Inventory)/CurDebt,"quick_ratio_lr")
    Factors.append(QuickRatio_LR)

    InventoryTurnover = Factorize(2*Sales_TTM/(Inventory+Inventory_L1),"inventory_turnover")
    Factors.append(InventoryTurnover)

    ReceivablesTurnover = Factorize(2*Sales_TTM/(AR+AR_L1),"receivables_turnover")
    Factors.append(ReceivablesTurnover)

    LTDebt2Equity_LR = Factorize(LTDebt/Equity,"lt_debt2equity_lr")
    Factors.append(LTDebt2Equity_LR)

    LTDebt2Equity_L1 = LTDebt_L1/Equity_L1
    LTDebt2Equity_LR_YoY = Factorize((LTDebt2Equity_LR-LTDebt2Equity_L1)/abs(LTDebt2Equity_L1),"lt_debt2equity_lr_yoy")
    Factors.append(LTDebt2Equity_LR_YoY)

    OCF2CurDebt = Factorize(2*OCF_TTM/(CurDebt+CurDebt_L1),'ocf2cur_debt')
    Factors.append(OCF2CurDebt)


    # ### 资本利用程度 ###################################################################################
    CurAsset_LR_Gr = Factorize((CurAsset-CurAsset_L1)/abs(CurAsset_L1),"cur_asset_lr_gr")
    Factors.append(CurAsset_LR_Gr)

    FixAsset_LR_Gr = Factorize((FixAsset-FixAsset_L1)/abs(FixAsset_L1),"fix_asset_lr_gr")
    Factors.append(FixAsset_LR_Gr)

    CurDebt_LR_Gr = Factorize((CurDebt-CurDebt_L1)/abs(CurDebt_L1),"cur_debt_lr_gr")
    Factors.append(CurDebt_LR_Gr)

    Debt_LR_Gr = Factorize((Debt-Debt_L1)/abs(Debt_L1),"debt_lr_gr")
    Factors.append(Debt_LR_Gr)

    Equity_LR_Gr = Factorize((Equity-Equity_L1)/abs(Equity_L1),"equity_lr_gr")
    Factors.append(Equity_LR_Gr)

    Asset_LR_Gr = Factorize((Asset-Asset_L1)/abs(Asset_L1),"asset_lr_gr")
    Factors.append(Asset_LR_Gr)

    # ### 其他 ##############################################################################################
    #Piotroski_F_Score = (NetProfit_TTM_Deducted>0)+(OCF_TTM>0)+(NetProfit_TTM_Deducted>NetProfit_TTM_Deducted_L1)+(OCF_TTM>NetProfit_TTM_Deducted)
    #Piotroski_F_Score = Piotroski_F_Score + (LTDebt2Equity_LR<=LTDebt2Equity_L1)+(CurrentRatio_LR>CurrentRatio_L1)+(TotalStock<=TotalStock_L1)
    #Piotroski_F_Score = Piotroski_F_Score + (GrossMargin_TTM>GrossMargin_L1)+(Revenue2Asset>Sale2Asset_L1)
    #Piotroski_F_Score = Factorize(Piotroski_F_Score,'Piotroski_F_Score')
    #Factors.append(Piotroski_F_Score)
    #Factors.append(Factorize(Capex_TTM/Sales_TTM,"Capex2Revenue"))#--来自于成长指标
    ## ### 股利支付率 ##############################################################################################
    ##--股利支付率+留存收益率=1
    ##--股利包括现金分红加上股票股利；我们通常所说的股息率等是现金部分，正推不太好算
    ##--留存收益率实际上是所有者权益/净利润，所以我们可以反推
    ##Dividend_Pay_Ratio=Factors.append(Factorize(1-Equity_Cur/NetProfit_LYR,"Dividend_Pay_Ratio"))#--股利支付率

    # # #### 股利支付率#############################################################################
    # FT = JYDB.getTable("中国A股分红")
    # CashDvdPerShare, BaseShare = FT.getFactor("每股派息(税前)"), FT.getFactor("基准股本")
    # Dividend_Pay_Ratio=Factors.append(Factorize(1-(CashDvdPerShare*BaseShare)/NetProfit_LYR,"Dividend_Pay_Ratio"))#--股利支付率

    # 20180806_光大证券_金融工程深度：创新基本面因子：财务数据间线性关系初窥——多因子系列报告之十四_ws 系列二
    # 营业收入营业成本的线性关系推算 
    PROC=QS.FactorDB.PointOperation("proc",[Sales_SQ7P,Sales_SQ6P,Sales_SQ5P,Sales_SQ4P,Sales_SQ3P,Sales_SQ2P,Sales_SQ1P,Sales_SQ0P,\
                                            Cost_SQ7P,Cost_SQ6P,Cost_SQ5P,Cost_SQ4P,Cost_SQ3P,Cost_SQ2P,Cost_SQ1P,Cost_SQ0P],{'算子':RROC_Fun,"参数":{'非空率':0.4}})
    Factors.append(PROC)

    # 20180909_光大证券_金融工程深度：创新基本面因子：提纯净利数据中的选股信息——多因子系列报告之十五_ws 系列三
    # 财务因子的提纯
    LPNP=QS.FactorDB.PointOperation("lpnp",[NetProfit_SQ7P,NetProfit_SQ6P,NetProfit_SQ5P,NetProfit_SQ4P,NetProfit_SQ3P,NetProfit_SQ2P,NetProfit_SQ1P,NetProfit_SQ0P,\
                                            Empl_Pay_SQ7P,Empl_Pay_SQ6P,Empl_Pay_SQ5P,Empl_Pay_SQ4P,Empl_Pay_SQ3P,Empl_Pay_SQ2P,Empl_Pay_SQ1P,Empl_Pay_SQ0P,\
                                            Non_Inc_SQ7P,Non_Inc_SQ6P,Non_Inc_SQ5P,Non_Inc_SQ4P,Non_Inc_SQ3P,Non_Inc_SQ2P,Non_Inc_SQ1P,Non_Inc_SQ0P],{'算子':LPNP_Fun,"参数":{'非空率':0.4}})
    Factors.append(LPNP)

    # 20181101_光大证券_金融工程深度：创新基本面因子：捕捉产能利用率中的讯号——多因子系列报告之十六_ws 系列四
    # 用固定资产与营业成本捕捉产能利用率
    OCFA_val=QS.FactorDB.PointOperation("ocfa_val",[Cost_SQ7P,Cost_SQ6P,Cost_SQ5P,Cost_SQ4P,Cost_SQ3P,Cost_SQ2P,Cost_SQ1P,Cost_SQ0P,\
                                                    FixAsset_SQ7P,FixAsset_SQ6P,FixAsset_SQ5P,FixAsset_SQ4P,FixAsset_SQ3P,FixAsset_SQ2P,FixAsset_SQ1P,FixAsset_SQ0P],{'算子':OCFA_Fun,"参数":{'非空率':0.4},"数据类型":"string"})
    Factors.append(fd.fetch(OCFA_val,0,factor_name="OCFA_Resd"))
    Factors.append(fd.fetch(OCFA_val,1,factor_name="OCFA_Para"))

    return Factors

if __name__=="__main__":
    pass