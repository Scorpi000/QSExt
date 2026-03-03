# -*- coding: utf-8 -*-
"""A股一致预期"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


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

def defFactor(fdi: FactorDefInput):
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    FT = JYDB.getTable("股票盈利综合预测表(新)", args={"AdditionalConditon": {"ForeYearLevel": "t"}})
    ForecastYear_FY0 = FT.getFactor("预测年度")
    NetProfitAvg_FY0 = rename(FT.getFactor("预测净利润平均值(元)"), factor_name="net_profit_fy0")
    EPSAvg_FY0 = rename(FT.getFactor("预测EPS平均值(元-股)"), factor_name="eps_fy0")
    EarningsAvg_FY0 = rename(FT.getFactor("预测营业收入平均值(万元)") * 10000, factor_name="earnings_fy0")
    EPSNum_FY0 = rename(FT.getFactor("预测EPS的机构家数"), factor_name="eps_num_fy0")
    EPSStd_FY0 = rename(FT.getFactor("预测EPS标准差"), factor_name="eps_std_fy0")
    BPSAvg_FY0 = rename(FT.getFactor("预测每股净资产平均值(元-股)"), factor_name="bps_fy0")
    
    FT = JYDB.getTable("股票盈利综合预测表(新)", args={"AdditionalConditon": {"ForeYearLevel": "t+1"}})
    NetProfitAvg_FY1 = rename(FT.getFactor("预测净利润平均值(元)"), factor_name="net_profit_fy1")
    EPSAvg_FY1 = rename(FT.getFactor("预测EPS平均值(元-股)"), factor_name="eps_fy1")
    EarningsAvg_FY1 = rename(FT.getFactor("预测营业收入平均值(万元)") * 10000, factor_name="earnings_fy1")
    EPSNum_FY1 = rename(FT.getFactor("预测EPS的机构家数"), factor_name="eps_num_fy1")
    EPSStd_FY1 = rename(FT.getFactor("预测EPS标准差"), factor_name="eps_std_fy1")
    BPSAvg_FY1 = rename(FT.getFactor("预测每股净资产平均值(元-股)"), factor_name="bps_fy1")
    
    FT = JYDB.getTable("股票盈利综合预测表(新)", args={"AdditionalConditon": {"ForeYearLevel": "t+2"}})
    NetProfitAvg_FY2 = rename(FT.getFactor("预测净利润平均值(元)"), factor_name="net_profit_fy2")
    EPSAvg_FY2 = rename(FT.getFactor("预测EPS平均值(元-股)"), factor_name="eps_fy2")
    EarningsAvg_FY2 = rename(FT.getFactor("预测营业收入平均值(万元)") * 10000, factor_name="earnings_fy2")
    EPSNum_FY2 = rename(FT.getFactor("预测EPS的机构家数"), factor_name="eps_num_fy2")
    EPSStd_FY2 = rename(FT.getFactor("预测EPS标准差"), factor_name="eps_std_fy2")
    BPSAvg_FY2 = rename(FT.getFactor("预测每股净资产平均值(元-股)"), factor_name="bps_fy2")
    
    NetProfitAvg_Fwd12M = calcFwd12M(ForecastYear_FY0, NetProfitAvg_FY0, NetProfitAvg_FY1, NetProfitAvg_FY2, factor_args={"Name": "net_profit_fwd12m"})
    EPSAvg_Fwd12M = calcFwd12M(ForecastYear_FY0, EPSAvg_FY0, EPSAvg_FY1, EPSAvg_FY2, factor_args={"Name": "eps_fwd12m"})
    EarningsAvg_Fwd12M = calcFwd12M(ForecastYear_FY0, EarningsAvg_FY0, EarningsAvg_FY1, EarningsAvg_FY2, factor_args={"Name": "earnings_fwd12m"})
    
    Factors = [
        NetProfitAvg_FY0, NetProfitAvg_FY1, NetProfitAvg_FY2, NetProfitAvg_Fwd12M,
        EPSAvg_FY0, EPSAvg_FY1, EPSAvg_FY2, EPSAvg_Fwd12M,
        EarningsAvg_FY0, EarningsAvg_FY1, EarningsAvg_FY2, EarningsAvg_Fwd12M,
        EPSNum_FY0, EPSNum_FY1, EPSNum_FY2,
        EPSStd_FY0, EPSStd_FY1, EPSStd_FY2,
        BPSAvg_FY0, BPSAvg_FY1, BPSAvg_FY2
    ]
    
    Equity = JYDB.getTable("资产负债表_新会计准则", args={"CalcType": "最新", "ReportDate": "所有"}).getFactor("归属母公司股东权益合计")
    
    TotalCap = JYDB.getTable("股票行情表现", args={"LookBack": np.inf}).getFactor("总市值(万元)") * 10000
    
    Factors.append(rename(NetProfitAvg_FY0 / Equity, factor_name="roe_fy0"))
    Factors.append(rename(NetProfitAvg_FY1 / Equity, factor_name="roe_fy1"))
    Factors.append(rename(NetProfitAvg_FY2 / Equity, factor_name="roe_fy2"))
    Factors.append(rename(NetProfitAvg_Fwd12M / Equity, factor_name="roe_fwd12m"))    
    
    Factors.append(rename(NetProfitAvg_FY0 / TotalCap, factor_name="ep_fy0"))
    Factors.append(rename(NetProfitAvg_FY1 / TotalCap, factor_name="ep_fy1"))
    Factors.append(rename(NetProfitAvg_FY2 / TotalCap, factor_name="ep_fy2"))
    Factors.append(rename(NetProfitAvg_Fwd12M / TotalCap, factor_name="ep_fwd12m"))
    
    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_consensus_expectation",
        MaxLookBack=365,
        IDType="A股",
        Author="麦冬"
    )