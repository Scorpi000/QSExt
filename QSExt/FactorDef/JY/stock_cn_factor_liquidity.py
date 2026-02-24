# coding=utf-8
"""流动性因子"""
import datetime as dt
from functools import partial

import numpy as np
import pandas as pd

import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.BasicOperator import rename
from QuantStudio.Core.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar
from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStockStatus


def defFactor(fdi: FactorDefInput):
    Factors = []

    # ### 日行情因子 #############################################################################
    StockDayBarDef = defStockDayBar(fdi=fdi)
    DayReturn = StockDayBarDef.getFactor(factor_name="chg_rate")
    Turnover = StockDayBarDef.getFactor("turnover")# %
    Volume = StockDayBarDef.getFactor("volume")# 股
    Amount = StockDayBarDef.getFactor("amount")# 元    
    
    StockStatusDef = defStockStatus(fdi=fdi)
    IfTrading = StockStatusDef.getFactor(factor_name="if_trading")
    IfListed = StockStatusDef.getFactor(factor_name="if_listed")
    Mask = ((IfListed==1) & (IfTrading==1))
    Mask_20D = (fo.RollingApply(func=np.nansum, window=20)(Mask) >= 20*0.8)
    Mask_240D = (fo.RollingApply(func=np.nansum, window=240)(Mask) >= 240*0.8)
    
    where = fo.Where(dtype="double")
    rolling_mean_20d = fo.RollingMean(window=20, min_periods=2)
    rolling_mean_240d = fo.RollingMean(window=240, min_periods=2)
    Factors.append(where(rolling_mean_20d(Amount), Mask_20D, np.nan, factor_args={"Name": "amount_20d_avg"}))
    Factors.append(where(rolling_mean_240d(Amount), Mask_240D, np.nan, factor_args={"Name": "amount_240d_avg"}))
    Factors.append(where(rolling_mean_20d(Turnover), Mask_20D, np.nan, factor_args={"Name": "turnover_20d_avg"}))
    Factors.append(where(rolling_mean_240d(Turnover), Mask_240D, np.nan, factor_args={"Name": "turnover_240d_avg"}))
    
    ILLIQ = abs(DayReturn) / (Amount / 10**9)
    Factors.append(where(rolling_mean_20d(ILLIQ), Mask_20D, np.nan, factor_args={"Name": "illiq_20d"}))
    Factors.append(where(rolling_mean_240d(ILLIQ), Mask_240D, np.nan, factor_args={"Name": "illiq_240d"}))

    VolAvg_20D = where(rolling_mean_20d(Volume), Mask_20D, np.nan)
    VolAvg_240D = where(rolling_mean_240d(Volume), Mask_240D, np.nan)
    Factors.append(rename(VolAvg_20D / VolAvg_240D, factor_name="vol_avg_20d_240d"))

    VolStd_20D = where(fo.RollingApply(func=partial(np.nanstd, ddof=1), window=20, min_periods=2)(Volume), Mask_20D, np.nan)
    Factors.append(rename(VolStd_20D / VolAvg_20D, factor_name="vol_20d_cv"))
    
    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_factor_liquidity",
        MaxLookBack=max(365 * 2, StockDayBarDef.MaxLookBack, StockStatusDef.MaxLookBack), 
        IDType="A股",
        Author="麦冬"
    )