# -*- coding: utf-8 -*-
"""基金经理风险因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# 计算 beta, TimeOperation, 单时点, 多ID
# x: [基金收益率, 风险收益率, 市场收益率]
# args: {min_periods: ...}
def beta_fun(f, idt, iid, x, args):
    r_ex = x[0] - x[1]
    rm_ex = x[2] - x[1]
    Mask = (pd.notnull(r_ex) & pd.notnull(rm_ex))
    nSample = np.sum(Mask, axis=0)
    r_ex[~Mask] = np.nan
    rm_ex[~Mask] = np.nan
    x_avg = np.nanmean(rm_ex, axis=0)
    beta = (np.nansum(r_ex * rm_ex, axis=0) - nSample * x_avg * np.nanmean(r_ex, axis=0)) / (np.nansum(rm_ex ** 2, axis=0) - nSample * x_avg**2)
    beta[(nSample<args["min_periods"]) | np.isinf(beta)] = np.nan
    return beta

# 计算下行风险, TimeOperation, 单时点, 多ID
# x: [基金收益率]
# args: {min_periods: ..., annual_period: ...}
def down_volatility_fun(f, idt, iid, x, args):
    Mask = (np.sum(pd.notnull(x[0]), axis=0) < args["min_periods"])
    ret = np.clip(x[0], -np.inf, 0)
    Rslt = (np.nansum(ret ** 2, axis=0) / (np.sum(np.where(np.isnan(ret), 0, 1), axis=0) - 1)) ** 0.5 * np.sqrt(args["annual_period"])
    Rslt[Mask] = np.nan
    return Rslt

# 计算最大回撤, TimeOperation, 单时点, 多ID
# x: [基金收益率]
# args: {min_periods: ...}
def max_drawdown_fun(f, idt, iid, x, args):
    r = x[0][1:, :]
    Mask = (np.sum(pd.notnull(r), axis=0) < args["min_periods"])
    NV = np.r_[np.ones((1, r.shape[1])), np.nancumprod(r+1, axis=0)]
    Drawdown = 1 - NV / np.maximum.accumulate(NV)
    end_index = np.nanargmax(Drawdown, axis=0)
    MaxDrawdown = Drawdown[end_index, np.arange(end_index.shape[0])]
    end_time = np.array(idt)[end_index]# 结束时点
    end = end_time.reshape(1, len(iid)).repeat(len(idt), axis=0)
    row = np.array(idt).reshape(len(idt), 1).repeat(len(iid), axis=1)
    new_nv = np.where(row<=end, NV, np.nan)# 结束时点以后的数据全部剔除
    new_nv = new_nv[::-1]# 倒序之后取净值第一个最大值的索引, 即为开始时点
    start_index = np.nanargmax(new_nv, axis=0)
    start_time = np.array(idt[::-1])[start_index]
    start_time = start_time.astype("datetime64[D]").astype(str).astype("O")
    end_time = end_time.astype("datetime64[D]").astype(str).astype("O")
    # 起止时间相同设置为空
    same_mask = (start_time==end_time)
    start_time[same_mask] = None
    end_time[same_mask] = None
    # 样本量检查
    MaxDrawdown[Mask] = np.nan
    start_time[Mask] = None
    end_time[Mask] = None
    return list(zip(MaxDrawdown, start_time, end_time))

# 计算最长回撤期, TimeOperation, 单时点, 多ID
# x: [基金收益率]
# args: {min_periods: ...}
def longest_drawdown_fun(f, idt, iid, x, args):
    r = x[0][1:, :]
    Mask = (np.sum(pd.notnull(r), axis=0) < args["min_periods"])
    nv = np.r_[np.ones((1, r.shape[1])), np.nancumprod(r+1, axis=0)]
    nv_df = pd.DataFrame(nv, index=idt, columns=iid)
    nv_df_cummax = nv_df.cummax(axis=0)
    time_mask = (nv_df==nv_df_cummax)
    date_df = pd.DataFrame(np.array(idt).reshape(len(idt), 1).repeat(len(iid), axis=1), index=idt, columns=iid)
    date_df_cummax = date_df.where(time_mask, np.nan)
    date_df_cummax = date_df_cummax.fillna(method="ffill")
    timedelta_df = date_df - date_df_cummax
    longest_drawdown = timedelta_df.max(axis=0).dt.days.to_numpy().astype(float)
    end_series = timedelta_df.idxmax(axis=0).to_numpy()
    end_time = timedelta_df.idxmax(axis=0).dt.date.to_numpy()
    end_df = pd.DataFrame(end_series.reshape(1, len(iid)).repeat(len(idt), axis=0), index=idt, columns=iid)
    new_nv_df = nv_df.where(date_df <= end_df, np.nan)
    new_nv_df_reverse = new_nv_df[::-1]
    start_time = new_nv_df_reverse.idxmax(axis=0).dt.date.to_numpy()
    start_time = start_time.astype(str).astype("O")
    end_time = end_time.astype(str).astype("O")
    # 起止时间相同设置为空
    same_mask = (start_time==end_time)
    start_time[same_mask] = None
    end_time[same_mask] = None
    # 样本量检查
    longest_drawdown[Mask] = np.nan
    start_time[Mask] = None
    end_time[Mask] = None
    return list(zip(MaxDrawdown, start_time, end_time))    
    
# 计算相对基准最大亏损比例
def get_max_loss_ratio_relative_benchmark(f, idt, iid, x, args):
    nDT, nID = len(idt), len(iid)
    lb = args["look_back_days"]
    fund_return, benchmark_return = x[0], x[1]
    mask = (x[2]==1)
    fund_return[pd.isnull(fund_return) & mask] = 0
    benchmark_return[pd.isnull(benchmark_return) & mask] = 0
    loss_ratio = np.full(shape=(nDT-lb+1, nID), fill_value=np.inf)
    for i in range(0, nDT):
        iIdx = max(0, i+1-lb)
        iloss_ratio = np.cumprod(fund_return[i:i+lb]+1, axis=0) - np.cumpord(benchmark_return[i:i+lb]+1, axis=0)
        iloss_ratio[pd.isnull(iloss_ratio)] = np.inf
        iloss_ratio = np.minimum.accumulate(iloss_ratio, axis=0)[max(0, lb-1-i):]
        loss_ratio[iIdx:i+1] = np.nanmin([iloss_ratio, loss_ratio[iIdx:i+1]], axis=0)
    loss_ratio[np.isinf(loss_ratio)] = np.nan
    return loss_ratio

# 计算峰度
def get_kurtosis(f, idt, iid, x, args):
    mask = (np.sum(pd.notna(x[0]), axis=0) < args["min_periods"])
    avg = np.nanmean(x[0], axis=0)
    kurtosis = np.nanmean((x[0] - avg) ** 4, axis=0) / np.nanmean((x[0] - avg) ** 2, axis=0) ** 2 - 3
    kurtosis[mask] = np.nan
    return kurtosis


def defFactor(args={}, debug=False):
    Factors = []
    
    annual_period = args.get("annual_period", 252)# 年化周期数
    
    JYDB = args["JYDB"].connect()
    LDB = args["LDB"]
    
    IDs = JYDB.getTable("公募基金经理(新)(基金经理ID)", args={"多重映射": True}).getID()
    
    ReturnFT = LDB.getTable("mf_manager_cn_net_value", args={"回溯天数": 0})
    BenchmarkReturnFT = LDB.getTable("mf_manager_cn_benchmark_net_value", args={"回溯天数": 0})

    # 市场收益率
    MarketID = "000300.SH"# 市场指数
    FT = JYDB.getTable("指数行情", args={"回溯天数": 0})
    MarketReturn = fd.disaggregate(FT.getFactor("涨跌幅") / 100, aggr_ids=[MarketID])
    
    # 无风险利率
    RiskFreeRateID = "600020002"# 3月期国债利率
    FT = JYDB.getTable("宏观基础指标数据", args={"回溯天数": np.inf, "公告时点字段": None, "忽略时间": True})
    rf = fd.disaggregate(FT.getFactor("指标数据") / 100 * 10 ** FT.getFactor("量纲系数"), aggr_ids=[RiskFreeRateID])# 无风险年利率
    RiskFreeRate = rf / 360
    
    for iType in ["All"]+args["MFAllTypes"]:
        ManagerReturn = ReturnFT.getFactor(f"daily_return_{args['rebalance']}_{args['weight']}_{iType}")
        BenchmarkReturn = BenchmarkReturnFT.getFactor(f"daily_return_{args['rebalance']}_{args['weight']}_{iType}")
        ActiveReturn = ManagerReturn - BenchmarkReturn
        
        look_back_period = {"1m": 21, "3m": 63, "6m": 126, "1y": 252, "3y": 756, "5y": 1260}# 回溯期
        min_period = 20# 最小期数
        min_period_ratio = 0.5# 最小期数比例
        for iLookBack, iLookBackPeriods in look_back_period.items():
            # ####################### 年化波动率 #######################
            ijFactorName = f"return_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"
            Volatility = fd.rolling_std(
                ManagerReturn, 
                window=iLookBackPeriods, 
                min_periods=max(min_period, int(iLookBackPeriods*min_period_ratio)), 
                factor_name=ijFactorName
            ) * np.sqrt(annual_period)
            Factors.append(Volatility)
            
            # ####################### 年化超额波动率 #######################
            ijFactorName = f"active_volatility_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"
            ActiveVolatility = fd.rolling_std(
                ActiveReturn, 
                window=iLookBackPeriods, 
                min_periods=max(min_period, int(iLookBackPeriods*min_period_ratio)), 
                factor_name=ijFactorName
            ) * np.sqrt(annual_period)
            Factors.append(ActiveVolatility)
        
            # ####################### 年化下行风险 #######################
            ijFactorName = f"down_volatility_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"
            down_volatility = QS.FactorDB.TimeOperation(
                ijFactorName
                [ManagerReturn],
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
            ijFactorName = f"kurtosis_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"
            kurtosis = QS.FactorDB.TimeOperation(
                ijFactorName
                [ManagerReturn],
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
            ijFactorName = f"beta_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"
            beta = QS.FactorDB.TimeOperation(
                ijFactorName,
                [ManagerReturn, RiskFreeRate, MarketReturn],
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
            ijFactorName = f"var_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"
            var = fd.rolling_quantile(
                ManagerReturn, 
                quantile=0.05, 
                window=iLookBackPeriods,
                min_periods=max(min_period, int(iLookBackPeriods*min_period_ratio)), 
                factor_name=ijFactorName
            )
            Factors.append(var)
            
            # ####################### 最大回撤 #######################
            ijFactorName = f"max_drawdown_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"
            max_drawdown = QS.FactorDB.TimeOperation(
                ijFactorName
                [ManagerReturn],
                sys_args={
                    "算子": max_drawdown_fun,
                    "参数": {"min_periods": max(min_period, int(iLookBackPeriods*min_period_ratio))},
                    "回溯期数": [iLookBackPeriods - 1 + 1],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "object"
                }
            )
            Factors.append(fd.fetch(max_drawdown, pos=0, dtype="double", factor_name=f"max_drawdown_rate_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"))
            Factors.append(fd.fetch(max_drawdown, pos=1, dtype="string", factor_name=f"max_drawdown_start_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"))
            Factors.append(fd.fetch(max_drawdown, pos=0, dtype="string", factor_name=f"max_drawdown_end_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"))
    
            # ####################### 最长回撤 #######################
            longest_drawdown = QS.FactorDB.TimeOperation(
                f"longest_drawdown_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}",
                [ManagerReturn],
                sys_args={
                    "算子": longest_drawdown_fun,
                    "参数": {"min_periods": max(min_period, int(iLookBackPeriods*min_period_ratio))},
                    "回溯期数": [iLookBackPeriods - 1 + 1],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "object"
                }
            )
            Factors.append(fd.fetch(longest_drawdown, pos=0, dtype="double", factor_name=f"longest_drawdown_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"))
            Factors.append(fd.fetch(longest_drawdown, pos=1, dtype="string", factor_name=f"max_drawdown_start_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"))
            Factors.append(fd.fetch(longest_drawdown, pos=0, dtype="string", factor_name=f"max_drawdown_end_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"))
            
            # ####################### 亏损频率 #######################
            cnt = fd.rolling_count(ManagerReturn, window=iLookBackPeriods)
            loss_cnt = fd.rolling_sum(ManagerReturn<0, window=iLookBackPeriods, min_periods=1)# 亏损个数
            loss_frequency = fd.where(
                loss_cnt / cnt, 
                cnt>=max(min_period, int(iLookBackPeriods * min_period_ratio)), 
                np.nan,
                factor_name=f"loss_frequency_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"
            )
            Factors.append(loss_frequency)
            
            # ####################### 平均亏损 #######################
            avg_loss = fd.rolling_mean(fd.where(ManagerReturn, ManagerReturn<0, np.nan), window=iLookBackPeriods, min_periods=1)
            avg_loss = fd.where(avg_loss, loss_cnt>0, 0)
            avg_loss = fd.where(
                avg_loss, 
                cnt>=max(min_period, int(iLookBackPeriods * min_period_ratio)), 
                np.nan,
                factor_name=f"avg_loss_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}"
            )
            Factors.append(avg_loss)
            
            # ####################### 相对基准的最大亏损比例 #######################
            max_loss_ratio_relative_benchmark = QS.FactorDB.TimeOperation(
                f"max_loss_ratio_relative_benchmark_{iLookBack}_{args['rebalance']}_{args['weight']}_{iType}",
                [ManagerReturn, BenchmarkReturn, fd.notnull(ManagerReturn)],
                sys_args={
                    "算子": get_max_loss_ratio_relative_benchmark,
                    "参数": {"look_back_days": iLookBackPeriods},
                    "回溯期数": [iLookBackPeriods - 1, iLookBackPeriods - 1, iLookBackPeriods - 1],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "double"
                }
            )
            Factors.append(max_loss_ratio_relative_benchmark)
        
        
    UpdateArgs = {
        "因子表": "mf_manager_cn_factor_risk",
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": IDs
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
    
    SQLStr = "SELECT FundTypeName FROM mf_fundtype WHERE Standard=75 AND StandardLevel=2 ORDER BY DisclosureCode"
    MFAllTypes = [iType[0] for iType in JYDB.fetchall(sql_str=SQLStr) if iType[0].find("其他")==-1]
    
    Args = {"JYDB": JYDB, "LDB": TDB, "MFType": "jy_type_second", "MFAllTypes": MFAllTypes, "weight": "ew", "rebalance": "m"}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
    IDs = UpdateArgs["IDs"]
    
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