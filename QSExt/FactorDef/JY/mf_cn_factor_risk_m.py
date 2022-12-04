# -*- coding: utf-8 -*-
"""公募基金风险因子(月频)"""
import os
import re
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize
from .mf_cn_factor_risk import beta_fun, down_volatility_fun, get_kurtosis


def defFactor(args={}, debug=False):
    Factors = []
    
    annual_period = args.get("annual_period", 12)# 年化周期数
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    # 基金是否存续
    Exist = LDB.getTable("mf_cn_status").getFactor("if_exist")
    Mask = (Exist==1)
    
    # 基金净值和收益率
    FT = JYDB.getTable("公募基金复权净值")
    NetValueAdj = FT.getFactor("复权单位净值", args={"回溯天数": np.inf})
    NetValueAdj = fd.where(NetValueAdj, Mask, np.nan)
    FundReturn = NetValueAdj / fd.lag(NetValueAdj, 1, 1) - 1
    
    # 基金基准日收益率和主动收益率
    FT = LDB.getTable("mf_cn_benchmark_return")
    BenchmarkReturn = FT.getFactor("return_this_month")
    ActiveReturn = FundReturn - BenchmarkReturn
    
    # 市场收益率
    MarketID = "000300.SH"# 市场指数
    FT = JYDB.getTable("指数行情", args={"回溯天数": 0})
    MarketReturn = fd.disaggregate(FT.getFactor("涨跌幅") / 100, aggr_ids=[MarketID])
    
    # 无风险利率
    RiskFreeRateID = "600020002"# 3月期国债利率
    FT = JYDB.getTable("宏观基础指标数据", args={"回溯天数": np.inf, "公告时点字段": None, "忽略时间": True})
    rf = fd.disaggregate(FT.getFactor("指标数据") / 100 * 10 ** FT.getFactor("量纲系数"), aggr_ids=[RiskFreeRateID])# 无风险年利率
    RiskFreeRate = rf / 52
    
    look_back_period = {"1y": 12, "3y": 36, "5y": 60}# 回溯期
    min_period = 12# 最小期数
    min_period_ratio = 0.5# 最小期数比例
    for iLookBack, iLookBackPeriods in look_back_period.items():
        # ####################### 年化波动率 #######################
        Volatility = fd.rolling_std(
            FundReturn, 
            window=iLookBackPeriods, 
            min_periods=max(min_period, int(iLookBackPeriods*min_period_ratio)), 
            factor_name=f"volatility_{iLookBack}"
        ) * np.sqrt(annual_period)
        Factors.append(Volatility)
        
        # ####################### 年化超额波动率 #######################
        ActiveVolatility = fd.rolling_std(
            ActiveReturn, 
            window=iLookBackPeriods, 
            min_periods=max(min_period, int(iLookBackPeriods*min_period_ratio)), 
            factor_name=f"active_volatility_{iLookBack}"
        ) * np.sqrt(annual_period)
        Factors.append(ActiveVolatility)
    
        # ####################### 年化下行风险 #######################
        down_volatility = QS.FactorDB.TimeOperation(
            f"down_volatility_{iLookBack}",
            [FundReturn],
            sys_args={
                "算子": down_volatility_fun,
                "参数": {"annual_period": annual_period, "min_periods": max(min_period, int(iLookBackPeriods*min_period_ratio))},
                "回溯期数": [iLookBackPeriods - 1],
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
        Factors.append(down_volatility)
        
        # ####################### 峰度 #######################
        kurtosis = QS.FactorDB.TimeOperation(
            f"kurtosis_{iLookBack}",
            [FundReturn],
            sys_args={
                "算子": get_kurtosis,
                "参数": {"min_periods": max(min_period, int(iLookBackPeriods*min_period_ratio))},
                "回溯期数": [iLookBackPeriods - 1],
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
        Factors.append(kurtosis)
        
        # ####################### beta #######################
        beta = QS.FactorDB.TimeOperation(
            f"beta_{iLookBack}",
            [FundReturn, RiskFreeRate, MarketReturn],
            sys_args={
                "算子": beta_fun,
                "参数": {"min_periods": max(min_period, int(iLookBackPeriods*min_period_ratio))},
                "回溯期数": [iLookBackPeriods - 1],
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
        Factors.append(beta)
        
        # ####################### VaR #######################
        var = fd.rolling_quantile(
            FundReturn, 
            quantile=0.05, 
            window=iLookBackPeriods,
            min_periods=max(min_period, int(iLookBackPeriods*min_period_ratio)), 
            factor_name=f"var_{iLookBack}"
        )
        Factors.append(var)
        
        # ####################### 亏损频率 #######################
        cnt = fd.rolling_count(FundReturn, window=iLookBackPeriods)
        loss_cnt = fd.rolling_sum(FundReturn<0, window=iLookBackPeriods, min_periods=1)# 亏损个数
        loss_frequency = fd.where(
            loss_cnt / cnt, 
            cnt>=max(min_period, int(iLookBackPeriods * min_period_ratio)), 
            np.nan,
            factor_name=f"loss_frequency_{iLookBack}"
        )
        Factors.append(loss_frequency)
        
        # ####################### 平均亏损 #######################
        avg_loss = fd.rolling_mean(fd.where(FundReturn, FundReturn<0, np.nan), window=iLookBackPeriods, min_periods=1)
        avg_loss = fd.where(avg_loss, loss_cnt>0, 0)
        avg_loss = fd.where(
            avg_loss, 
            cnt>=max(min_period, int(iLookBackPeriods * min_period_ratio)), 
            np.nan,
            factor_name=f"avg_loss_{iLookBack}"
        )
        Factors.append(avg_loss)
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_risk_m",
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": "公募基金",
        "更新频率": "月"
    }
    return Factors, UpdateArgs

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Args = {"JYDB": JYDB, "LDB": TDB}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    DTs = QS.Tools.DateTime.getMonthLastDateTime(DTs)
    DTRuler = QS.Tools.DateTime.getMonthLastDateTime(DTRuler)
        
    IDs = JYDB.getMutualFundID(is_current=False)
    #IDs = ["159956.OF"]
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTRuler)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, 
                  factor_db=TDB, table_name=TargetTable, 
                  if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    JYDB.disconnect()