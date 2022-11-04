# -*- coding: utf-8 -*-
"""公募基金基准历史收益率"""
import os
import re
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

def roll_back_months(idt, n):
    nYear, nMonth = (n-1) // 12, (n-1) % 12
    TargetYear = idt.year - nYear
    TargetMonth = idt.month - nMonth
    TargetYear -= (TargetMonth<=0)
    TargetMonth += (TargetMonth<=0) * 12
    TargetDT = dt.datetime(TargetYear, TargetMonth, 1) - dt.timedelta(1)
    return dt.datetime(TargetDT.year, TargetDT.month, min(idt.day, TargetDT.day))

# 计算本周以来的收益率
def calculate_return_this_week(f, idt, iid, x, args):
    Idx = np.array(idt, dtype="O").searchsorted(idt[-1] - dt.timedelta(idt[-1].weekday()))
    Mask = (np.sum(pd.notnull(x[0][Idx:, :]), axis=0)==0)
    Rslt = np.nanprod(1 + x[0][Idx:, :], axis=0) - 1
    Rslt[Mask] = np.nan
    return Rslt


# 计算本月以来的收益率
def calculate_return_this_month(f, idt, iid, x, args):
    Idx = np.array(idt, dtype="O").searchsorted(dt.datetime(idt[-1].year, idt[-1].month, 1))
    Mask = (np.sum(pd.notnull(x[0][Idx:, :]), axis=0)==0)
    Rslt = np.nanprod(1 + x[0][Idx:, :], axis=0) - 1
    Rslt[Mask] = np.nan
    return Rslt


# 计算本季以来的收益率
def calculate_return_this_quarter(f, idt, iid, x, args):
    Idx = np.array(idt, dtype="O").searchsorted(dt.datetime(idt[-1].year, (idt[-1].month-1) // 3 * 3 + 1, 1))
    Mask = (np.sum(pd.notnull(x[0][Idx:, :]), axis=0)==0)
    Rslt = np.nanprod(1 + x[0][Idx:, :], axis=0) - 1
    Rslt[Mask] = np.nan
    return Rslt


# 计算今年以来的收益率
def calculate_return_this_year(f, idt, iid, x, args):
    Idx = np.array(idt, dtype="O").searchsorted(dt.datetime(idt[-1].year, 1, 1))
    Mask = (np.sum(pd.notnull(x[0][Idx:, :]), axis=0)==0)
    Rslt = np.nanprod(1 + x[0][Idx:, :], axis=0) - 1
    Rslt[Mask] = np.nan
    return Rslt


def return_week_fun(f, idt, iid, x, args):
    Idx = np.array(idt).searchsorted(idt[-1] - dt.timedelta(args["n_period"]*7-1))
    Mask = (np.sum(pd.notnull(x[0][Idx:, :]), axis=0)==0)
    Rslt = np.nanprod(1 + x[0][Idx:, :], axis=0) - 1
    Rslt[Mask] = np.nan
    return Rslt


def return_month_fun(f, idt, iid, x, args):
    Idx = np.array(idt).searchsorted(roll_back_months(idt[-1], args["n_period"])+dt.timedelta(1))
    Mask = (np.sum(pd.notnull(x[0][Idx:, :]), axis=0)==0)
    Rslt = np.nanprod(1 + x[0][Idx:, :], axis=0) - 1
    Rslt[Mask] = np.nan
    return Rslt


# args 应该包含的参数
# JYDB: 聚源因子库对象
def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    # 基金是否存续状态
    Exist = LDB.getTable("mf_cn_status").getFactor("if_exist")
    Mask = (Exist==1)
    
    FT = JYDB.getTable("公募基金基准收益率", args={"回溯天数":0})
    DailyReturn = Factorize(FT.getFactor("本日基金基准增长率") / 100, factor_name="daily_return")
    Factors.append(DailyReturn)
    DailyReturn = fd.where(DailyReturn, Mask, np.nan)
    
    # 成立以来收益率
    Factors.append(Factorize(FT.getFactor("基金成立以来基准增长率") / 100, factor_name="return_for_since"))
    
    # 历史收益率
    look_back_period = ['1w', '2w', '3w', '1m', '2m', '3m', '6m', '1y', '2y', '3y', '5y']# 回溯期
    for time_node in look_back_period:
        n_period = int(re.findall("\d+", time_node)[0])
        period_type = re.findall("\D+", time_node)[0]
        if period_type=="w":
            iFactor = QS.FactorDB.TimeOperation(f"return_{time_node}",
                                                [DailyReturn],
                                                sys_args={"算子": return_week_fun,
                                                          "参数": {"n_period": n_period},
                                                          "回溯期数": [7*n_period],
                                                          "运算时点": "单时点",
                                                          "运算ID": "多ID",
                                                          "数据类型": "double"})
        elif period_type=="m":
            iFactor = QS.FactorDB.TimeOperation(f"return_{time_node}",
                                                [DailyReturn],
                                                sys_args={"算子": return_month_fun,
                                                          "参数": {"n_period": n_period},
                                                          "回溯期数": [31*n_period],
                                                          "运算时点": "单时点",
                                                          "运算ID": "多ID",
                                                          "数据类型": "double"})
        elif period_type=="y":
            iFactor = QS.FactorDB.TimeOperation(f"return_{time_node}",
                                                [DailyReturn],
                                                sys_args={"算子": return_month_fun,
                                                          "参数": {"n_period": n_period*12},
                                                          "回溯期数": [31*n_period*12],
                                                          "运算时点": "单时点",
                                                          "运算ID": "多ID",
                                                          "数据类型": "double"})
        else:
            raise Exception(f"{period_type} is not a supported period type!")
        Factors.append(iFactor)
    
    # 本周收益率
    Return = QS.FactorDB.TimeOperation(
        "return_this_week",
        [DailyReturn],
        sys_args={
            "算子": calculate_return_this_week,
            "参数": {},
            "回溯期数": [7 - 1],
            "运算时点": "单时点",
            "运算ID": "多ID",
            "数据类型": "double"
        }
    )
    Factors.append(Return)
    
    # 本月收益率
    Return = QS.FactorDB.TimeOperation(
        "return_this_month",
        [DailyReturn],
        sys_args={
            "算子": calculate_return_this_month,
            "参数": {},
            "回溯期数": [31 - 1],
            "运算时点": "单时点",
            "运算ID": "多ID",
            "数据类型": "double"
        }
    )
    Factors.append(Return)
    
    # 本季收益率
    Return = QS.FactorDB.TimeOperation(
        "return_this_quarter",
        [DailyReturn],
        sys_args={
            "算子": calculate_return_this_quarter,
            "参数": {},
            "回溯期数": [93 - 1],
            "运算时点": "单时点",
            "运算ID": "多ID",
            "数据类型": "double"
        }
    )
    Factors.append(Return)
    
    # 本年收益率
    Return = QS.FactorDB.TimeOperation(
        "return_this_year",
        [DailyReturn],
        sys_args={
            "算子": calculate_return_this_year,
            "参数": {},
            "回溯期数": [366 - 1],
            "运算时点": "单时点",
            "运算ID": "多ID",
            "数据类型": "double"
        }
    )
    Factors.append(Return)
    
    UpdateArgs = {"因子表": "mf_cn_benchmark_return",
                  "默认起始日": dt.datetime(2002,1,1),
                  "最长回溯期": 365*10,
                  "IDs": "公募基金"}
    
    return (Factors, UpdateArgs)


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
    
    StartDT, EndDT = dt.datetime(2020, 3, 1), dt.datetime(2021, 4, 30)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365*10), end_date=EndDT.date(), output_type="datetime")
    
    #IDs = sorted(pd.read_csv("../conf/mf/MFIDs.csv", index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
    IDs = JYDB.getMutualFundID(is_current=False)
    
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
