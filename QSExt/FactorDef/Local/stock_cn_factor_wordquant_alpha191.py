# coding: utf-8
"""短周期价量因子"""

# 参考文献：国泰君安-数量化专题之九十三：基于短周期价量特征的多因子选股体系

import os
import datetime as dt

import numpy as np
import pandas as pd
from scipy import stats

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# 辅助算子
RANK = lambda A: fd.standardizeRank(A, mask=IfTrading, ascending=True, uniformization=False)
MAX = lambda A, B: fd.nanmax(A, B)
MIN = lambda A, B: fd.nanmin(A, B)
STD = lambda A, n: fd.rolling_std(A, window=n, min_periods=n, ddof=1)
CORR = lambda A, B, n: fd.rolling_corr(A, B, window=n, min_periods=n, method="pearson")
COV = lambda A, B, n: fd.rolling_cov(A, B, window=n, min_periods=n, ddof=1)
DELTA = lambda A, n: A - fd.lag(A, lag_period=n, window=n)
LOG = lambda A: fd.log(A, base=np.e)
SUM = lambda A, n: fd.rolling_sum(A, window=n, min_periods=n)
ABS = lambda A: abs(A)
MEAN = lambda A, n: fd.rolling_mean(A, window=n, min_periods=n)
TSRANK = lambda A, n: fd.rolling_rank(A, window=n, min_periods=n)
SIGN = lambda A: fd.sign(A)
DELAY = lambda A, n: fd.lag(A, lag_period=n, window=n)
TSMIN = lambda A, n: fd.rolling_min(A, window=n, min_periods=n)
TSMAX = lambda A, n: fd.rolling_max(A, window=n, min_periods=n)
PROD = lambda A, n: fd.rolling_prod(A, window=n, min_periods=n)
COUNT = lambda condition, n: fd.rolling_sum(condition, window=n, min_periods=n)
REGBETA = lambda A, B, n: fd.fetch(fd.rolling_regress(A, B, window=n, constant=True, half_life=np.inf), pos=1, dtype="double")
SUMIF = lambda A, n, condition: fd.rolling_sum(A * condition, window=n, min_periods=n)
IF = lambda condition, B, C: fd.where(B, condition, C)
def _SMA(f, idt, iid, x, args):
    w = args["m"] / args["n"]
    T = x[0].shape[0]
    return np.nansum((w * (1 - w) ** np.arange(T))[::-1] * x[0].T, axis=1)
SMA = lambda A, n, m: QS.FactorDB.TimeOperation(A.Name, [A], sys_args={"算子": _SMA, "参数": {"n":n,"m":m}, "回溯期数": [3*n], "运算时点": "单时点", "运算ID": "多ID"})
REGCHG = lambda A, n: fd.rolling_regress_change(A, window=n, min_periods=n)
DECAYLINEAR = lambda A, d: fd.rolling_mean(A, window=d, min_periods=d, weights=np.arange(1, d+1))
WMA = lambda A, n: fd.rolling_mean(A, window=n, min_periods=n, weights=(0.9**np.arange(n))[::-1])
FILTER = lambda A, condition: fd.where(A, condition, np.nan)
HIGHDAY = lambda A, n: n - 1 - fd.rolling_argmax(A, window=n, min_periods=n)
LOWDAY = lambda A, n: n - 1 - fd.rolling_argmin(A, window=n, min_periods=n)
def _MAX_SUMAC(x): return np.nanmax(np.nancumsum(x - np.nanmean(x)))
MAX_SUMAC = lambda A, n: fd.rolling_apply(A, func=_MAX_SUMAC, window=n, min_periods=n, raw=True)
def _MIN_SUMAC(x): return np.nanmin(np.nancumsum(x - np.nanmean(x)))
MIN_SUMAC = lambda A, n: fd.rolling_apply(A, func=_MIN_SUMAC, window=n, min_periods=n, raw=True)


def defFactor(args={}):
    Factors = []
    LDB = args["LDB"]

    # 基础价量因子
    FT = LDB.getTable("stock_cn_quote_adj_no_nafilled")
    PRECLOSE = FT.getFactor("pre_close")
    OPEN = FT.getFactor("open")
    HIGH = FT.getFactor("high")
    LOW = FT.getFactor("low")
    CLOSE = FT.getFactor("close")
    VOLUME = FT.getFactor("volume")
    AMOUNT = FT.getFactor("amount")
    RET = FT.getFactor("chg")
    VWAP = AMOUNT / VOLUME
    IfTrading = (FT.getFactor("if_trading")==1)
    
    FT = LDB.getTable("index_cn_quote")
    BENCHMARKINDEXCLOSE = fd.disaggregate(FT.getFactor("close"), aggr_ids=["000300.SH"], disaggr_ids=None)
    BENCHMARKINDEXOPEN = fd.disaggregate(FT.getFactor("open"), aggr_ids=["000300.SH"], disaggr_ids=None)

    # 辅助因子
    MID = (HIGH + LOW) / 2
    PREHIGH = DELAY(HIGH, 1)
    PRELOW = DELAY(LOW, 1)
    PREOPEN = DELAY(OPEN, 1)
    PREMID = DELAY(MID, 1)
    DTM = IF(OPEN<=PREOPEN, 0, MAX(HIGH - OPEN, OPEN - PREOPEN))
    DBM = IF(OPEN>=PREOPEN, 0, MAX(OPEN - LOW, OPEN - PREOPEN))
    TR = MAX(MAX(HIGH - LOW, ABS(HIGH - PRECLOSE)), ABS(LOW - PRECLOSE))
    HD = HIGH - PREHIGH
    LD = PRELOW - LOW
    PRECLOSE5 = DELAY(CLOSE, 5)
    PRECLOSE6 = DELAY(CLOSE, 6)


    # 价量因子
    alpha1 = - CORR(RANK(DELTA(LOG(VOLUME), 1)), RANK((CLOSE - OPEN) / OPEN), 6)
    Factors.append(Factorize(alpha1, factor_name="alpha1"))
    
    alpha2 = - DELTA(((CLOSE - LOW) - (HIGH - CLOSE)) / (HIGH - LOW), 1)
    Factors.append(Factorize(alpha2, factor_name="alpha2"))
    
    alpha3 = SUM(IF(CLOSE==PRECLOSE, 0, CLOSE - IF(CLOSE>PRECLOSE, MIN(LOW, PRECLOSE), MAX(HIGH, PRECLOSE))), 6)
    Factors.append(Factorize(alpha3, factor_name="alpha3"))
    
    alpha4 = IF(SUM(CLOSE, 8) / 8 + STD(CLOSE, 8) < SUM(CLOSE, 2) / 2, -1, IF(SUM(CLOSE, 2) / 2 < SUM(CLOSE, 8) / 8 - STD(CLOSE, 8), 1, IF((VOLUME / MEAN(VOLUME, 20) >= 1), 1, -1)))
    Factors.append(Factorize(alpha4, factor_name="alpha4"))
    
    alpha5 = - TSMAX(CORR(TSRANK(VOLUME, 5), TSRANK(HIGH, 5), 5), 3)
    Factors.append(Factorize(alpha5, factor_name="alpha5"))
    
    alpha6 = - RANK(SIGN(DELTA(0.85 * OPEN + 0.15 * HIGH, 4)))
    Factors.append(Factorize(alpha6, factor_name="alpha6"))
    
    alpha7 = (RANK(TSMAX(VWAP - CLOSE, 3)) + RANK(TSMIN(VWAP - CLOSE, 3))) * RANK(DELTA(VOLUME, 3))
    Factors.append(Factorize(alpha7, factor_name="alpha7"))
    
    alpha8 = - RANK(DELTA(MID * 0.2 + VWAP * 0.8, 4))
    Factors.append(Factorize(alpha8, factor_name="alpha8"))
    
    alpha9 = SMA((MID - PREMID) * (HIGH - LOW) / VOLUME, 7, 2)
    Factors.append(Factorize(alpha9, factor_name="alpha9"))
    
    alpha10 = RANK(MAX(IF(RET<0, STD(RET, 20), CLOSE) ** 2, 5))# TOCHECK
    Factors.append(Factorize(alpha10, factor_name="alpha10"))
    
    alpha11 = SUM(((CLOSE - LOW) - (HIGH - CLOSE)) / (HIGH - LOW) * VOLUME, 6)
    Factors.append(Factorize(alpha11, factor_name="alpha11"))
    
    alpha12 = - RANK(OPEN - (SUM(VWAP, 10) / 10)) * RANK(ABS(CLOSE - VWAP))
    Factors.append(Factorize(alpha12, factor_name="alpha12"))
    
    alpha13 = (HIGH * LOW) ** 0.5 - VWAP
    Factors.append(Factorize(alpha13, factor_name="alpha13"))
    
    alpha14 = CLOSE - PRECLOSE5
    Factors.append(Factorize(alpha14, factor_name="alpha14"))
    
    alpha15 = OPEN / PRECLOSE - 1
    Factors.append(Factorize(alpha15, factor_name="alpha15"))
    
    alpha16 = - TSMAX(RANK(CORR(RANK(VOLUME), RANK(VWAP), 5)), 5)
    Factors.append(Factorize(alpha16, factor_name="alpha16"))
    
    alpha17 = RANK(VWAP - MAX(VWAP, 15)) ** DELTA(CLOSE, 5)# TOCHECK
    Factors.append(Factorize(alpha17, factor_name="alpha17"))
    
    alpha18 = CLOSE / PRECLOSE5
    Factors.append(Factorize(alpha18, factor_name="alpha18"))
    
    alpha19 = IF(CLOSE<PRECLOSE5, (CLOSE - PRECLOSE5) / PRECLOSE5, IF(CLOSE==PRECLOSE5, 0, (CLOSE - PRECLOSE5) / CLOSE))
    Factors.append(Factorize(alpha19, factor_name="alpha19"))
    
    alpha20 = (CLOSE / PRECLOSE6 - 1) * 100
    Factors.append(Factorize(alpha20, factor_name="alpha20"))
    
    alpha21 = REGCHG(MEAN(CLOSE, 6), 6)
    Factors.append(Factorize(alpha21, factor_name="alpha21"))
    
    TEMP = CLOSE / MEAN(CLOSE, 6) - 1
    alpha22 = SMA(TEMP - DELAY(TEMP, 3), 12, 1)# TOCHECK
    Factors.append(Factorize(alpha22, factor_name="alpha22"))
    
    TEMP = SMA(IF(CLOSE>PRECLOSE, STD(CLOSE, 20), 0), 20, 1)
    alpha23 = TEMP / (TEMP + SMA(IF(CLOSE<=PRECLOSE, STD(CLOSE, 20), 0), 20, 1)) * 100
    Factors.append(Factorize(alpha23, factor_name="alpha23"))
    
    alpha24 = SMA(CLOSE - PRECLOSE5, 5, 1)
    Factors.append(Factorize(alpha24, factor_name="alpha24"))
    
    alpha25 = - RANK(DELTA(CLOSE, 7) * (1 - RANK(DECAYLINEAR(VOLUME / MEAN(VOLUME, 20), 9)))) * (1 + RANK(SUM(RET, 250)))
    Factors.append(Factorize(alpha25, factor_name="alpha25"))
    
    alpha26 = SUM(CLOSE, 7) / 7 - CLOSE + CORR(VWAP, PRECLOSE5, 230)# TOCHECK
    Factors.append(Factorize(alpha26, factor_name="alpha26"))
    
    alpha27 = WMA((CLOSE / DELAY(CLOSE, 3) - 1) * 100 + (CLOSE / DELAY(CLOSE,6) - 1) * 100, 12)
    Factors.append(Factorize(alpha27, factor_name="alpha27"))
    
    TEMP = TSMIN(LOW, 9)
    alpha28 = 3 * SMA((CLOSE - TEMP) / (TSMAX(HIGH, 9) - TEMP) * 100, 3, 1) - 2 * SMA(SMA((CLOSE - TEMP) / (TSMAX(HIGH, 9) - TSMAX(LOW, 9)) * 100, 3, 1), 3, 1)
    Factors.append(Factorize(alpha28, factor_name="alpha28"))
    
    alpha29 = (CLOSE / PRECLOSE6 - 1) * VOLUME
    Factors.append(Factorize(alpha29, factor_name="alpha29"))
    
    # TODEF
    #alpha30 = WMA((REGRESI(CLOSE / PRECLOSE-1, MKT, SMB, HML, 60)) ** 2, 20)
    #Factors.append(Factorize(alpha30, factor_name="alpha30"))
    
    alpha31 = (CLOSE / MEAN(CLOSE, 12) - 1) * 100
    Factors.append(Factorize(alpha31, factor_name="alpha31"))
    
    alpha32 = - SUM(RANK(CORR(RANK(HIGH), RANK(VOLUME), 3)), 3)
    Factors.append(Factorize(alpha32, factor_name="alpha32"))
    
    TEMP = TSMIN(LOW, 5)
    alpha33 = (- TEMP + DELAY(TEMP, 5)) * RANK((SUM(RET, 240) - SUM(RET, 20)) / 220) * TSRANK(VOLUME, 5)
    Factors.append(Factorize(alpha33, factor_name="alpha33"))
    
    alpha34 = MEAN(CLOSE, 12) / CLOSE
    Factors.append(Factorize(alpha34, factor_name="alpha34"))
    
    alpha35 = - MIN(RANK(DECAYLINEAR(DELTA(OPEN, 1), 15)), RANK(DECAYLINEAR(CORR(VOLUME, OPEN * 0.65 + OPEN *0.35, 17), 7)))
    Factors.append(Factorize(alpha35, factor_name="alpha35"))
    
    alpha36 = RANK(SUM(CORR(RANK(VOLUME), RANK(VWAP), 6), 2))
    Factors.append(Factorize(alpha36, factor_name="alpha36"))
    
    TEMP = SUM(OPEN, 5) * SUM(RET, 5)
    alpha37 = - RANK(TEMP - DELAY(TEMP, 10))
    Factors.append(Factorize(alpha37, factor_name="alpha37"))
    
    alpha38 = IF(SUM(HIGH, 20) / 20 < HIGH, - DELTA(HIGH, 2), 0)
    Factors.append(Factorize(alpha38, factor_name="alpha38"))
    
    alpha39 = - (RANK(DECAYLINEAR(DELTA(CLOSE, 2), 8)) - RANK(DECAYLINEAR(CORR(VWAP * 0.3 + OPEN * 0.7, SUM(MEAN(VOLUME, 180), 37), 14), 12)))
    Factors.append(Factorize(alpha39, factor_name="alpha39"))
    
    alpha40 = SUM(IF(CLOSE > PRECLOSE, VOLUME, 0), 26) / SUM(IF(CLOSE<=PRECLOSE, VOLUME, 0), 26) * 100
    Factors.append(Factorize(alpha40, factor_name="alpha40"))
    
    alpha41 = - RANK(MAX(DELTA(VWAP, 3), 5))
    Factors.append(Factorize(alpha41, factor_name="alpha41"))
    
    alpha42 = - RANK(STD(HIGH, 10)) * CORR(HIGH, VOLUME, 10)
    Factors.append(Factorize(alpha42, factor_name="alpha42"))
    
    alpha43 = SUM(IF(CLOSE>PRECLOSE, VOLUME, IF(CLOSE<PRECLOSE, - VOLUME, 0)), 6)
    Factors.append(Factorize(alpha43, factor_name="alpha43"))
    
    alpha44 = TSRANK(DECAYLINEAR(CORR(LOW, MEAN(VOLUME, 10), 7), 6), 4) + TSRANK(DECAYLINEAR(DELTA(VWAP, 3), 10), 15)
    Factors.append(Factorize(alpha44, factor_name="alpha44"))
    
    alpha45 = RANK(DELTA(CLOSE * 0.6 + OPEN * 0.4, 1)) * RANK(CORR(VWAP, MEAN(VOLUME, 150), 15))
    Factors.append(Factorize(alpha45, factor_name="alpha45"))
    
    alpha46 = (MEAN(CLOSE, 3) + MEAN(CLOSE, 6) + MEAN(CLOSE, 12) + MEAN(CLOSE, 24)) / (4 * CLOSE)
    Factors.append(Factorize(alpha46, factor_name="alpha46"))
    
    TEMP = TSMAX(HIGH, 6)
    alpha47 = SMA((TEMP - CLOSE) / (TEMP - TSMIN(LOW, 6)) * 100, 9, 1)
    Factors.append(Factorize(alpha47, factor_name="alpha47"))
    
    TEMP = DELAY(CLOSE, 2)
    alpha48 = - RANK(SIGN(CLOSE - PRECLOSE) + SIGN(PRECLOSE - TEMP) + SIGN(TEMP - DELAY(CLOSE, 3))) * SUM(VOLUME, 5) / SUM(VOLUME, 20)
    Factors.append(Factorize(alpha48, factor_name="alpha48"))
    
    TEMP = MAX(ABS(HIGH - PREHIGH), ABS(LOW - PRELOW))
    TEMP1 = SUM(IF(HIGH + LOW >= PREHIGH + PRELOW, 0, TEMP), 12)
    TEMP2 = SUM(IF(HIGH + LOW <= PREHIGH + PRELOW, 0, TEMP), 12)
    alpha49 = TEMP1 / (TEMP1 + TEMP2)
    Factors.append(Factorize(alpha49, factor_name="alpha49"))
    
    alpha50 = (TEMP2 - TEMP1) / (TEMP2 + TEMP1)
    Factors.append(Factorize(alpha50, factor_name="alpha50"))
    
    alpha51 = TEMP2 / (TEMP1 + TEMP2)
    Factors.append(Factorize(alpha51, factor_name="alpha51"))
    
    TEMP = DELAY((HIGH + LOW + CLOSE) / 3, 1)
    alpha52 = SUM(MAX(0, HIGH - TEMP), 26) / SUM(MAX(0, TEMP - LOW), 26) * 100
    Factors.append(Factorize(alpha52, factor_name="alpha52"))
    
    alpha53 = COUNT(CLOSE > PRECLOSE, 12) / 12 * 100
    Factors.append(Factorize(alpha53, factor_name="alpha53"))
    
    alpha54 = - RANK(STD(ABS(CLOSE - OPEN), 10) + (CLOSE - OPEN) + CORR(CLOSE, OPEN, 10))
    Factors.append(Factorize(alpha54, factor_name="alpha54"))
    
    TEMP1 = ABS(HIGH - PRECLOSE)
    TEMP2 = ABS(LOW - PRECLOSE)
    TEMP3 = ABS(HIGH - PRELOW)
    TEMP4 = ABS(PRECLOSE - PREOPEN)
    MASK1 = ((TEMP1 > TEMP2) & (TEMP1 > TEMP3))
    MASK2 = ((TEMP2 > TEMP3) & (TEMP2 > TEMP1))
    alpha55 = SUM(16 * (CLOSE - PRECLOSE + (CLOSE - OPEN) / 2 + PRECLOSE - PREOPEN) / IF(MASK1, TEMP1 + TEMP2 / 2 + TEMP4 / 4, IF(MASK2, TEMP2 + TEMP1 / 2 + TEMP4 / 4, TEMP3 + TEMP4 / 4)) * MAX(TEMP1, TEMP2), 20)
    Factors.append(Factorize(alpha55, factor_name="alpha55"))
    
    alpha56 = (RANK(OPEN - TSMIN(OPEN, 12)) < RANK(RANK(CORR(SUM(MID, 19), SUM(MEAN(VOLUME, 40), 19), 13)) ** 5))
    Factors.append(Factorize(alpha56, factor_name="alpha56"))
    
    TEMP = TSMIN(LOW, 9)
    alpha57 = SMA((CLOSE - TEMP) / (TSMAX(HIGH, 9) - TEMP) * 100, 3, 1)
    Factors.append(Factorize(alpha57, factor_name="alpha57"))
    
    alpha58 = COUNT(CLOSE > PRECLOSE, 20) / 20 * 100
    Factors.append(Factorize(alpha58, factor_name="alpha58"))
    
    alpha59 = SUM(IF(CLOSE == PRECLOSE, 0, CLOSE - IF(CLOSE > PRECLOSE, MIN(LOW, PRECLOSE), MAX(HIGH, PRECLOSE))), 20)
    Factors.append(Factorize(alpha59, factor_name="alpha59"))
    
    alpha60 = SUM(((CLOSE - LOW) - (HIGH - CLOSE)) / (HIGH - LOW) * VOLUME, 20)
    Factors.append(Factorize(alpha60, factor_name="alpha60"))
    
    alpha61 = - MAX(RANK(DECAYLINEAR(DELTA(VWAP, 1), 12)), RANK(DECAYLINEAR(RANK(CORR(LOW, MEAN(VOLUME, 80), 8)), 17)))
    Factors.append(Factorize(alpha61, factor_name="alpha61"))
    
    alpha62 = - CORR(HIGH, RANK(VOLUME), 5)
    Factors.append(Factorize(alpha62, factor_name="alpha62"))
    
    alpha63 = SMA(MAX(CLOSE - PRECLOSE, 0), 6, 1) / SMA(ABS(CLOSE - PRECLOSE), 6, 1) * 100
    Factors.append(Factorize(alpha63, factor_name="alpha63"))
    
    alpha64 = - MAX(RANK(DECAYLINEAR(CORR(RANK(VWAP), RANK(VOLUME), 4), 4)), RANK(DECAYLINEAR(MAX(CORR(RANK(CLOSE), RANK(MEAN(VOLUME, 60)), 4), 13), 14)))
    Factors.append(Factorize(alpha64, factor_name="alpha64"))
    
    TEMP = MEAN(CLOSE, 6)
    alpha65 = TEMP / CLOSE
    Factors.append(Factorize(alpha65, factor_name="alpha65"))
    
    alpha66 = (CLOSE - TEMP) / TEMP * 100
    Factors.append(Factorize(alpha66, factor_name="alpha66"))
    
    alpha67 = SMA(MAX(CLOSE - PRECLOSE, 0), 24, 1) / SMA(ABS(CLOSE - PRECLOSE), 24, 1) * 100
    Factors.append(Factorize(alpha67, factor_name="alpha67"))
    
    alpha68 = SMA((MID - PREMID) * (HIGH - LOW) / VOLUME, 15, 2)
    Factors.append(Factorize(alpha68, factor_name="alpha68"))
    
    TEMP1 = SUM(DTM, 20)
    TEMP2 = SUM(DBM, 20)
    alpha69 = IF(TEMP1 > TEMP2, (TEMP1 - TEMP2) / TEMP1, IF(TEMP1 == TEMP2, 0, (TEMP1 - TEMP2) / TEMP2))
    Factors.append(Factorize(alpha69, factor_name="alpha69"))
    
    alpha70 = STD(AMOUNT, 6)
    Factors.append(Factorize(alpha70, factor_name="alpha70"))
    
    alpha71 = (CLOSE / MEAN(CLOSE, 24) - 1) * 100
    Factors.append(Factorize(alpha71, factor_name="alpha71"))
    
    TEMP = TSMAX(HIGH, 6)
    alpha72 = SMA((TEMP - CLOSE) / (TEMP - TSMIN(LOW, 6)) * 100, 15, 1)
    Factors.append(Factorize(alpha72, factor_name="alpha72"))
    
    alpha73 = - (TSRANK(DECAYLINEAR(DECAYLINEAR(CORR(CLOSE, VOLUME, 10), 16), 4), 5) - RANK(DECAYLINEAR(CORR(VWAP, MEAN(VOLUME, 30), 4), 3)))
    Factors.append(Factorize(alpha73, factor_name="alpha73"))
    
    alpha74 = RANK(CORR(SUM(LOW * 0.35 + VWAP * 0.65, 20), SUM(MEAN(VOLUME, 40), 20), 7)) + RANK(CORR(RANK(VWAP), RANK(VOLUME), 6))
    Factors.append(Factorize(alpha74, factor_name="alpha74"))
    
    alpha75 = COUNT((CLOSE > OPEN) & (BENCHMARKINDEXCLOSE < BENCHMARKINDEXOPEN), 50) / COUNT(BENCHMARKINDEXCLOSE < BENCHMARKINDEXOPEN, 50)
    Factors.append(Factorize(alpha75, factor_name="alpha75"))
    
    alpha76 = STD(ABS(CLOSE / PRECLOSE - 1) / VOLUME, 20) / MEAN(ABS(CLOSE / PRECLOSE - 1) / VOLUME, 20)
    Factors.append(Factorize(alpha76, factor_name="alpha76"))
    
    alpha77 = MIN(RANK(DECAYLINEAR(MID - VWAP, 20)), RANK(DECAYLINEAR(CORR(MID, MEAN(VOLUME, 40), 3), 6)))
    Factors.append(Factorize(alpha77, factor_name="alpha77"))
    
    TEMP = (HIGH + LOW + CLOSE) / 3
    alpha78 = (TEMP - MEAN(TEMP, 12)) / (0.015 * MEAN(ABS(CLOSE - TEMP), 12), 12)
    Factors.append(Factorize(alpha78, factor_name="alpha78"))
    
    alpha79 = SMA(MAX(CLOSE - PRECLOSE, 0), 12, 1) / SMA(ABS(CLOSE - PRECLOSE), 12, 1) * 100
    Factors.append(Factorize(alpha79, factor_name="alpha79"))
    
    alpha80 = (VOLUME / DELAY(VOLUME, 5) - 1) * 100
    Factors.append(Factorize(alpha80, factor_name="alpha80"))
    
    alpha81 = SMA(VOLUME, 21, 2)
    Factors.append(Factorize(alpha81, factor_name="alpha81"))
    
    alpha82 = SMA((TSMAX(HIGH, 6) - CLOSE) / (TSMAX(HIGH, 6) - TSMIN(LOW, 6)) * 100, 20, 1)
    Factors.append(Factorize(alpha82, factor_name="alpha82"))
    
    alpha83 = - RANK(COV(RANK(HIGH), RANK(VOLUME), 5))
    Factors.append(Factorize(alpha83, factor_name="alpha83"))
    
    alpha84 = SUM(IF(CLOSE > PRECLOSE, VOLUME, IF(CLOSE < PRECLOSE, -VOLUME, 0)), 20)
    Factors.append(Factorize(alpha84, factor_name="alpha84"))
    
    alpha85 = TSRANK(VOLUME / MEAN(VOLUME, 20), 20) * TSRANK(- DELTA(CLOSE, 7), 8)
    Factors.append(Factorize(alpha85, factor_name="alpha85"))
    
    TEMP1 = DELAY(CLOSE, 10)
    TEMP2 = DELAY(CLOSE, 20)
    TEMP = (TEMP2 - TEMP1) / 10 - (TEMP1 - CLOSE) / 10
    alpha86 = IF(TEMP > 0.25, -1, IF(TEMP < 0, 1, - (CLOSE - PRECLOSE)))
    Factors.append(Factorize(alpha86, factor_name="alpha86"))
    
    # TOCHECK
    alpha87 = - (RANK(DECAYLINEAR(DELTA(VWAP, 4), 7)) + TSRANK(DECAYLINEAR((LOW - VWAP) / (OPEN - MID), 11), 7))
    Factors.append(Factorize(alpha87, factor_name="alpha87"))
    
    alpha88 = (CLOSE / DELAY(CLOSE, 20) - 1) * 100
    Factors.append(Factorize(alpha88, factor_name="alpha88"))
    
    TEMP = SMA(CLOSE, 13, 2) - SMA(CLOSE, 27, 2)
    alpha89 = 2 * (TEMP - SMA(TEMP, 10, 2))
    Factors.append(Factorize(alpha89, factor_name="alpha89"))
    
    alpha90 = - RANK(CORR(RANK(VWAP), RANK(VOLUME), 5))
    Factors.append(Factorize(alpha90, factor_name="alpha90"))
    
    # TOCHECK
    alpha91 = - RANK(CLOSE - MAX(CLOSE, 5)) * RANK(CORR(MEAN(VOLUME, 40), LOW, 5))
    Factors.append(Factorize(alpha91, factor_name="alpha91"))
    
    alpha92 = - MAX(RANK(DECAYLINEAR(DELTA(CLOSE * 0.35 + VWAP * 0.65, 2), 3)), TSRANK(DECAYLINEAR(ABS(CORR(MEAN(VOLUME, 180), CLOSE, 13)), 5), 15))
    Factors.append(Factorize(alpha92, factor_name="alpha92"))
    
    alpha93 = SUM(IF(OPEN >= PREOPEN, 0, MAX(OPEN - LOW, OPEN - PREOPEN)), 20)
    Factors.append(Factorize(alpha93, factor_name="alpha93"))
    
    alpha94 = SUM(IF(CLOSE > PRECLOSE, VOLUME, IF(CLOSE < PRECLOSE, -VOLUME, 0)), 30)
    Factors.append(Factorize(alpha94, factor_name="alpha94"))
    
    alpha95 = STD(AMOUNT, 20)
    Factors.append(Factorize(alpha95, factor_name="alpha95"))
    
    TEMP = TSMIN(LOW, 9)
    alpha96 = SMA(SMA((CLOSE - TEMP) / (TSMAX(HIGH, 9) - TEMP) * 100, 3, 1), 3, 1)
    Factors.append(Factorize(alpha96, factor_name="alpha96"))
    
    alpha97 = STD(VOLUME, 10)
    Factors.append(Factorize(alpha97, factor_name="alpha97"))
    
    alpha98 = IF(DELTA(MEAN(CLOSE, 100), 100) / DELAY(CLOSE, 100) <= 0.05, -(CLOSE - TSMIN(CLOSE, 100)), -DELTA(CLOSE, 3))
    Factors.append(Factorize(alpha98, factor_name="alpha98"))
    
    alpha99 = - RANK(COV(RANK(CLOSE), RANK(VOLUME), 5))
    Factors.append(Factorize(alpha99, factor_name="alpha99"))
    
    alpha100 = STD(VOLUME, 20)
    Factors.append(Factorize(alpha100, factor_name="alpha100"))
    
    alpha101 = - (RANK(CORR(CLOSE, SUM(MEAN(VOLUME, 30), 37), 15)) < RANK(CORR(RANK(HIGH * 0.1 + VWAP * 0.9), RANK(VOLUME), 11)))
    Factors.append(Factorize(alpha101, factor_name="alpha101"))
    
    TEMP = DELAY(VOLUME, 1)
    alpha102 = SMA(MAX(VOLUME - TEMP, 0), 6, 1) / SMA(ABS(VOLUME - TEMP), 6, 1) * 100
    Factors.append(Factorize(alpha102, factor_name="alpha102"))
    
    alpha103 = (20 - LOWDAY(LOW, 20)) / 20 * 100
    Factors.append(Factorize(alpha103, factor_name="alpha103"))
    
    alpha104 = - DELTA(CORR(HIGH, VOLUME, 5), 5) * RANK(STD(CLOSE, 20))
    Factors.append(Factorize(alpha104, factor_name="alpha104"))
    
    alpha105 = - CORR(RANK(OPEN), RANK(VOLUME), 10)
    Factors.append(Factorize(alpha105, factor_name="alpha105"))
    
    alpha106 = CLOSE - DELAY(CLOSE, 20)
    Factors.append(Factorize(alpha106, factor_name="alpha106"))
    
    alpha107 = - RANK(OPEN - PREHIGH) * RANK(OPEN - PRECLOSE) * RANK(OPEN - PRELOW)
    Factors.append(Factorize(alpha107, factor_name="alpha107"))
    
    alpha108 = - RANK(HIGH - MIN(HIGH, 2)) ** RANK(CORR(VWAP, MEAN(VOLUME, 120), 6))
    Factors.append(Factorize(alpha108, factor_name="alpha108"))
    
    TEMP = SMA(HIGH - LOW, 10, 2)
    alpha109 = TEMP / SMA(TEMP, 10, 2)
    Factors.append(Factorize(alpha109, factor_name="alpha109"))
    
    alpha110 = SUM(MAX(0, HIGH - PRECLOSE), 20) / SUM(MAX(0, PRECLOSE - LOW), 20) * 100
    Factors.append(Factorize(alpha110, factor_name="alpha110"))
    
    alpha111 = SMA(VOLUME * ((CLOSE - LOW) - (HIGH - CLOSE)) / (HIGH - LOW), 11, 2) - SMA(VOLUME * ((CLOSE - LOW) - (HIGH - CLOSE)) / (HIGH - LOW), 4, 2)
    Factors.append(Factorize(alpha111, factor_name="alpha111"))
    
    TEMP1 = SUM(MAX(CLOSE - PRECLOSE, 0), 12)
    TEMP2 = SUM(-MIN(CLOSE - PRECLOSE, 0), 12)
    alpha112 = (TEMP1 - TEMP2) / (TEMP1 + TEMP2) * 100
    Factors.append(Factorize(alpha112, factor_name="alpha112"))
    
    alpha113 = - RANK(MEAN(PRECLOSE5, 20)) * CORR(CLOSE, VOLUME, 2) * RANK(CORR(SUM(CLOSE, 5), SUM(CLOSE, 20), 2))
    Factors.append(Factorize(alpha113, factor_name="alpha113"))
    
    # TOCHECK
    alpha114 = RANK(DELAY((HIGH - LOW) / MEAN(CLOSE, 5), 2) * RANK(RANK(VOLUME))) / ((HIGH - LOW) / MEAN(CLOSE, 5) / (VWAP - CLOSE))
    Factors.append(Factorize(alpha114, factor_name="alpha114"))
    
    alpha115 = RANK(CORR(HIGH * 0.9 + CLOSE * 0.1, MEAN(VOLUME, 30), 10)) ** RANK(CORR(TSRANK(MID, 4), TSRANK(VOLUME, 10), 7))
    Factors.append(Factorize(alpha115, factor_name="alpha115"))
    
    alpha116 = REGCHG(CLOSE, 20)
    Factors.append(Factorize(alpha116, factor_name="alpha116"))
    
    alpha117 = TSRANK(VOLUME, 32) * (1 - TSRANK(CLOSE + HIGH - LOW, 16)) * (1 - TSRANK(RET, 32))
    Factors.append(Factorize(alpha117, factor_name="alpha117"))
    
    alpha118 = SUM(HIGH - OPEN, 20) / SUM(OPEN - LOW, 20) * 100
    Factors.append(Factorize(alpha118, factor_name="alpha118"))
    
    # TOCHECK
    alpha119 = RANK(DECAYLINEAR(CORR(VWAP, SUM(MEAN(VOLUME, 5), 26), 5), 7)) - RANK(DECAYLINEAR(TSRANK(MIN(CORR(RANK(OPEN), RANK(MEAN(VOLUME, 15)), 21), 9), 7), 8))
    Factors.append(Factorize(alpha119, factor_name="alpha119"))
    
    alpha120 = RANK(VWAP - CLOSE) / RANK(VWAP + CLOSE)
    Factors.append(Factorize(alpha120, factor_name="alpha120"))
    
    alpha121 = - RANK(VWAP - MIN(VWAP, 12)) ** TSRANK(CORR(TSRANK(VWAP, 20), TSRANK(MEAN(VOLUME, 60), 2), 18), 3)
    Factors.append(Factorize(alpha121, factor_name="alpha121"))
    
    TEMP = SMA(SMA(SMA(LOG(CLOSE), 13, 2), 13, 2), 13, 2)
    alpha122 = TEMP / DELAY(TEMP, 1) - 1
    Factors.append(Factorize(alpha122, factor_name="alpha122"))
    
    alpha123 = - (RANK(CORR(SUM(MID, 20), SUM(MEAN(VOLUME, 60), 20), 9)) < RANK(CORR(LOW, VOLUME, 6)))
    Factors.append(Factorize(alpha123, factor_name="alpha123"))
    
    alpha124 = (CLOSE - VWAP) / DECAYLINEAR(RANK(TSMAX(CLOSE, 30)), 2)
    Factors.append(Factorize(alpha124, factor_name="alpha124"))
    
    alpha125 = RANK(DECAYLINEAR(CORR(VWAP, MEAN(VOLUME, 80), 17), 20)) / RANK(DECAYLINEAR(DELTA(CLOSE * 0.5 + VWAP * 0.5, 3), 16))
    Factors.append(Factorize(alpha125, factor_name="alpha125"))
    
    alpha126 = (CLOSE + HIGH + LOW) / 3
    Factors.append(Factorize(alpha126, factor_name="alpha126"))
    
    alpha127 = MEAN((100 * (CLOSE / MAX(CLOSE, 12) - 1)) ** 2) ** (1/2)
    Factors.append(Factorize(alpha127, factor_name="alpha127"))
    
    TEMP = (CLOSE + HIGH + LOW) / 3
    TEMP1 = DELAY(TEMP, 1)
    alpha128 = 100 - (100 / (1 + SUM(IF(TEMP > TEMP1, TEMP * VOLUME, 0), 14) / SUM(IF(TEMP < TEMP1, TEMP * VOLUME, 0), 14)))
    Factors.append(Factorize(alpha128, factor_name="alpha128"))
    
    alpha129 = SUM(-MIN(CLOSE - PRECLOSE, 0), 12)
    Factors.append(Factorize(alpha129, factor_name="alpha129"))
    
    alpha130 = RANK(DECAYLINEAR(CORR(MID, MEAN(VOLUME, 40), 9), 10)) / RANK(DECAYLINEAR(CORR(RANK(VWAP), RANK(VOLUME), 7),3))
    Factors.append(Factorize(alpha130, factor_name="alpha130"))
    
    alpha131 = RANK(DELTA(VWAP, 1)) ** TSRANK(CORR(CLOSE, MEAN(VOLUME, 50), 18), 18)
    Factors.append(Factorize(alpha131, factor_name="alpha131"))
    
    alpha132 = MEAN(AMOUNT, 20)
    Factors.append(Factorize(alpha132, factor_name="alpha132"))
    
    alpha133 = (20 - HIGHDAY(HIGH, 20)) / 20 * 100 - (20 - LOWDAY(LOW, 20)) / 20 * 100
    Factors.append(Factorize(alpha133, factor_name="alpha133"))
    
    alpha134 = (CLOSE / DELAY(CLOSE, 12) - 1) * VOLUME
    Factors.append(Factorize(alpha134, factor_name="alpha134"))
    
    alpha135 = SMA(DELAY(CLOSE / DELAY(CLOSE, 20), 1), 20, 1)
    Factors.append(Factorize(alpha135, factor_name="alpha135"))
    
    alpha136 = - RANK(DELTA(RET, 3)) * CORR(OPEN, VOLUME, 10)
    Factors.append(Factorize(alpha136, factor_name="alpha136"))
    
    alpha137 = None# TODEF
    
    alpha138 = - (RANK(DECAYLINEAR(DELTA(LOW * 0.7 + VWAP * 0.3, 3), 20)) - TSRANK(DECAYLINEAR(TSRANK(CORR(TSRANK(LOW, 8), TSRANK(MEAN(VOLUME, 60), 17), 5), 19), 16), 7))
    Factors.append(Factorize(alpha138, factor_name="alpha138"))
    
    alpha139 = - CORR(OPEN, VOLUME, 10)
    Factors.append(Factorize(alpha139, factor_name="alpha139"))
    
    alpha140 = MIN(RANK(DECAYLINEAR((RANK(OPEN) + RANK(LOW)) - (RANK(HIGH) + RANK(CLOSE)), 8)), TSRANK(DECAYLINEAR(CORR(TSRANK(CLOSE, 8), TSRANK(MEAN(VOLUME, 60), 20), 8), 7), 3))
    Factors.append(Factorize(alpha140, factor_name="alpha140"))
    
    alpha141 = - RANK(CORR(RANK(HIGH), RANK(MEAN(VOLUME, 15)), 9))
    Factors.append(Factorize(alpha141, factor_name="alpha141"))
    
    alpha142 = - RANK(TSRANK(CLOSE, 10)) * RANK(DELTA(DELTA(CLOSE, 1), 1)) * RANK(TSRANK(VOLUME / MEAN(VOLUME, 20), 5))
    Factors.append(Factorize(alpha142, factor_name="alpha142"))
    
    # TODEF
    alpha143 = IF(CLOSE > PRECLOSE, (CLOSE - PRECLOSE) / PRECLOSE * SELF, SELF)
    Factors.append(Factorize(alpha143, factor_name="alpha143"))
    
    MASK = (CLOSE < PRECLOSE)
    alpha144 = SUMIF(ABS(CLOSE / PRECLOSE - 1) / AMOUNT, 20, MASK) / COUNT(MASK, 20)
    Factors.append(Factorize(alpha144, factor_name="alpha144"))
    
    alpha145 = (MEAN(VOLUME, 9) - MEAN(VOLUME, 26)) / MEAN(VOLUME, 12) * 100
    Factors.append(Factorize(alpha145, factor_name="alpha145"))
    
    alpha146 = None# TODEF
    
    alpha147 = REGCHG(MEAN(CLOSE, 12), 12)
    Factors.append(Factorize(alpha147, factor_name="alpha147"))
    
    alpha148 = - (RANK(CORR(OPEN, SUM(MEAN(VOLUME, 60), 9), 6)) < RANK(OPEN - TSMIN(OPEN, 14)))
    Factors.append(Factorize(alpha148, factor_name="alpha148"))
    
    TEMP = DELAY(BENCHMARKINDEXCLOSE, 1)
    MASK = (BENCHMARKINDEXCLOSE < TEMP)
    alpha149 = REGBETA(FILTER(CLOSE / PRECLOSE - 1, MASK), FILTER(BENCHMARKINDEXCLOSE / TEMP - 1, MASK), 252)
    Factors.append(Factorize(alpha149, factor_name="alpha149"))
    
    alpha150 = (CLOSE + HIGH + LOW) / 3 * VOLUME
    Factors.append(Factorize(alpha150, factor_name="alpha150"))
    
    alpha151 = SMA(CLOSE - DELAY(CLOSE, 20), 20, 1)
    Factors.append(Factorize(alpha151, factor_name="alpha151"))
    
    TEMP = DELAY(SMA(DELAY(CLOSE / DELAY(CLOSE, 9), 1), 9, 1), 1)
    alpha152 = SMA(MEAN(TEMP, 12) - MEAN(TEMP, 26), 9, 1)
    Factors.append(Factorize(alpha152, factor_name="alpha152"))
    
    alpha153 = (MEAN(CLOSE, 3) + MEAN(CLOSE, 6) + MEAN(CLOSE, 12) + MEAN(CLOSE, 24)) / 4
    Factors.append(Factorize(alpha153, factor_name="alpha153"))
    
    # TOCHECK
    alpha154 = (VWAP - MIN(VWAP, 16) < CORR(VWAP, MEAN(VOLUME, 180), 18))
    Factors.append(Factorize(alpha154, factor_name="alpha154"))
    
    TEMP = SMA(VOLUME, 13, 2) - SMA(VOLUME, 27, 2)
    alpha155 = TEMP - SMA(TEMP, 10, 2)
    Factors.append(Factorize(alpha155, factor_name="alpha155"))
    
    TEMP = OPEN * 0.15 + LOW * 0.85
    alpha156 = - MAX(RANK(DECAYLINEAR(DELTA(VWAP, 5), 3)), RANK(DECAYLINEAR(- DELTA(TEMP, 2) / TEMP, 3)))
    Factors.append(Factorize(alpha156, factor_name="alpha156"))
    
    # TOCHECK
    alpha157 = MIN(PROD(RANK(RANK(LOG(SUM(TSMIN(RANK(RANK(- RANK(DELTA(CLOSE - 1, 5)))), 2), 1)))), 1), 5) + TSRANK(DELAY(-RET, 6), 5)
    Factors.append(Factorize(alpha157, factor_name="alpha157"))
    
    TEMP = SMA(CLOSE, 15, 2)
    alpha158 = ((HIGH - TEMP) - (LOW - TEMP)) / CLOSE
    Factors.append(Factorize(alpha158, factor_name="alpha158"))
    
    TEMP1 = MIN(LOW, PRECLOSE)
    TEMP2 = MAX(HIGH, PRECLOSE)
    alpha159 = ((CLOSE - SUM(TEMP1, 6)) / SUM(TEMP2 - TEMP1, 6) * 12 * 24 + (CLOSE - SUM(TEMP1, 12)) / SUM(TEMP2 - TEMP1, 12) * 6 * 24 + (CLOSE - SUM(TEMP1, 24)) / SUM(TEMP2 - TEMP1, 24) * 6 * 24) * 100 / (6 * 12 + 6 * 24 + 12 * 24)
    Factors.append(Factorize(alpha159, factor_name="alpha159"))
    
    alpha160 = SMA(IF(CLOSE <= PRECLOSE, STD(CLOSE, 20), 0), 20, 1)
    Factors.append(Factorize(alpha160, factor_name="alpha160"))
    
    alpha161 = MEAN(MAX(MAX(HIGH-LOW, ABS(PRECLOSE - HIGH)), ABS(PRECLOSE - LOW)), 12)
    Factors.append(Factorize(alpha161, factor_name="alpha161"))
    
    TEMP = SMA(MAX(CLOSE - PRECLOSE, 0), 12, 1) / SMA(ABS(CLOSE - PRECLOSE), 12, 1)
    alpha162 = (TEMP * 100 - MIN(TEMP * 100, 12)) / (MAX(TEMP * 100, 12) - MIN(TEMP * 100, 12))
    Factors.append(Factorize(alpha162, factor_name="alpha162"))
    
    alpha163 = RANK(- RET * MEAN(VOLUME, 20) * VWAP * (HIGH - CLOSE))
    Factors.append(Factorize(alpha163, factor_name="alpha163"))
    
    TEMP = IF(CLOSE > PRECLOSE, 1 / (CLOSE - PRECLOSE), 1)
    alpha164 = SMA((TEMP - MIN(TEMP, 12)) / (HIGH - LOW) * 100, 13, 2)
    Factors.append(Factorize(alpha164, factor_name="alpha164"))
    
    # TOCHECK
    alpha165 = (MAX_SUMAC(CLOSE, 48) - MIN_SUMAC(CLOSE, 48)) / STD(CLOSE, 48)
    Factors.append(Factorize(alpha165, factor_name="alpha165"))
    
    # TOCHECK
    # alpha166 = -20 * (20-1)**1.5 * SUM(RET - MEAN(RET, 20), 20) / ((20-1)*(20-2)*(SUM((CLOSE/PRECLOSE, 20)**2, 20)) ** 1.5)
    # Factors.append(Factorize(alpha166, factor_name="alpha166"))
    
    alpha167 = SUM(MAX(CLOSE - PRECLOSE, 0), 12)
    Factors.append(Factorize(alpha167, factor_name="alpha167"))
    
    alpha168 = - VOLUME / MEAN(VOLUME, 20)
    Factors.append(Factorize(alpha168, factor_name="alpha168"))
    
    TEMP = DELAY(SMA(CLOSE - PRECLOSE, 9, 1), 1)
    alpha169 = SMA(MEAN(TEMP, 12) - MEAN(TEMP, 26), 10, 1)
    Factors.append(Factorize(alpha169, factor_name="alpha169"))
    
    alpha170 = (RANK(1 / CLOSE) * VOLUME / MEAN(VOLUME, 20) * HIGH * RANK(HIGH - CLOSE) / MEAN(HIGH, 5)) - RANK(VWAP - DELAY(VWAP, 5))
    Factors.append(Factorize(alpha170, factor_name="alpha170"))
    
    alpha171 = (- (LOW - CLOSE) * (OPEN ** 5)) / ((CLOSE - HIGH) * (CLOSE ** 5))
    Factors.append(Factorize(alpha171, factor_name="alpha171"))
    
    TEMP = SUM(TR, 14)
    TEMP1 = SUM(IF((LD>0) & (LD>HD), LD, 0), 14) * 100 / TEMP
    TEMP2 = SUM(IF((HD>0) & (HD>LD), HD, 0), 14) * 100 / TEMP
    alpha172 = MEAN(ABS(TEMP1 - TEMP2) / (TEMP1 + TEMP2) * 100, 6)
    Factors.append(Factorize(alpha172, factor_name="alpha172"))
    
    TEMP = SMA(CLOSE, 13, 2)
    alpha173 = 3 * TEMP - 2 * SMA(TEMP, 13, 2) + SMA(SMA(SMA(LOG(CLOSE), 13, 2), 13, 2), 13, 2)
    Factors.append(Factorize(alpha173, factor_name="alpha173"))
    
    alpha174 = SMA(IF(CLOSE>PRECLOSE, STD(CLOSE, 20), 0), 20, 1)
    Factors.append(Factorize(alpha174, factor_name="alpha174"))
    
    alpha175 = MEAN(MAX(MAX(HIGH - LOW, ABS(PRECLOSE - HIGH)), ABS(PRECLOSE - LOW)), 6)
    Factors.append(Factorize(alpha175, factor_name="alpha175"))
    
    TEMP = TSMIN(LOW, 12)
    alpha176 = CORR(RANK((CLOSE - TEMP) / (TSMAX(HIGH, 12) - TEMP)), RANK(VOLUME), 6)
    Factors.append(Factorize(alpha176, factor_name="alpha176"))
    
    alpha177 = ((20 - HIGHDAY(HIGH, 20)) / 20) * 100
    Factors.append(Factorize(alpha177, factor_name="alpha177"))
    
    alpha178 = (CLOSE / PRECLOSE - 1) * VOLUME
    Factors.append(Factorize(alpha178, factor_name="alpha178"))
    
    alpha179 = RANK(CORR(VWAP, VOLUME, 4)) * RANK(CORR(RANK(LOW), RANK(MEAN(VOLUME, 50)), 12))
    Factors.append(Factorize(alpha179, factor_name="alpha179"))
    
    alpha180 = IF(MEAN(VOLUME, 20) < VOLUME, - TSRANK(ABS(DELTA(CLOSE, 7)), 60) * SIGN(DELTA(CLOSE, 7)), - VOLUME)
    Factors.append(Factorize(alpha180, factor_name="alpha180"))
    
    # TOCHECK
    alpha181 = SUM(RET - MEAN(RET, 20) - (BENCHMARKINDEXCLOSE - MEAN(BENCHMARKINDEXCLOSE, 20))**2, 20) / SUM((BENCHMARKINDEXCLOSE - MEAN(BENCHMARKINDEXCLOSE, 20)) ** 3, 20)
    Factors.append(Factorize(alpha181, factor_name="alpha181"))
    
    alpha182 = COUNT(((CLOSE > OPEN) & (BENCHMARKINDEXCLOSE>BENCHMARKINDEXCLOSE)) | ((CLOSE < OPEN) & (BENCHMARKINDEXCLOSE < BENCHMARKINDEXCLOSE)), 20) / 20
    Factors.append(Factorize(alpha182, factor_name="alpha182"))
    
    # TOCHECK
    alpha183 = (MAX_SUMAC(CLOSE, 24) - MIN_SUMAC(CLOSE, 24)) / STD(CLOSE, 24)
    Factors.append(Factorize(alpha183, factor_name="alpha183"))
    
    alpha184 = RANK(CORR(DELAY(OPEN - CLOSE, 1), CLOSE, 200)) + RANK(OPEN - CLOSE)
    Factors.append(Factorize(alpha184, factor_name="alpha184"))
    
    alpha185 = RANK(- (1 - OPEN / CLOSE)**2)
    Factors.append(Factorize(alpha185, factor_name="alpha185"))
    
    TEMP = SUM(TR, 14)
    TEMP1 = SUM(IF((LD>0) & (LD>HD), LD, 0), 14) * 100 / TEMP
    TEMP2 = SUM(IF((HD>0) & (HD>LD), HD, 0), 14) * 100 / TEMP
    TEMP3 = MEAN(ABS(TEMP1 - TEMP2) / (TEMP1 + TEMP2) * 100, 6)
    alpha186 = (TEMP3 + DELAY(TEMP3, 6)) / 2
    Factors.append(Factorize(alpha186, factor_name="alpha186"))
    
    alpha187 = SUM(IF(OPEN <= PREOPEN, 0, MAX(HIGH - OPEN, OPEN - PREOPEN)), 20)
    Factors.append(Factorize(alpha187, factor_name="alpha187"))
    
    TEMP = SMA(HIGH - LOW, 11, 2)
    alpha188 = (HIGH - LOW - TEMP) / TEMP * 100
    Factors.append(Factorize(alpha188, factor_name="alpha188"))
    
    alpha189 = MEAN(ABS(CLOSE - MEAN(CLOSE, 6)), 6)
    Factors.append(Factorize(alpha189, factor_name="alpha189"))
    
    TEMP1 = (CLOSE/DELAY(CLOSE, 19))**(1/20)-1
    alpha190 = LOG((COUNT(RET > TEMP1, 20) - 1) * SUMIF((RET - TEMP1) ** 2, 20, RET < TEMP1) / (COUNT(RET < TEMP1, 20) * SUMIF((RET - TEMP1) ** 2, 20, RET > TEMP1)))
    Factors.append(Factorize(alpha190, factor_name="alpha190"))
    
    alpha191 = CORR(MEAN(VOLUME, 20), LOW, 5) + MID - CLOSE
    Factors.append(Factorize(alpha191, factor_name="alpha191"))
    
    UpdateArgs = {
        "IDs": "A股"
    }
    
    return Factors, UpdateArgs

if __name__=="__main__":
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()    
    
    
    FT = TDB.getTable("stock_cn_quote_adj_no_nafilled")
    
    StartDT, EndDT = dt.datetime(2018, 1, 1), dt.datetime(2018, 1, 10)
    DTs = FT.getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = FT.getDateTime()
    
    IDs = FT.getID()[:5]
    
    CFT = QS.FactorDB.CustomFT("stock_cn_factor_price_vol")
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTRuler)
    CFT.setID(IDs)
    
    Data = CFT.readData(factor_names=CFT.FactorNames, ids=IDs, dts=DTs)
    
    print("===")