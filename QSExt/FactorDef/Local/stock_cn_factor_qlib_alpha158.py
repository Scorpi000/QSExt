# coding=utf-8
"""QLib Alpha 158"""
import os
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.Factor.FactorOperator import QuantileStandardization, Orthogonalization
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QuantStudio.Tools.DateTimeFun import getMonthLastDateTime


@FactorOperatorized(operator_type="Panel", args={"Arity": 3, "LookBack":[30, 30, 30], "DTMode": "单时点"})
def calcMonthIC(f, idt, iid, x, args):
    MonthDTs = getMonthLastDateTime(idt)
    if MonthDTs[-1]==idt[-1]: PrePos = idt.index(MonthDTs[-2])
    else: PrePos = idt.index(MonthDTs[-1])
    Ret = x[1][-1] / x[1][PrePos] - 1
    Mask = (x[0][PrePos]==1)
    Data = x[2][PrePos]
    return pd.Series(Data[Mask]).corr(pd.Series(Ret[Mask]), method="spearman")

@FactorOperatorized(operator_type="Time", args={"Arity": 1, "LookBack": [365], "DTMode": "单时点", "IDMode": "多ID"})
def calcMonthICAvg(f, idt, iid, x, args):
    MonthDTs = getMonthLastDateTime(idt)
    Index = pd.Series(np.arange(0, len(idt)), index=idt)
    return np.nanmean(x[0][Index[MonthDTs].tolist()], axis=0)

@FactorOperatorized(operator_type="Time", args={"Arity": 1, "LookBack": [365], "DTMode": "单时点", "IDMode": "多ID"})
def calcMonthIR(f, idt, iid, x, args):
    MonthDTs = getMonthLastDateTime(idt)
    Index = pd.Series(np.arange(0, len(idt)), index=idt)
    MonthIndex = Index[MonthDTs].tolist()
    ICAvg = np.nanmean(x[0][MonthIndex], axis=0)
    ICStd = np.nanstd(x[0][MonthIndex], axis=0)
    return ICAvg / ICStd


def defFactor(fdi: FactorDefInput):
    Factors = []

    LDB = fdi.FDB["LDB"]

    # 基本算子
    max = fo.Max(all_nan=np.nan)
    min = fo.Min(all_nan=np.nan)
    where = fo.Where()

    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    PreClose = FT.getFactor("pre_close")
    Close = FT.getFactor("close")
    High = FT.getFactor("high")
    Low = FT.getFactor("low")
    Open = FT.getFactor("open")
    AvgPrice = FT.getFactor("avg")
    DailyReturn = FT.getFactor("chg_rate")
    Volume = FT.getFactor("volume")

    FT = LDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    AdjClose = FT.getFactor("close")

    # 价格形态
    # KMID: 中轨价格 = (收盘价 - 开盘价) / 开盘价
    Factors.append(rename((Close - Open) / Open, factor_name="KMID"))
    # KLEN: K线长度 = (最高价 - 最低价) / 开盘价
    Factors.append(rename((High - Low) / Open, factor_name="KLEN"))
    # KMID2: 
    Factors.append(rename((Close - Open) / (High - Low + 1e-12), factor_name="KMID2"))
    # KUP: 上影线 = (最高价 - MAX(收盘价, 开盘价)) / 开盘价
    Factors.append(rename((High - max(Close, Open)) / Open, factor_name="KUP"))
    # KUP2: 
    Factors.append(rename((High - max(Close, Open)) / (High - Low + 1e-12), factor_name="KUP2"))
    # KLOW: 下影线 = (MIN(收盘价, 开盘价) - 最低价) / 开盘价
    Factors.append(rename((min(Close, Open) - Low) / Open, factor_name="KLOW"))
    # KLOW2: 
    Factors.append(rename((min(Close, Open) - Low) / (High - Low + 1e-12), factor_name="KLOW2"))
    # KSFT: 价格偏移
    Factors.append(rename((2 * Close - High - Low) / Open, factor_name="KSFT"))
    # KSFT2: 
    Factors.append(rename((2 * Close - High - Low) / (High - Low + 1e-12), factor_name="KSFT2"))


    # 价格类
    for i in range(5):
        # OPENN
        Factors.append(rename(fo.Lag(lag_period=i, window=i)(Open) / Close, factor_name=f"OPEN{i}"))
        # HIGHN
        Factors.append(rename(fo.Lag(lag_period=i, window=i)(High) / Close, factor_name=f"HIGH{i}"))
        # LOWN
        Factors.append(rename(fo.Lag(lag_period=i, window=i)(Low) / Close, factor_name=f"LOW{i}"))
        # VWAPN
        Factors.append(rename(fo.Lag(lag_period=i, window=i)(AvgPrice) / Close, factor_name=f"VWAP{i}"))

    # 动量类
    for i in [5, 10, 20, 30, 60]:
        # ROCN: N日收益率 = (收盘价 - N日前收盘价) / N日前收盘价
        Factors.append(rename(AdjClose / fo.Lag(lag_period=i, window=i)(AdjClose) - 1, factor_name=f"ROC{i}"))
        # MAN: N日简单移动平均
        Factors.append(fo.RollingMean(window=i, min_periods=i)(AdjClose, factor_args={"Name": f"MA{i}"}))
        # STDN: N日收益率标准差
        Factors.append(fo.RollingApply(func=np.std, window=i, min_periods=i)(DailyReturn, factor_args={"Name": f"STD{i}"}))

    # 回归类因子
    # BETA5/10/20/30/60: N日市场beta(与基准的协方差/基准方差)

    # RSQR5/10/20/30/60: N日回归R平方

    # RESI5/10/20/30/60: N日回归残差

    # 极值统计因子
    for i in [5, 10, 20, 30, 60]:
        # MAX5/10/20/30/60: N日内最高价
        Factors.append(fo.RollingApply(func=np.max, window=i, min_periods=i)(High, factor_args={"Name": f"MAX{i}"}))
        # MIN5/10/20/30/60: N日内最低价
        # IMAX5/10/20/30/60: N日内最高价出现的位置(0-1)
        # IMIN5/10/20/30/60: N日内最低价出现的位置(0-1)
        # IMXD5/10/20/30/60: 最高价与最低价位置差

    # 分位数因子
    # QTLU5/10/20/30/60: N日上分位数(如80%分位)

    # QTLD5/10/20/30/60: N日下分位数(如20%分位)

    # RANK5/10/20/30/60: 当前价格在N日内的排名百分位

    # RSV5/10/20/30/60: N日随机指标 = (收盘价-N日最低)/(N日最高-N日最低)

    # 相关性因子
    # CORR5/10/20/30/60: N日与基准收益率相关性

    # CORD5/10/20/30/60: N日与基准收益率距离

    # 计数统计因子
    for i in [5, 10, 20, 30, 60]:
        # CNTP5/10/20/30/60: N日内上涨天数
        iCNTP = fo.RollingApply(func=np.sum, window=i, min_periods=i)(DailyReturn > 0, factor_args={"Name": f"CNTP{i}"})
        Factors.append(iCNTP)
        # CNTN5/10/20/30/60: N日内下跌天数
        iCNTN = fo.RollingApply(func=np.sum, window=i, min_periods=i)(DailyReturn < 0, factor_args={"Name": f"CNTN{i}"})
        Factors.append(iCNTN)
        # CNTD5/10/20/30/60: N日净上涨天数(上涨 - 下跌)
        Factors.append(rename(iCNTP - iCNTN, factor_name=f"CNTD{i}"))
        # SUMP5/10/20/30/60: N日上涨幅度总和
        iSUMP = fo.RollingApply(func=np.sum, window=i, min_periods=i)(where(DailyReturn, DailyReturn > 0, 0), factor_args={"Name": f"SUMP{i}"})
        Factors.append(iSUMP)
        # SUMN5/10/20/30/60: N日下跌幅度总和
        iSUMN = fo.RollingApply(func=np.sum, window=i, min_periods=i)(where(-DailyReturn, DailyReturn < 0, 0), factor_args={"Name": f"SUMN{i}"})
        Factors.append(iSUMN)
        # SUMD5/10/20/30/60: N日净上涨幅度(上涨总和-下跌总和)
        Factors.append(rename(iSUMP - iSUMN, factor_name=f"SUMD{i}"))
    
    # 成交量因子
    for i in [5, 10, 20, 30, 60]:
        # VMA5/10/20/30/60: N日成交量平均
        Factors.append(fo.RollingMean(window=i, min_periods=i)(Volume, factor_args={"Name": f"VMA{i}"}))
        # VSTD5/10/20/30/60: N日成交量标准差
        Factors.append(fo.RollingApply(func=np.std, window=i, min_periods=i)(Volume, factor_args={"Name": f"VSTD{i}"}))
        # WVMA5/10/20/30/60: N日加权成交量平均

        # VSUMP5/10/20/30/60: N日放量上涨天数成交量总和

        # VSUMN5/10/20/30/60: N日放量下跌天数成交量总和

        # VSUMD5/10/20/30/60: N日净放量成交量(上涨 - 下跌)
    



    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_factor_qlib_alpha158",
        IDType="A股",
        MaxLookBack=365 * 2,
        Author="麦冬",
        Description="QLib Alpha 158 因子集, 主要为量价类因子",
        DefScriptPath=__file__
    )
