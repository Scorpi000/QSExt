# coding=utf-8
"""Barra 模型描述子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStockStatus
from QSExt.FactorDef.JY.stock_cn_industry import defFactor as defStockIndustry
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar
from QSExt.FactorDef.JY.stock_cn_consensus_expectation import defFactor as defStockConsensus


@FactorOperatorized(operator_type="Time", args={"Arity": 1, "ModelArgs": {"非空率": 0.8}, "LookBack": [21-1], "IDMode": "多ID", "DTMode": "单时点"})
def calcMonthReturn(f, idt, iid, x, args):
    DayRet = x[0]
    Rslt = np.empty((DayRet.shape[1],),dtype='float')+np.nan
    Mask = (np.sum(~np.isnan(DayRet),axis=0)/DayRet.shape[0]>=args['非空率'])
    Rslt = np.nanprod(1+DayRet,axis=0)-1
    Rslt[~Mask] = np.nan
    return Rslt

@FactorOperatorized(operator_type="Panel", args={"Arity": 3, "OutputMode": "全截面", "DTMode": "单时点", "LookBack":[0, 1, 1]})
def calcMarketReturn(f, idt, iid, x, args):
    Return = x[0][0,:]
    Weight = x[2][0,:]
    Mask = ((x[1][0,:]==1) & pd.notnull(Weight))
    Return = Return[Mask]
    Weight = Weight[Mask]
    MarketReturn = np.nansum(Return*Weight)/np.nansum(Weight)
    return np.zeros((x[0].shape[1],))+MarketReturn

@FactorOperatorized(operator_type="Section", args={"Arity": 3, "OutputMode": "全截面", "DTMode": "单时点"})
def standardize(f, idt, iid, x, args):
    Mask = ((x[2]==1) & pd.notnull(x[0]) & pd.notnull(x[1]))
    Weight = x[1][Mask]
    Data = x[0][Mask]
    Avg = np.nansum(Data*(Weight/np.sum(Weight)))
    Std = np.nanstd(Data)
    return (x[0]-Avg)/Std

@FactorOperatorized(operator_type="Section", args={"Arity": 3, "OutputMode": "全截面", "DTMode": "单时点"})
def calcNLSIZE(f, idt, iid, x, args):
    LNCAP = x[0].astype('float')
    LNCAP_Cube = LNCAP**3
    Cap = x[1]
    NLSIZE = np.zeros(LNCAP.shape)+np.nan
    # 取出非Null值
    Mask = ((~np.isnan(LNCAP)) & (x[2]==1))
    LNCAP = LNCAP[Mask]
    LNCAP_Cube = LNCAP_Cube[Mask]
    Cap = Cap[Mask]
    Cap = Cap/np.sum(Cap)
    # LNCAP^3关于LNCAP回归取残差项
    nLen = LNCAP.shape[0]
    xMean = np.mean(LNCAP)
    yMean = np.mean(LNCAP_Cube)
    Beta = (np.sum(LNCAP*LNCAP_Cube*Cap)-np.sum(LNCAP*Cap)*np.sum(LNCAP_Cube*Cap))/(np.sum(LNCAP**2*Cap)-np.sum(Cap*LNCAP)**2)
    Alpha = yMean-xMean*Beta
    NLSIZE[Mask] = LNCAP_Cube-Alpha-Beta*LNCAP
    return NLSIZE

@FactorOperatorized(operator_type="Time", args={"Arity": 3, "ModelArgs": {"非空率": 0.8, "半衰期": 63}, "LookBack": [252-1, 252-1, 252-1]})
def calcBETA(f, idt, iid, x, args):
    ExcessReturn = x[0]-x[2]
    MarketExcessReturn = x[1]-x[2]
    WindowLen = ExcessReturn.shape[0]
    Weight = f.UserData.get("指数权重")
    if Weight is None:
        Weight = (0.5**(1/args["半衰期"]))**np.arange(WindowLen)
        Weight = Weight[::-1]/np.sum(Weight)
        f.UserData['指数权重'] = Weight
    Mask = (~(np.isnan(ExcessReturn) | np.isnan(MarketExcessReturn)))
    if np.sum(Mask)/WindowLen<args['非空率']: return np.nan
    ExcessReturn = ExcessReturn[Mask]
    MarketExcessReturn = MarketExcessReturn[Mask]
    Weight = Weight[Mask]
    TotalWeight = np.sum(Weight)
    Temp = np.nansum(Weight*MarketExcessReturn)
    Rslt = TotalWeight * np.nansum(Weight * ExcessReturn * MarketExcessReturn) - Temp * np.nansum(Weight * ExcessReturn)
    Rslt = Rslt / (TotalWeight * np.nansum(Weight * MarketExcessReturn * MarketExcessReturn) - Temp**2)
    return (Rslt if np.isfinite(Rslt) else np.nan)

@FactorOperatorized(operator_type="Time", args={"Arity": 2, "ModelArgs": {'窗口长度': 504, '半衰期': 126, '非空率': 0.8}, "LookBack": [504+21-2, 504+21-2], "IDMode":"多ID"})
def calcRSTR(f, idt, iid, x, args):
    WindowLen = args['窗口长度']
    Weight = f.UserData.get("指数权重")
    if Weight is None:
        Weight = (0.5**(1/args["半衰期"]))**np.arange(WindowLen)
        Weight = Weight[::-1]/np.sum(Weight)
        f.UserData['指数权重'] = Weight
    Return = x[0][:WindowLen, :].copy()
    Return[Return<=-1] = np.nan
    RiskFreeReturn = x[1][:WindowLen].copy()
    RiskFreeReturn[pd.isnull(RiskFreeReturn) | (RiskFreeReturn<=-1)] = 0.0
    Mask = (~np.isnan(Return))
    TotalWeight = np.sum(Mask.T*Weight, axis=1)
    Rslt = np.nansum((np.log(1 + Return) - np.log(1 + RiskFreeReturn)).T*Weight, axis=1)
    Rslt = np.where(np.sum(Mask, axis=0) / WindowLen < args['非空率'], np.nan, Rslt)
    return Rslt / TotalWeight

@FactorOperatorized(operator_type="Time", args={"Arity": 2, "ModelArgs": {'半衰期': 42, '非空率': 0.8}, "LookBack": [252-1, 252-1], "IDMode": "多ID"})
def calcDASTD(f, idt, iid, x, args):
    ExcessReturn = x[0]-x[1]
    WindowLen = ExcessReturn.shape[0]
    Weight = f.UserData.get("指数权重")
    if Weight is None:
        Weight = (0.5**(1/args["半衰期"]))**np.arange(WindowLen)
        Weight = Weight[::-1] / np.sum(Weight)
        f.UserData['指数权重'] = Weight
    Mask = (~np.isnan(ExcessReturn))
    TotalWeight = np.nansum(Weight * Mask.T, axis=1)
    Avg = np.nansum(ExcessReturn.T * Weight, axis=1) / TotalWeight
    Rslt = (np.nansum(Weight * (ExcessReturn-Avg).T ** 2, axis=1) / TotalWeight) ** 0.5
    Rslt = np.where(np.sum(Mask, axis=0) / WindowLen < args['非空率'], np.nan, Rslt)
    return Rslt

@FactorOperatorized(operator_type="Time", args={"Arity": 2, "ModelArgs": {'T1': 21, 'T': 12, '非空率': 0.8}, "LookBack": [21*(12-1), 21*(12-1)], "IDMode": "多ID"})
def calcCMRA(f, idt, iid, x, args):
    MReturn = x[0]
    MonthInds = np.arange(0, args['T1']*(args['T']-1)+1, args['T1'])
    RiskFreeRate = x[1][MonthInds, :].copy()
    RiskFreeRate[RiskFreeRate <= -1] = np.nan
    MReturn = MReturn[MonthInds, :].copy()
    MReturn[MReturn<=-1] = np.nan
    Temp = np.log(MReturn + 1) - np.log(RiskFreeRate + 1)
    Mask = np.isnan(Temp)
    NaMask = (np.sum(~Mask,axis=0) / args["T"] < args['非空率'])
    Temp[Mask] = 0.0
    Temp = np.cumsum(Temp, axis=0)
    Temp[Mask] = np.nan
    ZMax = np.nanmax(Temp, axis=0)
    ZMin = np.nanmin(Temp, axis=0)
    Rslt = np.log(1 + ZMax) - np.log(1 + ZMin)
    Rslt[NaMask | np.isinf(Rslt)] = np.nan
    return Rslt

@FactorOperatorized(operator_type="Time", args={"Arity": 4, "ModelArgs": {'半衰期': 63,'非空率': 0.8}, "LookBack": [252-1, 252-1, 1-1, 252-1]})
def calcEPSILON(f, idt, iid, x, args):
    ExcessReturn = x[0] - x[3]
    iExcessReturn = ExcessReturn[-1]
    MarketExcessReturn = x[1] - x[3]
    iMarketExcessReturn = MarketExcessReturn[-1]
    WindowLen = ExcessReturn.shape[0]
    Weight = f.UserData.get("指数权重")
    if Weight is None:
        Weight = (0.5**(1 / args["半衰期"]))**np.arange(WindowLen)
        Weight = Weight[::-1] / np.sum(Weight)
        f.UserData['指数权重'] = Weight
    Mask = (~(np.isnan(ExcessReturn) | np.isnan(MarketExcessReturn)))
    if np.sum(Mask) / WindowLen < args['非空率']: return np.nan
    Beta = x[2][-1]
    ExcessReturn = ExcessReturn[Mask]
    MarketExcessReturn = MarketExcessReturn[Mask]
    Weight = Weight[Mask]
    Weight = Weight / np.sum(Weight)
    Alpha = np.nansum(ExcessReturn * Weight) - Beta * np.nansum(MarketExcessReturn * Weight)
    return iExcessReturn - Alpha - Beta * iMarketExcessReturn

@FactorOperatorized(operator_type="Time", args={"Arity": 1, "ModelArgs": {'半衰期': 63, '非空率': 0.8}, "LookBack": [252-1], "IDMode": "多ID"})
def calcHSIGMA(f, idt, iid, x, args):
    Epsilon = x[0]
    WindowLen = Epsilon.shape[0]
    Weight = f.UserData.get("指数权重")
    if Weight is None:
        Weight = (0.5 ** (1/args["半衰期"])) ** np.arange(WindowLen)
        Weight = Weight[::-1] / np.sum(Weight)
        f.UserData['指数权重'] = Weight
    Mask = (~np.isnan(Epsilon))
    TotalWeight = np.sum(Weight * Mask.T, axis=1)
    Avg = np.nansum(Epsilon.T * Weight, axis=1) / TotalWeight
    Rslt = (np.nansum(Weight * (Epsilon - Avg).T ** 2, axis=1) / TotalWeight) ** 0.5
    Mask = (np.sum(Mask, axis=0) / WindowLen < args['非空率'])
    Rslt[Mask] = np.nan
    return Rslt

@FactorOperatorized(operator_type="Time", args={"Arity": 2, "ModelArgs": {'非空率': 0.8}, "LookBack": [21-1, 21-1], "IDMode": "多ID"})
def calcSTOM(f, idt, iid, x, args):
    Turnover = x[0]
    TradeStatus = x[1]
    WindowLen = Turnover.shape[0]
    Rslt = np.log(np.nansum(Turnover, axis=0))
    Mask = (np.sum((TradeStatus==1), axis=0) / WindowLen < args['非空率'])
    Rslt[Mask] = np.nan
    return Rslt

@FactorOperatorized(operator_type="Time", args={"Arity": 1, "ModelArgs": {'T': 3, 'T1': 21, '非空数': 2}, "LookBack": [21*(3-1)], "IDMode": "多ID"})
def calcSTOQ(f, idt, iid, x, args):
    T = args['T']
    T1 = args['T1']
    STOM = x[0][np.arange(0, T1*(T-1)+1, T1), :]
    NotNANum = np.sum(pd.notnull(STOM), axis=0)
    Rslt = np.log(np.nansum(np.exp(STOM), axis=0) / NotNANum)
    Rslt[NotNANum < args['非空数']] = np.nan
    return Rslt


def defFactor(fdi: FactorDefInput):
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    ND_RF = fdi.ModelArgs.get("ND_RF", 360)
    
    # ### 行情因子 #################################################################################
    StockDayBarDef = defStockDayBar(fdi=fdi)
    DayTurnover = StockDayBarDef.getFactor(factor_name="turnover")# %
    TotalCap = StockDayBarDef.getFactor("total_cap")# 万元
    DayReturn = StockDayBarDef.getFactor("chg_rate")
    
    StockStatusDef = defStockStatus(fdi=fdi)
    IsTrading = StockStatusDef.getFactor("if_trading")
    ST = StockStatusDef.getFactor("st")
    ListDayNum = StockStatusDef.getFactor("listed_days")
    IsListed = StockStatusDef.getFactor("if_listed")
    
    StockIndustryDef = defStockIndustry(fdi=fdi)
    Industry = StockIndustryDef.getFactor(factor_name="barra_industry")
    Factors.append(Industry)
    
    where, notnull = fo.Where(), fo.NotNull()
    
    # ### Estimation Universe, ESTU ###########################################################################
    ESTU = rename(((ListDayNum>=30) & (fo.RollingApply(func=np.nansum, window=252)(notnull(ST))==0) & notnull(Industry) & notnull(TotalCap)), factor_name="ESTU")
    Factors.append(ESTU)
    
    # ### 财务因子 #################################################################################
    StockConsensusDef = defStockConsensus(fdi=fdi)
    PredictedEarnings = StockConsensusDef.getFactor(factor_name="net_profit_fwd12m")
    PredictedEarningsFY0 = StockConsensusDef.getFactor(factor_name="net_profit_fy0")
    PredictedEarningsFY2 = StockConsensusDef.getFactor(factor_name="net_profit_fy2")
    
    CashEarnings_TTM = JYDB.getTable("现金流量表_新会计准则", args={"Calc":"TTM", "ReportDate":"所有"}).getFactor("经营活动产生的现金流量净额")

    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType":"TTM", "ReportDate":"所有"})
    Earnings_TTM = FT.getFactor("归属于母公司所有者的净利润")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType":"最新", "ReportDate":"年报"})
    Earnings_LYR = FT.getFactor("归属于母公司所有者的净利润")

    FT = JYDB.getTable("公司主要财务分析指标_新会计准则", args={"CalcType":"最新", "ReportDate":"年报", "YearLookBack":0})
    EPS0 = FT.getFactor("基本每股收益(元-股)")
    SPS0 = FT.getFactor("每股营业收入(元-股)")
    FT = JYDB.getTable("公司主要财务分析指标_新会计准则", args={"CalcType":"最新", "ReportDate":"年报", "YearLookBack":1})
    EPS1 = FT.getFactor("基本每股收益(元-股)")
    SPS1 = FT.getFactor("每股营业收入(元-股)")
    FT = JYDB.getTable("公司主要财务分析指标_新会计准则", args={"CalcType":"最新", "ReportDate":"年报", "YearLookBack":2})
    EPS2 = FT.getFactor("基本每股收益(元-股)")
    SPS2 = FT.getFactor("每股营业收入(元-股)")
    FT = JYDB.getTable("公司主要财务分析指标_新会计准则", args={"CalcType":"最新", "ReportDate":"年报", "YearLookBack":3})
    EPS3 = FT.getFactor("基本每股收益(元-股)")
    SPS3 = FT.getFactor("每股营业收入(元-股)")
    FT = JYDB.getTable("公司主要财务分析指标_新会计准则", args={"CalcType":"最新", "ReportDate":"年报", "YearLookBack":4})
    EPS4 = FT.getFactor("基本每股收益(元-股)")
    SPS4 = FT.getFactor("每股营业收入(元-股)")
    
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType":"最新", "ReportDate":"年报"})
    LongDebt = FT.getFactor("非流动负债合计")
    TotalAsset = FT.getFactor("资产总计")
    TotalDebt = FT.getFactor("负债合计")
    Equity_LYR = FT.getFactor("归属母公司股东权益合计")
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType":"最新", "ReportDate":"所有"})
    Equity_LR = FT.getFactor("归属母公司股东权益合计")

    # ### 收益率 ###########################################################################
    MonthReturn = calcMonthReturn(DayReturn, factor_args={"Name": "月收益率"})
    MarketReturn = calcMarketReturn(DayReturn, ESTU, TotalCap, factor_args={"Name": "市场日收益率"})
    
    RiskFreeRateID = "600020002"# 无风险利率 : 3月期国债利率
    # 无风险利率, 日频
    FT = JYDB.getTable("宏观基础指标数据", args={"LookBack": 0, "IgnorePublDate": False, "IgnoreTime": True})
    PowerNum = FT.getFactor("量纲系数")
    PowerNum = where(PowerNum, notnull(PowerNum), 0)
    RiskFreeRate = FT.getFactor("指标数据")
    RiskFreeRate = where(RiskFreeRate, notnull(RiskFreeRate), 0) / 100 * 10 ** PowerNum
    DayRiskFreeRate = fo.Disaggregate(aggr_ids=[RiskFreeRateID])(RiskFreeRate / ND_RF)
    MonthRiskFreeRate = fo.Disaggregate(aggr_ids=[RiskFreeRateID])(RiskFreeRate / 12)
    DayRiskFreeRate = MonthRiskFreeRate = 0# DEBUG

    # LNCAP
    LNCAP = fo.Log()(TotalCap, factor_args={"Name": "LNCAP"})
    Factors.append(LNCAP)

    # NLSIZE
    Size = standardize(LNCAP, TotalCap, ESTU, factor_args={"Name": "size"})
    NLSIZE = calcNLSIZE(Size, TotalCap, IsListed, factor_args={"Name": "NLSIZE"})
    Factors.append(NLSIZE)

    # BETA
    BETA = calcBETA(DayReturn, MarketReturn, DayRiskFreeRate, factor_args={"Name": "BETA"})
    Factors.append(BETA)

    # RSTR
    RSTR = calcRSTR(DayReturn, DayRiskFreeRate, factor_args={"Name": "RSTR"})
    Factors.append(RSTR)

    # DASTD
    DASTD = calcDASTD(DayReturn, DayRiskFreeRate, factor_args={"Name": "DASTD"})
    Factors.append(DASTD)

    # CMRA
    CMRA = calcCMRA(MonthReturn, MonthRiskFreeRate, factor_args={"Name": "CMRA"})
    Factors.append(CMRA)

    # HSIGMA
    EPSILON = calcEPSILON(DayReturn, MarketReturn, BETA, DayRiskFreeRate, factor_args={"Name": "EPSILON"})
    HSIGMA = calcHSIGMA(EPSILON, factor_args={"Name": "HSIGMA"})
    Factors.append(HSIGMA)

    # BTOP
    BTOP = rename(Equity_LR / TotalCap / 10000, factor_name="BTOP")
    Factors.append(BTOP)

    # STOM
    Mask = ((IsListed==1) & (IsTrading==1))
    STOM = calcSTOM(DayTurnover, Mask, factor_args={"Name": "STOM"})
    Factors.append(STOM)

    # STOQ
    STOQ = calcSTOQ(STOM, factor_args={"Name": "STOQ"})
    Factors.append(STOQ)

    # STOA
    STOA = calcSTOQ.new(args={"ModelArgs": {'T': 12, 'T1': 21, '非空数': 4}, "LookBack": [21*(12-1)]})(STOM, factor_args={"Name": "STOA"})
    Factors.append(STOA)

    # EPFWD
    EPFWD = rename(PredictedEarnings / TotalCap / 10000, factor_name="EPFWD")
    Factors.append(EPFWD)

    # CETOP
    CETOP = rename(CashEarnings_TTM / TotalCap / 10000, factor_name="CETOP")
    Factors.append(CETOP)

    # ETOP
    ETOP = rename(Earnings_TTM / TotalCap / 10000, factor_name="ETOP")
    Factors.append(ETOP)

    # EGRLF
    EGRLF = 1 + (PredictedEarningsFY2 - Earnings_LYR) / abs(Earnings_LYR)
    EGRLF = rename(where(1, EGRLF>=0, -1) * abs(EGRLF) ** (1/3) - 1, factor_name="EGRLF")
    Factors.append(EGRLF)

    # EGRSF
    EGRSF = rename((PredictedEarningsFY0 - Earnings_LYR) / abs(Earnings_LYR), factor_name="EGRSF")
    Factors.append(EGRSF)

    # EGRO
    EGRO = fo.RegressChangeRate()(EPS4, EPS3, EPS2, EPS1, EPS0, factor_args={"Name": "EGRO"})
    Factors.append(EGRO)

    # SGRO
    SGRO = fo.RegressChangeRate()(SPS4, SPS3, SPS2, SPS1, SPS0, factor_args={"Name": "SGRO"})
    Factors.append(SGRO)

    # MLEV
    MLEV = rename((LongDebt / 10000 + TotalCap) / TotalCap, factor_name="MLEV")
    Factors.append(MLEV)

    # DTOA
    DTOA = rename(TotalDebt / TotalAsset, factor_name="DTOA")
    Factors.append(DTOA)

    # BLEV
    BLEV = rename((LongDebt + Equity_LYR) / Equity_LYR, factor_name="BLEV")
    Factors.append(BLEV)
    
    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_factor_barra_descriptor",
        MaxLookBack=max(3650, StockConsensusDef.MaxLookBack, StockDayBarDef.MaxLookBack, StockIndustryDef.MaxLookBack, StockStatusDef.MaxLookBack), 
        IDType="A股",
        Author="麦冬"
    )
