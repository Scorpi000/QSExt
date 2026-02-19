# -*- coding: utf-8 -*-
"""情绪因子""" 
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.BasicOperator import rename
from QuantStudio.Core.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar
from QSExt.FactorDef.JY.stock_cn_consensus_expectation import defFactor as defStockConsensus


def defFactor(fdi: FactorDefInput):
    Factors = []

    JYDB = fdi.FDB["JYDB"]

    # ### 行情因子 #############################################################################
    StockDayBarDef = defStockDayBar(fdi=fdi)
    Close = StockDayBarDef.getFactor("close")

    # ### 一致预期因子 #########################################################################
    StockConsensusDef = defStockConsensus(fdi=fdi)
    NetProfitAvg_FY0 = StockConsensusDef.getFactor(factor_name="net_profit_fy0")
    NetProfitAvg_Fwd12M = StockConsensusDef.getFactor(factor_name="net_profit_fwd12m")
    EPSAvg_FY0 = StockConsensusDef.getFactor(factor_name="eps_fy0")
    EPSAvg_Fwd12M = StockConsensusDef.getFactor(factor_name="eps_fwd12m")
    
    FT = JYDB.getTable("个股评级", args={"回溯天数": 180, "统计周期时间间隔": "180"})
    Rating = rename(FT.getFactor("评级标准分"), factor_name="rating")
    FT = JYDB.getTable("个股目标价")
    TargetPrice = FT.getFactor("平均目标价(元)")

    # ### 资产负债表因子 #########################################################################
    Equity = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "最新", "ReportDate": "所有"}).getFactor("归属母公司股东权益合计")
    
    # 算子
    rolling_change_rate_20d = fo.RollingChangeRate(window=20+1)
    rolling_change_rate_60d = fo.RollingChangeRate(window=60+1)
    
    # ### EPS 预测变化 #########################################################################
    Factors.append(rolling_change_rate_20d(EPSAvg_FY0, factor_args={"Name": "eps_fy0_r1m"}))
    Factors.append(rolling_change_rate_60d(EPSAvg_FY0, factor_args={"Name": "eps_fy0_r3m"}))
    Factors.append(rolling_change_rate_20d(EPSAvg_Fwd12M, factor_args={"Name": "eps_fwd12m_r1m"}))
    Factors.append(rolling_change_rate_60d(EPSAvg_Fwd12M, factor_args={"Name": "eps_fwd12m_r3m"}))

    # ### ROE 预测变化 #########################################################################
    ROE_FY0 = NetProfitAvg_FY0 / Equity
    Factors.append(rolling_change_rate_20d(ROE_FY0, factor_args={"Name": "roe_fy0_r1m"}))
    Factors.append(rolling_change_rate_60d(ROE_FY0, factor_args={"Name": "roe_fy0_r3m"}))

    ROE_Fwd12M = NetProfitAvg_Fwd12M / Equity
    Factors.append(rolling_change_rate_20d(ROE_Fwd12M, factor_args={"Name": "roe_fwd12m_r1m"}))
    Factors.append(rolling_change_rate_60d(ROE_Fwd12M, factor_args={"Name": "roe_fwd12m_r3m"}))

    # ### 分析师评级 #########################################################################
    Factors.append(Rating)
    Factors.append(rolling_change_rate_20d(Rating, factor_args={"Name": "raing_r1m"}))
    Factors.append(rolling_change_rate_60d(Rating, factor_args={"Name": "raing_r3m"}))

    # ### 分析师预测目标收益率 #########################################################################
    Factors.append(rename(TargetPrice / Close - 1, factor_name="target_return"))
    
    Factors.append(rename(EPSStd_FY0 / abs(EPSAvg_FY0), factor_name="eps_fy0_cv"))

    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_factor_sentiment",
        MaxLookBack=365, 
        IDType="A股",
        Author="麦冬"
    )
