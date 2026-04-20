# coding=utf-8
"""QLib Alpha 158"""
from functools import partial
from typing import Dict

import numpy as np
from scipy import stats

from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.Factor.FactorOperator import RollingCorr


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []

    # 基本算子
    log = fo.Log(base=np.e)
    max = fo.Max(all_nan=np.nan)
    min = fo.Min(all_nan=np.nan)
    lag1 = fo.Lag(1)

    # LDB = fdi.FDB["LDB"]
    # FT = LDB.getTable("stock_cn_day_bar_nafilled")
    # Volume = FT.getFactor("volume")

    # FT = LDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    # AdjClose = FT.getFactor("close")
    # AdjHigh = FT.getFactor("high")
    # AdjLow = FT.getFactor("low")
    # AdjOpen = FT.getFactor("open")
    # AdjVWAP = FT.getFactor("avg")

    # 基本因子
    StockDayBarDef = dep_fd["stock_cn_day_bar_nafilled"]
    Volume = StockDayBarDef.getFactor("volume")

    StockDayBarAdjDef = dep_fd["stock_cn_day_bar_adj_backward_nafilled"]
    AdjClose = StockDayBarAdjDef.getFactor("close")
    AdjHigh = StockDayBarAdjDef.getFactor("high")
    AdjLow = StockDayBarAdjDef.getFactor("low")
    AdjOpen = StockDayBarAdjDef.getFactor("open")
    AdjVWAP = StockDayBarAdjDef.getFactor("avg")

    # K 线类
    # KMID
    Factors.append(rename((AdjClose - AdjOpen) / AdjOpen, factor_name="KMID"))
    # KLEN: K线长度 = (最高价 - 最低价) / 开盘价
    Factors.append(rename((AdjHigh - AdjLow) / AdjOpen, factor_name="KLEN"))
    # KMID2
    Factors.append(rename((AdjClose - AdjOpen) / (AdjHigh - AdjLow + 1e-12), factor_name="KMID2"))
    # KUP: 上影线 = (最高价 - MAX(收盘价, 开盘价)) / 开盘价
    Factors.append(rename((AdjHigh - max(AdjClose, AdjOpen)) / AdjOpen, factor_name="KUP"))
    # KUP2
    Factors.append(rename((AdjHigh - max(AdjClose, AdjOpen)) / (AdjHigh - AdjLow + 1e-12), factor_name="KUP2"))
    # KLOW: 下影线 = (MIN(收盘价, 开盘价) - 最低价) / 开盘价
    Factors.append(rename((min(AdjClose, AdjOpen) - AdjLow) / AdjOpen, factor_name="KLOW"))
    # KLOW2
    Factors.append(rename((min(AdjClose, AdjOpen) - AdjLow) / (AdjHigh - AdjLow + 1e-12), factor_name="KLOW2"))
    # KSFT
    Factors.append(rename((2 * AdjClose - AdjHigh - AdjLow) / AdjOpen, factor_name="KSFT"))
    # KSFT2
    Factors.append(rename((2 * AdjClose - AdjHigh - AdjLow) / (AdjHigh - AdjLow + 1e-12), factor_name="KSFT2"))


    # 价量回溯类
    for N in [0]:# range(5):
        lagN = fo.Lag(N)
        # OPEN
        Factors.append(rename(lagN(AdjOpen) / AdjClose, factor_name=f"OPEN{N}"))
        # HIGH
        Factors.append(rename(lagN(AdjHigh) / AdjClose, factor_name=f"HIGH{N}"))
        # LOW
        Factors.append(rename(lagN(AdjLow) / AdjClose, factor_name=f"LOW{N}"))
        # VWAP
        Factors.append(rename(lagN(AdjVWAP) / AdjClose, factor_name=f"VWAP{N}"))
        # # CLOSE
        # Factors.append(rename(lagN(AdjClose) / AdjClose, factor_name=f"CLOSE{N}"))
        # # VOLUME
        # Factors.append(rename(lagN(Volume) / Volume, factor_name=f"VOLUME{N}"))


    # 滚动指标类
    for N in [5, 10, 20, 30, 60]:
        lagN = fo.Lag(N)
        rollingMeanN = fo.RollingMean(window=N, min_periods=N)
        rollingStdN = fo.RollingApply(func=np.nanstd, window=N, min_periods=N)
        rollingSumN = fo.RollingApply(func=np.nansum, window=N, min_periods=N)
        rollingCorrN = RollingCorr(window=N, min_periods=N)
        # ROC
        Factors.append(rename(lagN(AdjClose) / AdjClose, factor_name=f"ROC{N}"))
        # MA
        Factors.append(rename(rollingMeanN(AdjClose) / AdjClose, factor_name=f"MA{N}"))
        # STD
        Factors.append(rename(rollingStdN(AdjClose) / AdjClose, factor_name=f"STD{N}"))
        # BETA, RSQR, RESI
        RegN = fo.RollingRegress(window=N, min_periods=N, intercept=True)(AdjClose)
        AlphaN, BetaN = fo.Fetch(pos="alpha")(RegN), fo.Fetch(pos="beta0")(RegN)
        ResiN = AdjClose - AlphaN - BetaN * (N - 1)
        Factors.append(rename(BetaN / AdjClose, factor_name=f"BETA{N}"))
        Factors.append(rename(fo.Fetch(pos="r2")(RegN), factor_name=f"RSQR{N}"))
        Factors.append(rename(ResiN / AdjClose, factor_name=f"RESI{N}"))
        # MAX
        HighN = fo.RollingApply(func=np.nanmax, window=N, min_periods=N)(AdjHigh)
        Factors.append(rename(HighN / AdjClose, factor_name=f"MAX{N}"))
        # MIN
        LowN = fo.RollingApply(func=np.nanmin, window=N, min_periods=N)(AdjLow)
        Factors.append(rename(LowN / AdjClose, factor_name=f"MIN{N}"))
        # QTLU
        Factors.append(rename(fo.RollingApply(func=partial(np.nanquantile, q=0.8), window=N, min_periods=N)(AdjClose) / AdjClose, factor_name=f"QTLU{N}"))
        # QTLD
        Factors.append(rename(fo.RollingApply(func=partial(np.nanquantile, q=0.2), window=N, min_periods=N)(AdjClose) / AdjClose, factor_name=f"QTLD{N}"))
        # RANK
        Factors.append(rename(fo.RollingRank(window=N, min_periods=N)(AdjClose), factor_name=f"RANK{N}"))
        # RSV
        Factors.append(rename((AdjClose - LowN) / (HighN - LowN + 1e-12), factor_name=f"RSV{N}"))
        # IMAX
        IMaxN = fo.RollingApply(func=np.nanargmax, window=N, min_periods=N)(AdjHigh)
        Factors.append(rename(IMaxN / N, factor_name=f"IMAX{N}"))
        # IMIN
        IMinN = fo.RollingApply(func=np.nanargmin, window=N, min_periods=N)(AdjLow)
        Factors.append(rename(IMinN / N, factor_name=f"IMIN{N}"))
        # IMXD
        Factors.append(rename((IMaxN - IMinN) / N, factor_name=f"IMXD{N}"))
        # CORR
        Factors.append(rename(rollingCorrN(AdjClose, log(Volume + 1)), factor_name=f"CORR{N}"))
        # CORD
        Factors.append(rename(rollingCorrN(AdjClose / lag1(AdjClose), log(Volume / lag1(Volume) + 1)), factor_name=f"CORD{N}"))
        # CNTP
        CntPN = rollingMeanN(AdjClose > lag1(AdjClose))
        Factors.append(rename(CntPN, factor_name=f"CNTP{N}"))
        # CNTN
        CntNN = rollingMeanN(AdjClose < lag1(AdjClose))
        Factors.append(rename(CntNN, factor_name=f"CNTN{N}"))
        # CNTD
        Factors.append(rename(CntPN - CntNN, factor_name=f"CNTD{N}"))
        # SUMP
        SumPN = rollingSumN(max(AdjClose - lag1(AdjClose), 0))
        SumN = rollingSumN(abs(AdjClose - lag1(AdjClose)))
        Factors.append(rename(SumPN / (SumN + 1e-12), factor_name=f"SUMP{N}"))
        # SUMN
        SumNN = rollingSumN(max(lag1(AdjClose) - AdjClose, 0))
        Factors.append(rename(SumNN / (SumN + 1e-12), factor_name=f"SUMN{N}"))
        # SUMD
        Factors.append(rename((SumPN - SumNN) / (SumN + 1e-12), factor_name=f"SUMD{N}"))
        # VMA
        Factors.append(rename(rollingMeanN(Volume) / (Volume + 1e-12), factor_name=f"VMA{N}"))
        # VSTD
        Factors.append(rename(rollingStdN(Volume) / (Volume + 1e-12), factor_name=f"VSTD{N}"))
        # WVMA
        RV = abs(AdjClose / lag1(AdjClose) - 1) * Volume
        Factors.append(rename(rollingStdN(RV) / (rollingMeanN(RV) + 1e-12), factor_name=f"WVMA{N}"))
        # VSUMP: Sum(Greater($volume-Ref($volume, 1), 0), %d)/(Sum(Abs($volume-Ref($volume, 1)), %d)+1e-12)
        VSumPN = rollingSumN(max(Volume - lag1(Volume), 0))
        VSumN = rollingSumN(abs(Volume - lag1(Volume)))
        Factors.append(rename(VSumPN / (VSumN + 1e-12), factor_name=f"VSUMP{N}"))
        # VSUMN
        VSumNN = rollingSumN(max(lag1(Volume) - Volume, 0))
        Factors.append(rename(VSumNN / (VSumN + 1e-12), factor_name=f"VSUMN{N}"))
        # VSUMD
        Factors.append(rename((VSumPN - VSumNN) / (VSumN + 1e-12), factor_name=f"VSUMD{N}"))

    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_factor_qlib_alpha158",
        IDType="A股",
        MaxLookBack=365,
        Author="麦冬",
        Description="QLib Alpha 158 因子集, 全部为量价类因子",
        DefScriptPath=__file__
    )
