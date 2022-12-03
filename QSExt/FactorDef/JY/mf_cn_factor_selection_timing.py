# -*- coding: utf-8 -*-
"""公募基金选券择时因子"""
import datetime as dt

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import linregress

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# 计算上行捕获率, TimeOperation, 单时点, 多ID
# x: [基金收益率, 市场收益率]
# args: {min_periods: ...}
def up_capture_fun(f, idt, iid, x, args):
    r, rb = x[0], x[1]
    Mask = (pd.notnull(r) & pd.notnull(rb))
    nSample = np.sum(Mask, axis=0)
    r[~Mask] = np.nan
    rb[~Mask] = np.nan
    r[r<=args["up_limit_port"]] = 0
    rb[rb<=args["up_limit_benchmark"]] = 0
    d1 = np.nanprod(r + 1, axis=0) ** (args["annual_period"] / nSample) - 1
    d2 = np.nanprod(rb + 1, axis=0) ** (args["annual_period"] / nSample) - 1
    Rslt = d1 / d2
    Rslt[d2<=0] = d1[d2<=0]
    Rslt[(nSample<args["min_periods"]) | np.isinf(Rslt)] = np.nan
    return Rslt

# 计算下行捕获率, TimeOperation, 单时点, 多ID
# x: [基金收益率, 市场收益率]
# args: {min_periods: ...}
def down_capture_fun(f, idt, iid, x, args):
    r, rb = x[0], x[1]
    Mask = (pd.notnull(r) & pd.notnull(rb))
    nSample = np.sum(Mask, axis=0)
    r[~Mask] = np.nan
    rb[~Mask] = np.nan
    r[r>=args["down_limit_port"]] = 0
    rb[rb>=args["down_limit_benchmark"]] = 0
    d1 = np.nanprod(r + 1, axis=0) ** (args["annual_period"] / nSample) - 1
    d2 = np.nanprod(rb + 1, axis=0) ** (args["annual_period"] / nSample) - 1
    Rslt = d1 / d2
    Rslt[d2>=0] = d1[d2>=0]
    Rslt[(nSample<args["min_periods"]) | np.isinf(Rslt)] = np.nan
    return Rslt


# 计算择时收益率, TimeOperation, 单时点, 多ID
# x: [基金收益率, 无风险利率, 市场收益率]
# args: {min_periods: ...}
def timing_return_fun(f, idt, iid, x, args):
    sub_interval = args["sub_interval"]
    nSubInterval = int(x[0].shape[0] / sub_interval)
    L = nSubInterval * sub_interval
    r_ex = (x[0] - x[1])[-L:]
    rm_ex = (x[2] - x[1])[-L:]
    Mask = (pd.isnull(r_ex) | pd.isnull(rm_ex))
    nSample = Mask.shape[0] - np.sum(Mask, axis=0)
    r_ex[Mask] = np.nan
    rm_ex[Mask] = np.nan
    x_avg = np.nanmean(rm_ex, axis=0)
    beta0 = (np.nansum(r_ex * rm_ex, axis=0) - nSample * x_avg * np.nanmean(r_ex, axis=0)) / (np.nansum(rm_ex ** 2, axis=0) - nSample * x_avg ** 2)
    beta0[(nSample<args["min_periods"]) | np.isinf(beta0)] = np.nan
    sub_beta = np.full((nSubInterval, x[0].shape[1]), np.nan)
    sub_rm_ex_avg = np.full((nSubInterval, x[0].shape[1]), np.nan)
    for i in range(nSubInterval):
        ir_ex = r_ex[i*sub_interval:(i+1)*sub_interval]
        irm_ex = rm_ex[i*sub_interval:(i+1)*sub_interval]
        iMask = Mask[i*sub_interval:(i+1)*sub_interval]
        iSampleLen = iMask.shape[0] - np.sum(iMask, axis=0)
        x_avg = np.nanmean(irm_ex, axis=0)
        ibeta = (np.nansum(ir_ex * irm_ex, axis=0) - iSampleLen * x_avg * np.nanmean(ir_ex, axis=0)) / (np.nansum(irm_ex ** 2, axis=0) - iSampleLen * x_avg ** 2)
        ibeta[(iSampleLen<args["min_periods"]) | np.isinf(ibeta)] = np.nan
        sub_beta[i, :] = ibeta
        sub_rm_ex_avg[i, :] = x_avg
    Rslt = (sub_beta - beta0) * sub_rm_ex_avg
    Mask = (np.sum(pd.notnull(Rslt), axis=0)==0)
    Rslt = np.nansum(Rslt, axis=0)
    Rslt[Mask] = 0
    return Rslt

# 计算 MPT 模型, TimeOperation, 单时点, 单ID
# x: [基金收益率, 基准收益率, 无风险利率]
# args: {min_periods: ...}
def mpt_model_fun(f, idt, iid, x, args):
    X = x[1] - x[2]
    Y = x[0] - x[2]
    Mask = (pd.notnull(X) & pd.notnull(Y))
    if np.sum(Mask)<args["min_periods"]:
        return (np.nan, np.nan, np.nan)
    X, Y = X[Mask], Y[Mask]
    Rslt = linregress(X, Y)
    return (Rslt.intercept, Rslt.slope, Rslt.rvalue**2)

# 计算 T-M 模型, TimeOperation, 单时点, 单ID
# x: [基金收益率, 基准收益率, 无风险利率]
# args: {min_periods: ...}
def tm_model_fun(f, idt, iid, x, args):
    X = x[1] - x[2]
    Y = x[0] - x[2]
    Mask = (pd.notnull(X) & pd.notnull(Y))
    if np.sum(Mask)<args["min_periods"]:
        return (np.nan, np.nan, np.nan)
    X, Y = X[Mask], Y[Mask]
    X = np.c_[np.ones((X.shape[0],)), X, X ** 2]
    try:
        return tuple(np.dot(np.dot(np.linalg.inv(np.dot(X.T, X)), X.T), Y))
    except:
        f.Logger.warning(f"tm_model_fun 对于 {iid} 在 {idt[-1]} 时的快速回归失败!")
    try:
        Mdl = sm.OLS(Y, X).fit()
        return tuple(Mdl.params)
    except:
        f.Logger.warning(f"tm_model_fun 对于 {iid} 在 {idt[-1]} 时的 statsmodels 回归失败!")
        return (np.nan, np.nan, np.nan)

# 计算 H-M 模型, TimeOperation, 单时点, 单ID
# x: [基金收益率, 基准收益率, 无风险利率]
# args: {min_periods: ...}
def hm_model_fun(f, idt, iid, x, args):
    X = x[1] - x[2]
    Y = x[0] - x[2]
    Mask = (pd.notnull(X) & pd.notnull(Y))
    if np.sum(Mask)<args["min_periods"]:
        return (np.nan, np.nan, np.nan)
    X, Y = X[Mask], Y[Mask]
    X = np.c_[np.ones((X.shape[0],)), X, X * (X>0)]
    try:
        return tuple(np.dot(np.dot(np.linalg.inv(np.dot(X.T, X)), X.T), Y))
    except:
        f.Logger.warning(f"hm_model_fun 对于 {iid} 在 {idt[-1]} 时的快速回归失败!")
    try:
        Mdl = sm.OLS(Y, X).fit()
        return tuple(Mdl.params)
    except:
        f.Logger.warning(f"hm_model_fun 对于 {iid} 在 {idt[-1]} 时的 statsmodels 回归失败!")
        return (np.nan, np.nan, np.nan)

# 计算 C-L 模型, TimeOperation, 单时点, 单ID
# x: [基金收益率, 基准收益率, 无风险利率]
# args: {min_periods: ...}
def cl_model_fun(f, idt, iid, x, args):
    X = x[1] - x[2]
    Y = x[0] - x[2]
    Mask = (pd.notnull(X) & pd.notnull(Y))
    if np.sum(Mask)<args["min_periods"]:
        return (np.nan, np.nan, np.nan)
    X, Y = X[Mask], Y[Mask]
    X = np.c_[np.ones((X.shape[0],)), np.clip(X, 0, np.inf), -np.clip(X, -np.inf, 0)]
    try:
        return tuple(np.dot(np.dot(np.linalg.inv(np.dot(X.T, X)), X.T), Y))
    except:
        f.Logger.warning(f"cl_model_fun 对于 {iid} 在 {idt[-1]} 时的快速回归失败!")
    try:
        Mdl = sm.OLS(Y, X).fit()
        return tuple(Mdl.params)
    except:
        f.Logger.warning(f"cl_model_fun 对于 {iid} 在 {idt[-1]} 时的 statsmodels 回归失败!")
        return (np.nan, np.nan, np.nan)


def defFactor(args={}, debug=False):
    Factors = []
    
    annual_period = args.get("annual_period", 252)# 年化周期数
    annual_period_risk_free = 360# 无风险利率的年化周期数
    
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
    
    look_back_period = {"1y": 252, "3y": 756, "5y": 1260}# 回溯期
    min_period_ratio = 0.67# 最小期数比例
    for iLookBack, iLookBackPeriods in look_back_period.items():
        iMinPeriod = max(int(iLookBackPeriods * min_period_ratio))
        
        # ####################### 上(下)行捕获率 #######################
        up_capture = QS.FactorDB.TimeOperation(
            f"up_capture_{iLookBack}",
            [FundReturn, MarketReturn],
            sys_args={
                "算子": up_capture_fun,
                "参数": {
                    "min_periods": iMinPeriod,
                    "annual_period": annual_period,
                    "up_limit_port": 0,
                    "up_limit_benchmark": 0
                },
                "回溯期数": [iLookBackPeriods - 1, iLookBackPeriods - 1],
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
        Factors.append(up_capture)
        
        down_capture = QS.FactorDB.TimeOperation(
            f"down_capture_{iLookBack}",
            [FundReturn, MarketReturn],
            sys_args={
                "算子": down_capture_fun,
                "参数": {
                    "min_periods": iMinPeriod,
                    "annual_period": annual_period,
                    "down_limit_port": 0,
                    "down_limit_benchmark": 0
                },
                "回溯期数": [iLookBackPeriods - 1, iLookBackPeriods - 1],
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
        Factors.append(down_capture)
        
        # ####################### 择时收益 #######################
        timing_return = QS.FactorDB.TimeOperation(
            f"timing_return_{iLookBack}",
            [FundReturn, RiskFreeRate, MarketReturn],
            sys_args={
                "算子": timing_return_fun,
                "参数": {
                    "min_periods": max(252, iMinPeriod),
                    "sub_interval": 63
                },
                "回溯期数": [iLookBackPeriods - 1] * 3,
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
        Factors.append(timing_return)
        
        # ####################### MPT 模型 #######################
        MPTModel = QS.FactorDB.TimeOperation(
            f"MPTModel_{iLookBack}",
            [FundReturn, BenchmarkReturn, RiskFreeRate],
            sys_args={
                "算子": mpt_model_fun,
                "参数": {"min_periods": max(252, iMinPeriod)},
                "回溯期数": [iLookBackPeriods - 1] * 3,
                "运算时点": "单时点",
                "运算ID": "单ID",
                "数据类型": "object"
            }
        )
        Factors.append(fd.fetch(MPTModel, pos=0, dtype="double", factor_name=f"mpt_alpha_{iLookBack}"))
        Factors.append(fd.fetch(MPTModel, pos=1, dtype="double", factor_name=f"mpt_beta_{iLookBack}"))
        Factors.append(fd.fetch(MPTModel, pos=2, dtype="double", factor_name=f"mpt_r2_{iLookBack}"))
    
        # ####################### T-M 模型 #######################
        TMModel = QS.FactorDB.TimeOperation(
            f"TMModel_{iLookBack}",
            [FundReturn, MarketReturn, RiskFreeRate],
            sys_args={
                "算子": tm_model_fun,
                "参数": {"min_periods": max(252, iMinPeriod)},
                "回溯期数": [iLookBackPeriods - 1] * 3,
                "运算时点": "单时点",
                "运算ID": "单ID",
                "数据类型": "object"
            }
        )
        Factors.append(fd.fetch(TMModel, pos=0, dtype="double", factor_name=f"tm_alpha_{iLookBack}"))
        Factors.append(fd.fetch(TMModel, pos=1, dtype="double", factor_name=f"tm_beta1_{iLookBack}"))
        Factors.append(fd.fetch(TMModel, pos=2, dtype="double", factor_name=f"tm_beta2_{iLookBack}"))
        
        # ####################### H-M 模型 #######################
        HMModel = QS.FactorDB.TimeOperation(
            f"HMModel_{iLookBack}",
            [FundReturn, MarketReturn, RiskFreeRate],
            sys_args={
                "算子": hm_model_fun,
                "参数": {"min_periods": max(252, iMinPeriod)},
                "回溯期数": [iLookBackPeriods - 1] * 3,
                "运算时点": "单时点",
                "运算ID": "单ID",
                "数据类型": "object"
            }
        )
        Factors.append(fd.fetch(HMModel, pos=0, dtype="double", factor_name=f"hm_alpha_{iLookBack}"))
        Factors.append(fd.fetch(HMModel, pos=1, dtype="double", factor_name=f"hm_beta1_{iLookBack}"))
        Factors.append(fd.fetch(HMModel, pos=2, dtype="double", factor_name=f"hm_beta2_{iLookBack}"))
        
        # ####################### C-L 模型 #######################
        CLModel = QS.FactorDB.TimeOperation(
            f"CLModel_{iLookBack}",
            [FundReturn, MarketReturn, RiskFreeRate],
            sys_args={
                "算子": cl_model_fun,
                "参数": {"min_periods": max(252, iMinPeriod)},
                "回溯期数": [iLookBackPeriods - 1] * 3,
                "运算时点": "单时点",
                "运算ID": "单ID",
                "数据类型": "object"
            }
        )
        Factors.append(fd.fetch(CLModel, pos=0, dtype="double", factor_name=f"cl_alpha_{iLookBack}"))
        Factors.append(fd.fetch(CLModel, pos=1, dtype="double", factor_name=f"cl_beta1_{iLookBack}"))
        Factors.append(fd.fetch(CLModel, pos=2, dtype="double", factor_name=f"cl_beta2_{iLookBack}"))
        
    UpdateArgs = {
        "因子表": "mf_cn_factor_selection_timing",
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