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

    JYDB = args["JYDB"]
    LDB = args["LDB"]

    # ### 行情因子 #############################################################################
    Close = LDB.getTable("stock_cn_day_bar_nafilled").getFactor("close")

    # ### 一致预期因子 #########################################################################
    FT = LDB.getTable("stock_cn_consensus")
    EPSAvg_FY0 = FT.getFactor("eps_fy0")
    EPSAvg_Fwd12M = FT.getFactor("eps_fwd12m")
    NetProfitAvg_FY0 = FT.getFactor("net_profit_fy0")
    NetProfitAvg_Fwd12M = FT.getFactor("net_profit_fwd12m")
    EPSStd_FY0 = FT.getFactor("eps_std_fy0")

    FT = JYDB.getTable("个股评级")
    Rating = FT.getFactor("评级标准分", args={"回溯天数":180, "统计周期时间间隔":"180"}, new_name="rating")
    FT = JYDB.getTable("个股目标价")
    TargetPrice = FT.getFactor("平均目标价(元)", args={"回溯天数":180, "统计周期时间间隔":"180"})

    # ### 资产负债表因子 #########################################################################
    Equity = JYDB.getTable("资产负债表_新会计准则").getFactor("归属母公司股东权益合计", args={"计算方法":"最新", "报告期":"所有"})

    # ### EPS 预测变化 #########################################################################
    Factors.append(fd.rolling_change_rate(EPSAvg_FY0, window=20+1, factor_name="eps_fy0_r1m"))
    Factors.append(fd.rolling_change_rate(EPSAvg_FY0, window=60+1, factor_name="eps_fy0_r3m"))
    Factors.append(fd.rolling_change_rate(EPSAvg_Fwd12M, window=20+1, factor_name="eps_fwd12m_r1m"))
    Factors.append(fd.rolling_change_rate(EPSAvg_Fwd12M, window=60+1, factor_name="eps_fwd12m_r3m"))

    # ### ROE 预测变化 #########################################################################
    ROE_FY0 = NetProfitAvg_FY0 / Equity
    Factors.append(fd.rolling_change_rate(ROE_FY0, window=20+1, factor_name="roe_fy0_r1m"))
    Factors.append(fd.rolling_change_rate(ROE_FY0, window=60+1, factor_name="roe_fy0_r3m"))

    ROE_Fwd12M = NetProfitAvg_Fwd12M / Equity
    Factors.append(fd.rolling_change_rate(ROE_Fwd12M, window=20+1, factor_name="roe_fwd12m_r1m"))
    Factors.append(fd.rolling_change_rate(ROE_Fwd12M, window=60+1, factor_name="roe_fwd12m_r3m"))

    # ### 分析师评级 #########################################################################
    Factors.append(Rating)
    Factors.append(fd.rolling_change_rate(Rating, window=20+1, factor_name="raing_r1m"))
    Factors.append(fd.rolling_change_rate(Rating, window=20*3+1, factor_name="raing_r3m"))

    # ### 分析师预测目标收益率 #########################################################################
    Factors.append(Factorize(TargetPrice / Close - 1, factor_name="target_return"))
    
    Factors.append(Factorize(EPSStd_FY0 / abs(EPSAvg_FY0), factor_name="eps_fy0_cv"))

    return Factors


if __name__=="__main__":
    pass