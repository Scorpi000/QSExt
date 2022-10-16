# coding=utf-8
"""另类因子(TODO)"""
import datetime as dt
import UpdateDate
import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.api as QS
from Fun_Lib import calcQuantilePortfolio

Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

Factors = []

WDB = QS.FactorDB.WindDB2()
HDB = QS.FactorDB.HDF5DB()
HDB.connect()

Factors = []

# ### Level2 指标因子 #############################################################################
FT = WDB.getTable("中国A股Level2指标")
ActiveBuyAmount = FT.getFactor("主买总额(万元)")
ActiveSellAmount = FT.getFactor("主卖总额(万元)")
ActiveBuyVolume = FT.getFactor("主买总量(手)")
ActiveSellVolume = FT.getFactor("主卖总量(手)")

# ### 行情因子 #############################################################################
FT = HDB.getTable("ElementaryFactor")
DayReturn = FT.getFactor("日收益率")
FloatCap_sig = FT.getFactor("流通市值")# 万元
MarketCap_sig = FT.getFactor("总市值")# 万元
Turnover = FT.getFactor("换手率")# %
Volume = FT.getFactor("成交量")# 手
Amount = FT.getFactor("成交金额")# 千元
TradeStatus = FT.getFactor("交易状态")
Close = FT.getFactor("收盘价")
Low = FT.getFactor("最低价")
High = FT.getFactor("最高价")
AdjClose = FT.getFactor("复权收盘价")

#--为FamaFrench准备
ST = FT.getFactor("特殊处理")
ListDays = FT.getFactor("上市天数")
Weight = FT.getFactor("流通市值")
FT = HDB.getTable("StyleValueFactor")# ### 基础因子准备之--估值因子表
BP = FT.getFactor("BP_LR")


# ### 财务因子 ##########################################################################
Asset = WDB.getTable("中国A股资产负债表").getFactor("资产总计", args={"计算方法":"最新", "报告期":"所有"})
Sales_TTM = WDB.getTable("中国A股利润表").getFactor("营业收入", args={"计算方法":"TTM", "报告期":"所有"})

# ### 企业管理因子 ##########################################################################
Num_Emp = WDB.getTable("A股员工人数变更").getFactor("员工人数(人)", args={"日期字段":"公告日期", "回溯天数":9999})


# ### Tier1 规模类因子 ##########################################################################
MarketCap = Factorize(MarketCap_sig,"MarketCap")#--总市值
FloatCap = Factorize(FloatCap_sig,"FloatCap")#--流通市值
Asset_LR = Factorize(Asset,"Asset_LR")#--总资产
Revenue_TTM = Factorize(Sales_TTM,"Revenue_TTM")#--营业收入
Factors.append(MarketCap)
Factors.append(FloatCap)
Factors.append(Asset_LR)
Factors.append(Revenue_TTM)

Num_Emp = Factorize(Num_Emp,"Num_Emp")#-员工人数
Factors.append(Num_Emp)

MktCap_Ln = Factorize(fd.log(MarketCap_sig),"MktCap_Ln")#--总市值对数
Factors.append(MktCap_Ln)

FloatCap_Ln = Factorize(fd.log(FloatCap_sig),"FloatCap_Ln")#--流通市值对数
Factors.append(FloatCap_Ln)

Asset_LR_Ln = Factorize(fd.log(Asset),"Asset_LR_Ln")#--总资产对数
Factors.append(Asset_LR_Ln)

Revenue_TTM_Ln = Factorize(fd.log(Sales_TTM),"Revenue_TTM_Ln")#--营业收入对数
Factors.append(Revenue_TTM_Ln)

FT = WDB.getTable("中国A股日行情估值指标")
Float_Stk_Nums = FT.getFactor("当日自由流通股本", new_name="自由流通股本")
FT = WDB.getTable("中国A股日行情")
Close=FT.getFactor("收盘价(元)", new_name="收盘价")
PreClose, AdjFactor = FT.getFactor("昨收盘价(元)", new_name="昨收盘价"), FT.getFactor("复权因子")
Pre_AdjClose = Factorize(AdjFactor * PreClose, factor_name="昨复权收盘价")

Free_FloatCap = Factorize(Float_Stk_Nums*Close,"Free_FloatCap")#--自由流通市值
FreeFloatCap_Ln = Factorize(fd.log(Free_FloatCap),"FreeFloatCap_Ln")#--自由流通市值对数
Factors.append(Free_FloatCap)
Factors.append(FreeFloatCap_Ln)
# ### Tier2 风险因子 ##########################################################################
Mask = ((TradeStatus!="停牌") & fd.notnull(TradeStatus))
Mask_20D = (fd.rolling_sum(Mask,20)>=20*0.8)
Mask_60D = (fd.rolling_sum(Mask,60)>=60*0.8)
Mask_240D = (fd.rolling_sum(Mask,240)>=240*0.8)

# ### Tier2.1 波动性因子 ##########################################################################
RealizedVolatility_60D = Factorize(fd.where(fd.rolling_std(DayReturn,60,min_periods=2),Mask_60D,np.nan),"RealizedVolatility_60D")
Factors.append(RealizedVolatility_60D)

RealizedVolatility_240D = Factorize(fd.where(fd.rolling_std(DayReturn,240,min_periods=2),Mask_240D,np.nan),"RealizedVolatility_240D")
Factors.append(RealizedVolatility_240D)

RealizedSkewness_240D = Factorize(fd.where(fd.rolling_skew(DayReturn,240,min_periods=2),Mask_240D,np.nan),"RealizedSkewness_240D")
Factors.append(RealizedSkewness_240D)


RealizedSkewness_60D = Factorize(fd.where(fd.rolling_skew(DayReturn,60,min_periods=2),Mask_60D,np.nan),"RealizedSkewness_60D")
Factors.append(RealizedSkewness_60D)


RealizedKurtosis_240D = Factorize(fd.where(fd.rolling_kurt(DayReturn,240,min_periods=2),Mask_240D,np.nan),"RealizedKurtosis_240D")
Factors.append(RealizedKurtosis_240D)

RealizedKurtosis_60D = Factorize(fd.where(fd.rolling_kurt(DayReturn,60,min_periods=2),Mask_60D,np.nan),"RealizedKurtosis_60D")
Factors.append(RealizedKurtosis_60D)

Close_Ln = Factorize(fd.log(Close),"Close_Ln")#--收盘价的自然对数
Factors.append(Close_Ln)

#计算MaxReturn_20D-->从动量反转转移过来
MaxReturn_20D = Factorize(fd.rolling_max(DayReturn,window=20,min_periods=int(20*0.8)),"MaxReturn_20D")
Factors.append(MaxReturn_20D)

# ### Tier2.2 FamaFrench 特质波动率因子 ##########################################################################
# 因子收益率
def FactorReturnFun(f,idate,iid,x,args):
    FactorData = pd.Series(x[0][0,:])
    ReturnData = pd.Series(x[1][0,:])
    ST = pd.Series(x[2][0,:])
    ListDays = pd.Series(x[3][0,:])
    Weight = pd.Series(x[4][0,:])
    Mask = (pd.isnull(ST) & (ListDays>=6*30))
    PortfolioReturn,Temp = calcQuantilePortfolio(FactorData,ReturnData,Mask,weight_data=Weight,ascending=args["ascending"],n_group=3)
    return np.zeros((FactorData.shape[0],))+PortfolioReturn[0]-PortfolioReturn[-1]

BPLSRet = QS.FactorDB.PanelOperation("BP收益率", [BP,DayReturn,ST,ListDays,Weight], {"算子":FactorReturnFun,"参数":{"ascending":False}, "输出形式":"全截面", "回溯期数":[1,0,1,1,1]})

FloatCapLSRet = QS.FactorDB.PanelOperation("流通市值收益率", [FloatCap_sig, DayReturn, ST,ListDays,Weight], {"算子":FactorReturnFun,"参数":{"ascending":True}, "输出形式":"全截面", "回溯期数":[1,0,1,1,1]})

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
#MarketRet = PanelOperation.PanelOperate("市场收益率",[DayReturn,ST,ListDays,Weight],{"算子":MarketReturnFun,"参数":{},"输出形式":"全截面","回溯期数":[0,1,1,1]},data_type="double")
MarketRet = QS.FactorDB.PanelOperation("市场收益率", [DayReturn,ST,ListDays,Weight], {"算子":MarketReturnFun,"参数":{}, "输出形式":"全截面", "回溯期数":[0,1,1,1]})

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
RegressResult_20D = QS.FactorDB.TimeOperation(name="RegressResult", descriptors=[DayReturn,FloatCapLSRet,BPLSRet,MarketRet], sys_args={"算子": RegressFun, "回溯期数": [20,20,20,20], "数据类型":"string"})
RegressResult_240D = QS.FactorDB.TimeOperation(name="RegressResult", descriptors=[DayReturn,FloatCapLSRet,BPLSRet,MarketRet], sys_args={"算子": RegressFun, "回溯期数": [240,240,240,240], "数据类型":"string"})


Factors.append(fd.fetch(RegressResult_20D,0,factor_name="IVFF_20D"))
Factors.append(fd.fetch(RegressResult_20D,1,factor_name="IVR_20D"))

# ### Tier3 流动性因子 ##########################################################################
Amount_20D_Avg = Factorize(fd.where(fd.rolling_mean(Amount,20,min_periods=2),Mask_20D,np.nan),"Amount_20D_Avg")
Factors.append(Amount_20D_Avg)

Amount_240D_Avg = Factorize(fd.where(fd.rolling_mean(Amount,240,min_periods=2),Mask_240D,np.nan),"Amount_240D_Avg")
Factors.append(Amount_240D_Avg)

Turnover_20D_Avg = Factorize(fd.where(fd.rolling_mean(Turnover,20,min_periods=2),Mask_20D,np.nan),"Turnover_20D_Avg")
Factors.append(Turnover_20D_Avg)

Turnover_240D_Avg = Factorize(fd.where(fd.rolling_mean(Turnover,240,min_periods=2),Mask_240D,np.nan),"Turnover_240D_Avg")
Factors.append(Turnover_240D_Avg)

ILLIQ = 10**6*(abs(DayReturn)/Amount)
ILLIQ_20D = Factorize(fd.where(fd.rolling_mean(ILLIQ,20,min_periods=2),Mask_20D,np.nan),"ILLIQ_20D")
Factors.append(ILLIQ_20D)

ILLIQ_240D = Factorize(fd.where(fd.rolling_mean(ILLIQ,240,min_periods=2),Mask_240D,np.nan),"ILLIQ_240D")
Factors.append(ILLIQ_240D)

VolAvg_20D = fd.where(fd.rolling_mean(Volume,20,min_periods=2),Mask_20D,np.nan)
VolAvg_240D = fd.where(fd.rolling_mean(Volume,240,min_periods=2),Mask_240D,np.nan)
Vol_20D_240D_Avg = Factorize(VolAvg_20D/VolAvg_240D,"Vol_20D_240D_Avg")
Factors.append(Vol_20D_240D_Avg)
VolStd_20D = fd.where(fd.rolling_std(Volume,20,min_periods=2),Mask_20D,np.nan)
Vol_20D_CV = Factorize(VolStd_20D/VolAvg_20D,"Vol_20D_CV")
Factors.append(Vol_20D_CV)


# ### Tier4 技术性因子 ##########################################################################
# 资金流向因子 
STVDelta = WDB.getTable("中国A股资金流向数据").getFactor("散户量差(仅主动)(手)")# 手
SmallTradeFlow_1D = Factorize(STVDelta/Volume,"SmallTradeFlow_1D")
Factors.append(SmallTradeFlow_1D)

#计算Price_52WHigh-->从动量反转转移过来
def Price_52WHighFun(f,idt,iid,x,args):
    Close = x[0]
    LastClose = Close[-1,:]
    TradeStatus = x[1]
    HighClose = np.nanmax(Close)
    Len = TradeStatus.shape[0]
    Mask = (np.sum((TradeStatus!="停牌") & pd.notnull(TradeStatus), axis=0)/Len<args['非空率'])
    LastClose[(LastClose==0) | Mask] = np.nan    
    return HighClose/LastClose-1
Close2MaxClose_240D = QS.FactorDB.TimeOperation('Close2MaxClose_240D',[AdjClose,TradeStatus],{'算子':Price_52WHighFun,'参数':{"非空率":0.8},'回溯期数':[240-1,240-1],"运算ID":"多ID"})
Factors.append(Close2MaxClose_240D)

#计算PriceTrend_240D-->从动量反转转移过来
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
CloseTrend_240D_Reg = QS.FactorDB.TimeOperation('CloseTrend_240D_Reg',[AdjClose],{'算子':RegressionFun,'参数':{"非空率":0.8},'回溯期数':[240-1]})
Factors.append(CloseTrend_240D_Reg)


# CL, 升序, 参考《银河量化十周年专题之五：选股因子及因子择时新视角》, 银河证券, 20140909-->从动量反转转移过来
Factors.append(Factorize(fd.rolling_sum((Close-Low)/Low,5),"CL"))

# BS, 升序, 参考《银河量化十周年专题之五：选股因子及因子择时新视角》, 银河证券, 20140909-->从动量反转转移过来
Factors.append(Factorize(fd.rolling_sum(ActiveBuyAmount-ActiveSellAmount,5),"BuyMinusSell_5D_Amount"))
Factors.append(Factorize(fd.rolling_sum(ActiveBuyVolume-ActiveSellVolume,5),"BuyMinusSell_5D_Vol"))

# 5日收益率增速, 升序, 参考《银河量化十周年专题之五：选股因子及因子择时新视角》, 银河证券, 20140909-->从动量反转转移过来
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
Factors.append(QS.FactorDB.TimeOperation('DayReturn_5D_Reg',[AdjClose],{'算子':MomentumChgFun,'参数':{"收益期":5,"回归期":5},'回溯期数':[5+5+1]}))
# ### Tier3.2一致预期因子 ##########################################################################
EPSNum_FY0 = HDB.getTable("WindConsensusFactor").getFactor("WEST_EPSNum_FY0")
Num_EPS_FY0 = Factorize(EPSNum_FY0,"Num_EPS_FY0")
Factors.append(Num_EPS_FY0)
# ### Tier3.3 RSI指标计算

def RSI_Fun(f, idt, iid, x, args):
    Close = x[0]
    Pre_Close = x[1]
    TradeStatus = x[2]
    Len = TradeStatus.shape[0]
    Mask = (np.sum((TradeStatus != "停牌") & pd.notnull(TradeStatus), axis=0) / Len < args['非空率'])
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

RSI_5D = QS.FactorDB.TimeOperation('RSI_5D',[AdjClose,Pre_AdjClose,TradeStatus],{'算子':RSI_Fun,'参数':{"非空率":0.8,'回测期':5},'回溯期数':[1000-1,1000-1,1000-1],"运算ID":"多ID"})
RSI_20D = QS.FactorDB.TimeOperation('RSI_20D',[AdjClose,Pre_AdjClose,TradeStatus],{'算子':RSI_Fun,'参数':{"非空率":0.8,'回测期':20},'回溯期数':[1000-1,1000-1,1000-1],"运算ID":"多ID"})
RSI_60D = QS.FactorDB.TimeOperation('RSI_60D',[AdjClose,Pre_AdjClose,TradeStatus],{'算子':RSI_Fun,'参数':{"非空率":0.8,'回测期':60},'回溯期数':[1000-1,1000-1,1000-1],"运算ID":"多ID"})
Factors.append(RSI_5D)
Factors.append(RSI_20D)
Factors.append(RSI_60D)

# ### Tier3.4 乖离率指标计算
def Bias_Fun(f, idt, iid, x, args):
    #Mask = (x[1]==1)
    Data = x[0]
    TradeStatus=x[1]
    Len = TradeStatus.shape[0]
    Mask = (np.sum((TradeStatus!="停牌") & pd.notnull(TradeStatus), axis=0)/Len<args['非空率'])
    Avg = np.nanmean(Data,axis=0)
    Bias=(Data[-1]-Avg)/Avg
    Bias[Mask] = np.nan
    return Bias
Bias_5D = QS.FactorDB.TimeOperation(name="Bias_5D", descriptors=[AdjClose,TradeStatus], sys_args={"算子": Bias_Fun,'参数':{"非空率":0.8}, "回溯期数": [5-1,5-1],"运算ID":"多ID"})
Bias_20D = QS.FactorDB.TimeOperation(name="Bias_20D", descriptors=[AdjClose,TradeStatus], sys_args={"算子": Bias_Fun,'参数':{"非空率":0.8}, "回溯期数": [20-1,20-1],"运算ID":"多ID"})
Bias_60D = QS.FactorDB.TimeOperation(name="Bias_60D", descriptors=[AdjClose,TradeStatus], sys_args={"算子": Bias_Fun,'参数':{"非空率":0.8}, "回溯期数": [60-1,60-1],"运算ID":"多ID"})
Factors.append(Bias_5D)
Factors.append(Bias_20D)
Factors.append(Bias_60D)

# ### Tier3.5 收盘价与换手率关系
FT = WDB.getTable("中国A股日行情估值指标")
Turnover = FT.getFactor("换手率")# %
from scipy import stats
def Cls_Trun_Correl_Fun(f, idt, iid, x, args):
    Turnover = x[0]
    AdjClose = x[1]
    TradeStatus=x[2]
    Len = TradeStatus.shape[0]
    Mask = (np.sum((TradeStatus!="停牌") & pd.notnull(TradeStatus), axis=0)/Len<args['非空率'])
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

Turnover_Close_5D_Corr = QS.FactorDB.TimeOperation(name="Turnover_Close_5D_Corr", descriptors=[Turnover,AdjClose,TradeStatus], sys_args={"算子": Cls_Trun_Correl_Fun, '参数':{"非空率":0.8},"回溯期数": [5-1,5-1,5-1],"运算ID":"多ID"})
Turnover_Close_20D_Corr = QS.FactorDB.TimeOperation(name="Turnover_Close_20D_Corr", descriptors=[Turnover,AdjClose,TradeStatus], sys_args={"算子": Cls_Trun_Correl_Fun, '参数':{"非空率":0.8},"回溯期数": [20-1,20-1,20-1],"运算ID":"多ID"})
Turnover_Close_60D_Corr = QS.FactorDB.TimeOperation(name="Turnover_Close_60D_Corr", descriptors=[Turnover,AdjClose,TradeStatus], sys_args={"算子": Cls_Trun_Correl_Fun, '参数':{"非空率":0.8},"回溯期数": [60-1,60-1,60-1],"运算ID":"多ID"})
Factors.append(Turnover_Close_5D_Corr)
Factors.append(Turnover_Close_20D_Corr)
Factors.append(Turnover_Close_60D_Corr)

# ### Tier3.6 每一天的最高价/最低价与成交量的相关系数
def HL_Vol_Correl_Fun(f, idt, iid, x, args):
    Low = x[0]
    High = x[1]
    Vol = x[2]
    TradeStatus=x[3]
    Len = TradeStatus.shape[0]
    Mask = (np.sum((TradeStatus!="停牌") & pd.notnull(TradeStatus), axis=0)/Len<args['非空率'])
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
High2Low_Vol_5D_Corr = QS.FactorDB.TimeOperation('High2Low_Vol_5D_Corr',[Low,High,Volume,TradeStatus],{'算子':HL_Vol_Correl_Fun,'参数':{"非空率":0.8},'回溯期数':[5-1,5-1,5-1,5-1],"运算ID":"多ID"})
High2Low_Vol_20D_Corr = QS.FactorDB.TimeOperation('High2Low_Vol_20D_Corr',[Low,High,Volume,TradeStatus],{'算子':HL_Vol_Correl_Fun,'参数':{"非空率":0.8},'回溯期数':[20-1,20-1,20-1,20-1],"运算ID":"多ID"})
High2Low_Vol_60D_Corr = QS.FactorDB.TimeOperation('High2Low_Vol_60D_Corr',[Low,High,Volume,TradeStatus],{'算子':HL_Vol_Correl_Fun,'参数':{"非空率":0.8},'回溯期数':[60-1,60-1,60-1,60-1],"运算ID":"多ID"})
Factors.append(High2Low_Vol_5D_Corr)
Factors.append(High2Low_Vol_20D_Corr)
Factors.append(High2Low_Vol_60D_Corr)

# ### Tier3.7 过去一段时间最高价/最低价比值
def HL_Fun(f, idt, iid, x, args):
    Low = x[0]
    High = x[1]
    TradeStatus = x[2]
    High_Max = np.max(High,axis=0)
    Low_Min = np.min(Low,axis=0)
    Len = TradeStatus.shape[0]
    Mask = (np.sum((TradeStatus!="停牌") & pd.notnull(TradeStatus), axis=0)/Len<args['非空率'])
    Low_Min[(Low_Min==0) | Mask] = np.nan
    Val=High_Max/Low_Min
    return Val
High2Low_5D = QS.FactorDB.TimeOperation(name="High2Low_5D", descriptors=[Low,High,TradeStatus], sys_args={"算子": HL_Fun,'参数':{"非空率":0.8}, "回溯期数": [5-1,5-1,5-1],"运算ID":"多ID"})
High2Low_20D = QS.FactorDB.TimeOperation(name="High2Low_20D", descriptors=[Low,High,TradeStatus], sys_args={"算子": HL_Fun,'参数':{"非空率":0.8}, "回溯期数": [20-1,20-1,20-1],"运算ID":"多ID"})
High2Low_60D = QS.FactorDB.TimeOperation(name="High2Low_60D", descriptors=[Low,High,TradeStatus], sys_args={"算子": HL_Fun,'参数':{"非空率":0.8}, "回溯期数": [60-1,60-1,60-1],"运算ID":"多ID"})
Factors.append(High2Low_5D)
Factors.append(High2Low_20D)
Factors.append(High2Low_60D)

if __name__=="__main__":
    WDB.connect()
    CFT = QS.FactorDB.CustomFT("StyleAlternativeFactor")
    CFT.addFactors(factor_list=Factors)
    
    IDs = WDB.getStockID(index_id="全体A股", is_current=False)
    #IDs = ["000001.SZ", "000003.SZ", "603297.SH"]# debug
    
    #if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2018, 8, 31, 23, 59, 59, 999999)
    #else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    #EndDT = dt.datetime(2018, 10, 31, 23, 59, 59, 999999)
    StartDT, EndDT = UpdateDate.StartDT, UpdateDate.EndDT
    
    DTs = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT-dt.timedelta(365000), end_dt=EndDT)

    TargetTable = "StyleAlternativeFactor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler)
    
    HDB.disconnect()
    WDB.disconnect()