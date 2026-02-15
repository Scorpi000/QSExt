# coding=utf-8
"""另类因子"""
import datetime as dt

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm

import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.BasicOperator import rename
from QuantStudio.Core.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStockStatus
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar
from QSExt.FactorDef.JY.stock_cn_day_bar_adj_backward_nafilled import defFactor as defStockAdjDayBar
from QSExt.FactorDef.JY.stock_cn_factor_momentum import defFactor as defStockFactorMomentum


UpdateArgs = {
    "因子表": "stock_cn_factor_alternative",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

@FactorOperatorized(operator_type="Time", args={"Arity": 2, 'ModelArgs': {"非空率": 0.8}, 'LookBack': [240-1, 240-1], "IDMode": "多ID"})
def calcPrice52WHigh(f, idt, iid, x, args):
    Close = x[0]
    LastClose = Close[-1,:]
    IfTrading = x[1]
    HighClose = np.nanmax(Close)
    Len = IfTrading.shape[0]
    Mask = (np.sum(IfTrading==1, axis=0)/Len<args['非空率'])
    LastClose[(LastClose==0) | Mask] = np.nan    
    return HighClose/LastClose-1

@FactorOperatorized(operator_type="Time", args={"Arity": 1, 'ModelArgs': {"非空率": 0.8}, 'LookBack': [240-1], "IDMode": "单ID", "DTMode": "单时点"})
def rollingRegress(f, idt, iid, x, args):
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

@FactorOperatorized(operator_type="Time", args={"Arity": 1, 'ModelArgs': {"收益期": 5, "回归期": 5}, 'LookBack': [5+5+1]})
def calcMomentumChg(f, idt, iid, x, args):
    Y = np.zeros(args["回归期"])
    for i in range(args["回归期"]):
        iDenorminator = x[0][-1-i-args['收益期']]
        Y[args["回归期"]-i-1] = (x[0][-1-i]/iDenorminator-1 if iDenorminator!=0 else np.nan)
    X = np.arange(5)
    Mask = (~np.isnan(Y))
    Y = Y[Mask]
    X = X[Mask]
    return (np.sum(Y*X)-Y.shape[0]*np.mean(Y)*np.mean(X))/np.sum((X-np.mean(X))**2)


@FactorOperatorized(operator_type="Time", args={"Arity": 3, 'ModelArgs': {"非空率": 0.8}, "LookBack": [5-1, 5-1, 5-1], "IDMode": "多ID", "DTMode": "单时点"})
def calcClsTrunCorrel(f, idt, iid, x, args):
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


@FactorOperatorized(operator_type="Time", args={"Arity": 4, 'ModelArgs': {"非空率": 0.8}, 'LookBack': [5-1, 5-1, 5-1, 5-1], "IDMode": "多ID", "DTMode": "单时点"})
def calcHLVolCorrel(f, idt, iid, x, args):
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


@FactorOperatorized(operator_type="Time", args={"Arity": 3, 'ModelArgs': {"非空率": 0.8}, "LookBack": [5-1, 5-1, 5-1], "IDMode": "多ID", "DTMode": "单时点"})
def calcHL(f, idt, iid, x, args):
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
    

def defFactor(fdi: FactorDefInput):
    Factors = []
    
    # ## 行情因子 ############################################
    StockDayBarDef = defStockDayBar(fdi=fdi)
    PreClose = StockDayBarDef.getFactor(factor_name="pre_close")
    DayReturn = StockDayBarDef.getFactor(factor_name="chg_rate")
    Turnover = StockDayBarDef.getFactor(factor_name="turnover")
    Volume = StockDayBarDef.getFactor(factor_name="volume")
    Amount = StockDayBarDef.getFactor(factor_name="amount")
    Close = StockDayBarDef.getFactor(factor_name="close")
    High = StockDayBarDef.getFactor(factor_name="high")
    Low = StockDayBarDef.getFactor(factor_name="low")
    
    StockStatusDef = defStockStatus(fdi=fdi)
    IfTrading = StockStatusDef.getFactor(factor_name="if_trading")
    
    StockAdjDayBarDef = defStockAdjDayBar(fdi=fdi)
    AdjClose = StockAdjDayBarDef.getFactor(factor_name="close")
    
    StockFactorMomentumDef = defStockFactorMomentum(fdi=fdi)
    Ret20D = StockFactorMomentumDef.getFactor("rtn_20d")

    #--收盘价的自然对数
    Factors.append(fo.Log()(Close, factor_args={"Name": "ln_price"}))

    #计算MaxReturn_20D
    Factors.append(fo.RollingMax(window=20, min_periods=int(20*0.8))(DayReturn, factor_args={"Name": "MaxReturn_20D"}))

    #计算Price_52WHigh
    Close2MaxClose_240D = calcPrice52WHigh(AdjClose, IfTrading, factor_args={"Name": "close2max_close_240d"})
    Factors.append(Close2MaxClose_240D)

    #计算PriceTrend_240D
    CloseTrend_240D_Reg = rollingRegress(AdjClose, factor_args={"Name": "close_trend_240d_reg"})
    Factors.append(CloseTrend_240D_Reg)

    # CL, 升序, 参考《银河量化十周年专题之五：选股因子及因子择时新视角》, 银河证券, 20140909
    Factors.append(fo.RollingSum(window=5)((Close - Low) / Low, factor_args={"Name": "cl"}))

    # 5日收益率增速, 升序, 参考《银河量化十周年专题之五：选股因子及因子择时新视角》, 银河证券, 20140909
    Factors.append(calcMomentumChg(AdjClose, factor_args={"Name": "daily_return_5d_reg"}))

    # 收盘价和换手率的相关性
    Turnover_Close_5D_Corr = calcClsTrunCorrel(Turnover, AdjClose, IfTrading, factor_args={"Name": "turnover_close_5d_corr"})
    Turnover_Close_20D_Corr = calcClsTrunCorrel.new(args={"LookBack": [20 - 1, 20 - 1, 20 - 1]})(Turnover, AdjClose, IfTrading, factor_args={"Name": "turnover_close_20d_corr"})
    Turnover_Close_60D_Corr = calcClsTrunCorrel.new(args={"LookBack": [60 - 1, 60 - 1, 60 - 1]})(Turnover, AdjClose, IfTrading, factor_args={"Name": "turnover_close_60d_corr"})
    Factors.append(Turnover_Close_5D_Corr)
    Factors.append(Turnover_Close_20D_Corr)
    Factors.append(Turnover_Close_60D_Corr)

    # 每一天的最高价/最低价与成交量的相关系数
    High2Low_Vol_5D_Corr = calcHLVolCorrel(Low, High, Volume, IfTrading, factor_args={"Name": "high2low_vol_5d_corr"})
    High2Low_Vol_20D_Corr = calcHLVolCorrel.new(args={"LookBack": [20-1, 20-1, 20-1, 20-1]})(Low, High, Volume, IfTrading, factor_args={"Name": "high2low_vol_20d_corr"})
    High2Low_Vol_60D_Corr = calcHLVolCorrel.new(args={"LookBack": [60-1, 60-1, 60-1, 60-1]})(Low, High, Volume, IfTrading, factor_args={"Name": "high2low_vol_60d_corr"})
    Factors.append(High2Low_Vol_5D_Corr)
    Factors.append(High2Low_Vol_20D_Corr)
    Factors.append(High2Low_Vol_60D_Corr)

    # 过去一段时间最高价/最低价比值
    High2Low_5D = calcHL(Low, High, IfTrading, factor_args={"Name": "high2low_5d"})
    High2Low_20D = calcHL.new(args={"LookBack": [20-1, 20-1, 20-1]})(Low, High, IfTrading, factor_args={"Name": "high2low_20d"})
    High2Low_60D = calcHL.new(args={"LookBack": [60-1, 60-1, 60-1]})(Low, High, IfTrading, factor_args={"Name": "high2low_60d"})
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
    
    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_factor_alternative",
        MaxLookBack=365 * 2,
        IDType="A股",
        Author="麦冬"
    )