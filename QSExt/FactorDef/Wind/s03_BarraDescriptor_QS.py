# coding=utf-8
"""Barra 模型描述子"""
import datetime as dt
import UpdateDate
import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

Factors = []

WDB = QS.FactorDB.WindDB2()
HDB = QS.FactorDB.HDF5DB()
HDB.connect()

Factors = []# 因子列表

# ### 行情因子 #################################################################################
FT = HDB.getTable("ElementaryFactor")
TradeStatus = FT.getFactor("交易状态")
DayTurnover = FT.getFactor("换手率")
TotalCap = FT.getFactor("总市值")
DayReturn = FT.getFactor("日收益率")
ST = FT.getFactor("特殊处理")
ListDayNum = FT.getFactor("上市天数")
IsListed = FT.getFactor("是否在市")


# ### 财务因子 #################################################################################
FT = WDB.getTable("中国A股盈利预测汇总")
PredictedEarnings = FT.getFactor("净利润平均值(万元)", args={"计算方法":"Fwd12M", "周期":"263001000", "回溯天数":180})# 万元
PredictedEarningsFY0 = FT.getFactor("净利润平均值(万元)", args={"计算方法":"FY0", "周期":"263001000", "回溯天数":180})# 万元
PredictedEarningsFY2 = FT.getFactor("净利润平均值(万元)", args={"计算方法":"FY2", "周期":"263001000", "回溯天数":180})# 万元

CashEarnings_TTM = WDB.getTable("中国A股现金流量表").getFactor("经营活动产生的现金流量净额", args={"计算方法":"TTM", "报告期":"所有"})

FT = WDB.getTable("中国A股利润表")
Earnings_TTM = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"TTM", "报告期":"所有"})
Earnings_LYR = FT.getFactor("净利润(不含少数股东损益)", args={"计算方法":"最新", "报告期":"年报"})

FT = WDB.getTable("中国A股资产负债表")
LongDebt = FT.getFactor("非流动负债合计", args={"计算方法":"最新", "报告期":"年报"})
TotalAsset = FT.getFactor("资产总计", args={"计算方法":"最新", "报告期":"年报"})
TotalDebt = FT.getFactor("负债合计", args={"计算方法":"最新", "报告期":"年报"})
Equity_LR = FT.getFactor("股东权益合计(不含少数股东权益)", args={"计算方法":"最新", "报告期":"所有"})
Equity_LYR = FT.getFactor("股东权益合计(不含少数股东权益)", args={"计算方法":"最新", "报告期":"年报"})

FT = WDB.getTable("中国A股财务指标")
EPS0 = FT.getFactor("基本每股收益", args={"计算方法":"最新", "报告期":"年报", "回溯年数":0})
EPS1 = FT.getFactor("基本每股收益", args={"计算方法":"最新", "报告期":"年报", "回溯年数":1})
EPS2 = FT.getFactor("基本每股收益", args={"计算方法":"最新", "报告期":"年报", "回溯年数":2})
EPS3 = FT.getFactor("基本每股收益", args={"计算方法":"最新", "报告期":"年报", "回溯年数":3})
EPS4 = FT.getFactor("基本每股收益", args={"计算方法":"最新", "报告期":"年报", "回溯年数":4})

SPS0 = FT.getFactor("每股营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":0})
SPS1 = FT.getFactor("每股营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":1})
SPS2 = FT.getFactor("每股营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":2})
SPS3 = FT.getFactor("每股营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":3})
SPS4 = FT.getFactor("每股营业收入", args={"计算方法":"最新", "报告期":"年报", "回溯年数":4})


# ### Barra CNE5 行业分类 #################################################################################
Wind3LevelIndustry = WDB.getTable("中国A股Wind行业分类").getFactor("行业代码", args={"分类级别":3})
def IndustryMapFun(f, idt, iid, x, args):
    IndustryCode = x[0]
    IndustryCode[pd.isnull(IndustryCode)] = "None"
    Rslt = np.empty(IndustryCode.shape,dtype='O')
    Rslt[(IndustryCode>="62100000") & (IndustryCode<"62150000")] = "Energy"
    Rslt[(IndustryCode=="62151010")] = "Chemicals"
    Rslt[(IndustryCode=="62151020")] = "Construction Materials"
    Rslt[(IndustryCode=="62151040")] = "Diversified Metals"
    Rslt[(IndustryCode=="62151030") | (IndustryCode=="62151050")] = "Materials"
    Rslt[(IndustryCode=="62201010")] = "Aerospace and Defense"
    Rslt[(IndustryCode=="62201020")] = "Building Products"
    Rslt[(IndustryCode=="62201030")] = "Construction and Engineering"
    Rslt[(IndustryCode=="62201040")] = "Electrical Equipment"
    Rslt[(IndustryCode=="62201050")] = "Industrial Conglomerates"
    Rslt[(IndustryCode=="62201060")] = "Industrial Machinery"
    Rslt[(IndustryCode=="62201070")] = "Trading Companies and Distributors"
    Rslt[(IndustryCode>="62202000") & (IndustryCode<"62203000")] = "Commercial and Professional Services"
    Rslt[(IndustryCode=="62203010") | (IndustryCode=="62203020")] = "Airlines"
    Rslt[(IndustryCode=="62203030")] = "Marine"
    Rslt[(IndustryCode=="62203040") | (IndustryCode=="62203050")] = "Road Rail and Transportation Infrastructure"
    Rslt[(IndustryCode>="62251000") & (IndustryCode<"62252000")] = "Automobiles and Components"
    Rslt[(IndustryCode=="62252010")] = "Household Durables (non-Homebuilding)"
    Rslt[(IndustryCode=="62252020") | (IndustryCode=="62252030")] = "Leisure Products Textiles Apparel and Luxury"
    Rslt[(IndustryCode>="62253000") & (IndustryCode<"62254000")] = "Hotels Restaurants and Leisure"
    Rslt[(IndustryCode>="62254000") & (IndustryCode<"62255000")] = "Media"
    Rslt[(IndustryCode>="62255000") & (IndustryCode<"62256000")] = "Retail"
    Rslt[(IndustryCode>="62301000") & (IndustryCode<"62302000")] = "Food Staples Retail Household Personal Prod"
    Rslt[(IndustryCode>="62303000") & (IndustryCode<"62304000")] = "Food Staples Retail Household Personal Prod"
    Rslt[(IndustryCode=="62302010")] = "Beverages"
    Rslt[(IndustryCode=="62302020")] = "Food Products"
    Rslt[(IndustryCode>="62350000") & (IndustryCode<"62400000")] = "Health"
    Rslt[(IndustryCode>="62401000") & (IndustryCode<"62402000")] = "Banks"
    Rslt[(IndustryCode>="62402000") & (IndustryCode<"62404000")] = "Diversified Financial Services"
    Rslt[(IndustryCode>="62404000") & (IndustryCode<"62405000")] = "Real Estate"
    Rslt[(IndustryCode>="62451000") & (IndustryCode<"62452000")] = "Software"
    Rslt[(IndustryCode>="62452000") & (IndustryCode<"62454000")] = "Hardware and Semiconductors"
    Rslt[(IndustryCode>="62500000") & (IndustryCode<"62550000")] = "Hardware and Semiconductors"
    Rslt[(IndustryCode>="62550000") & (IndustryCode<"62600000")] = "Utilities"
    Rslt[(IndustryCode>="62600000") & (IndustryCode<"62650000")] = "Real Estate"
    MissCode = IndustryCode[pd.isnull(Rslt) & (IndustryCode!="None")]
    if MissCode.shape[0]>0: print("未分类的行业代码 : "+str(MissCode))
    return Rslt
Industry = QS.FactorDB.PointOperation("Industry", [Wind3LevelIndustry], {"算子":IndustryMapFun, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"string"})
Factors.append(Industry)


# ### Estimation Universe, ESTU ###########################################################################
ESTU = Factorize(((ListDayNum>=30) & (fd.rolling_sum(fd.notnull(ST), window=252)==0) & fd.notnull(Industry) & fd.notnull(TotalCap)), factor_name="ESTU")
Factors.append(ESTU)


# ### 收益率 ###########################################################################
def MonthReturnFun(f, idt, iid, x, args):
    DayRet = x[0]
    Rslt = np.empty((DayRet.shape[1],),dtype='float')+np.nan
    Mask = (np.sum(~np.isnan(DayRet),axis=0)/DayRet.shape[0]>=args['非空率'])
    Rslt = np.nanprod(1+DayRet,axis=0)-1
    Rslt[~Mask] = np.nan
    return Rslt
MonthReturn = QS.FactorDB.TimeOperation("月收益率", [DayReturn], {"算子":MonthReturnFun, "参数":{"非空率":0.8}, "回溯期数":[21-1], "运算ID":"多ID"})
def MarketReturnFun(f, idt, iid, x, args):
    Return = x[0][0,:]
    Weight = x[2][0,:]
    Mask = ((x[1][0,:]==1) & pd.notnull(Weight))
    Return = Return[Mask]
    Weight = Weight[Mask]
    MarketReturn = np.nansum(Return*Weight)/np.nansum(Weight)
    return np.zeros((x[0].shape[1],))+MarketReturn
MarketReturn = QS.FactorDB.PanelOperation("市场日收益率", [DayReturn, ESTU, TotalCap], {"算子":MarketReturnFun, "输出形式":"全截面", "回溯期数":[0,1,1]})

DayRiskFreeRate, MonthRiskFreeRate = [], []# 无风险利率

# LNCAP
LNCAP = fd.log(TotalCap, factor_name="LNCAP")
Factors.append(LNCAP)

# NLSIZE
def StandardizeFun(f, idt, iid, x, args):
    Mask = ((x[2]==1) & pd.notnull(x[0]) & pd.notnull(x[1]))
    Weight = x[1][Mask]
    Data = x[0][Mask]
    Avg = np.nansum(Data*(Weight/np.sum(Weight)))
    Std = np.nanstd(Data)
    return (x[0]-Avg)/Std
Size = QS.FactorDB.SectionOperation("Size", [LNCAP, TotalCap, ESTU], {"算子":StandardizeFun, "输出形式":"全截面"})
def NLSIZEFun(f, idt, iid, x, args):
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
NLSIZE = QS.FactorDB.SectionOperation('NLSIZE', [Size, TotalCap, IsListed], {"算子":NLSIZEFun, "输出形式":"全截面"})
Factors.append(NLSIZE)

# BETA
def BETAFun(f, idt, iid, x, args):
    RiskFreeRate = args["无风险日利率"][0].ix[idt].values
    ExcessReturn = x[0]-RiskFreeRate
    MarketExcessReturn = x[1]-RiskFreeRate
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
BETAArgs = {"非空率":0.8, "半衰期":63, "无风险日利率":DayRiskFreeRate}
BETA = QS.FactorDB.TimeOperation('BETA', [DayReturn,MarketReturn], {"算子":BETAFun, "参数":BETAArgs, "回溯期数":[252-1,252-1]})
Factors.append(BETA)

# RSTR
def RSTRFun(f, idt, iid, x, args):
    WindowLen = args['窗口长度']
    Weight = f.UserData.get("指数权重")
    if Weight is None:
        Weight = (0.5**(1/args["半衰期"]))**np.arange(WindowLen)
        Weight = Weight[::-1]/np.sum(Weight)
        f.UserData['指数权重'] = Weight
    Return = x[0][:WindowLen,:]
    Return[Return<=-1] = np.nan
    RiskFreeReturn = args["无风险日利率"][0].ix[idt].values
    RiskFreeReturn = RiskFreeReturn[:WindowLen]
    RiskFreeReturn[pd.isnull(RiskFreeReturn) | (RiskFreeReturn<=-1)] = 0.0
    RiskFreeReturn = np.reshape(RiskFreeReturn, (RiskFreeReturn.shape[0], 1)).repeat(Return.shape[1], axis=1)
    Mask = (~np.isnan(Return))
    TotalWeight = np.sum(Mask.T*Weight,axis=1)
    Rslt = np.nansum((np.log(1+Return)-np.log(1+RiskFreeReturn)).T*Weight, axis=1)
    Rslt[np.sum(Mask,axis=0)/WindowLen<args['非空率']] = np.nan
    return Rslt / TotalWeight
RSTRArgs = {'窗口长度':504, '半衰期':126, '非空率':0.8, "无风险日利率":DayRiskFreeRate}
RSTR = QS.FactorDB.TimeOperation('RSTR', [DayReturn], {"算子":RSTRFun, "参数":RSTRArgs, "回溯期数":[504+21-2], "运算ID":"多ID"})
Factors.append(RSTR)

# DASTD
def DASTDFun(f, idt, iid, x, args):
    RiskFreeRate = args["无风险日利率"][0].ix[idt].values.reshape((x[0].shape[0], 1)).repeat(x[0].shape[1], axis=1)
    ExcessReturn = x[0]-RiskFreeRate
    WindowLen = ExcessReturn.shape[0]
    Weight = f.UserData.get("指数权重")
    if Weight is None:
        Weight = (0.5**(1/args["半衰期"]))**np.arange(WindowLen)
        Weight = Weight[::-1]/np.sum(Weight)
        f.UserData['指数权重'] = Weight
    Mask = (~np.isnan(ExcessReturn))
    TotalWeight = np.nansum(Weight*Mask.T,axis=1)
    Avg = np.nansum(ExcessReturn.T*Weight,axis=1)/TotalWeight
    Rslt = (np.nansum(Weight*(ExcessReturn-Avg).T**2,axis=1)/TotalWeight)**(1/2)
    Rslt[np.sum(Mask,axis=0)/WindowLen<args['非空率']] = np.nan
    return Rslt
DASTDArgs = {'半衰期':42, '非空率':0.8, "无风险日利率":DayRiskFreeRate}
DASTD = QS.FactorDB.TimeOperation('DASTD', [DayReturn], {"算子":DASTDFun, "参数":DASTDArgs, "回溯期数":[252-1], "运算ID":"多ID"})
Factors.append(DASTD)

# CMRA
def CMRAFun(f, idt, iid, x, args):
    MReturn = x[0]
    RiskFreeRate = args["无风险月利率"][0].ix[idt].values.reshape((x[0].shape[0], 1)).repeat(x[0].shape[1], axis=1)
    MonthInds = np.arange(0,args['T1']*(args['T']-1)+1,args['T1'])
    MReturn = MReturn[MonthInds,:]
    MReturn[MReturn<=-1] = np.nan
    RiskFreeRate = RiskFreeRate[MonthInds,:]
    RiskFreeRate[RiskFreeRate<=-1] = np.nan
    Temp = np.log(MReturn+1)-np.log(RiskFreeRate+1)
    Mask = np.isnan(Temp)
    NaMask = (np.sum(~Mask,axis=0)/args["T"]<args['非空率'])
    Temp[Mask] = 0.0
    Temp = np.cumsum(Temp,axis=0)
    Temp[Mask] = np.nan
    ZMax = np.nanmax(Temp,axis=0)
    ZMin = np.nanmin(Temp,axis=0)
    Rslt = np.log(1+ZMax)-np.log(1+ZMin)
    Rslt[NaMask | np.isinf(Rslt)] = np.nan
    return Rslt
CMRAArgs = {'T1':21,'T':12,'非空率':0.8, "无风险月利率":MonthRiskFreeRate}
CMRA = QS.FactorDB.TimeOperation('CMRA', [MonthReturn], {"算子":CMRAFun, "参数":CMRAArgs, "回溯期数":[21*(12-1)], "运算ID":"多ID"})
Factors.append(CMRA)

# HSIGMA
def EPSILONFun(f, idt, iid, x, args):
    RiskFreeRate = args["无风险日利率"][0].ix[idt].values
    ExcessReturn = x[0]-RiskFreeRate
    iExcessReturn = ExcessReturn[-1]
    MarketExcessReturn = x[1]-RiskFreeRate
    iMarketExcessReturn = MarketExcessReturn[-1]
    WindowLen = ExcessReturn.shape[0]
    Weight = f.UserData.get("指数权重")
    if Weight is None:
        Weight = (0.5**(1/args["半衰期"]))**np.arange(WindowLen)
        Weight = Weight[::-1]/np.sum(Weight)
        f.UserData['指数权重'] = Weight
    Mask = (~(np.isnan(ExcessReturn) | np.isnan(MarketExcessReturn)))
    if np.sum(Mask)/WindowLen<args['非空率']: return np.nan
    Beta = x[2][-1]
    ExcessReturn = ExcessReturn[Mask]
    MarketExcessReturn = MarketExcessReturn[Mask]
    Weight = Weight[Mask]
    Weight = Weight/np.sum(Weight)
    Alpha = np.nansum(ExcessReturn*Weight)-Beta*np.nansum(MarketExcessReturn*Weight)
    return iExcessReturn-Alpha-Beta*iMarketExcessReturn
EPSILONArgs = {'半衰期':63,'非空率':0.8, "无风险日利率":DayRiskFreeRate}
EPSILON = QS.FactorDB.TimeOperation('EPSILON', [DayReturn,MarketReturn,BETA], {"算子":EPSILONFun,"参数":EPSILONArgs,"回溯期数":[252-1,252-1,1-1]})
def HSIGMAFun(f, idt, iid, x, args):
    Epsilon = x[0]
    WindowLen = Epsilon.shape[0]
    Weight = f.UserData.get("指数权重")
    if Weight is None:
        Weight = (0.5**(1/args["半衰期"]))**np.arange(WindowLen)
        Weight = Weight[::-1]/np.sum(Weight)
        f.UserData['指数权重'] = Weight
    Mask = (~np.isnan(Epsilon))
    TotalWeight = np.sum(Weight*Mask.T,axis=1)
    Avg = np.nansum(Epsilon.T*Weight,axis=1)/TotalWeight
    Rslt = (np.nansum(Weight*(Epsilon-Avg).T**2,axis=1)/TotalWeight)**(1/2)
    Mask = (np.sum(Mask,axis=0)/WindowLen<args['非空率'])
    Rslt[Mask] = np.nan
    return Rslt
HSIGMAArgs = {'半衰期':63,'非空率':0.8}
HSIGMA = QS.FactorDB.TimeOperation('HSIGMA', [EPSILON], {"算子":HSIGMAFun,"参数":HSIGMAArgs,"回溯期数":[252-1],"运算ID":"多ID"})
Factors.append(HSIGMA)

# BTOP
BTOP = Factorize(Equity_LR / TotalCap / 10000, factor_name="BTOP")
Factors.append(BTOP)

# STOM
def STOMFun(f, idt, iid, x, args):
    Turnover = x[0]
    TradeStatus = x[1]
    WindowLen = Turnover.shape[0]
    Rslt = np.log(np.nansum(Turnover,axis=0))
    Mask = (np.sum((TradeStatus!="停牌") & pd.notnull(TradeStatus),axis=0)/WindowLen<args['非空率'])
    Rslt[Mask] = np.nan
    return Rslt
STOMArgs = {'非空率':0.8}
STOM = QS.FactorDB.TimeOperation('STOM', [DayTurnover,TradeStatus], {"算子":STOMFun,"参数":STOMArgs,"回溯期数":[21-1,21-1],"运算ID":"多ID"})
Factors.append(STOM)

# STOQ
def STOQFun(f, idt, iid, x, args):
    T = args['T']
    T1 = args['T1']
    STOM = x[0][np.arange(0,T1*(T-1)+1,T1),:]
    NotNANum = np.sum(pd.notnull(STOM),axis=0)
    Rslt = np.log(np.nansum(np.exp(STOM),axis=0)/NotNANum)
    Rslt[NotNANum<args['非空数']] = np.nan
    return Rslt
STOQArgs = {'T':3,'T1':21,'非空数':2}
STOQ = QS.FactorDB.TimeOperation('STOQ', [STOM], {"算子":STOQFun,"参数":STOQArgs,"回溯期数":[21*(3-1)],"运算ID":"多ID"})
Factors.append(STOQ)

# STOA
STOAArgs = {'T':12,'T1':21,'非空数':4}
STOA = QS.FactorDB.TimeOperation('STOA', [STOM], {'算子':STOQFun,"参数":STOAArgs,"回溯期数":[21*(12-1)],"运算ID":"多ID"})
Factors.append(STOA)

# EPFWD
EPFWD = Factorize(PredictedEarnings / TotalCap, factor_name="EPFWD")
Factors.append(EPFWD)

# CETOP
CETOP = Factorize(CashEarnings_TTM / TotalCap / 10000, factor_name="CETOP")
Factors.append(CETOP)

# ETOP
ETOP = Factorize(Earnings_TTM / TotalCap / 10000, factor_name="ETOP")
Factors.append(ETOP)

# EGRLF
EGRLF = 1 + (PredictedEarningsFY2*10000 - Earnings_LYR) / abs(Earnings_LYR)
EGRLF = Factorize(fd.sign(EGRLF) * abs(EGRLF)**(1/3) - 1, factor_name="EGRLF")
Factors.append(EGRLF)

# EGRSF
EGRSF = Factorize((PredictedEarningsFY0*10000 - Earnings_LYR) / abs(Earnings_LYR), factor_name="EGRSF")
Factors.append(EGRSF)

# EGRO
EGRO = Factorize(fd.regress_change_rate(EPS4, EPS3, EPS2, EPS1, EPS0), factor_name="EGRO")
Factors.append(EGRO)

# SGRO
SGRO = Factorize(fd.regress_change_rate(SPS4, SPS3, SPS2, SPS1, SPS0), factor_name="SGRO")
Factors.append(SGRO)

# MLEV
MLEV = Factorize((LongDebt/10000 + TotalCap) / TotalCap, factor_name="MLEV")
Factors.append(MLEV)

# DTOA
DTOA = Factorize(TotalDebt / TotalAsset, factor_name="DTOA")
Factors.append(DTOA)

# BLEV
BLEV = Factorize((LongDebt+Equity_LYR) / Equity_LYR, factor_name="BLEV")
Factors.append(BLEV)

if __name__=="__main__":
    WDB.connect()
    
    CFT = QS.FactorDB.CustomFT("BarraDescriptor")
    CFT.addFactors(factor_list=Factors)
    
    IDs = WDB.getStockID(index_id="全体A股", is_current=False)
    #IDs = ["000001.SZ", "000003.SZ", "603297.SH"]# debug
    
    #if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2018, 8, 31, 23, 59, 59, 999999)
    #else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    #EndDT = dt.datetime(2018, 10, 31, 23, 59, 59, 999999)
    StartDT, EndDT = UpdateDate.StartDT, UpdateDate.EndDT
    
    DTs = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT-dt.timedelta(365*5), end_dt=EndDT)

    YearRiskFreeRate = WDB.getTable("货币市场日行情").readData(factor_names=["加权平均利率"], ids=["DR007.IB"], dts=DTRuler).iloc[0, :, 0]
    DayRiskFreeRate.append((1 + YearRiskFreeRate / 100)**(1/365)-1)
    MonthRiskFreeRate.append((1 + DayRiskFreeRate[0]).rolling(window=20).apply(lambda x: np.nanprod(x), raw=True)-1)

    TargetTable = "BarraDescriptor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler)
    
    HDB.disconnect()
    WDB.disconnect()