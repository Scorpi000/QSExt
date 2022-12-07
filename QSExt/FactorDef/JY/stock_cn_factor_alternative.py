# coding=utf-8
"""另类因子"""
import datetime as dt

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_factor_alternative",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def Price_52WHighFun(f, idt, iid, x, args):
    Close = x[0]
    LastClose = Close[-1,:]
    IfTrading = x[1]
    HighClose = np.nanmax(Close)
    Len = IfTrading.shape[0]
    Mask = (np.sum(IfTrading==1, axis=0)/Len<args['非空率'])
    LastClose[(LastClose==0) | Mask] = np.nan    
    return HighClose/LastClose-1

def RegressionFun(f,idt,iid,x,args):
    Y = np.array(x[0])
    Mask = (~np.isnan(Y))
    L = Y.shape[0]
    if np.sum(Mask)/L<args['非空率']:
        return np.nan
    X = np.array(range(L),dtype='float')[Mask]
    Y = Y[Mask]
    x = X-np.nanmean(X)
    y = Y-np.nanmean(Y)
    Numerator = np.nansum(x*y)/np.nansum(x*x)
    Denominator = np.abs(np.nanmean(Y))
    if Denominator==0:
        return np.sign(Numerator)
    else:
        return Numerator/Denominator

def MomentumChgFun(f, idt, iid, x, args):
    Y = np.zeros(args["回归期"])
    for i in range(args["回归期"]):
        iDenorminator = x[0][-1-i-args['收益期']]
        Y[args["回归期"]-i-1] = (x[0][-1-i]/iDenorminator-1 if iDenorminator!=0 else np.nan)
    X = np.arange(5)
    Mask = (~np.isnan(Y))
    Y = Y[Mask]
    X = X[Mask]
    return (np.sum(Y*X)-Y.shape[0]*np.mean(Y)*np.mean(X))/np.sum((X-np.mean(X))**2)

def Cls_Trun_Correl_Fun(f, idt, iid, x, args):
    Turnover = x[0]
    AdjClose = x[1]
    IfTrading=x[2]
    Len = IfTrading.shape[0]
    Mask = (np.sum(IfTrading==1, axis=0)/Len<args['非空率'])
    spearman_cor = np.zeros(AdjClose.shape[1])+np.nan
    for i in range(Turnover.shape[1]):
        iTurnover = Turnover[:,i]
        iAdjClose = AdjClose[:,i]
        try:
            spearman_cor[i] = stats.spearmanr(iTurnover,iAdjClose,nan_policy='omit').correlation
        except:
            pass
    spearman_cor[Mask] = np.nan
    return spearman_cor

def HL_Vol_Correl_Fun(f, idt, iid, x, args):
    Low = x[0]
    High = x[1]
    Vol = x[2]
    IfTrading=x[3]
    Len = IfTrading.shape[0]
    Mask = (np.sum(IfTrading==1, axis=0)/Len<args['非空率'])
    Ratio=High/Low
    spearman_cor = np.zeros(Vol.shape[1])+np.nan
    for i in range(Vol.shape[1]):
        iRatio = Ratio[:,i]
        iVol = Vol[:,i]
        try:
            spearman_cor[i] = stats.spearmanr(iRatio,iVol,nan_policy='omit').correlation
        except:
            pass
    spearman_cor[Mask] = np.nan
    return spearman_cor

def HL_Fun(f, idt, iid, x, args):
    Low = x[0]
    High = x[1]
    IfTrading = x[2]
    High_Max = np.max(High,axis=0)
    Low_Min = np.min(Low,axis=0)
    Len = IfTrading.shape[0]
    Mask = (np.sum(IfTrading==1, axis=0)/Len<args['非空率'])
    Low_Min[(Low_Min==0) | Mask] = np.nan
    Val=High_Max/Low_Min
    return Val

def VWAPPFun(f, idt, iid, x, args):
    X, Y = x[0], x[1]
    Rslt = np.full(shape=(X.shape[0],), fill_value=np.nan)
    Mask = (pd.notnull(X) & pd.notnull(Y))
    if np.sum(Mask)==0: return Rslt
    X, Y = X[Mask], Y[Mask]
    X = sm.add_constant(X, prepend=True)
    try:
        Result = sm.OLS(Y, X, missing="drop").fit()
    except Exception as e:
        f.Logger.warning(f"{idt} 时 VWAPPFun 计算中的回归失败: {e}")
        return Rslt
    Rslt[Mask] = Result.resid
    return Rslt

def PriceSpreadFun(f, idt, iid, x, args):
    ret = pd.DataFrame(x[0])
    ret20D = pd.Series(x[1][0, :])
    C = ret.corr(min_periods=int(240 * 0.8))
    rp = C.apply(lambda x, ret20D: ret20D.loc[x.sort_values(ascending=False).iloc[:10].index].mean(), args=(ret20D,))
    rp[rp<=-1] = np.nan
    ps = np.log(1+ret20D) - np.log(1+rp)
    return ps.values

def SpreadBiasFun(f, idt, iid, x, args):
    Data = x[0]
    Avg = np.nanmean(Data, axis=0)
    Std = np.nanstd(Data, axis=0)
    Std[Std==0] = np.nan
    Rslt = (Data[-1, :] - Avg) / Std
    Mask = (np.sum(np.isnan(Data), axis=0) / Data.shape[0] >= 1-args["非空率"])
    Rslt[Mask] = np.nan
    return Rslt
    

def defFactor(args={}):
    Factors = []

    LDB = args["LDB"]

    # ## 行情因子 ############################################
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    PreClose = FT.getFactor("pre_close")
    DayReturn = FT.getFactor("chg_rate")
    Turnover = FT.getFactor("turnover")# %
    Volume = FT.getFactor("volume")# 手
    Amount = FT.getFactor("amount")
    IfTrading = FT.getFactor("if_trading")
    Close = FT.getFactor("close")
    Low = FT.getFactor("low")
    High = FT.getFactor("high")
    
    FT = LDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    AdjClose = FT.getFactor("close")
    
    FT = LDB.getTable("stock_cn_factor_momentum")
    Ret20D = FT.getFactor("rtn_20d")    

    #--收盘价的自然对数
    Factors.append(fd.log(Close, factor_name="ln_price"))

    #计算MaxReturn_20D
    Factors.append(fd.rolling_max(DayReturn, window=20, min_periods=int(20*0.8), factor_name="MaxReturn_20D"))

    #计算Price_52WHigh
    Close2MaxClose_240D = QS.FactorDB.TimeOperation("close2max_close_240d", [AdjClose, IfTrading], {'算子':Price_52WHighFun,'参数':{"非空率":0.8},'回溯期数':[240-1,240-1],"运算ID":"多ID"})
    Factors.append(Close2MaxClose_240D)

    #计算PriceTrend_240D
    CloseTrend_240D_Reg = QS.FactorDB.TimeOperation("close_trend_240d_reg", [AdjClose], {'算子':RegressionFun,'参数':{"非空率":0.8},'回溯期数':[240-1]})
    Factors.append(CloseTrend_240D_Reg)

    # CL, 升序, 参考《银河量化十周年专题之五：选股因子及因子择时新视角》, 银河证券, 20140909
    Factors.append(fd.rolling_sum((Close - Low) / Low, 5, factor_name="cl"))

    # 5日收益率增速, 升序, 参考《银河量化十周年专题之五：选股因子及因子择时新视角》, 银河证券, 20140909
    Factors.append(QS.FactorDB.TimeOperation("daily_return_5d_reg", [AdjClose], {'算子':MomentumChgFun,'参数':{"收益期":5,"回归期":5},'回溯期数':[5+5+1]}))

    # 收盘价和换手率的相关性
    Turnover_Close_5D_Corr = QS.FactorDB.TimeOperation("turnover_close_5d_corr", [Turnover, AdjClose, IfTrading], sys_args={"算子": Cls_Trun_Correl_Fun, '参数':{"非空率":0.8},"回溯期数": [5-1,5-1,5-1],"运算ID":"多ID"})
    Turnover_Close_20D_Corr = QS.FactorDB.TimeOperation("turnover_close_20d_corr", [Turnover, AdjClose, IfTrading], sys_args={"算子": Cls_Trun_Correl_Fun, '参数':{"非空率":0.8},"回溯期数": [20-1,20-1,20-1],"运算ID":"多ID"})
    Turnover_Close_60D_Corr = QS.FactorDB.TimeOperation("turnover_close_60d_corr", [Turnover, AdjClose, IfTrading], sys_args={"算子": Cls_Trun_Correl_Fun, '参数':{"非空率":0.8},"回溯期数": [60-1,60-1,60-1],"运算ID":"多ID"})
    Factors.append(Turnover_Close_5D_Corr)
    Factors.append(Turnover_Close_20D_Corr)
    Factors.append(Turnover_Close_60D_Corr)

    # 每一天的最高价/最低价与成交量的相关系数
    High2Low_Vol_5D_Corr = QS.FactorDB.TimeOperation('high2low_vol_5d_corr',[Low, High, Volume, IfTrading],{'算子':HL_Vol_Correl_Fun,'参数':{"非空率":0.8},'回溯期数':[5-1,5-1,5-1,5-1],"运算ID":"多ID"})
    High2Low_Vol_20D_Corr = QS.FactorDB.TimeOperation('high2low_vol_20d_corr',[Low, High, Volume, IfTrading],{'算子':HL_Vol_Correl_Fun,'参数':{"非空率":0.8},'回溯期数':[20-1,20-1,20-1,20-1],"运算ID":"多ID"})
    High2Low_Vol_60D_Corr = QS.FactorDB.TimeOperation('high2low_vol_60d_corr',[Low, High, Volume, IfTrading],{'算子':HL_Vol_Correl_Fun,'参数':{"非空率":0.8},'回溯期数':[60-1,60-1,60-1,60-1],"运算ID":"多ID"})
    Factors.append(High2Low_Vol_5D_Corr)
    Factors.append(High2Low_Vol_20D_Corr)
    Factors.append(High2Low_Vol_60D_Corr)

    # 过去一段时间最高价/最低价比值
    High2Low_5D = QS.FactorDB.TimeOperation("high2low_5d", [Low, High, IfTrading], sys_args={"算子": HL_Fun,'参数':{"非空率":0.8}, "回溯期数": [5-1,5-1,5-1],"运算ID":"多ID"})
    High2Low_20D = QS.FactorDB.TimeOperation("high2low_20d", [Low, High, IfTrading], sys_args={"算子": HL_Fun,'参数':{"非空率":0.8}, "回溯期数": [20-1,20-1,20-1],"运算ID":"多ID"})
    High2Low_60D = QS.FactorDB.TimeOperation("high2low_60d", [Low, High, IfTrading], sys_args={"算子": HL_Fun,'参数':{"非空率":0.8}, "回溯期数": [60-1,60-1,60-1],"运算ID":"多ID"})
    Factors.append(High2Low_5D)
    Factors.append(High2Low_20D)
    Factors.append(High2Low_60D)
    
    # 基于均价计算的日收益率
    VWAPReturn = Amount / (Volume / 100) / PreClose - 1
    # 日收益率相对于均价日收益率的截面回归残差
    VWAPP = QS.FactorDB.SectionOperation("vwapp_ols", [DayReturn, VWAPReturn], {"算子": VWAPPFun})
    Factors.append(VWAPP)
    
    VWAPP_5D = fd.rolling_mean(VWAPP, window=5, min_periods=int(5*0.8), factor_name="vwapp_5d")
    Factors.append(VWAPP_5D)
    VWAPP_10D = fd.rolling_mean(VWAPP, window=10, min_periods=int(10*0.8), factor_name="vwapp_10d")
    Factors.append(VWAPP_10D)
    VWAPP_20D = fd.rolling_mean(VWAPP, window=20, min_periods=int(20*0.8), factor_name="vwapp_20d")
    Factors.append(VWAPP_20D)
    
    # 价差偏离度因子
    PriceSpread = QS.FactorDB.PanelOperation(
        "price_spread",
        [DayReturn, Ret20D],
        sys_args={
            "算子": PriceSpreadFun,
            "回溯期数": [240-1, 1-1]
        }
    )
    Factors.append(PriceSpread)
    SpreadBias_120D = QS.FactorDB.TimeOperation(
        "spread_bias_120d",
        [PriceSpread],
        sys_args={
            "算子": SpreadBiasFun,
            "参数": {"非空率": 0.8},
            "回溯期数": [120-1],
            "运算ID": "多ID"
        }
    )
    Factors.append(SpreadBias_120D)
    
    return Factors

if __name__=="__main__":
    pass