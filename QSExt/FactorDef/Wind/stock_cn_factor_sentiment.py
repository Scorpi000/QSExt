# -*- coding: utf-8 -*-
"""情绪因子""" 
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_factor_sentiment",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def defFactor(args={}):
    Factors = []

    WDB = args["WDB"]
    LDB = args["LDB"]

    # ### 行情因子 #############################################################################
    Close = LDB.getTable("stock_cn_day_bar_nafilled").getFactor("close")

    # ### 一致预期因子 #########################################################################
    FT = LDB.getTable("stock_cn_factor_consensus")
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
    Factors.append(fd.rolling_change_rate(EPSAvg_FY0, window=20+1, factor_name="EPS_FY0_R1M"))
    Factors.append(fd.rolling_change_rate(EPSAvg_FY0, window=60+1, factor_name="EPS_FY0_R3M"))
    Factors.append(fd.rolling_change_rate(EPSAvg_Fwd12M, window=20+1, factor_name="EPS_Fwd12M_R1M"))
    Factors.append(fd.rolling_change_rate(EPSAvg_Fwd12M, window=60+1, factor_name="EPS_Fwd12M_R3M"))

    # ### ROE 预测变化 #########################################################################
    ROE_FY0 = EarningsAvg_FY0 / Equity
    Factors.append(fd.rolling_change_rate(ROE_FY0, window=20+1, factor_name="ROE_FY0_R1M"))
    Factors.append(fd.rolling_change_rate(ROE_FY0, window=60+1, factor_name="ROE_FY0_R3M"))

    ROE_Fwd12M = EarningsAvg_Fwd12M / Equity
    Factors.append(fd.rolling_change_rate(ROE_Fwd12M, window=20+1, factor_name="ROE_Fwd12M_R1M"))
    Factors.append(fd.rolling_change_rate(ROE_Fwd12M, window=60+1, factor_name="ROE_Fwd12M_R3M"))

    # ### 分析师评级 #########################################################################
    Factors.append(Rating)
    Factors.append(fd.rolling_change_rate(Rating, window=20+1, factor_name="Rating_R1M"))
    Factors.append(fd.rolling_change_rate(Rating, window=20*3+1, factor_name="Rating_R3M"))

    # ### 分析师预测目标收益率 #########################################################################
    Factors.append(Factorize(TargetPrice / Close - 1, factor_name="TargetReturn"))
    
    Factors.append(Factorize(EPSStd_FY0 / abs(EPSAvg_FY0), factor_name="EPS_FY0_CV"))

    return Factors


if __name__=="__main__":
    pass