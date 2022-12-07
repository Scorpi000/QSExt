# -*- coding: utf-8 -*-
"""A股一致预期"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools


def DetailProspectFun(f, idt, iid, x, args):
    EPS_FY = []
    EPS_Std_FY = []
    EPS_Num_FY = []
    NetProfit_FY = []
    EaringsYoY_FY = []
    Earnings_FY = []
    BPS_FY = []
    OCFPS_FY = []
    PB_FY = []
    PE_FY = []
    PS_FY = []
    GrossMargin_FY = []
    ReportDate = []
    for i in range(3):
        iData = x[i]
        iData.iloc[:, 3:] = iData.iloc[:, 3:].astype(float)
        if iData.shape[0]==0:
            EPS_FY.append(np.nan)
            EPS_Std_FY.append(np.nan)
            EPS_Num_FY.append(np.nan)
            NetProfit_FY.append(np.nan)
            EaringsYoY_FY.append(np.nan)
            Earnings_FY.append(np.nan)
            BPS_FY.append(np.nan)
            OCFPS_FY.append(np.nan)
            PB_FY.append(np.nan)
            PE_FY.append(np.nan)
            PS_FY.append(np.nan)
            GrossMargin_FY.append(np.nan)
            ReportDate.append(None)
            continue
        EPS_FY.append(iData["每股收益"].mean())
        EPS_Std_FY.append(iData["每股收益"].std())
        EPS_Num_FY.append(float(pd.notnull(iData["每股收益"]).sum()))
        NetProfit_FY.append(iData["净利润(万元)"].mean())
        EaringsYoY_FY.append(iData["净利润增长率"].mean())
        Earnings_FY.append(iData["归属于母公司净利润(万元)"].mean())
        BPS_FY.append(iData["每股净资产"].mean())
        OCFPS_FY.append(iData["每股现金流"].mean())
        PB_FY.append(iData["市净率"].mean())
        PE_FY.append(iData["市盈率"].mean())
        PS_FY.append(iData["市售率"].mean())
        GrossMargin_FY.append(iData["毛利率"].mean())
        ReportDate.append(iData["预测年度"].iloc[0])
    TargetDate1 = str(idt.year) + "1231"
    TargetDate2 = str(idt.year+1) + "1231"
    if (TargetDate1 not in ReportDate) or (TargetDate2 not in ReportDate):
        EPS_Fwd12M = np.nan
        NetProfit_Fwd12M = np.nan
        Earnings_Fwd12M = np.nan
    else:
        Weight1 = (dt.date(int(TargetDate1[0:4]), 12, 31) - idt.date()).days / 365
        EPS_Fwd12M = Weight1 * EPS_FY[ReportDate.index(TargetDate1)] + (1 - Weight1) * EPS_FY[ReportDate.index(TargetDate2)]
        NetProfit_Fwd12M = Weight1 * NetProfit_FY[ReportDate.index(TargetDate1)] + (1 - Weight1) * NetProfit_FY[ReportDate.index(TargetDate2)]
        Earnings_Fwd12M = Weight1 * Earnings_FY[ReportDate.index(TargetDate1)] + (1 - Weight1) * Earnings_FY[ReportDate.index(TargetDate2)]
    return tuple(EPS_FY) + tuple(Earnings_FY) + tuple(EaringsYoY_FY) + tuple(NetProfit_FY) + tuple(BPS_FY) + tuple(OCFPS_FY) + tuple(PE_FY) + tuple(PB_FY) + tuple(PS_FY) + tuple(GrossMargin_FY) + (EPS_Fwd12M, NetProfit_Fwd12M, Earnings_Fwd12M) + tuple(EPS_Std_FY) + tuple(EPS_Num_FY)


def defFactor(args={}):
    Factors = []
    
    JYDB = args["JYDB"]
    
    Equity = JYDB.getTable("资产负债表_新会计准则").getFactor("归属母公司股东权益合计", args={"计算方法": "最新", "报告期": "所有"})
    
    TotalCap = JYDB.getTable("股票行情表现").getFactor("总市值(万元)", args={"回溯天数": np.inf})
    
    DetailProspect = JYDB.getTable("研究报告_盈利预测").getFactor(
        "每股收益",
        args={
            "算子": DetailProspectFun,
            "附加字段": ["归属于母公司净利润(万元)", "每股净资产", "每股现金流", "市盈率", "市净率", "净利润(万元)", "净利润增长率", "毛利率"],
            "向前年数": [0, 1, 2],
            "周期": 180,
            "数据类型": "object"
        }
    )
    Factors.append(fd.fetch(DetailProspect, 0, factor_name="eps_fy0"))
    Factors.append(fd.fetch(DetailProspect, 1, factor_name="eps_fy1"))
    Factors.append(fd.fetch(DetailProspect, 2, factor_name="eps_fy2"))
    Factors.append(fd.fetch(DetailProspect, 3, factor_name="earnings_fy0"))
    Factors.append(fd.fetch(DetailProspect, 4, factor_name="earnings_fy1"))
    Factors.append(fd.fetch(DetailProspect, 5, factor_name="earnings_fy2"))
    Factors.append(fd.fetch(DetailProspect, 6, factor_name="earnings_yoy_fy0"))
    Factors.append(fd.fetch(DetailProspect, 7, factor_name="earnings_yoy_fy1"))
    Factors.append(fd.fetch(DetailProspect, 8, factor_name="earnings_yoy_fy2"))
    NetProfitAvg_FY0 = fd.fetch(DetailProspect, 9, factor_name="net_profit_fy0")
    Factors.append(NetProfitAvg_FY0)
    NetProfitAvg_FY1 = fd.fetch(DetailProspect, 10, factor_name="net_profit_fy1")
    Factors.append(NetProfitAvg_FY1)
    NetProfitAvg_FY2 = fd.fetch(DetailProspect, 11, factor_name="net_profit_fy2")
    Factors.append(NetProfitAvg_FY2)
    Factors.append(fd.fetch(DetailProspect, 12, factor_name="bps_fy0"))
    Factors.append(fd.fetch(DetailProspect, 13, factor_name="bps_fy1"))
    Factors.append(fd.fetch(DetailProspect, 14, factor_name="bps_fy2"))
    Factors.append(fd.fetch(DetailProspect, 15, factor_name="ocfps_fy0"))
    Factors.append(fd.fetch(DetailProspect, 16, factor_name="ocfps_fy1"))
    Factors.append(fd.fetch(DetailProspect, 17, factor_name="ocfps_fy2"))
    Factors.append(fd.fetch(DetailProspect, 18, factor_name="pe_fy0"))
    Factors.append(fd.fetch(DetailProspect, 19, factor_name="pe_fy1"))
    Factors.append(fd.fetch(DetailProspect, 20, factor_name="pe_fy2"))
    Factors.append(fd.fetch(DetailProspect, 21, factor_name="pb_fy0"))
    Factors.append(fd.fetch(DetailProspect, 22, factor_name="pb_fy1"))
    Factors.append(fd.fetch(DetailProspect, 23, factor_name="pb_fy2"))
    Factors.append(fd.fetch(DetailProspect, 24, factor_name="ps_fy0"))
    Factors.append(fd.fetch(DetailProspect, 25, factor_name="ps_fy1"))
    Factors.append(fd.fetch(DetailProspect, 26, factor_name="ps_fy2"))
    Factors.append(fd.fetch(DetailProspect, 27, factor_name="gross_margin_fy0"))
    Factors.append(fd.fetch(DetailProspect, 28, factor_name="gross_margin_fy1"))
    Factors.append(fd.fetch(DetailProspect, 29, factor_name="gross_margin_fy2"))
    Factors.append(fd.fetch(DetailProspect, 30, factor_name="eps_fwd12m"))
    NetProfit_Fwd12M = fd.fetch(DetailProspect, 31, factor_name="net_profit_fwd12m")
    Factors.append(NetProfit_Fwd12M)
    Factors.append(fd.fetch(DetailProspect, 32, factor_name="earnings_fwd12m"))
    Factors.append(fd.fetch(DetailProspect, 33, factor_name="eps_std_fy0"))
    Factors.append(fd.fetch(DetailProspect, 34, factor_name="eps_std_fy1"))
    Factors.append(fd.fetch(DetailProspect, 35, factor_name="eps_std_fy2"))
    Factors.append(fd.fetch(DetailProspect, 36, factor_name="eps_num_fy0"))
    Factors.append(fd.fetch(DetailProspect, 37, factor_name="eps_num_fy1"))
    Factors.append(fd.fetch(DetailProspect, 38, factor_name="eps_num_fy2"))

    Factors.append(Factorize(10000 * NetProfitAvg_FY0 / Equity, factor_name="roe_fy0"))
    Factors.append(Factorize(10000 * NetProfitAvg_FY1 / Equity, factor_name="roe_fy1"))
    Factors.append(Factorize(10000 * NetProfitAvg_FY2 / Equity, factor_name="roe_fy2"))
    Factors.append(Factorize(10000 * NetProfit_Fwd12M / Equity, factor_name="roe_fwd12m"))
    
    Factors.append(Factorize(NetProfitAvg_FY0 / TotalCap, factor_name="ep_fy0"))
    Factors.append(Factorize(NetProfitAvg_FY1 / TotalCap, factor_name="ep_fy1"))
    Factors.append(Factorize(NetProfitAvg_FY2 / TotalCap, factor_name="ep_fy2"))
    Factors.append(Factorize(NetProfit_Fwd12M / TotalCap, factor_name="ep_fwd12m"))
    
    
    UpdateArgs = {
        "因子表": "stock_cn_consensus",
        "默认起始日": dt.datetime(2002, 1, 1),
        "最长回溯期": 365,
        "IDs": "股票",
        "时点类型": "自然日"
    }    
    
    return Factors, UpdateArgs


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
    
    IDs = JYDB.getStockID()
    
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