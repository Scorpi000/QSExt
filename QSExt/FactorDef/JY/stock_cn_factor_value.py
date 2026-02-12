# -*- coding: utf-8 -*-
"""价值因子"""
import datetime as dt

import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.BasicOperator import rename
from QuantStudio.Core.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStockStatus
from QSExt.FactorDef.JY.stock_cn_industry import defFactor as defStockIndustry
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar


@FactorOperatorized(operator_type="Point", args={"Arity": 4, "DTMode": "多时点", "IDMode": "多ID", "DataType": "double"})
def calcFwd12M(f, idt, iid, x, args):
    ForecastYear_FY0, NetProfitAvg_FY0, NetProfitAvg_FY1, NetProfitAvg_FY2 = x
    NetProfitAvg_FY0, NetProfitAvg_FY1, NetProfitAvg_FY2 = pd.DataFrame(NetProfitAvg_FY0).astype(float), pd.DataFrame(NetProfitAvg_FY1).astype(float), pd.DataFrame(NetProfitAvg_FY2).astype(float)
    DTs = pd.DataFrame(np.array([idt], dtype="O").T.repeat(ForecastYear_FY0.shape[1], axis=1))
    Mask = pd.isnull(ForecastYear_FY0)
    ForecastYear_FY0 = pd.DataFrame(ForecastYear_FY0).fillna(pd.NaT).astype(np.dtype("datetime64[ns]"))
    ForecastYear_FY1 = ForecastYear_FY0 + dt.timedelta(days=365)
    Weight = (ForecastYear_FY0 - DTs).map(lambda d: d.days if pd.notnull(d) else np.nan) / 365
    Weight_FY1 = (ForecastYear_FY1 - DTs).map(lambda d: d.days if pd.notnull(d) else np.nan) / 365
    Mask = ((Weight >= 0) | pd.isnull(Weight))
    Weight = Weight.where(Mask, Weight_FY1)
    NetProfitAvg0 = NetProfitAvg_FY0.where(Mask, NetProfitAvg_FY1)
    NetProfitAvg1 = NetProfitAvg_FY1.where(Mask, NetProfitAvg_FY2)
    Fwd12M = Weight * NetProfitAvg0 + (1 - Weight) * NetProfitAvg1
    return Fwd12M.values

@FactorOperatorized(operator_type="Point", args={"Arity": 2, "DTMode": "多时点", "IDMode": "多ID", "DataType": "double"})
def calcDvd(f, idt, iid, x, args):
    #Fun = np.vectorize(lambda x1, x2: np.nansum(np.array(x1) * np.array(x2)))
    Fun = np.vectorize(lambda x1, x2: np.nansum(np.array(x1) * np.array(x2)) if (x1 is not None) and (x2 is not None) else 0)
    return Fun(x[0], x[1])

@FactorOperatorized(operator_type="Section", args={"Arity": 3, "DTMode": "单时点", "OutputMode": "全截面", "DataType": "object"})
def calcSectorMedian(f, idt, iid, x, args):
    VR, Sector, IsListed = pd.Series(x[0]), pd.Series(x[1]), pd.Series(x[2])
    Data = pd.Series(index=VR.index, dtype=float)
    Mask = (pd.notnull(Sector) & (VR>0) & (IsListed==1))
    if Mask.sum()==0: return Data.values
    VR, Sector = VR[Mask], Sector[Mask]
    Grouped = VR.groupby(Sector)
    Data[Mask] = Grouped.transform(lambda x: x.median())
    return Data.values

@FactorOperatorized(operator_type="Time", args={"Arity": 2, "DTMode": "单时点", "IDMode": "单ID", "DataType": "object", "LookBack": [37*20-1, 37*20-1]})
def regressValueBias(f, idt, iid, x, args):
    VR, SVR = x[0], x[1]
    VR = VR[np.arange(20-1, VR.shape[0], 20)]
    SVR = SVR[np.arange(20-1, SVR.shape[0], 20)]
    DVR = np.diff(VR)
    DSVR = np.diff(SVR)
    X = np.array([DSVR, VR[:-1], SVR[:-1]]).T
    try:
        Rslt = sm.OLS(DVR, X, missing="drop").fit()
    except:
        return (np.nan, np.nan, np.nan)
    return (Rslt.params[0], Rslt.params[1], Rslt.params[2])
     
@FactorOperatorized(operator_type="Point", args={"Arity": 3, "DTMode": "多时点", "IDMode": "多ID", "DataType": "double"})
def calcValueBias(f, idt, iid, x, args):
    DataType = np.dtype([("0", float), ("1", float), ("2", float)])
    x = x[0].astype(DataType)
    a, l, b = x["0"], x["1"], x["2"]
    l[l==0] = np.nan
    c = -1 * b / l
    VR = x[1]
    VR[VR==0] = np.nan
    SVR = x[2]
    return 1 - c * SVR / VR
    
    
def defFactor(fdi: FactorDefInput):
    Factors = []

    JYDB = fdi.FDB["JYDB"]
    
    where = fo.Where(dtype="double")
    notnull = fo.NotNull()

    # ### 资产负债表因子 #########################################################################
    FT = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "最新"})
    TotalAsset = FT.getFactor("资产总计")
    IntangibleAsset = FT.getFactor("无形资产")
    IntangibleAsset = where(IntangibleAsset, notnull(IntangibleAsset), 0)
    Goodwill = FT.getFactor("商誉")
    Goodwill = where(Goodwill, notnull(Goodwill), 0)
    TotalLiability = FT.getFactor("负债合计")
    MonetaryFund = FT.getFactor("货币资金")
    
    # ### 利润表因子 #############################################################################
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "TTM"})
    Sales_TTM = FT.getFactor("营业收入")
    NetProfit_TTM = FT.getFactor("归属于母公司所有者的净利润")
    FT = JYDB.getTable("利润分配表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报"})
    Sales_LYR = FT.getFactor("营业收入")
    NetProfit_LYR = FT.getFactor("归属于母公司所有者的净利润")
    
    # ### 现金流量表因子 #############################################################################
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "TTM"})
    OCF_TTM = FT.getFactor("经营活动产生的现金流量净额")
    FT = JYDB.getTable("现金流量表_新会计准则", args={"CalcType": "最新", "ReportDate": "年报"})
    OCF_LYR = FT.getFactor("经营活动产生的现金流量净额")
    
    # ### 衍生报表因子 #########################################################################
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType":"最新"})
    InterestBearingObligation = FT.getFactor("带息债务")
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType":"TTM"})
    EBIT_TTM = FT.getFactor("息税前利润")
    EBITDA_TTM = FT.getFactor("息税折旧摊销前利润")
    NetProfit_TTM_Deducted = FT.getFactor("扣除非经常性损益后的净利润")
    FCF_TTM = FT.getFactor("企业自由现金流量FCFF")
    # 在TTM因缺失值不能计算时，采用最近年报数据填充
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType":"最新", "ReportDate":"年报"})
    EBIT  = where(EBIT_TTM, notnull(EBIT_TTM), FT.getFactor("息税前利润"))
    EBITDA  = where(EBITDA_TTM, notnull(EBITDA_TTM), FT.getFactor("息税折旧摊销前利润"))
    NetProfit_LYR_Deducted = FT.getFactor("扣除非经常性损益后的净利润")
    FCF_LYR = FT.getFactor("企业自由现金流量FCFF")
    
    # ### 一致预期因子 #############################################################################
    FT = JYDB.getTable("股票盈利综合预测表(新)", args={"AdditionalConditon": {"ForeYearLevel": "t"}})
    NetProfitAvg_FY0 = FT.getFactor("预测净利润平均值(元)")
    ForecastYear_FY0 = FT.getFactor("预测年度")
    FT = JYDB.getTable("股票盈利综合预测表(新)", args={"AdditionalConditon": {"ForeYearLevel": "t+1"}})
    NetProfitAvg_FY1 = FT.getFactor("预测净利润平均值(元)")
    FT = JYDB.getTable("股票盈利综合预测表(新)", args={"AdditionalConditon": {"ForeYearLevel": "t+2"}})
    NetProfitAvg_FY2 = FT.getFactor("预测净利润平均值(元)")
    NetProfitAvg_Fwd12M = calcFwd12M(ForecastYear_FY0, NetProfitAvg_FY0, NetProfitAvg_FY1, NetProfitAvg_FY2, factor_args={"Name": "net_profit_fwd12m"})

    # ### 特征因子 #############################################################################
    StockIndustryDef = defStockIndustry(fdi=fdi)
    Sector = StockIndustryDef.getFactor("citic2019_level1")
    StockStatusDef = defStockStatus(fdi=fdi)
    IsListed = StockStatusDef.getFactor(factor_name="if_listed", def_path="...")

    # ### 行情因子 #############################################################################
    StockDayBarDef = defStockDayBar(fdi=fdi)
    MarketCap = StockDayBarDef.getFactor(factor_name="total_cap", def_path="...")# 单位: 万元
    
    # #### 股息类 #############################################################################
    FT = JYDB.getTable("公司分红")
    CashDvdPerShare, BaseShare = FT.getFactor("派现(含税-人民币元)"), FT.getFactor("分红股本基数(股)")
    Dividend = calcDvd(CashDvdPerShare, BaseShare, factor_args={"Name": "税前现金总红利"})
    Factors.append(rename(fo.RollingSum(window=240, min_periods=1)(Dividend) / MarketCap, factor_name="dp_ltm"))

    # ### 盈利类 ########################################################################
    Factors.append(rename(NetProfit_TTM_Deducted / (MarketCap * 10000), factor_name="ep_ttm_deducted"))
    
    EP_LYR_Deducted=rename(NetProfit_LYR_Deducted / (MarketCap * 10000), factor_name="ep_lyr_deducted")
    Factors.append(EP_LYR_Deducted)
    
    EP_TTM = rename(NetProfit_TTM / (MarketCap * 10000), factor_name="ep_ttm")
    Factors.append(EP_TTM)
    Factors.append(rename(NetProfit_LYR / (MarketCap * 10000), factor_name="ep_lyr"))
    Factors.append(rename(NetProfitAvg_FY0 / (MarketCap * 10000), factor_name="ep_fy0"))
    Factors.append(rename(NetProfitAvg_FY1 / (MarketCap * 10000), factor_name="ep_fy1"))
    Factors.append(rename(NetProfitAvg_Fwd12M / (MarketCap * 10000), factor_name="ep_fwd12m"))

    # ### 现金流类 ######################################################################
    Factors.append(rename(OCF_TTM / (MarketCap * 10000), factor_name="ocfp_ttm"))
    OCFP_LYR=rename(OCF_LYR / (MarketCap * 10000), factor_name="ocfp_lyr")
    Factors.append(OCFP_LYR)
    
    Factors.append(rename(FCF_TTM / (MarketCap * 10000), factor_name="fcfp_ttm"))
    FCFP_LYR=rename(FCF_LYR / (MarketCap * 10000), factor_name="fcfp_lyr")
    Factors.append(FCFP_LYR)

    # ### 营业收入类 ########################################################################
    SP_TTM = rename(Sales_TTM / (MarketCap * 10000), factor_name="sp_ttm")
    Factors.append(SP_TTM)
    SP_LYR=rename(Sales_LYR / (MarketCap * 10000), factor_name="sp_lyr")
    Factors.append(SP_LYR)

    # ### 账面净资产类 ######################################################################
    BP_LR = rename((TotalAsset - TotalLiability) / (MarketCap * 10000), factor_name="bp_lr")
    Factors.append(BP_LR)
    Factors.append(rename((TotalAsset - TotalLiability - IntangibleAsset - Goodwill) / (MarketCap * 10000), factor_name="bp_lr_tangible"))# 在无形资产或商誉缺失的情况下, TangibleBP_LR 退化为 BP_LR

    # ### 企业价值类 ########################################################################
    EV = MarketCap * 10000 + InterestBearingObligation - MonetaryFund
    Factors.append(rename(EBITDA / EV, factor_name="ebitda2ev"))
    Factors.append(rename(EBIT / EV, factor_name="ebit2ev"))
    Factors.append(rename(Sales_TTM / EV, factor_name="revenue2ev"))
    
    # ### 价值偏离度 ########################################################################
    EP_SectorMedian = calcSectorMedian(EP_TTM, Sector, IsListed, factor_args={"Name": "EP_SectorMedian"})
    EPResult = regressValueBias(EP_TTM, EP_SectorMedian, factor_args={"Name": "EPResult"})
    EP_DR = calcValueBias(EPResult, EP_TTM, EP_SectorMedian, factor_args={"Name": "ep_dr"})
    Factors.append(EP_DR)
    
    SP_SectorMedian = calcSectorMedian(SP_TTM, Sector, IsListed, factor_args={"Name": "SP_SectorMedian"})
    SPResult = regressValueBias(SP_TTM, SP_SectorMedian, factor_args={"Name": "SPResult"})
    SP_DR = calcValueBias(SPResult, SP_TTM, SP_SectorMedian, factor_args={"Name": "sp_dr"})
    Factors.append(SP_DR)

    BP_SectorMedian = calcSectorMedian(BP_LR, Sector, IsListed, factor_args={"Name": "BP_SectorMedian"})
    BPResult = regressValueBias(BP_LR, BP_SectorMedian, factor_args={"Name": "BPResult"})
    BP_DR = calcValueBias(BPResult, BP_LR, BP_SectorMedian, factor_args={"Name": "bp_dr"})
    Factors.append(BP_DR)
    
    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_factor_value",
        MaxLookBack=365 * 4,
        IDType="A股",
        Author="麦冬"
    )
    