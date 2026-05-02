# -*- coding: utf-8 -*-
"""公募基金同类平均收益率"""
import os
import re
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize
from .mf_cn_benchmark_return import return_week_fun, return_month_fun, calculate_return_this_week, calculate_return_this_month, calculate_return_this_quarter, calculate_return_this_year

def peer_return_fun(f, idt, iid, x, args):
    Data = pd.DataFrame({"Return": x[0], "Cate": x[1]}, index=iid)
    PeerReturn = Data.groupby(by=["Cate"]).mean().rename(columns={"Return": "PeerReturn"})
    return Data.merge(PeerReturn, how="left", left_on=["Cate"], right_index=True)["PeerReturn"].loc[iid].values

def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    # 基金是否存续状态
    Exist = LDB.getTable("mf_cn_status").getFactor("if_exist")
    Mask = (Exist==1)
    
    # 基金分类
    FT = LDB.getTable("mf_cn_type")
    FundType = FT.getFactor("jy_type_second")
    
    # 基金净值
    FT = JYDB.getTable("公募基金复权净值")
    NetValueAdj = FT.getFactor("复权单位净值", args={"回溯天数": np.inf})
    NetValueAdj = fd.where(NetValueAdj, Mask, np.nan)
    FundReturn = NetValueAdj / fd.lag(NetValueAdj, 1, 1) - 1
    
    # 单期收益率
    PeerReturn = QS.FactorDB.SectionOperation(
        "daily_return",
        [FundReturn, FundType],
        sys_args={
            "算子": peer_return_fun,
            "参数": {},
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors.append(PeerReturn)
    
    # 历史收益率
    look_back_period = ['1w', '2w', '3w', '1m', '2m', '3m', '6m', '1y', '2y', '3y', '5y']# 回溯期
    for time_node in look_back_period:
        n_period = int(re.findall("\d+", time_node)[0])
        period_type = re.findall("\D+", time_node)[0]
        if period_type=="w":
            iFactor = QS.FactorDB.TimeOperation(
                f"return_{time_node}",
                [PeerReturn],
                sys_args={
                    "算子": return_week_fun,
                    "参数": {"n_period": n_period},
                    "回溯期数": [7*n_period],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "double"
                }
            )
        elif period_type=="m":
            iFactor = QS.FactorDB.TimeOperation(
                f"return_{time_node}",
                [PeerReturn],
                sys_args={
                    "算子": return_month_fun,
                    "参数": {"n_period": n_period},
                    "回溯期数": [31*n_period],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "double"
                }
            )
        elif period_type=="q":
            iFactor = QS.FactorDB.TimeOperation(
                f"return_{time_node}",
                [PeerReturn],
                sys_args={
                    "算子": return_month_fun,
                    "参数": {"n_period": n_period},
                    "回溯期数": [31*n_period*3],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "double"
                }
            )
        elif period_type=="y":
            iFactor = QS.FactorDB.TimeOperation(
                f"return_{time_node}",
                [PeerReturn],
                sys_args={
                    "算子": return_month_fun,
                    "参数": {"n_period": n_period*12},
                    "回溯期数": [31*n_period*12],
                    "运算时点": "单时点",
                    "运算ID": "多ID",
                    "数据类型": "double"
                }
            )
        else:
            raise Exception(f"{period_type} is not a supported period type!")
        Factors.append(iFactor)
    
    # 本周收益率
    Return = QS.FactorDB.TimeOperation(
        "return_this_week",
        [PeerReturn],
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
        [PeerReturn],
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
        [PeerReturn],
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
        [PeerReturn],
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
    
    UpdateArgs = {"因子表": "mf_cn_peer_return",
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
