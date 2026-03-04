# coding=utf-8
"""技术因子"""
import datetime as dt
from collections import OrderedDict

import numpy as np
import pandas as pd

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStockStatus
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar
from QSExt.FactorDef.JY.stock_cn_day_bar_adj_backward_nafilled import defFactor as defStockAdjDayBar


def EMAFun(f, idt, iid, x, args):
    N = args["N"]
    w = 2 / (N + 1)
    T = x[0].shape[0]
    return np.nansum((w * (1 - w) ** np.arange(T))[::-1] * x[0].T, axis=1)

# 滚动窗口计算 EMA
@FactorOperatorized(operator_type="Time", args={"Arity": 1, "ModelArgs": {"N": 9}, "LookBack": [9 * 3], "IDMode": "多ID"})
def calcEMA2(f, idt, iid, x, args):
    p = x[0]
    N = args["N"]
    T = p.shape[0]
    Lambda = 2 / (N + 1)
    Mask = pd.isnull(p)
    w = Lambda * (1 - Lambda) ** (np.cumsum(~Mask[::-1], axis=0)[::-1] - 1)
    w[Mask] = np.nan
    Idx = np.argmax(~Mask, axis=0)
    w[Idx, np.arange(p.shape[1])] /= Lambda
    Rslt = np.nansum(w * p, axis=0)
    Rslt[np.all(Mask, axis=0)] = np.nan
    return Rslt

# 在除权日对前一日均线进行复权调整
@FactorOperatorized(operator_type="Time", args={"Arity": 2, "LookBack": [5 * 3, 5 * 3], "IDMode": "多ID"})
def calcAdjEMA(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    p = Price * AdjFactor / AdjFactor[-1, :]
    N, T = args["N"], p.shape[0]
    Lambda = 2 / (N + 1)
    Mask = pd.isnull(p)
    w = Lambda * (1 - Lambda) ** (np.cumsum(~Mask[::-1], axis=0)[::-1] - 1)
    w[Mask] = np.nan
    Idx = np.argmax(~Mask, axis=0)
    w[Idx, np.arange(p.shape[1])] /= Lambda
    Rslt = np.nansum(w * p, axis=0)
    Rslt[np.all(Mask, axis=0)] = np.nan
    return Rslt

# 迭代法计算 EMA
def EMAFun_Iter(f, idt, iid, x, args):
    if x[0].shape[0]==0: return x[1][0, :]
    PreRslt = x[0][0, :]
    N = args["N"]
    Rslt = 2 / (N + 1) * x[1][0, :] + (1 - 2 / (N + 1)) * PreRslt
    Mask = pd.isnull(PreRslt)
    Rslt[Mask] = x[1][0, Mask]
    return Rslt

# 迭代法计算 EMA, 在除权日对前一日均线进行复权调整
def EMAFun_Adj_Iter(f, idt, iid, x, args):
    if x[0].shape[0]==0: return x[1][0, :]
    AdjFactor = x[2][0, :] / x[2][-1, :]
    PreRslt = x[0][0, :] * AdjFactor
    N = args["N"]
    Rslt = 2 / (N + 1) * x[1][0, :] + (1 - 2 / (N + 1)) * PreRslt
    Mask = pd.isnull(PreRslt)
    Rslt[Mask] = x[1][0, Mask]
    return Rslt

# 迭代法计算 EMA, 忽略非交易日
@FactorOperatorized(operator_type="Time", args={"Arity": 2, "LookBack": [5 * 3, 5 * 3], "IDMode": "多ID"})
def calcIterIgnoreNonTradingEMA(f, idt, iid, x, args):
    if x[0].shape[0]==0: return x[1][0, :]
    PreRslt = x[0][0, :]
    N = args["N"]
    Rslt = 2 / (N + 1) * x[1][0, :] + (1 - 2 / (N + 1)) * PreRslt
    Mask = pd.isnull(PreRslt)
    Rslt[Mask] = x[1][0, Mask]
    Mask = (x[-1][-1, :]!=1)
    Rslt[Mask] = PreRslt[Mask]
    return Rslt

# 迭代法计算 EMA, 在除权日对前一日均线进行复权调整, 忽略非交易日
def EMAFun_Adj_Iter_IgnoreNonTrading(f, idt, iid, x, args):
    if x[0].shape[0]==0: return x[1][0, :]
    AdjFactor = x[2][0, :] / x[2][-1, :]
    PreRslt = x[0][0, :] * AdjFactor
    N = args["N"]
    Rslt = 2 / (N + 1) * x[1][0, :] + (1 - 2 / (N + 1)) * PreRslt
    Mask = pd.isnull(PreRslt)
    Rslt[Mask] = x[1][0, Mask]
    Mask = (x[-1][-1, :]!=1)
    Rslt[Mask] = PreRslt[Mask]
    return Rslt

# Expanding Sum
@FactorOperatorized(operator_type="Time", args={"Arity": 1, "LookBack": [5-1], "IDMode": "多ID"})
def calcIterESum(f, idt, iid, x, args):
    PreRslt = x[0][0, :]
    PreRslt[pd.isnull(PreRslt)] = 0
    VA = x[1][-1, :]
    VA[pd.isnull(VA)] = 0
    return PreRslt + VA

# MA, 在除权日对前一日均线进行复权调整
@FactorOperatorized(operator_type="Time", args={"Arity": 2, "LookBack": [5-1, 5-1], "IDMode": "多ID"})
def calcAdjMA(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return np.mean(Price * AdjFactor / AdjFactor[-1, :], axis=0)

@FactorOperatorized(operator_type="Time", args={"Arity": 2, "LookBack": [5-1, 5-1], "IDMode": "多ID"})
def calcAdjMMD(f, idt, iid, x, args):
    p = x[0] * x[1] / x[1][-1, :]
    return np.sum(np.abs(p - np.mean(p, axis=0))) / p.shape[0]

# Moving Std, 在除权日对前一日均线进行复权调整
@FactorOperatorized(operator_type="Time", args={"Arity": 2, "LookBack": [5 - 1, 5 - 1], "IDMode": "多ID"})
def calcAdjMStd(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return np.std(Price * AdjFactor / AdjFactor[-1, :], axis=0, ddof=args["ddof"])

# Moving Sum, 在除权日对前一日均线进行复权调整
@FactorOperatorized(operator_type="Time", args={"Arity": 2, "LookBack": [5-1, 5-1], "IDMode": "多ID"})
def calcAdjVolMSum(f, idt, iid, x, args):
    Vol, AdjFactor = x[0], x[1]
    return np.std(Vol * AdjFactor[-1, :] / AdjFactor, axis=0)

# Moving Min, 在除权日对前一日均线进行复权调整
@FactorOperatorized(operator_type="Time", args={"Arity": 2, "LookBack": [9 - 1, 9 - 1], "IDMode": "多ID"})
def calcAdjMMin(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return np.nanmin(Price * AdjFactor / AdjFactor[-1, :], axis=0)

# Moving Max, 在除权日对前一日均线进行复权调整
@FactorOperatorized(operator_type="Time", args={"Arity": 2, "LookBack": [9 - 1, 9 - 1], "IDMode": "多ID"})
def calcAdjMMax(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return np.nanmax(Price * AdjFactor / AdjFactor[-1, :], axis=0)

# Moving Diff, 在除权日对前一日均线进行复权调整
@FactorOperatorized(operator_type="Time", args={"Arity": 2, "ModelArgs": {"N": 1}, "LookBack": [2 - 1, 2 - 1], "IDMode": "多ID"})
def calcAdjMDiff(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return np.diff(Price * AdjFactor / AdjFactor[-1, :], args["N"], axis=0)[-1]

# Lag, 在除权日对前一日均线进行复权调整
def LagFun_Adj(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return Price[0, :] * AdjFactor[0, :] / AdjFactor[-1, :]

# RSI SI
@FactorOperatorized(operator_type="Time", args={"Arity": 5, "LookBack": [1, 1, 1, 1, 1], "IDMode": "多ID"})
def calcSI(f, idt, iid, x, args):
    AdjFactor = x[-1] / x[-1][-1, :]
    High, Low, Close, Open = x[0] * AdjFactor, x[1] * AdjFactor, x[2] * AdjFactor, x[3] * AdjFactor
    A = np.abs(High[-1] - Close[-2])
    B = np.abs(Low[-1] - Close[-2])
    C = np.abs(High[-1] - Low[-2])
    D = np.abs(Close[-1] - Open[-2])
    E = Close[-1] - Close[-2]
    F = Close[-1] - Open[-1]
    E = Close[-2] - Open[-2]
    X = E + 0.5 * F + G
    K = np.nanmax([A, B], axis=0)
    ArgMax = np.argmax([A, B, C], axis=0)
    R = (ArgMax==0) * (A + 0.5 * B + 0.25 * D) + (ArgMax==1) * (B + 0.5 * A + 0.25 * D) + (ArgMax==2) * (C + 0.25 * D)
    L = 3
    SI = 50 * X / R * K / L
    return SI

# DKX
@FactorOperatorized(operator_type="Time", args={"Arity": 2, "LookBack": [21 - 1, 21 - 1], "IDMode": "多ID"})
def calcDKX(f, idt, iid, x, args):
    p = x[0] * x[-1] / x[-1][-1, :]
    w = np.r_[1, 0, np.arange(2, p.shape[0])]
    return np.sum(w * p.T, axis=1) / np.sum(w)

@FactorOperatorized(operator_type="Time", args={"Arity": 3, 'ModelArgs': {"非空率": 0.8, '回测期': 5},'LookBack': [1000-1, 1000-1, 1000-1], "IDMode": "多ID"})
def calcRSI(f, idt, iid, x, args):
    Close = x[0]
    Pre_Close = x[1]
    IfTrading = x[2]
    Len = IfTrading.shape[0]
    Mask = (np.sum(IfTrading==1, axis=0) / Len < args['非空率'])
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

@FactorOperatorized(operator_type="Time", args={"Arity": 2, 'ModelArgs': {"非空率": 0.8}, "LookBack": [5-1, 5-1], "IDMode":"多ID"})
def calcBias(f, idt, iid, x, args):
    Data = x[0]
    IfTrading=x[1]
    Len = IfTrading.shape[0]
    Mask = (np.sum(IfTrading==1, axis=0)/Len<args['非空率'])
    Avg = np.nanmean(Data,axis=0)
    Bias=(Data[-1]-Avg)/Avg
    Bias[Mask] = np.nan
    return Bias

def defFactor(fdi: FactorDefInput):
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    # ### 日行情因子 #################################
    StockDayBarDef = defStockDayBar(fdi=fdi)
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    PreClose = StockDayBarDef.getFactor(factor_name="pre_close")
    Open = StockDayBarDef.getFactor(factor_name="open")
    High = StockDayBarDef.getFactor(factor_name="high")
    Low = StockDayBarDef.getFactor(factor_name="low")
    Close = StockDayBarDef.getFactor(factor_name="close")
    DailyReturn = StockDayBarDef.getFactor(factor_name="chg_rate")
    Amount = StockDayBarDef.getFactor(factor_name="amount")
    Volume = StockDayBarDef.getFactor(factor_name="volume")
    Turnover = StockDayBarDef.getFactor(factor_name="turnover")
    
    StockStatusDef = defStockStatus(fdi=fdi)
    IfTrading = StockStatusDef.getFactor(factor_name="if_trading")
    
    StockAdjDayBarDef = defStockAdjDayBar(fdi=fdi)
    AdjFactor = StockAdjDayBarDef.getFactor(factor_name="adj_factor")
    AdjPreClose = StockAdjDayBarDef.getFactor(factor_name="pre_close")
    AdjClose = StockAdjDayBarDef.getFactor(factor_name="close")
    
    # MA, pass
    MA_Periods = [3, 5, 6, 10, 12, 20, 24, 30, 60, 120]
    MAs = OrderedDict()
    for iN in MA_Periods:
        iFactorName = f"ma{iN}"
        MAs[iFactorName] = calcAdjMA.new(args={"LookBack": [iN-1, iN-1]})(Close, AdjFactor, factor_args={"Name": iFactorName})
    Factors += list(MAs.values())
    
    # EMA, pass
    EMA_Periods = [5, 9, 10, 12, 20, 26, 30, 60, 120]
    EMAs = OrderedDict()
    for iN in EMA_Periods:
        iFactorName = f"ema{iN}"
        EMAs[iFactorName] = calcAdjEMA.new(args={"LookBack": [iN * 3, iN * 3]})(Close, AdjFactor, factor_args={"Name": iFactorName})
    Factors += list(EMAs.values())
    
    ema_12 = QS.FactorDB.TimeOperation("ema12", [Close], sys_args={"算子": EMAFun, "参数": {"N": 12}, "回溯期数": [36], "运算ID": "多ID"})
    Factors.append(ema_12)
    ema_26 = QS.FactorDB.TimeOperation("ema26", [Close], sys_args={"算子": EMAFun, "参数": {"N": 26}, "回溯期数": [78], "运算ID": "多ID"})
    Factors.append(ema_26)
    ema_5 = QS.FactorDB.TimeOperation("ema5", [Close], sys_args={"算子": EMAFun, "参数": {"N": 5}, "回溯期数": [15], "运算ID": "多ID"})
    Factors.append(ema_5)
    ema_9 = QS.FactorDB.TimeOperation("ema9", [Close], sys_args={"算子": EMAFun, "参数": {"N": 9}, "回溯期数": [30], "运算ID": "多ID"})
    Factors.append(ema_9)
    ema_10 = QS.FactorDB.TimeOperation("ema10", [Close], sys_args={"算子": EMAFun, "参数": {"N": 10}, "回溯期数": [30], "运算ID": "多ID"})
    Factors.append(ema_10)
    ema_20 = QS.FactorDB.TimeOperation("ema20", [Close], sys_args={"算子": EMAFun, "参数": {"N": 20}, "回溯期数": [60], "运算ID": "多ID"})
    Factors.append(ema_20)
    ema_30 = QS.FactorDB.TimeOperation("ema30", [Close], sys_args={"算子": EMAFun, "参数": {"N": 30}, "回溯期数": [90], "运算ID": "多ID"})
    Factors.append(ema_30)
    ema_60 = QS.FactorDB.TimeOperation("ema60", [Close], sys_args={"算子": EMAFun, "参数": {"N": 60}, "回溯期数": [180], "运算ID": "多ID"})
    Factors.append(ema_60)
    ema_120 = QS.FactorDB.TimeOperation("ema120", [Close], sys_args={"算子": EMAFun, "参数": {"N": 120}, "回溯期数": [360], "运算ID": "多ID"})
    Factors.append(ema_120)    
    
    # MACD
    SMA = EMAs["ema12"]
    LMA = EMAs["ema26"]
    DIF = rename(SMA - LMA, factor_name="macd_dif")
    DEA = calcEMA2(DIF, factor_args={"Name": "macd_dea"})
    MACD = rename(2 * (DIF - DEA), factor_name="macd")
    Factors += [DIF, DEA, MACD]
    
    # Bolling Band
    iN = 20
    BollMid = calcAdjMA.new(args={"LookBack": [iN - 1, iN - 1]})(Close, AdjFactor, factor_args={"Name": "boll_mid"})
    Factors.append(BollMid)
    CloseStd = calcAdjMStd.new(args={"LookBack": [iN - 1, iN - 1]})(Close, AdjFactor, factor_args={"Name": "close_std"})
    BollLower = rename(BollMid - 2 * CloseStd, factor_name="boll_lower")
    Factors.append(BollLower)
    BollUpper = rename(BollMid + 2 * CloseStd, factor_name="boll_upper")
    Factors.append(BollUpper)
    
    # KDJ
    iLow = calcAdjMMin(Low, AdjFactor)
    iHigh = calcAdjMMax(High, AdjFactor)
    RSV = rename((Close - iLow) / (iHigh - iLow) * 100, factor_name="kdj_rsv")
    Factors.append(RSV)
    KDJK = calcEMA2.new(args={"ModelArgs": {"N": 5}, "LookBack": [5 * 3]})(RSV, factor_args={"Name": "kdj_k"})
    KDJD = calcEMA2.new(args={"ModelArgs": {"N": 5}, "LookBack": [5 * 3]})(KDJK, factor_args={"Name": "kdj_d"})
    Factors.append(KDJK)
    Factors.append(KDJD)
    KDJJ = rename(3 * KDJD - 2 * KDJK, factor_name="kdj_j")
    Factors.append(KDJJ)
    
    # RSI
    where = fo.Where()
    CloseDiff = calcAdjMDiff(Close, AdjFactor)
    CloseDiffPos = where(CloseDiff, CloseDiff>0, 0)
    CloseDiffNeg = where(-CloseDiff, CloseDiff<0, 0)
    RSI_Periods = [6, 12, 14, 24]
    for iN in RSI_Periods:
        iU = calcIterIgnoreNonTradingEMA.new(args={"ModelArgs": {"N": 2*iN-1}})(CloseDiffPos, IfTrading, factor_args={"Name": f"rsi_u{iN}"})
        iD = calcIterIgnoreNonTradingEMA.new(args={"ModelArgs": {"N": 2*iN-1}})(CloseDiffNeg, IfTrading, factor_args={"Name": f"rsi_d{iN}"})
        RSI = rename(iU / (iU + iD) * 100, factor_name=f"rsi{iN}")
        Factors += [iU, iD, RSI]
    
    # RSI
    RSI_5D = calcRSI(AdjClose, AdjPreClose, IfTrading, factor_args={"Name": "RSI_5D"})
    RSI_20D = calcRSI(AdjClose, AdjPreClose, IfTrading, factor_args={"Name": "RSI_20D"})
    RSI_60D = calcRSI(AdjClose, AdjPreClose, IfTrading, factor_args={"Name": "RSI_60D"})
    Factors.append(RSI_5D)
    Factors.append(RSI_20D)
    Factors.append(RSI_60D)
    
    # BIAS, pass
    BIAS_Periods = [5, 6, 12, 24]
    for iN in BIAS_Periods:
        BIAS = rename(Close / MAs[f"ma{iN}"] - 1, factor_name=f"bias{iN}")
        Factors.append(BIAS)
    
    # 乖离率指标
    Bias_5D = calcBias(AdjClose, IfTrading, factor_args={"Name": "Bias_5D"})
    Bias_20D = calcBias.new(args={"LookBack": [20-1, 20-1]})(AdjClose, IfTrading, factor_args={"Name": "Bias_20D"})
    Bias_60D = calcBias.new(args={"LookBack": [60-1, 60-1]})(AdjClose, IfTrading, factor_args={"Name": "Bias_60D"})
    Factors.append(Bias_5D)
    Factors.append(Bias_20D)
    Factors.append(Bias_60D)
    
    # Willam's R
    WR_Periods = [6, 10, 14]
    for iN in WR_Periods:
        iLow = calcAdjMMin.new(args={"LookBack": [iN - 1, iN - 1]})(Low, AdjFactor, factor_args={"Name": f"WR_Low{iN}"})
        iHigh = calcAdjMMax.new(args={"LookBack": [iN - 1, iN - 1]})(High, AdjFactor, factor_args={"Name": f"WR_High{iN}"})
        WillR = rename((iHigh - Close) / (iHigh - iLow) * 100, factor_name=f"wr{iN}")
        Factors.append(WillR)
    
    # ASI, 累计振动升降指标, Accumulation Swing Index
    SI = calcSI(High, Low, Close, Open, AdjFactor, factor_args={"Name": "asi_si"})
    Factors.append(SI)
    ASI_Periods = [6, 10, 14, 20, 26]
    for iN in ASI_Periods:
        ASI = fo.RollingApply(func=np.nansum, window=iN, min_periods=iN)(SI, factor_args={"Name": f"asi{iN}"})
        Factors.append(ASI)
    
    # VR
    iN = 26
    AVS = calcAdjVolMSum.new(args={"LookBack": [iN - 1, iN - 1]})(where(Volume, CloseDiff>0, 0), AdjFactor)
    BVS = calcAdjVolMSum.new(args={"LookBack": [iN - 1, iN - 1]})(where(Volume, CloseDiff<0, 0), AdjFactor)
    CVS = calcAdjVolMSum.new(args={"LookBack": [iN - 1, iN - 1]})(where(Volume, CloseDiff==0, 0), AdjFactor)
    VR = rename((AVS + 1/2 * CVS) / (BVS + 1/2 * CVS), factor_name="vr")
    Factors.append(VR)
    
    # BBI, 牛熊线, Bull and Bear Index
    BBI_Periods = [3, 6, 12, 24]
    BBI = fo.Mean()(*[MAs[f"ma{iN}"] for iN in BBI_Periods], factor_args={"Name": "bbi"})
    Factors.append(BBI)
    
    # ENE 轨道线
    N, M1, M2 = 10, 11, 9
    ENEUpper = rename((1 + M1 / 100) * MAs[f"ma{N}"], factor_name="ene_upper")
    ENELower = rename((1 - M2 / 100) * MAs[f"ma{N}"], factor_name="ene_lower")
    ENE = rename((ENEUpper + ENELower) / 2, factor_name="ene")
    Factors += [ENE, ENEUpper, ENELower]
    
    # DKX, 多空线
    MID = (3 * Close + Low + Open + High) / 6
    DKX = calcDKX(MID, AdjFactor, factor_args={"Name": "dkx"})
    MADKX = calcAdjMA.new(args={"LookBack": [10 - 1, 10 - 1]})(DKX, AdjFactor, factor_args={"Name": "dkx_madkx"})
    Factors += [DKX, MADKX]
    
    # CCI, 顺势指标
    N = 14
    TP = (High + Low + Close) / 3
    TP_MA = calcAdjMA.new(args={"LookBack": [N - 1, N - 1]})(TP, AdjFactor, args={"Name": "tp_ma"})
    TP_MD = calcAdjMMD.new(args={"LookBack": [N - 1, N - 1]})(TP, AdjFactor, args={"Name": "tp_std"})
    CCI = rename((TP - TP_MA) / TP_MD / 0.015, factor_name=f"cci{N}")
    Factors.append(CCI)
    
    # OBV, 能量潮, On Balance Volume
    VA = where(Volume, CloseDiff>0, where(-Volume, CloseDiff<0, 0)) / 10000
    OBV = calcIterESum(VA, factor_args={"Name": "obv"})
    Factors += [OBV]
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_factor_technical",
        MaxLookBack=365 * 2, 
        IDType="A股",
        Author="麦冬"
    )
