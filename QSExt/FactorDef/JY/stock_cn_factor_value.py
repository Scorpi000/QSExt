# -*- coding: utf-8 -*-
"""价值因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

UpdateArgs = {
    "因子表": "stock_cn_factor_value",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def DvdFun(f, idt, iid, x, args):
    #Fun = np.vectorize(lambda x1, x2: np.nansum(np.array(x1) * np.array(x2)))
    Fun = np.vectorize(lambda x1, x2: np.nansum(np.array(x1) * np.array(x2)) if (x1 is not None) and (x2 is not None) else 0)
    return Fun(x[0], x[1])

def SectorMedianFun(f, idt, iid, x, args):
    VR, Sector, IsListed = pd.Series(x[0]), pd.Series(x[1]), pd.Series(x[2])
    Data = pd.Series(index=VR.index, dtype=float)
    Mask = (pd.notnull(Sector) & (VR>0) & (IsListed==1))
    if Mask.sum()==0: return Data.values
    VR, Sector = VR[Mask], Sector[Mask]
    Grouped = VR.groupby(Sector)
    Data[Mask] = Grouped.transform(lambda x: x.median())
    return Data.values

# 回归函数
def ValueBiasRegressFun(f, idt, iid, x, args):
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

def ValueBiasFun(f, idt, iid, x, args):
    DataType = np.dtype([("0", np.float), ("1", np.float), ("2", np.float)])
    x = x[0].astype(DataType)
    a, l, b = x["0"], x["1"], x["2"]
    l[l==0] = np.nan
    c = -1 * b / l
    VR = x[1]
    VR[VR==0] = np.nan
    SVR = x[2]
    return 1 - c * SVR / VR
    
    
def defFactor(args={}):
    Factors = []

    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    # ### 资产负债表因子 #########################################################################
    FT = JYDB.getTable("资产负债表_新会计准则")
    TotalAsset = FT.getFactor("资产总计", args={"计算方法":"最新"})
    IntangibleAsset = FT.getFactor("无形资产", args={"计算方法":"最新"})
    IntangibleAsset = fd.where(IntangibleAsset, fd.notnull(IntangibleAsset), 0)
    Goodwill = FT.getFactor("商誉", args={"计算方法":"最新"})
    Goodwill = fd.where(Goodwill, fd.notnull(Goodwill), 0)
    TotalLiability = FT.getFactor("负债合计", args={"计算方法":"最新"})
    MonetaryFund = FT.getFactor("货币资金", args={"计算方法":"最新"})
    
    # ### 利润表因子 #############################################################################
    FT = JYDB.getTable("利润分配表_新会计准则")
    Sales_TTM = FT.getFactor("营业收入", args={"计算方法":"TTM"})
    Sales_LYR = FT.getFactor("营业收入", args={"计算方法":"最新", "报告期":"年报"})
    NetProfit_TTM = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"TTM"})
    NetProfit_LYR = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"最新", "报告期":"年报"})
    
    # ### 现金流量表因子 #############################################################################
    FT = JYDB.getTable("现金流量表_新会计准则")
    OCF_TTM = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"TTM"})
    OCF_LYR = FT.getFactor("经营活动产生的现金流量净额", args={"计算方法":"最新", "报告期":"年报"})
    
    # ### 衍生报表因子 #########################################################################
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)")
    InterestBearingObligation = FT.getFactor("带息债务", args={"计算方法":"最新"})
    EBIT_TTM = FT.getFactor("息税前利润", args={"计算方法":"TTM"})
    EBITDA_TTM = FT.getFactor("息税折旧摊销前利润", args={"计算方法":"TTM"})
    # 在TTM因缺失值不能计算时，采用最近年报数据填充
    EBIT  = fd.where(EBIT_TTM, fd.notnull(EBIT_TTM), FT.getFactor("息税前利润", args={"计算方法":"最新", "报告期":"年报"}))
    EBITDA  = fd.where(EBITDA_TTM, fd.notnull(EBITDA_TTM), FT.getFactor("息税折旧摊销前利润", args={"计算方法":"最新", "报告期":"年报"}))
    NetProfit_TTM_Deducted = FT.getFactor("扣除非经常性损益后的净利润", args={"计算方法":"TTM"})
    NetProfit_LYR_Deducted = FT.getFactor("扣除非经常性损益后的净利润", args={"计算方法":"最新", "报告期":"年报"})
    FCF_TTM = FT.getFactor("企业自由现金流量FCFF", args={"计算方法":"TTM"})
    FCF_LYR = FT.getFactor("企业自由现金流量FCFF", args={"计算方法":"最新", "报告期":"年报"})
    
    # ### 一致预期因子 #############################################################################
    FT = LDB.getTable("stock_cn_consensus")
    NetProfitAvg_FY0 = FT.getFactor("net_profit_fy0")# 单位: 万元
    NetProfitAvg_FY1 = FT.getFactor("net_profit_fy1")# 单位: 万元
    NetProfitAvg_Fwd12M = FT.getFactor("net_profit_fwd12m")# 单位: 万元

    # ### 特征因子 #############################################################################
    FT = LDB.getTable("stock_cn_info")
    Sector = FT.getFactor("citic_industry")
    IsListed = FT.getFactor("if_listed")

    # ### 行情因子 #############################################################################
    MarketCap = LDB.getTable("stock_cn_day_bar_nafilled").getFactor("total_cap")# 单位: 万元
    
    # #### 股息类 #############################################################################
    FT = JYDB.getTable("公司分红")
    CashDvdPerShare, BaseShare = FT.getFactor("派现(含税-人民币元)"), FT.getFactor("分红股本基数(股)")
    Dividend = QS.FactorDB.PointOperation("税前现金总红利", [CashDvdPerShare, BaseShare], sys_args={"算子":DvdFun, "运算时点":"多时点", "运算ID":"多ID"})
    Factors.append(Factorize(fd.rolling_sum(Dividend, window=240) / MarketCap, "dp_ltm"))

    # ### 盈利类 ########################################################################
    Factors.append(Factorize(NetProfit_TTM_Deducted / (MarketCap * 10000), "ep_ttm_deducted"))
    
    EP_LYR_Deducted=Factorize(NetProfit_LYR_Deducted / (MarketCap * 10000), "ep_lyr_deducted")
    Factors.append(EP_LYR_Deducted)
    
    EP_TTM = Factorize(NetProfit_TTM / (MarketCap * 10000), "ep_ttm")
    Factors.append(EP_TTM)
    Factors.append(Factorize(NetProfit_LYR / (MarketCap * 10000), "ep_lyr"))
    Factors.append(Factorize(NetProfitAvg_FY0 / MarketCap, "ep_fy0"))
    Factors.append(Factorize(NetProfitAvg_FY1 / MarketCap, "ep_fy1"))
    Factors.append(Factorize(NetProfitAvg_Fwd12M / MarketCap,"ep_fwd12m"))

    # ### 现金流类 ######################################################################
    Factors.append(Factorize(OCF_TTM / (MarketCap * 10000), "ocfp_ttm"))
    OCFP_LYR=Factorize(OCF_LYR / (MarketCap * 10000), "ocfp_lyr")
    Factors.append(OCFP_LYR)
    
    Factors.append(Factorize(FCF_TTM / (MarketCap * 10000), "fcfp_ttm"))
    FCFP_LYR=Factorize(FCF_LYR / (MarketCap * 10000), "fcfp_lyr")
    Factors.append(FCFP_LYR)

    # ### 营业收入类 ########################################################################
    SP_TTM = Factorize(Sales_TTM / (MarketCap * 10000), "sp_ttm")
    Factors.append(SP_TTM)
    SP_LYR=Factorize(Sales_LYR / (MarketCap * 10000), "sp_lyr")
    Factors.append(SP_LYR)

    # ### 账面净资产类 ######################################################################
    BP_LR = Factorize((TotalAsset - TotalLiability) / (MarketCap * 10000), "bp_lr")
    Factors.append(BP_LR)
    Factors.append(Factorize((TotalAsset - TotalLiability - IntangibleAsset - Goodwill) / (MarketCap * 10000), "bp_lr_tangible"))# 在无形资产或商誉缺失的情况下, TangibleBP_LR 退化为 BP_LR

    # ### 企业价值类 ########################################################################
    EV = MarketCap * 10000 + InterestBearingObligation - MonetaryFund
    Factors.append(Factorize(EBITDA / EV, "ebitda2ev"))
    Factors.append(Factorize(EBIT / EV, "ebit2ev"))
    Factors.append(Factorize(Sales_TTM / EV, "revenue2ev"))
    
    # ### 价值偏离度 ########################################################################
    EP_SectorMedian = QS.FactorDB.SectionOperation(
        "EP_SectorMedian"
        [EP_TTM, Sector, IsListed],
        sys_args={
            "算子": SectorMedianFun,
            "数据类型": "object"
        }
    )
    EPResult = QS.FactorDB.TimeOperation(
        "EPResult",
        [EP_TTM, EP_SectorMedian],
        sys_args={
            "算子": ValueBiasRegressFun,
            "回溯期数": [37*20-1, 37*20-1],
            "数据类型": "object"
        }        
    )
    EP_DR = QS.FactorDB.PointOperation(
        "ep_dr",
        [EPResult, EP_TTM, EP_SectorMedian],
        sys_args={
            "算子": ValueBiasFun,
            "运算时点": "多时点",
            "运算ID": "多ID",
            "数据类型": "object"
        }        
    )
    Factors.append(EP_DR)
    
    SP_SectorMedian = QS.FactorDB.SectionOperation(
        "SP_SectorMedian"
        [SP_TTM, Sector, IsListed],
        sys_args={
            "算子": SectorMedianFun,
            "数据类型": "object"
        }
    )
    SPResult = QS.FactorDB.TimeOperation(
        "SPResult",
        [SP_TTM, SP_SectorMedian],
        sys_args={
            "算子": ValueBiasRegressFun,
            "回溯期数": [37*20-1, 37*20-1],
            "数据类型": "object"
        }        
    )
    SP_DR = QS.FactorDB.PointOperation(
        "sp_dr",
        [SPResult, SP_TTM, SP_SectorMedian],
        sys_args={
            "算子": ValueBiasFun,
            "运算时点": "多时点",
            "运算ID": "多ID",
            "数据类型": "object"
        }        
    )
    Factors.append(SP_DR)
    
    BP_SectorMedian = QS.FactorDB.SectionOperation(
        "BP_SectorMedian"
        [BP_LR, Sector, IsListed],
        sys_args={
            "算子": SectorMedianFun,
            "数据类型": "object"
        }
    )
    BPResult = QS.FactorDB.TimeOperation(
        "BPResult",
        [BP_LR, BP_SectorMedian],
        sys_args={
            "算子": ValueBiasRegressFun,
            "回溯期数": [37*20-1, 37*20-1],
            "数据类型": "object"
        }        
    )
    BP_DR = QS.FactorDB.PointOperation(
        "bp_dr",
        [BPResult, BP_LR, BP_SectorMedian],
        sys_args={
            "算子": ValueBiasFun,
            "运算时点": "多时点",
            "运算ID": "多ID",
            "数据类型": "object"
        }        
    )
    Factors.append(BP_DR)    
    
    return Factors
    

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB()
    JYDB.connect()
    
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = JYDB.getStockID(is_current=False)
    
    Args = {"JYDB": JYDB, "LDB": TDB}
    Factors = defFactor(args=Args)
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTs)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
        factor_db=TDB, table_name=TargetTable,
        if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    JYDB.disconnect()
    