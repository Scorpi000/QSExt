# coding=utf-8
"""资金流因子"""
import datetime as dt

import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_factor_money_flow",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def defFactor(args={}):
    Factors = []

    WDB = args["WDB"]
    LDB = args["LDB"]

    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    Volume = FT.getFactor("volume")# 手

    # ### Level2 指标因子 #############################################################################
    FT = WDB.getTable("中国A股Level2指标")
    ActiveBuyAmount = FT.getFactor("主买总额(万元)")
    ActiveSellAmount = FT.getFactor("主卖总额(万元)")
    ActiveBuyVolume = FT.getFactor("主买总量(手)")
    ActiveSellVolume = FT.getFactor("主卖总量(手)")

    # 资金流向因子 
    STVDelta = WDB.getTable("中国A股资金流向数据").getFactor("散户量差(仅主动)(手)")# 手
    Factors.append(Factorize(STVDelta / Volume, factor_name="SmallTradeFlow_1D"))

    # BS, 升序, 参考《银河量化十周年专题之五：选股因子及因子择时新视角》, 银河证券, 20140909-->从动量反转转移过来
    Factors.append(fd.rolling_sum(ActiveBuyAmount - ActiveSellAmount, 5, factor_name="BuyMinusSell_5D_Amount"))
    Factors.append(fd.rolling_sum(ActiveBuyVolume - ActiveSellVolume, 5, factor_name="BuyMinusSell_5D_Vol"))

    return Factors

if __name__=="__main__":
    pass