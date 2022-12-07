# coding=utf-8
"""流动性因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_factor_liquidity",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def defFactor(args={}):
    Factors = []

    LDB = args["LDB"]
    
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    DayReturn = FT.getFactor("chg_rate")
    Turnover = FT.getFactor("turnover")# %
    Volume = FT.getFactor("volume")# 手
    Amount = FT.getFactor("amount")# 千元
    IfTrading = FT.getFactor("if_trading")
    
    FT = LDB.getTable("stock_cn_info")
    IfListed = FT.getFactor("if_listed")

    Mask = ((IfTrading==1) & (IfListed==1))
    Mask_20D = (fd.rolling_sum(Mask, 20)>=20*0.8)
    Mask_240D = (fd.rolling_sum(Mask, 240)>=240*0.8)

    Factors.append(fd.where(fd.rolling_mean(Amount, 20, min_periods=2), Mask_20D, np.nan, factor_name="amount_20d_avg"))
    Factors.append(fd.where(fd.rolling_mean(Amount, 240, min_periods=2), Mask_240D, np.nan, factor_name="amount_240d_avg"))
    Factors.append(fd.where(fd.rolling_mean(Turnover, 20, min_periods=2), Mask_20D, np.nan, factor_name="turnover_20d_avg"))
    Factors.append(fd.where(fd.rolling_mean(Turnover, 240, min_periods=2), Mask_240D, np.nan, factor_name="turnover_240d_avg"))
    
    ILLIQ = 10**6*(abs(DayReturn) / Amount)
    Factors.append(fd.where(fd.rolling_mean(ILLIQ, 20, min_periods=2), Mask_20D, np.nan, factor_name="illiq_20d"))
    Factors.append(fd.where(fd.rolling_mean(ILLIQ, 240, min_periods=2), Mask_240D, np.nan, factor_name="illiq_240d"))

    VolAvg_20D = fd.where(fd.rolling_mean(Volume, 20, min_periods=2), Mask_20D, np.nan)
    VolAvg_240D = fd.where(fd.rolling_mean(Volume, 240, min_periods=2), Mask_240D, np.nan)
    Factors.append(Factorize(VolAvg_20D / VolAvg_240D, factor_name="vol_avg_20d_240d"))

    VolStd_20D = fd.where(fd.rolling_std(Volume, 20, min_periods=2), Mask_20D, np.nan)
    Factors.append(Factorize(VolStd_20D / VolAvg_20D, factor_name="vol_20d_cv"))
    
    return Factors

if __name__=="__main__":
    pass