# coding=utf-8
"""波动性因子"""
import datetime as dt
from functools import partial

import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.BasicOperator import rename
from QuantStudio.Core.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar
from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStockStatus
from QSExt.FactorDef.JY.stock_cn_factor_value import defFactor as defStockFactorValue


@FactorOperatorized(operator_type="Time", args={"Arity": 1, "DataType": "double", "DTMode": "多时点", "IDMode": "多ID", "LookBack": [60 - 1]})
def calcRollingSkew(f, idt, iid, x, args):
    Data = pd.DataFrame(x[0])
    args = args.copy()
    return Data.rolling(**args).apply(lambda x : x.skew()).values[f.Operator.Args["LookBack"][0]:]

@FactorOperatorized(operator_type="Time", args={"Arity": 1, "DataType": "double", "DTMode": "多时点", "IDMode": "多ID", "LookBack": [60 - 1]})
def calcRollingKurt(f, idt, iid, x, args):
    Data = pd.DataFrame(x[0])
    args = args.copy()
    return Data.rolling(**args).apply(lambda x : x.kurt()).values[f.Operator.Args["LookBack"][0]:]

# 因子收益率(TODO)
@FactorOperatorized(operator_type="Panel", args={"Arity": 5, "ModelArgs": {"ascending": False}, "OutputMode": "全截面", "DTMode": "单时点", "LookBack": [1, 0, 1, 1, 1]})
def calcFactorReturn(f, idt, iid, x, args):
    FactorData = pd.Series(x[0][0,:])
    ReturnData = pd.Series(x[1][0,:])
    ST = pd.Series(x[2][0,:])
    ListDays = pd.Series(x[3][0,:])
    Weight = pd.Series(x[4][0,:])
    Mask = (pd.isnull(ST) & (ListDays>=6*30))
    PortfolioReturn, Temp = calcQuantilePortfolio(FactorData, ReturnData, Mask, weight_data=Weight, ascending=args["ascending"], n_group=3)
    return np.zeros((FactorData.shape[0],))+PortfolioReturn[0]-PortfolioReturn[-1]

# 市场收益率
@FactorOperatorized(operator_type="Panel", args={"Arity": 4, "OutputMode": "全截面", "DTMode": "单时点", "LookBack": [0, 1, 1, 1]})
def calcMarketReturn(f, idt, iid, x, args):
    ReturnData = x[0][0,:]
    ST = x[1][0,:]
    ListDays = x[2][0,:]
    Weight = x[3][0,:]
    Mask = (pd.isnull(ST) & (ListDays>=6*30))
    ReturnData = ReturnData[Mask]
    Weight = Weight[Mask]
    MarketReturn = np.nansum(ReturnData*Weight)/np.nansum(Weight)
    return np.zeros((x[0].shape[0],))+MarketReturn

# 回归函数
@FactorOperatorized(operator_type="Time", args={"Arity": 4, "LookBack": [20, 20, 20, 20], "DataType": "object"})
def calcIVFFAndIVR(f, idt, iid, x, args):
    X = np.array(x[1:]).T.astype("float")
    X = sm.add_constant(X,prepend=True)
    Y = x[0].astype("float")
    try:
        Result = sm.OLS(Y,X).fit()
    except:
        return (np.nan, np.nan)
    return (np.nanstd(Result.resid)*np.sqrt(240.0), 1-Result.rsquared_adj)

def defFactor(fdi: FactorDefInput):
    Factors = []

    # ### 行情因子 #############################################################################
    StockDayBarDef = defStockDayBar(fdi=fdi)
    DayReturn = StockDayBarDef.getFactor(factor_name="chg_rate")
    FloatCap = StockDayBarDef.getFactor(factor_name="float_cap")# 万元
    Weight = StockDayBarDef.getFactor(factor_name="float_cap")# 万元
    StockStatusDef = defStockStatus(fdi=fdi)
    IfTrading = StockStatusDef.getFactor(factor_name="if_trading")
    IfListed = StockStatusDef.getFactor(factor_name="if_listed")
    ST = StockStatusDef.getFactor("st")
    ListDays = StockStatusDef.getFactor("listed_days")
    StockFactorValue = defStockFactorValue(fdi=fdi)
    BP = StockFactorValue.getFactor(factor_name="bp_lr")

    Mask = ((IfTrading==1) & (IfListed==1))
    Mask_60D = (fo.RollingApply(func=np.nansum, window=60)(Mask) >= 60*0.8)
    Mask_240D = (fo.RollingApply(func=np.nansum, window=240)(Mask) >= 240*0.8)
    
    where = fo.Where(dtype="double")
    Factors.append(where(fo.RollingApply(func=partial(np.nanstd, ddof=1), window=60, min_periods=2)(DayReturn), Mask_60D, np.nan, factor_args={"Name": "realized_volatility_60d"}))
    Factors.append(where(fo.RollingApply(func=partial(np.nanstd, ddof=1), window=240, min_periods=2)(DayReturn), Mask_240D, np.nan, factor_args={"Name": "realized_volatility_240d"}))
    Factors.append(where(calcRollingSkew.new(args={"LookBack": [240 - 1], "ModelArgs": {"window": 240, "min_periods": 2}})(DayReturn), Mask_240D, np.nan, factor_args={"Name": "realized_skewness_240d"}))
    Factors.append(where(calcRollingSkew.new(args={"LookBack": [60 - 1], "ModelArgs": {"window": 60, "min_periods": 2}})(DayReturn), Mask_60D, np.nan, factor_args={"Name": "realized_skewness_60d"}))
    Factors.append(where(calcRollingKurt.new(args={"LookBack": [240 - 1], "ModelArgs": {"window": 240, "min_periods": 2}})(DayReturn), Mask_240D, np.nan, factor_args={"Name": "realized_kurtosis_240d"}))
    Factors.append(where(calcRollingKurt.new(args={"LookBack": [60 - 1], "ModelArgs": {"window": 60, "min_periods": 2}})(DayReturn), Mask_60D, np.nan, factor_args={"Name": "realized_kurtosis_60d"}))    
    
    # 特异性波动率
    BPLSRet = calcFactorReturn(BP, DayReturn, ST, ListDays, Weight, factor_args={"Name": "BP收益率"})
    FloatCapLSRet =  calcFactorReturn(FloatCap, DayReturn, ST, ListDays, Weight, factor_args={"Name": "流通市值收益率"})
    MarketRet = calcMarketReturn(DayReturn, ST, ListDays, Weight, factor_args={"Name": "市场收益率"})
    IVFFAndIVR = calcIVFFAndIVR(DayReturn, FloatCapLSRet, BPLSRet, MarketRet, factor_args={"Name": "IVFFAndIVR"})
    Factors.append(fo.Fetch(pos=0, dtype="double")(IVFFAndIVR, factor_args={"Name": "ivff_20d"}))
    Factors.append(fo.Fetch(pos=1, dtype="double")(IVFFAndIVR, factor_args={"Name": "ivr_20d"}))
    
    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_factor_volatility",
        MaxLookBack=max(365 * 2, StockDayBarDef.MaxLookBack, StockFactorValue.MaxLookBack, StockStatusDef.MaxLookBack),
        IDType="A股",
        Author="麦冬"
    )
