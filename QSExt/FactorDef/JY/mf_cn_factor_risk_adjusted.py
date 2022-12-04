# -*- coding: utf-8 -*-
"""公募基金风险调整因子(基于日数据)"""
import datetime as dt

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import linregress

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# 计算 M2 测度, TimeOperation, 单时点, 多ID
# x: [基金收益率, 无风险收益率, 市场收益率]
# args: {min_periods: ...}
def m2_measure_fun(f, idt, iid, x, args):
    Mask = (np.sum(pd.notnull(x[0]), axis=0) < args["min_periods"])
    r_bar = np.nanmean(x[0], axis=0)
    rf_bar = np.nanmean(x[1], axis=0)
    rm_bar = np.nanmean(x[2], axis=0)
    sigma = np.nanstd(x[0], ddof=1, axis=0)
    sigma[sigma==0] = np.nan
    sigma_m = np.nanstd(x[2], ddof=1, axis=0)
    Rslt = sigma_m / sigma * (r_bar - rf_bar) + rf_bar - rm_bar
    Rslt[Mask] = np.nan
    return Rslt

# 计算 Stutzer 指数, TimeOperation, 单时点, 多ID
# x: [基金收益率, 无风险收益率]
# args: {min_periods: ...}
def _brute_stutzer_index_fun(re, min_theta, max_theta, dtheta):
    theta = np.arange(min_theta, max_theta, dtheta)
    l = np.max(-np.log(np.sum(np.exp(np.dot(re.reshape((re.shape[0], 1)), theta.reshape((1, theta.shape[0])))), axis=0) / re.shape[0]))
    return np.sign(np.mean(re)) * (2 * l) ** 0.5

def stutzer_index_fun(f, idt, iid, x, args):
    re = x[0] - x[1]
    Mask = pd.notnull(re)
    NTD = np.sum(Mask)
    if NTD < args["min_periods"]:
        return np.nan
    re = re[Mask]
    if np.sum(re!=0)==0:
        return 0.0
    if (np.sum(re<=0)==0) or (np.sum(re>=0)==0):
        return np.sign(np.mean(re)) * 99999
    if (np.sum(re<0)==0) or (np.sum(re>0)==0):
        l = -np.log(np.sum(re==0) / NTD)
        return np.sign(np.mean(re)) * (2*l) ** 0.5
    Rslt = minimize_scalar(lambda theta: np.log(np.sum(np.exp(theta * re)) / NTD))
    if Rslt.success:
        return np.sign(np.mean(re)) * (-Rslt.fun * 2) ** 0.5
    else:
        f.Logger.warning(f"stutzer_index_fun 对于 {iid} 在 {idt[-1]} 时使用 scipy.optimize.minimize_scalar 计算 Stutzer 指数失败, 将转用蛮力搜索!")
        return _brute_stutzer_index_fun(re, -20, 20, 0.001)

# Hurst 指数, TimeOperation, 单时点, 多ID
# x: [基金收益率]
# args: {min_periods: ..., "min_element_number": ..., "min_split": ...}
def hurst_exponent_fun(f, idt, iid, x, args):
    r = x[0]
    Mask = pd.notnull(r)
    NTD = np.sum(Mask)
    if NTD < args["min_periods"]: return np.nan
    r = r[Mask]
    TotalLen = len(r)
    SplitNum = np.arange(args["min_split"], int(TotalLen / args["min_element_number"]) + 1)
    RS = np.full(shape=SplitNum.shape, fill_value=np.nan)
    Len = np.full(shape=SplitNum.shape, fill_value=np.nan)
    for i, iSplitNum in enumerate(SplitNum):
        iLen = int(TotalLen / iSplitNum)
        iData = r[-int(iLen * iSplitNum):].reshape((iSplitNum, iLen)).T
        iData = iData - np.mean(iData, axis=0)
        iS = np.std(iData, axis=0, ddof=1)
        iData = np.cumsum(iData, axis=0)
        iR = np.max(iData, axis=0) - np.min(iData, axis=0)
        RS[i] = np.nanmean(iR / iS)
        Len[i] = iLen
    Mask = pd.notnull(RS)
    RS = RS[Mask]
    Len = Len[Mask]
    if Len.shape[0]<2:
        return np.nan
    else:
        return linregress(np.log(Len), np.log(RS)).slope

def defFactor(args={}, debug=False):
    Factors = []
    
    annual_period = args.get("annual_period", 252)# 年化周期数
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    # 基金是否存续
    Exist = LDB.getTable("mf_cn_status").getFactor("if_exist")
    Mask = (Exist==1)
    
    # 基金净值和日收益率
    FT = JYDB.getTable("公募基金复权净值")
    NetValueAdj = FT.getFactor("复权单位净值", args={"回溯天数": np.inf})
    NetValueAdj = fd.where(NetValueAdj, Mask, np.nan)
    FundReturn = NetValueAdj / fd.lag(NetValueAdj, 1, 1) - 1
    
    # 基金基准日收益率和主动日收益率
    FT = JYDB.getTable("公募基金基准收益率", args={"回溯天数", 0})
    BenchmarkReturn = FT.getFactor("本日基金基准增长率") / 100
    ActiveReturn = FundReturn - BenchmarkReturn
    
    # 市场收益率, 日频
    MarketID = "000300.SH"# 市场指数
    FT = JYDB.getTable("指数行情", args={"回溯天数": 0})
    MarketReturn = fd.disaggregate(FT.getFactor("涨跌幅") / 100, aggr_ids=[MarketID])
    
    # 无风险利率
    RiskFreeRateID = "600020002"# 3月期国债利率
    FT = JYDB.getTable("宏观基础指标数据", args={"回溯天数": np.inf, "公告时点字段": None, "忽略时间": True})
    rf = fd.disaggregate(FT.getFactor("指标数据") / 100 * 10 ** FT.getFactor("量纲系数"), aggr_ids=[RiskFreeRateID])# 无风险年利率
    RiskFreeRate = rf / 360
    
    look_back_period = {"1m": 21, "3m": 63, "6m": 126, "1y": 252, "3y": 756, "5y": 1260}# 回溯期
    min_period = 20# 最小期数
    min_period_ratio = 0.5# 最小期数比例
    FT = LDB.getTable("mf_cn_factor_risk")
    for time_node, window in look_back_period.items():
        min_periods = max(min_period, int(window * min_period_ratio))
        
        beta = FT.getFactor(f"beta_{time_node}")
        max_drawdown_rate = FT.getFactor(f"max_drawdown_rate_{time_node}")
        down_volatility = FT.getFactor(f"down_volatility_{time_node}")
        
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
        
        # ####################### Hurst 指数 #######################
        hurst_exponent = QS.FactorDB.TimeOperation(
            f"hurst_exponent_{time_node}",
            [FundReturn],
            sys_args={
                "算子": hurst_exponent_fun,
                "参数": {"min_periods": min_periods, "min_split": 1, "min_element_number": 20},
                "回溯期数": [window - 1],
                "运算时点": "单时点",
                "运算ID": "单ID",
                "数据类型": "double"
            }
        )
        Factors.append(hurst_exponent)
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_risk_adjusted",
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": "公募基金"
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