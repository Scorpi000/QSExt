# coding=utf-8
"""波动性因子"""
import datetime as dt

import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_factor_volatility",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

# 因子收益率
def FactorReturnFun(f,idate,iid,x,args):
    FactorData = pd.Series(x[0][0,:])
    ReturnData = pd.Series(x[1][0,:])
    ST = pd.Series(x[2][0,:])
    ListDays = pd.Series(x[3][0,:])
    Weight = pd.Series(x[4][0,:])
    Mask = (pd.isnull(ST) & (ListDays>=6*30))
    PortfolioReturn, Temp = calcQuantilePortfolio(FactorData, ReturnData, Mask, weight_data=Weight, ascending=args["ascending"], n_group=3)
    return np.zeros((FactorData.shape[0],))+PortfolioReturn[0]-PortfolioReturn[-1]

# 市场收益率
def MarketReturnFun(f,idate,iid,x,args):
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
def RegressFun(f,idate,iid,x,args):
    X = np.array(x[1:]).T.astype("float")
    X = sm.add_constant(X,prepend=True)
    Y = x[0].astype("float")
    try:
        Result = sm.OLS(Y,X).fit()
    except:
        return (np.nan,np.nan)
    return (np.nanstd(Result.resid)*np.sqrt(240.0),1-Result.rsquared_adj)

def defFactor(args={}):
    Factors = []

    JYDB = args["JYDB"]
    LDB = args["LDB"]

    # ### 行情因子 #############################################################################
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    DayReturn = FT.getFactor("chg_rate")
    FloatCap = FT.getFactor("float_cap")# 万元
    Weight = FT.getFactor("float_cap")# 万元
    IfTrading = FT.getFactor("if_trading")

    FT = LDB.getTable("stock_cn_factor_value")
    BP = FT.getFactor("bp_lr")

    FT = LDB.getTable("stock_cn_info")
    ST = FT.getFactor("st")
    ListDays = FT.getFactor("listed_days")
    IfListed = FT.getFactor("if_listed")

    Mask = ((IfTrading==1) & (IfListed==1))
    Mask_60D = (fd.rolling_sum(Mask, 60)>=60*0.8)
    Mask_240D = (fd.rolling_sum(Mask, 240)>=240*0.8)

    Factors.append(fd.where(fd.rolling_std(DayReturn, 60, min_periods=2), Mask_60D, np.nan, factor_name="realized_volatility_60d"))
    Factors.append(fd.where(fd.rolling_std(DayReturn, 240, min_periods=2), Mask_240D, np.nan, factor_name="realized_volatility_240d"))
    Factors.append(fd.where(fd.rolling_skew(DayReturn, 240, min_periods=2), Mask_240D, np.nan, factor_name="realized_skewness_240d"))
    Factors.append(fd.where(fd.rolling_skew(DayReturn, 60, min_periods=2), Mask_60D, np.nan, factor_name="realized_skewness_60d"))
    Factors.append(fd.where(fd.rolling_kurt(DayReturn, 240, min_periods=2), Mask_240D, np.nan, factor_name="realized_kurtosis_240d"))
    Factors.append(fd.where(fd.rolling_kurt(DayReturn, 60, min_periods=2), Mask_60D, np.nan, factor_name="realized_kurtosis_60d"))

    # 特异性波动率
    BPLSRet = QS.FactorDB.PanelOperation("BP收益率", [BP, DayReturn, ST, ListDays, Weight], {"算子":FactorReturnFun,"参数":{"ascending":False}, "输出形式":"全截面", "回溯期数":[1,0,1,1,1]})
    FloatCapLSRet = QS.FactorDB.PanelOperation("流通市值收益率", [FloatCap, DayReturn, ST, ListDays, Weight], {"算子":FactorReturnFun, "参数":{"ascending":True}, "输出形式":"全截面", "回溯期数":[1,0,1,1,1]})
    MarketRet = QS.FactorDB.PanelOperation("市场收益率", [DayReturn, ST, ListDays, Weight], {"算子":MarketReturnFun, "参数":{}, "输出形式":"全截面", "回溯期数":[0,1,1,1]})
    RegressResult_20D = QS.FactorDB.TimeOperation(name="RegressResult", descriptors=[DayReturn, FloatCapLSRet, BPLSRet, MarketRet], sys_args={"算子": RegressFun, "回溯期数": [20,20,20,20], "数据类型":"object"})
    #RegressResult_240D = QS.FactorDB.TimeOperation(name="RegressResult", descriptors=[DayReturn, FloatCapLSRet, BPLSRet, MarketRet], sys_args={"算子": RegressFun, "回溯期数": [240,240,240,240], "数据类型":"object"})
    Factors.append(fd.fetch(RegressResult_20D, 0, factor_name="ivff_20d"))
    Factors.append(fd.fetch(RegressResult_20D, 1, factor_name="ivr_20d"))

    return Factors

if __name__=="__main__":
    pass