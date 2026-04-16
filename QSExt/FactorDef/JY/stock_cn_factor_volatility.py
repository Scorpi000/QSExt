# coding=utf-8
"""波动性因子"""
import datetime as dt
from itertools import product
from functools import partial
from typing import Dict

import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar
from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStockStatus
from QSExt.FactorDef.JY.stock_cn_factor_value import defFactor as defStockFactorValue
from QuantStudio.Tools.AuxiliaryFun import partitionList, getClassMask


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


# 计算分位数组合收益率
# factor_data: 因子数据, DataFrame(index=[日期],columns=[ID]) or Series(index=[ID]), 如果为DataFrame则用行数据
# return_data: 收益率数据, DataFrame(index=[日期],columns=[ID]) or Series(index=[ID]), 如果为DataFrame则用行数据
# mask: 过滤条件, None or DataFrame(index=[日期],columns=[ID]) or Series(index=[ID]), 如果为DataFrame则用行数据
# cat_data: 分类数据, [DataFrame(index=[日期],columns=[ID]) or Series(index=[ID])], 如果为DataFrame则用行数据, 如果非空, 类别内分别分组
# weight_data: 形成投资组合的权重数据, None or DataFrame(index=[日期],columns=[ID]) or Series(index=[ID]), 如果为DataFrame则用行数据
# factor_data, return_data, mask, cat_data[i], weight_data的行列维度和索引必须一致
# ascending: 是否升序排列, 可选: True or False
# n_group: 分组数, int, >0;
# 返回: 如果factor_data等为DataFrame, 返回(DataFrame(收益率,index=[日期],columns=[i]), [[分位数组合]]), 分位数组合: Series(index=[ID])
# 返回: 如果factor_data等为Series, 返回([收益率], [分位数组合]), 分位数组合: Series(index=[ID])
def calcQuantilePortfolio(factor_data, return_data, mask=None, *cat_data, weight_data=None, ascending=False, n_group=10):
    if isinstance(factor_data,pd.Series):
        if mask is not None:
            factor_data = factor_data[mask]
        factor_data = factor_data[pd.notnull(factor_data)]
        factor_data = factor_data.sort_values(ascending=ascending,inplace=False)
        if cat_data:
            cat_data = pd.DataFrame(list(cat_data), columns=cat_data[0].index).T
            cat_data = cat_data.loc[factor_data.index]
            cat_data = cat_data.where(pd.notnull(cat_data),np.nan)
            AllCats = list(product(*list(list(iCatData[iCat].unique()) for iCat in cat_data)))
        else:
            AllCats = [None]
            cat_data = factor_data
        PortfolioIDList = [[] for i in range(n_group)]
        for iCat in AllCats:
            iMask = getClassMask(iCat,cat_data)
            iPortfolioIDList = partitionList(list(factor_data[iMask].index),n_group)
            for j,jIDs in enumerate(iPortfolioIDList):
                PortfolioIDList[j] += jIDs
        weight_data = (weight_data[factor_data.index] if weight_data is not None else pd.Series(1.0, index=factor_data.index))
        return_data = return_data[factor_data.index]
        Portfolio = []
        PortfolioReturn = []
        for jIDs in PortfolioIDList:
            jWeight = weight_data.loc[jIDs]
            jPortfolio = jWeight[pd.notnull(jWeight)] / jWeight.sum()
            Portfolio.append(jPortfolio)
            PortfolioReturn.append((jPortfolio * return_data[jPortfolio.index]).sum())
        return (PortfolioReturn,Portfolio)
    PortfolioReturn = pd.DataFrame(0.0, index=factor_data.index, columns=[i for i in range(n_group)])
    Portfolio = []
    for i in range(factor_data.shape[0]):
        iFactorData = factor_data.iloc[i]
        if i<factor_data.shape[0]-1:
            iReturnData = return_data.iloc[i+1]
        else:
            iReturnData = pd.Series(np.nan,index=factor_data.columns)
        iMask = (mask.iloc[i] if mask is not None else None)
        iCatData = [jCatData.iloc[i] for jCatData in cat_data]
        iWeightData = (weight_data.iloc[i] if weight_data is not None else None)
        iPortfolioReturn, iPortfolio = calcQuantilePortfolio(iFactorData, iReturnData, iMask, *iCatData, weight_data=iWeightData, ascending=ascending, n_group=n_group)
        PortfolioReturn.iloc[(i+1) % factor_data.shape[0]] = iPortfolioReturn
        Portfolio.append(iPortfolio)
    return (PortfolioReturn, Portfolio)

# 因子收益率
@FactorOperatorized(operator_type="Panel", args={"Arity": 5, "ModelArgs": {"ascending": False}, "DTMode": "单时点", "LookBack": [1, 0, 1, 1, 1]})
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
@FactorOperatorized(operator_type="Panel", args={"Arity": 4, "DTMode": "单时点", "LookBack": [0, 1, 1, 1]})
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

def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []

    # ### 行情因子 #############################################################################
    StockDayBarDef = dep_fd.get("stock_cn_day_bar_nafilled", defStockDayBar(fdi=fdi, dep_fd=dep_fd))
    DayReturn = StockDayBarDef.getFactor(factor_name="chg_rate")
    FloatCap = StockDayBarDef.getFactor(factor_name="float_cap")# 万元
    Weight = StockDayBarDef.getFactor(factor_name="float_cap")# 万元
    StockStatusDef = dep_fd.get("stock_cn_status", defStockStatus(fdi=fdi, dep_fd=dep_fd))
    IfTrading = StockStatusDef.getFactor(factor_name="if_trading")
    IfListed = StockStatusDef.getFactor(factor_name="if_listed")
    ST = StockStatusDef.getFactor("st")
    ListDays = StockStatusDef.getFactor("listed_days")
    StockFactorValue = dep_fd.get("stock_cn_factor_value", defStockFactorValue(fdi=fdi, dep_fd=dep_fd))
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
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_factor_volatility",
        MaxLookBack=max(365 * 2, StockDayBarDef.MaxLookBack, StockFactorValue.MaxLookBack, StockStatusDef.MaxLookBack),
        IDType="A股",
        Author="麦冬",
        DefScriptPath=__file__
    )
