# -*- coding: utf-8 -*-
"""公募基金收益因子(基于日数据)"""
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
    Idx = np.array(idt).searchsorted(idt[-1]-dt.timedelta(args["n_period"]*7-1)) - 1
    return x[0][-1] / x[0][Idx] - 1

# 计算月频收益
def return_month_fun(f, idt, iid, x, args):
    Idx = np.array(idt).searchsorted(roll_back_months(idt[-1], args["n_period"]) + dt.timedelta(1)) - 1
    return x[0][-1] / x[0][Idx] - 1

# 计算给定周期最大收益率
def get_max_return(f, idt, iid, x, args):
    return np.nanmax(x[0], axis=0)

# 同类排名
def calculate_rank(f, idt, iid, x, args):
    Return, Cat = x[0], x[1]
    Mask = pd.notnull(Return)
    AllCats = pd.unique(Cat[pd.notnull(Cat) & Mask])
    if AllCats.shape[0]==0:
        return np.full(shape=Return.shape, fill_value=np.nan)
    Rank = np.full(shape=Return.shape, fill_value=np.nan)
    Num = np.full(shape=Return.shape, fill_value=np.nan)
    for i, iCat in enumerate(AllCats):
        iMask = ((Cat==iCat) & Mask)
        iNum = np.sum(iMask)
        if iNum==0: continue
        iRank = np.full(shape=(iNum,), fill_value=-1, dtype=int)
        iRank[np.argsort(-Return[iMask])] = np.arange(1, iNum+1)
        Rank[iMask] = iRank
        Num[iMask] = iNum
    return Rank / Num

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
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    # 基金是否存续
    Exist = LDB.getTable("mf_cn_status").getFactor("if_exist")
    Mask = (Exist==1)
    
    # 基金分类
    FT = LDB.getTable("mf_cn_type")
    FundType = FT.getFactor("jy_type_second")
    
    # 基金净值和日收益率
    FT = JYDB.getTable("公募基金复权净值")
    NetValueAdj = FT.getFactor("复权单位净值", args={"回溯天数": np.inf})
    NetValueAdj = fd.where(NetValueAdj, Mask, np.nan)
    FundReturn = NetValueAdj / fd.lag(NetValueAdj, 1, 1) - 1
    
    # 基金基准日收益率和主动日收益率
    FT = JYDB.getTable("公募基金基准收益率", args={"回溯天数", 0})
    BenchmarkReturn = FT.getFactor("本日基金基准增长率") / 100
    ActiveReturn = FundReturn - BenchmarkReturn
    
    # ####################### 累积收益(累积动量) #######################
    look_back_period = ["1w", "2w", "3w", "1m", "2m", "3m", "6m", "1y", "2y", "3y", "5y"]# 回溯期
    
    CumReturn = {}
    for time_node in look_back_period:
        n_period = int(re.findall("\d+", time_node)[0])
        period_type = re.findall("\D+", time_node)[0]
        if period_type=="w":
            CumReturn[time_node] = QS.FactorDB.TimeOperation(
                f"return_{time_node}",
                [NetValueAdj],
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
            CumReturn[time_node] = QS.FactorDB.TimeOperation(
                f"return_{time_node}",
                [NetValueAdj],
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
            CumReturn[time_node] = QS.FactorDB.TimeOperation(
                f"return_{time_node}",
                [NetValueAdj],
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
            CumReturn[time_node] = QS.FactorDB.TimeOperation(
                f"return_{time_node}",
                [NetValueAdj],
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
    Factors.extend(CumReturn.values())
    
    # ####################### 收益排名 #######################
    for time_node in look_back_period:
        Rank = QS.FactorDB.SectionOperation(
            f"rank_{time_node}",
            [CumReturn[time_node], FundType],
            sys_args={
                "算子": calculate_rank,
                "参数": {},
                "运算时点": "单时点",
                "输出形式": "全截面",
                "数据类型": "double"
            }
        )
        Factors.append(Rank)
    
    # ####################### 峰值收益(峰值动量) #######################
    look_back_period = {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252, "2y": 504, "3y": 756, "5y": 1260}# 回溯期
    for time_node, look_back_days in look_back_period.items():
        max_return = QS.FactorDB.TimeOperation(
            f"max_return_{time_node}",
            [FundReturn],
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
        arithmetic_annual_return = QS.FactorDB.TimeOperation(
            f"arithmetic_annual_return_{time_node}",
            [FundReturn],
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
        geometry_annual_return = QS.FactorDB.TimeOperation(
            f"geometry_annual_return_{time_node}",
            [FundReturn],
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
        arithmetic_annual_return_extra = QS.FactorDB.TimeOperation(
            f"arithmetic_annual_return_extra_{time_node}",
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
        geometry_annual_return_extra = QS.FactorDB.TimeOperation(
            f"geometry_annual_return_extra_{time_node}",
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
        skewness = QS.FactorDB.TimeOperation(
            f"skewness_{time_node}",
            [FundReturn],
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
        "因子表": "mf_cn_factor_return",
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