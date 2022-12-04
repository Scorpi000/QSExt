# -*- coding: utf-8 -*-
"""公募基金风险调整因子(月频)"""
import datetime as dt

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import linregress

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize
from .mf_cn_factor_risk_adjusted import m2_measure_fun, stutzer_index_fun, 


def defFactor(args={}, debug=False):
    Factors = []
    
    annual_period = args.get("annual_period", 52)# 年化周期数
    
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
    
    # 基金基准收益率和主动收益率
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
    RiskFreeRate = rf / 360
    
    look_back_period = {"1y": 52, "3y": 156, "5y": 260}# 回溯期
    min_period = 12# 最小期数
    min_period_ratio = 0.5# 最小期数比例
    FT_m = LDB.getTable("mf_cn_factor_risk_m")
    FT = LDB.getTable("mf_cn_factor_risk")
    for time_node, window in look_back_period.items():
        min_periods = max(min_period, int(window * min_period_ratio))
        
        beta = FT_m.getFactor(f"beta_{time_node}")
        max_drawdown_rate = FT.getFactor(f"max_drawdown_rate_{time_node}")
        down_volatility = FT_m.getFactor(f"down_volatility_{time_node}")
        
        # ####################### M2 测度 #######################
        m2_measure = QS.FactorDB.TimeOperation(
            f"m2_measure_{time_node}",
            [FundReturn, RiskFreeRate, MarketReturn],
            sys_args={
                "算子": m2_measure_fun,
                "参数": {"min_periods": min_periods},
                "回溯期数": [window - 1] * 3,
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
        Factors.append(m2_measure)
        
        # ####################### 夏普比率 #######################
        rp = fd.rolling_mean(FundReturn, window=window, min_periods=min_periods) * annual_period
        volatility = fd.rolling_std(FundReturn, window=window, min_periods=min_periods) * np.sqrt(annual_period)
        sharpe_ratio = Factorize((rp - rf) / volatility, factor_name=f"sharpe_ratio_{time_node}")
        Factors.append(sharpe_ratio)
        
        
        # ####################### 特雷诺比率 #######################
        treynor_ratio = Factorize((rp - rf) / abs(beta), factor_name=f"treynor_ratio_{time_node}")
        Factors.append(treynor_ratio)
    
        # ####################### Calmar 比率 #######################
        calmar_ratio = Factorize((rp - rf) / abs(fd.where(max_drawdown_rate, max_drawdown_rate!=0, 0.00001)), factor_name=f"calmar_ratio_{time_node}")
        Factors.append(calmar_ratio)
        
        # ####################### 索提诺比率 #######################
        sortino_ratio = Factorize((rp - rf) / down_volatility, factor_name=f"sortino_ratio_{time_node}")
        Factors.append(sortino_ratio)
        
        # ####################### 詹森指数 #######################
        rm = fd.rolling_mean(MarketReturn, window=window, min_periods=min_periods) * annual_period
        jensen_alpha = Factorize(rp - (rf + beta * (rm - rf)), factor_name=f"jensen_alpha_{time_node}")
        Factors.append(jensen_alpha)
        
        # ####################### 信息比率 #######################
        rpa = fd.rolling_mean(ActiveReturn, window=window, min_periods=min_periods) * annual_period
        extra_volatility = fd.rolling_std(ActiveReturn, window=window, min_periods=min_periods) * np.sqrt(annual_period)
        information_ratio = Factorize(rpa / extra_volatility, factor_name=f"information_ratio_{time_node}")
        Factors.append(information_ratio)        
        
        # ####################### Stutzer 指数 #######################
        stutzer_index = QS.FactorDB.TimeOperation(
            f"stutzer_index_{time_node}",
            [FundReturn, RiskFreeRate],
            sys_args={
                "算子": stutzer_index_fun,
                "参数": {"min_periods": min_periods},
                "回溯期数": [window - 1, window - 1],
                "运算时点": "单时点",
                "运算ID": "单ID",
                "数据类型": "double"
            }
        )
        Factors.append(stutzer_index)
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_risk_adjusted_m",
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