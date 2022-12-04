# -*- coding: utf-8 -*-
"""基金经理收益因子"""
import os
import re
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

def roll_back_months(idt, n):
    nYear, nMonth = (n-1)//12, (n-1)%12
    TargetYear = idt.year - nYear
    TargetMonth = idt.month - nMonth
    TargetYear -= (TargetMonth<=0)
    TargetMonth += (TargetMonth<=0) * 12
    TargetDT = dt.datetime(TargetYear, TargetMonth, 1) - dt.timedelta(1)
    return dt.datetime(TargetDT.year, TargetDT.month, min(idt.day, TargetDT.day))

# 计算周频收益
def return_week_fun(f, idt, iid, x, args):
    Idx = np.array(idt).searchsorted(idt[-1]-dt.timedelta(args["n_period"]*7-1))
    Mask = (np.sum(pd.notnull(x[0][Idx:, :]), axis=0)==0)
    Rslt = np.nanprod(1 + x[0][Idx:, :], axis=0) - 1
    Rslt[Mask] = np.nan
    return Rslt

# 计算月频收益
def return_month_fun(f, idt, iid, x, args):
    Idx = np.array(idt).searchsorted(roll_back_months(idt[-1], args["n_period"]) + dt.timedelta(1))
    Mask = (np.sum(pd.notnull(x[0][Idx:, :]), axis=0)==0)
    Rslt = np.nanprod(1 + x[0][Idx:, :], axis=0) - 1
    Rslt[Mask] = np.nan
    return Rslt

# 计算给定周期最大收益率
def get_max_return(f, idt, iid, x, args):
    return np.nanmax(x[0], axis=0)

# 计算算术年化收益率
def get_arithmetic_annual_return(f, idt, iid, x, args):
    mask = (np.sum(pd.notna(x[0]), axis=0) < args["min_periods"]) | (np.sum(pd.notna(x[0]), axis=0) < args["min_period_ratio"] * args["look_back_days"])
    annual_return = np.nansum(x[0], axis=0) * (args["annual_period"] / args["look_back_days"])
    annual_return[mask] = np.nan
    return annual_return

# 计算几何年化收益率
def get_geometry_annual_return(f, idt, iid, x, args):
    mask = (np.sum(pd.notna(x[0]), axis=0) < args["min_periods"]) | (np.sum(pd.notna(x[0]), axis=0) < args["min_period_ratio"] * args["look_back_days"])
    annual_return = np.nanprod(1 + x[0], axis=0) ** (args["annual_period"] / args["look_back_days"]) - 1
    annual_return[mask] = np.nan
    return annual_return

# 计算偏度
def get_skewness(f, idt, iid, x, args):
    mask = (np.sum(pd.notna(x[0]), axis=0) < args["min_periods"]) | (np.sum(pd.notna(x[0]), axis=0) < args["min_period_ratio"] * args["look_back_days"])
    avg = np.nanmean(x[0], axis=0)
    skewness = np.nanmean((x[0] - avg)**3, axis=0) / np.nanmean((x[0] - avg)**2, axis=0) ** (3/2)
    skewness[mask] = np.nan
    return skewness

def defFactor(args={}, debug=False):
    Factors = []
    
    annual_period = args.get("annual_period", 252)# 年化周期数
    
    JYDB = args["JYDB"].connect()
    LDB = args["LDB"]
    
    IDs = JYDB.getTable("公募基金经理(新)(基金经理ID)", args={"多重映射": True}).getID()
    
    ReturnFT = LDB.getTable("mf_manager_cn_net_value", args={"回溯天数": 0})
    BenchmarkReturnFT = LDB.getTable("mf_manager_cn_benchmark_net_value", args={"回溯天数": 0})
    
    for iType in ["All"]+args["MFAllTypes"]:
        ManagerReturn = ReturnFT.getFactor(f"daily_return_{args['rebalance']}_{args['weight']}_{iType}")
        BenchmarkReturn = BenchmarkReturnFT.getFactor(f"daily_return_{args['rebalance']}_{args['weight']}_{iType}")
        ActiveReturn = ManagerReturn - BenchmarkReturn
    
        # ####################### 累积收益(累积动量) #######################
        look_back_period = ["1w", "2w", "3w", "1m", "2m", "3m", "6m", "1y", "2y", "3y", "5y"]# 回溯期
        for time_node in look_back_period:
            n_period = int(re.findall("\d+", time_node)[0])
            period_type = re.findall("\D+", time_node)[0]
            ijFactorName = f"return_{time_node}_{args['rebalance']}_{args['weight']}_{iType}"
            if period_type=="w":
                ijCumReturn = QS.FactorDB.TimeOperation(
                    ijFactorName
                    [ManagerReturn],
                    sys_args={
                        "算子": return_week_fun,
                        "参数": {"n_period": n_period},
                        "回溯期数": [7 * n_period],
                        "运算时点": "单时点",
                        "运算ID": "多ID",
                        "数据类型": "double"
                    }
                )
            elif period_type=="m":
                ijCumReturn = QS.FactorDB.TimeOperation(
                    ijFactorName,
                    [ManagerReturn],
                    sys_args={
                        "算子": return_month_fun,
                        "参数": {"n_period": n_period},
                        "回溯期数": [31 * n_period],
                        "运算时点": "单时点",
                        "运算ID": "多ID",
                        "数据类型": "double"
                    }
                )
            elif period_type=="q":
                ijCumReturn = QS.FactorDB.TimeOperation(
                    ijFactorName,
                    [ManagerReturn],
                    sys_args={
                        "算子": return_month_fun,
                        "参数": {"n_period": n_period * 3},
                        "回溯期数": [31 * n_period * 3],
                        "运算时点": "单时点",
                        "运算ID": "多ID",
                        "数据类型": "double"
                    }
                )
            elif period_type=="y":
                ijCumReturn = QS.FactorDB.TimeOperation(
                    ijFactorName, 
                    [ManagerReturn],
                    sys_args={
                        "算子": return_month_fun,
                        "参数": {"n_period": n_period * 12},
                        "回溯期数": [31 * n_period * 12],
                        "运算时点": "单时点",
                        "运算ID": "多ID",
                        "数据类型": "double"
                    }
                )
            else:
                raise Exception(f"{period_type} is not a supported period type!")
            Factors.append(ijCumReturn)
            
            # ####################### 收益排名 #######################
            ijFactorName = f"rank_{time_node}_{args['rebalance']}_{args['weight']}_{iType}"
            ijRank = fd.standardizeRank(ijCumReturn, mask=fd.notnull(ijCumReturn), cat_data=None, ascending=False, uniformization=True, offset=0, factor_name=ijFactorName)
            Factors.append(ijRank)
    
        # ####################### 峰值收益(峰值动量) #######################
        look_back_period = {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252, "2y": 504, "3y": 756, "5y": 1260}# 回溯期
        for time_node, look_back_days in look_back_period.items():
            ijFactorName = f"max_return_{time_node}_{args['rebalance']}_{args['weight']}_{iType}"         
            max_return = QS.FactorDB.TimeOperation(
                ijFactorName,
                [ManagerReturn],
                sys_args={
                    "算子": get_max_return,
                    "参数": {},
                    "回溯期数": [look_back_days - 1],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "double"
                }
            )
            Factors.append(max_return)
    
        # ####################### 年化收益率 #######################
        look_back_period = {"1m": 21, "3m": 63, "6m": 126, "1y": 252, "3y": 756, "5y": 1260}# 回溯期
        MdlArgs = dict(
            annual_period = annual_period,# 年化周期数
            min_period = 20,# 最小期数
            min_period_ratio = 0.5# 最小期数比例
        )
        for time_node, look_back_days in look_back_period.items():
            # 算术平均年化收益率
            ijFactorName = f"arithmetic_annual_return_{time_node}_{args['rebalance']}_{args['weight']}_{iType}"
            arithmetic_annual_return = QS.FactorDB.TimeOperation(
                ijFactorName,
                [ManagerReturn],
                sys_args={
                    "算子": get_arithmetic_annual_return,
                    "参数": dict(**MdlArgs, look_back_days=look_back_days),
                    "回溯期数": [look_back_days - 1],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "double"
                }
            )
            Factors.append(arithmetic_annual_return)
            # 几何平均年化收益率
            ijFactorName = f"geometry_annual_return_{time_node}_{args['rebalance']}_{args['weight']}_{iType}"         
            geometry_annual_return = QS.FactorDB.TimeOperation(
                ijFactorName,
                [ManagerReturn],
                sys_args={
                    "算子": get_geometry_annual_return,
                    "参数": dict(**MdlArgs, look_back_days=look_back_days),
                    "回溯期数": [look_back_days - 1],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "double"
                }
            )
            Factors.append(geometry_annual_return)
        
            # ####################### 年化超额收益率 #######################
            # 算术平均年化收益率
            ijFactorName = f"arithmetic_annual_return_extra_{time_node}_{args['rebalance']}_{args['weight']}_{iType}"         
            arithmetic_annual_return_extra = QS.FactorDB.TimeOperation(
                ijFactorName,
                [ActiveReturn],
                sys_args={
                    "算子": get_arithmetic_annual_return,
                    "参数": dict(**MdlArgs, look_back_days=look_back_days),
                    "回溯期数": [look_back_days - 1],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "double"
                }
            )
            Factors.append(arithmetic_annual_return_extra)
            # 几何平均年化收益率
            ijFactorName = f"geometry_annual_return_extra_{time_node}_{args['rebalance']}_{args['weight']}_{iType}"         
            geometry_annual_return_extra = QS.FactorDB.TimeOperation(
                ijFactorName,
                [ActiveReturn],
                sys_args={
                    "算子": get_geometry_annual_return,
                    "参数": dict(**MdlArgs, look_back_days=look_back_days),
                    "回溯期数": [look_back_days - 1],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "double"
                }
            )
            Factors.append(geometry_annual_return_extra)
    
        # ####################### 偏度 #######################
        look_back_period = {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252, "2y": 504, "3y": 756, "5y": 1260}# 回溯期
        MdlArgs = dict(
            min_period = 20,# 最小期数
            min_period_ratio = 0.5# 最小期数比例
        )
        for time_node, look_back_days in look_back_period.items():
            ijFactorName = f"skewness_{time_node}_{args['rebalance']}_{args['weight']}_{iType}"           
            skewness = QS.FactorDB.TimeOperation(
                ijFactorName,
                [ManagerReturn],
                sys_args={
                    "算子": get_skewness,
                    "参数": dict(**MdlArgs, look_back_days=look_back_days),
                    "回溯期数": [look_back_days - 1],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "double"
                }
            )
            Factors.append(skewness)
    
    UpdateArgs = {
        "因子表": "mf_manager_cn_factor_return",
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