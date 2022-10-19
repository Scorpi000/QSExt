# coding=utf-8
"""技术因子"""
import datetime as dt

import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_factor_technical",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def RSI_Fun(f, idt, iid, x, args):
    Close = x[0]
    Pre_Close = x[1]
    TradeStatus = x[2]
    Len = TradeStatus.shape[0]
    Mask = (np.sum((TradeStatus != "停牌") & pd.notnull(TradeStatus), axis=0) / Len < args['非空率'])
    Gap_large = Close - Pre_Close
    Gap_large[Close < Pre_Close] = 0
    Gap_large = abs(Gap_large)
    Gap_Small = Close - Pre_Close
    Gap_Small[Close > Pre_Close] = 0
    Gap_Small = abs(Gap_Small)

    min_periods = args['回测期']
    RSI = np.zeros(Close.shape) + np.nan
    RSI_U = np.zeros(Close.shape) + np.nan
    RSI_D = np.zeros(Close.shape) + np.nan

    for i in range(min_periods, Close.shape[0]):
        if i == min_periods:
            ilarge = Gap_large[0:i + 1]
            isamll = Gap_Small[0:i + 1]
            RSI_U[i] = np.nansum(ilarge, axis=0) / min_periods
            RSI_D[i] = np.nansum(isamll, axis=0) / min_periods
        else:
            RSI_U[i] = (RSI_U[i - 1] * (min_periods - 1) + Gap_large[i:i + 1]) / min_periods
            RSI_D[i] = (RSI_D[i - 1] * (min_periods - 1) + Gap_Small[i:i + 1]) / min_periods
    RSI = RSI_U / (RSI_U + RSI_D)
    return RSI[-1, :]

def Bias_Fun(f, idt, iid, x, args):
    #Mask = (x[1]==1)
    Data = x[0]
    TradeStatus=x[1]
    Len = TradeStatus.shape[0]
    Mask = (np.sum((TradeStatus!="停牌") & pd.notnull(TradeStatus), axis=0)/Len<args['非空率'])
    Avg = np.nanmean(Data,axis=0)
    Bias=(Data[-1]-Avg)/Avg
    Bias[Mask] = np.nan
    return Bias

def defFactor(args={}):
    Factors = []

    LDB = args["LDB"]

    FT = LDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    TradeStatus = FT.getFactor("if_trading")
    AdjPreClose = FT.getFactor("pre_close")
    AdjClose = FT.getFactor("close")

    RSI_5D = QS.FactorDB.TimeOperation('RSI_5D',[AdjClose, AdjPreClose, TradeStatus], {'算子':RSI_Fun,'参数':{"非空率":0.8,'回测期':5},'回溯期数':[1000-1,1000-1,1000-1],"运算ID":"多ID"})
    RSI_20D = QS.FactorDB.TimeOperation('RSI_20D',[AdjClose, AdjPreClose, TradeStatus], {'算子':RSI_Fun,'参数':{"非空率":0.8,'回测期':20},'回溯期数':[1000-1,1000-1,1000-1],"运算ID":"多ID"})
    RSI_60D = QS.FactorDB.TimeOperation('RSI_60D',[AdjClose, AdjPreClose, TradeStatus], {'算子':RSI_Fun,'参数':{"非空率":0.8,'回测期':60},'回溯期数':[1000-1,1000-1,1000-1],"运算ID":"多ID"})
    Factors.append(RSI_5D)
    Factors.append(RSI_20D)
    Factors.append(RSI_60D)

    # 乖离率指标
    Bias_5D = QS.FactorDB.TimeOperation("Bias_5D", [AdjClose, TradeStatus], sys_args={"算子": Bias_Fun,'参数':{"非空率":0.8}, "回溯期数": [5-1,5-1],"运算ID":"多ID"})
    Bias_20D = QS.FactorDB.TimeOperation("Bias_20D", [AdjClose, TradeStatus], sys_args={"算子": Bias_Fun,'参数':{"非空率":0.8}, "回溯期数": [20-1,20-1],"运算ID":"多ID"})
    Bias_60D = QS.FactorDB.TimeOperation("Bias_60D", [AdjClose, TradeStatus], sys_args={"算子": Bias_Fun,'参数':{"非空率":0.8}, "回溯期数": [60-1,60-1],"运算ID":"多ID"})
    Factors.append(Bias_5D)
    Factors.append(Bias_20D)
    Factors.append(Bias_60D)

    return Factors

if __name__=="__main__":
    pass