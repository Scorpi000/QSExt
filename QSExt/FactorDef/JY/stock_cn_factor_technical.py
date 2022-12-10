# coding=utf-8
"""技术因子"""
import datetime as dt
from collections import OrderedDict

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_factor_technical",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def EMAFun(f, idt, iid, x, args):
    N = args["N"]
    w = 2 / (N + 1)
    T = x[0].shape[0]
    return np.nansum((w * (1 - w) ** np.arange(T))[::-1] * x[0].T, axis=1)

# 滚动窗口计算 EMA
def EMAFun2(f, idt, iid, x, args):
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
def EMAFun_Adj(f, idt, iid, x, args):
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
def EMAFun_Iter_IgnoreNonTrading(f, idt, iid, x, args):
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
def ESumFun_Iter(f, idt, iid, x, args):
    PreRslt = x[0][0, :]
    PreRslt[pd.isnull(PreRslt)] = 0
    VA = x[1][-1, :]
    VA[pd.isnull(VA)] = 0
    return PreRslt + VA

# MA, 在除权日对前一日均线进行复权调整
def MAFun_Adj(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return np.mean(Price * AdjFactor / AdjFactor[-1, :], axis=0)

def MMDFun_Adj(f, idt, iid, x, args):
    p = x[0] * x[1] / x[1][-1, :]
    return np.sum(np.abs(p - np.mean(p, axis=0))) / p.shape[0]

# Moving Std, 在除权日对前一日均线进行复权调整
def MStdFun_Adj(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return np.std(Price * AdjFactor / AdjFactor[-1, :], axis=0, ddof=args["ddof"])

# Moving Sum, 在除权日对前一日均线进行复权调整
def MSumFun_Adj_Vol(f, idt, iid, x, args):
    Vol, AdjFactor = x[0], x[1]
    return np.std(Vol * AdjFactor[-1, :] / AdjFactor, axis=0)

# Moving Min, 在除权日对前一日均线进行复权调整
def MMinFun_Adj(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return np.nanmin(Price * AdjFactor / AdjFactor[-1, :], axis=0)

# Moving Max, 在除权日对前一日均线进行复权调整
def MMaxFun_Adj(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return np.nanmax(Price * AdjFactor / AdjFactor[-1, :], axis=0)

# Moving Diff, 在除权日对前一日均线进行复权调整
def MDiffFun_Adj(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return np.diff(Price * AdjFactor / AdjFactor[-1, :], args["N"], axis=0)[-1]

# Lag, 在除权日对前一日均线进行复权调整
def LagFun_Adj(f, idt, iid, x, args):
    Price, AdjFactor = x[0], x[1]
    return Price[0, :] * AdjFactor[0, :] / AdjFactor[-1, :]

# RSI SI
def SIFun_Adj(f, idt, iid, x, args):
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
def DKXFun(f, idt, iid, x, args):
    p = x[0] * x[-1] / x[-1][-1, :]
    w = np.r_[1, 0, np.arange(2, p.shape[0])]
    return np.sum(w * p.T, axis=1) / np.sum(w)

# 获取初值
def _getInitData(ft, factor_name, ids, target_dt=None):
    iInitData = None
    if (ft is not None) and (factor_name in ft.FactorNames):
        if target_dt is None:
            dts = ft.getDateTime(ifactor_name=factor_name)
            if not dts:
                return None
            target_dt = [-1]
        iInitData = ft.readData(factor_names=[factor_name], ids=ids, dts=[target_dt]).iloc[0]
    return iInitData
    
def RSI_Fun(f, idt, iid, x, args):
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

def Bias_Fun(f, idt, iid, x, args):
    Data = x[0]
    IfTrading=x[1]
    Len = IfTrading.shape[0]
    Mask = (np.sum(IfTrading==1, axis=0)/Len<args['非空率'])
    Avg = np.nanmean(Data,axis=0)
    Bias=(Data[-1]-Avg)/Avg
    Bias[Mask] = np.nan
    return Bias

def defFactor(args={}):
    Factors = []
    
    JYDB = args["JYDB"].connect()
    LDB = args["LDB"]
    
    TargetTable = "stock_cn_factor_technical"
    if TargetTable in TDB.TableNames:
        TargetFT = TDB.getTable(TargetTable)
    else:
        TargetFT = None
    if "ids" in args:
        TargetIDs = args["ids"]
    else:
        TargetIDs = JYDB.getStockID(is_current=False)
    if "dts" in args:
        TargetDT = args["dt_ruler"][args["dt_ruler"].index(args["dts"][0]) - 1]
    else:
        TargetDT = dt.datetime(2000, 1, 1)
    
    # ### 日行情因子 #################################
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    PreClose = FT.getFactor("pre_close")
    Open = FT.getFactor("open")
    High = FT.getFactor("high")
    Low = FT.getFactor("low")
    Close = FT.getFactor("close")
    DailyReturn = FT.getFactor("chg_rate")
    Amount = FT.getFactor("amount")
    Volume = FT.getFactor("volume")
    Turnover = FT.getFactor("turnover")
    IfTrading = FT.getFactor("if_trading")

    FT = LDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    AdjFactor = FT.getFactor("adj_factor")
    AdjPreClose = FT.getFactor("pre_close")
    AdjClose = FT.getFactor("close")
    
    # MA, pass
    MA_Periods = [3, 5, 6, 10, 12, 20, 24, 30, 60, 120]
    MAs = OrderedDict()
    for iN in MA_Periods:
        iFactorName = f"ma{iN}"
        MAs[iFactorName] = QS.FactorDB.TimeOperation(
            iFactorName, 
            [Close, AdjFactor],
            sys_args={
                "算子": MAFun_Adj,
                "参数": {},
                "回溯期数": [iN-1, iN-1],
                "运算ID": "多ID"
            }
        )
    Factors += list(MAs.values())
    
    # EMA, pass
    EMA_Periods = [5, 9, 10, 12, 20, 26, 30, 60, 120]
    EMAs = OrderedDict()
    for iN in EMA_Periods:
        iFactorName = f"ema{iN}"
        EMAs[iFactorName] = QS.FactorDB.TimeOperation(
            iFactorName, 
            [Close, AdjFactor],
            sys_args={
                "算子": EMAFun_Adj,
                "参数": {},
                "回溯期数": [iN * 3, iN * 3],
                "运算ID": "多ID"
            }
        )
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
    DIF = Factorize(SMA - LMA, factor_name="macd_dif")
    DEA = QS.FactorDB.TimeOperation(
        "macd_dea", 
        [DIF],
        sys_args={
            "算子": EMAFun2,
            "参数": {"N": 9},
            "回溯期数": [9 * 3],
            "运算ID": "多ID"
        }
    )
    MACD = Factorize(2 * (DIF - DEA), factor_name="macd")
    Factors += [DIF, DEA, MACD]
    
    # Bolling Band
    iN = 20
    BollMid = QS.FactorDB.TimeOperation(
        "boll_mid", 
        [Close, AdjFactor],
        sys_args={
            "算子": MAFun_Adj,
            "参数": {},
            "回溯期数": [iN - 1, iN - 1],
            "运算ID": "多ID"
        }
    )
    Factors.append(BollMid)
    CloseStd = QS.FactorDB.TimeOperation(
        "close_std", 
        [Close, AdjFactor],
        sys_args={
            "算子": MStdFun_Adj,
            "参数": {},
            "回溯期数": [iN - 1, iN - 1],
            "运算ID": "多ID"
        }
    )
    BollLower = Factorize(BollMid - 2 * CloseStd, factor_name="boll_lower")
    Factors.append(BollLower)
    BollUpper = Factorize(BollMid + 2 * CloseStd, factor_name="boll_upper")
    Factors.append(BollUpper)
    
    # KDJ
    iLow = QS.FactorDB.TimeOperation(
        "KDJ_Low", 
        [Low, AdjFactor],
        sys_args={
            "算子": MMinFun_Adj,
            "参数": {},
            "回溯期数": [9 - 1, 9 - 1],
            "运算ID": "多ID"
        }
    )
    iHigh = QS.FactorDB.TimeOperation(
        "KDJ_High", 
        [High, AdjFactor],
        sys_args={
            "算子": MMaxFun_Adj,
            "参数": {},
            "回溯期数": [9 - 1, 9 - 1],
            "运算ID": "多ID"
        }
    )
    RSV = Factorize((Close - iLow) / (iHigh - iLow) * 100, factor_name="kdj_rsv")
    Factors.append(RSV)
    iInitData = _getInitData(TargetFT, "kdj_k", TargetIDs, target_dt=TargetDT)
    KDJK = QS.FactorDB.TimeOperation(
        "kdj_k", 
        [RSV],
        sys_args={
            "算子": EMAFun_Iter,
            "参数": {"N": 5},
            "回溯期数": [1 - 1],
            "自身回溯期数": 1,
            "自身初始值": iInitData,
            "运算ID": "多ID"
        }
    )
    Factors.append(KDJK)
    iInitData = _getInitData(TargetFT, "kdj_d", TargetIDs, target_dt=TargetDT)
    KDJD = QS.FactorDB.TimeOperation(
        "kdj_d", 
        [KDJK],
        sys_args={
            "算子": EMAFun_Iter,
            "参数": {"N": 5},
            "回溯期数": [1 - 1],
            "自身回溯期数": 1,
            "自身初始值": iInitData,
            "运算ID": "多ID"
        }
    )
    Factors.append(KDJD)
    KDJJ = Factorize(3 * KDJD - 2 * KDJK, factor_name="kdj_j")
    Factors.append(KDJJ)
    
    # RSI
    CloseDiff = QS.FactorDB.TimeOperation(
        "CloseDiff", 
        [Close, AdjFactor],
        sys_args={
            "算子": MDiffFun_Adj,
            "参数": {"N": 1},
            "回溯期数": [2 - 1, 2 - 1],
            "运算ID": "多ID"
        }
    )
    CloseDiffPos = fd.fillna(fd.clip(CloseDiff, 0, np.inf), value=0)
    CloseDiffNeg = fd.fillna(fd.clip(-CloseDiff, 0, np.inf), value=0)
    RSI_Periods = [6, 12, 14, 24]
    for iN in RSI_Periods:
        iInitData = _getInitData(TargetFT, f"rsi_u{iN}", TargetIDs, target_dt=TargetDT)
        if iInitData is None: iInitData = pd.DataFrame(0, index=[TargetDT], columns=TargetIDs)
        iU = QS.FactorDB.TimeOperation(
            f"rsi_u{iN}", 
            [CloseDiffPos, IfTrading],
            sys_args={
                "算子": EMAFun_Iter_IgnoreNonTrading,
                "参数": {"N": 2*iN-1},
                "回溯期数": [1 - 1, 1 - 1],
                "自身回溯期数": 1,
                "自身初始值": iInitData,
                "运算ID": "多ID"
            }
        )
        iInitData = _getInitData(TargetFT, f"rsi_d{iN}", TargetIDs, target_dt=TargetDT)
        if iInitData is None: iInitData = pd.DataFrame(0, index=[TargetDT], columns=TargetIDs)
        iD = QS.FactorDB.TimeOperation(
            f"rsi_d{iN}", 
            [CloseDiffNeg, IfTrading],
            sys_args={
                "算子": EMAFun_Iter_IgnoreNonTrading,
                "参数": {"N": 2*iN-1},
                "回溯期数": [1 - 1, 1 - 1],
                "自身回溯期数": 1,
                "自身初始值": iInitData,
                "运算ID": "多ID"
            }
        )
        RSI = Factorize(iU / (iU + iD) * 100, factor_name=f"rsi{iN}")
        Factors += [iU, iD, RSI]
    
    # RSI
    RSI_5D = QS.FactorDB.TimeOperation('RSI_5D',[AdjClose, AdjPreClose, IfTrading], {'算子':RSI_Fun,'参数':{"非空率":0.8,'回测期':5},'回溯期数':[1000-1,1000-1,1000-1],"运算ID":"多ID"})
    RSI_20D = QS.FactorDB.TimeOperation('RSI_20D',[AdjClose, AdjPreClose, IfTrading], {'算子':RSI_Fun,'参数':{"非空率":0.8,'回测期':20},'回溯期数':[1000-1,1000-1,1000-1],"运算ID":"多ID"})
    RSI_60D = QS.FactorDB.TimeOperation('RSI_60D',[AdjClose, AdjPreClose, IfTrading], {'算子':RSI_Fun,'参数':{"非空率":0.8,'回测期':60},'回溯期数':[1000-1,1000-1,1000-1],"运算ID":"多ID"})
    Factors.append(RSI_5D)
    Factors.append(RSI_20D)
    Factors.append(RSI_60D)
    
    # BIAS, pass
    BIAS_Periods = [5, 6, 12, 24]
    for iN in BIAS_Periods:
        BIAS = Factorize(Close / MAs[f"ma{iN}"] - 1, factor_name=f"bias{iN}")
        Factors.append(BIAS)
    
    # 乖离率指标
    Bias_5D = QS.FactorDB.TimeOperation("Bias_5D", [AdjClose, IfTrading], sys_args={"算子": Bias_Fun,'参数':{"非空率":0.8}, "回溯期数": [5-1,5-1],"运算ID":"多ID"})
    Bias_20D = QS.FactorDB.TimeOperation("Bias_20D", [AdjClose, IfTrading], sys_args={"算子": Bias_Fun,'参数':{"非空率":0.8}, "回溯期数": [20-1,20-1],"运算ID":"多ID"})
    Bias_60D = QS.FactorDB.TimeOperation("Bias_60D", [AdjClose, IfTrading], sys_args={"算子": Bias_Fun,'参数':{"非空率":0.8}, "回溯期数": [60-1,60-1],"运算ID":"多ID"})
    Factors.append(Bias_5D)
    Factors.append(Bias_20D)
    Factors.append(Bias_60D)
    
    # Willam's R
    WR_Periods = [6, 10, 14]
    for iN in WR_Periods:
        iLow = QS.FactorDB.TimeOperation(
            f"WR_Low{iN}", 
            [Low, AdjFactor],
            sys_args={
                "算子": MMinFun_Adj,
                "参数": {},
                "回溯期数": [iN - 1, iN - 1],
                "运算ID": "多ID"
            }
        )
        iHigh = QS.FactorDB.TimeOperation(
            f"WR_High{iN}", 
            [High, AdjFactor],
            sys_args={
                "算子": MMaxFun_Adj,
                "参数": {},
                "回溯期数": [iN - 1, iN - 1],
                "运算ID": "多ID"
            }
        )
        WillR = Factorize((iHigh - Close) / (iHigh - iLow) * 100, factor_name=f"wr{iN}")
        Factors.append(WillR)
    
    # ASI, 累计振动升降指标, Accumulation Swing Index
    SI = QS.FactorDB.TimeOperation(
        "asi_si", 
        [High, Low, Close, Open, AdjFactor],
        sys_args={
            "算子": SIFun_Adj,
            "参数": {},
            "回溯期数": [1, 1, 1, 1, 1],
            "运算ID": "多ID"
        }
    )
    Factors.append(SI)
    ASI_Periods = [6, 10, 14, 20, 26]
    for iN in ASI_Periods:
        ASI = fd.rolling_sum(SI, window=iN, min_periods=iN, factor_name=f"asi{iN}")
        Factors.append(ASI)
    
    # VR
    iN = 26
    AVS = QS.FactorDB.TimeOperation(
        "AVS", 
        [fd.where(Volume, CloseDiff>0, 0), AdjFactor],
        sys_args={
            "算子": MSumFun_Adj_Vol,
            "参数": {},
            "回溯期数": [iN - 1, iN - 1],
            "运算ID": "多ID"
        }
    )
    BVS = QS.FactorDB.TimeOperation(
        "BVS", 
        [fd.where(Volume, CloseDiff<0, 0), AdjFactor],
        sys_args={
            "算子": MSumFun_Adj_Vol,
            "参数": {},
            "回溯期数": [iN - 1, iN - 1],
            "运算ID": "多ID"
        }
    )
    CVS = QS.FactorDB.TimeOperation(
        "AVS", 
        [fd.where(Volume, CloseDiff==0, 0), AdjFactor],
        sys_args={
            "算子": MSumFun_Adj_Vol,
            "参数": {},
            "回溯期数": [iN - 1, iN - 1],
            "运算ID": "多ID"
        }
    )
    VR = Factorize((AVS + 1/2 * CVS) / (BVS + 1/2 * CVS), factor_name="vr")
    Factors.append(VR)
    
    # BBI, 牛熊线, Bull and Bear Index
    BBI_Periods = [3, 6, 12, 24]
    BBI = fd.nanmean(*[MAs[f"ma{iN}"] for iN in BBI_Periods], factor_name="bbi")
    Factors.append(BBI)
    
    # ENE 轨道线
    N, M1, M2 = 10, 11, 9
    ENEUpper = Factorize((1 + M1 / 100) * MAs[f"ma{N}"], factor_name="ene_upper")
    ENELower = Factorize((1 - M2 / 100) * MAs[f"ma{N}"], factor_name="ene_lower")
    ENE = Factorize((ENEUpper + ENELower) / 2, factor_name="ene")
    Factors += [ENE, ENEUpper, ENELower]
    
    # DKX, 多空线
    MID = (3 * Close + Low + Open + High) / 6
    DKX = QS.FactorDB.TimeOperation(
        "dkx", 
        [MID, AdjFactor],
        sys_args={
            "算子": DKXFun,
            "参数": {},
            "回溯期数": [21 - 1, 21 - 1],
            "运算ID": "多ID"
        }
    )
    MADKX = QS.FactorDB.TimeOperation(
        "dkx_madkx", 
        [DKX, AdjFactor],
        sys_args={
            "算子": MAFun_Adj,
            "参数": {},
            "回溯期数": [10 - 1, 10 - 1],
            "运算ID": "多ID"
        }
    )
    Factors += [DKX, MADKX]
    
    # CCI, 顺势指标
    N = 14
    TP = (High + Low + Close) / 3
    TP_MA = QS.FactorDB.TimeOperation(
        "tp_ma", 
        [TP, AdjFactor],
        sys_args={
            "算子": MAFun_Adj,
            "参数": {},
            "回溯期数": [N - 1, N - 1],
            "运算ID": "多ID"
        }
    )
    TP_MD = QS.FactorDB.TimeOperation(
        "tp_std", 
        [TP, AdjFactor],
        sys_args={
            "算子": MMDFun_Adj,
            "参数": {},
            "回溯期数": [N - 1, N - 1],
            "运算ID": "多ID"
        }
    )
    CCI = Factorize((TP - TP_MA) / TP_MD / 0.015, factor_name=f"cci{N}")
    Factors.append(CCI)
    
    # OBV, 能量潮, On Balance Volume
    VA = fd.where(Volume, CloseDiff>0, fd.where(-Volume, CloseDiff<0, 0)) / 10000
    iInitData = _getInitData(TargetFT, "obv", TargetIDs, target_dt=TargetDT)
    if iInitData is None: iInitData = pd.DataFrame(0, index=[TargetDT], columns=TargetIDs)
    OBV = QS.FactorDB.TimeOperation(
        "obv", 
        [VA],
        sys_args={
            "算子": ESumFun_Iter,
            "参数": {},
            "回溯期数": [1 - 1],
            "自身回溯期数": 1,
            "自身初始值": iInitData,
            "运算ID": "多ID"
        }
    )
    Factors += [OBV]
    
    return Factors

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.WindDB2()
    JYDB.connect()
    
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = JYDB.getStockID(is_current=False)
    
    Args = {"JYDB": JYDB}
    Factors = defFactor(args=Args)
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTs)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
        factor_db=TDB, table_name=TargetTable,
        if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    JYDB.disconnect()