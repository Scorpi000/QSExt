# -*- coding: utf-8 -*-
"""价值因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

UpdateArgs = {
    "因子表": "stock_cn_factor_value",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def DvdFun(f, idt, iid, x, args):
    #Fun = np.vectorize(lambda x1, x2: np.nansum(np.array(x1) * np.array(x2)))
    Fun = np.vectorize(lambda x1, x2: np.nansum(np.array(x1) * np.array(x2)) if (x1 is not None) and (x2 is not None) else 0)
    return Fun(x[0], x[1])

def defFactor(args={}):
    Factors = []

    WDB = args["WDB"]
    LDB = args["LDB"]
    
    # ### 资产负债表因子 #########################################################################
    FT = WDB.getTable("中国A股资产负债表")
    TotalAsset = FT.getFactor("资产总计", args={"计算方法":"最新"})
    IntangibleAsset = FT.getFactor("无形资产", args={"计算方法":"最新"})
    IntangibleAsset = fd.where(IntangibleAsset, fd.notnull(IntangibleAsset), 0)
    Goodwill = FT.getFactor("商誉", args={"计算方法":"最新"})
    Goodwill = fd.where(Goodwill, fd.notnull(Goodwill), 0)
    TotalLiability = FT.getFactor("负债合计", args={"计算方法":"最新"})
    MonetaryFund = FT.getFactor("货币资金", args={"计算方法":"最新"})
    InterestBearingObligation = WDB.getTable("中国A股财务指标").getFactor("带息债务", args={"计算方法":"最新"})

    # ### 利润表因子 #############################################################################
    FT = WDB.getTable("中国A股利润表")
    EBIT_TTM = FT.getFactor("息税前利润", args={"计算方法":"TTM"})
    EBITDA_TTM = FT.getFactor("息税折旧摊销前利润", args={"计算方法":"TTM"})
    # 在TTM因缺失值不能计算时，采用最近年报数据填充
    EBIT  = fd.where(EBIT_TTM, fd.notnull(EBIT_TTM), FT.getFactor("息税前利润", args={"计算方法":"最新", "报告期":"年报"}))
    EBITDA  = fd.where(EBITDA_TTM, fd.notnull(EBITDA_TTM), FT.getFactor("息税折旧摊销前利润", args={"计算方法":"最新", "报告期":"年报"}))
    Sales_TTM = FT.getFactor("营业收入", args={"计算方法":"TTM"})
    Sales_LYR = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报"})
    
    Earnings_TTM = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"TTM"})
    Earnings_LYR = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"最新", "报告期":"年报"})
    
    Earnings_TTM_Deducted = FT.getFactor("扣除非经常性损益后净利润", args={"计算方法":"TTM"})
    
    Earnings_LYR_Deducted = FT.getFactor("扣除非经常性损益后净利润", args={"计算方法":"最新", "报告期":"年报"})

    # ### 现金流量表因子 #############################################################################
    FT = WDB.getTable("中国A股现金流量表")
    FCF_TTM = FT.getFactor("企业自由现金流量(FCFF)", args={"计算方法":"TTM"})
    FCF_LYR = FT.getFactor("企业自由现金流量(FCFF)", args={"计算方法":"最新", "报告期":"年报"})
    
    OCF_TTM = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"TTM"})
    OCF_LYR = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"最新", "报告期":"年报"})
    
    # ### 一致预期因子 #############################################################################
    FT = HDB.getTable("WindConsensusFactor")
    EarningsAvg_FY0 = FT.getFactor("WEST_EarningsAvg_FY0")# 单位: 万元
    EarningsAvg_FY1 = FT.getFactor("WEST_EarningsAvg_FY1")# 单位: 万元
    EarningsAvg_Fwd12M = FT.getFactor("WEST_EarningsFwd_12M")# 单位: 万元

    # ### 行情因子 #############################################################################
    MarketCap = LDB.getTable("stock_cn_day_bar_nafilled").getFactor("total_cap")# 单位: 万元

    # #### 股息类 #############################################################################
    FT = WDB.getTable("中国A股分红")
    CashDvdPerShare, BaseShare = FT.getFactor("每股派息(税前)"), FT.getFactor("基准股本")
    Dividend = QS.FactorDB.PointOperation("税前现金总红利(万元)", [CashDvdPerShare, BaseShare], sys_args={"算子":DvdFun, "运算时点":"多时点", "运算ID":"多ID"})
    Factors.append(Factorize(fd.rolling_sum(Dividend, window=240) / MarketCap, "DP_LTM"))

    # ### 盈利类 ########################################################################
    Factors.append(Factorize(Earnings_TTM_Deducted/(MarketCap*10000), "EP_TTM_Deducted"))
    
    EP_LYR_Deducted=Factorize(Earnings_LYR_Deducted/(MarketCap*10000),'EP_LYR_Deducted')
    Factors.append(EP_LYR_Deducted)#--新添加
    
    Factors.append(Factorize(Earnings_TTM/(MarketCap*10000), "EP_TTM"))
    Factors.append(Factorize(Earnings_LYR/(MarketCap*10000), "EP_LYR"))
    Factors.append(Factorize(EarningsAvg_FY0/MarketCap, "EP_FY0"))
    Factors.append(Factorize(EarningsAvg_FY1/MarketCap,"EP_FY1"))
    Factors.append(Factorize(EarningsAvg_Fwd12M/MarketCap,"EP_Fwd12M"))

    # ### 现金流类 ######################################################################
    Factors.append(Factorize(OCF_TTM/(MarketCap*10000), "OCFP_TTM"))
    OCFP_LYR=Factorize(OCF_LYR/(MarketCap*10000),'OCFP_LYR')
    Factors.append(OCFP_LYR)#--新添加
    
    Factors.append(Factorize(FCF_TTM/(MarketCap*10000), "FCFP_TTM"))
    FCFP_LYR=Factorize(FCF_LYR/(MarketCap*10000),'FCFP_LYR')
    Factors.append(FCFP_LYR)#--新添加

    # ### 营业收入类 ########################################################################
    Factors.append(Factorize(Sales_TTM/(MarketCap*10000), "SP_TTM"))
    SP_LYR=Factorize(Sales_LYR/(MarketCap*10000),'SP_LYR')
    Factors.append(SP_LYR)#--新添加

    # ### 账面净资产类 ######################################################################
    Factors.append(Factorize((TotalAsset-TotalLiability)/(MarketCap*10000), "BP_LR"))
    Factors.append(Factorize((TotalAsset-TotalLiability-IntangibleAsset-Goodwill)/(MarketCap*10000), "BP_LR_Tangible"))# 在无形资产或商誉缺失的情况下, TangibleBP_LR 退化为 BP_LR

    # ### 企业价值类 ########################################################################
    EV = MarketCap*10000 + InterestBearingObligation - MonetaryFund
    Factors.append(Factorize(EBITDA/EV, "EBITDA2EV"))
    Factors.append(Factorize(EBIT/EV, "EBIT2EV"))
    Factors.append(Factorize(Sales_TTM/EV, "Revenue2EV"))
    
    return Factors
    

if __name__=="__main__":
    pass
    