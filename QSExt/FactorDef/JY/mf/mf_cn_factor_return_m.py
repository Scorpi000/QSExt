# -*- coding: utf-8 -*-
"""公募基金收益因子(月频)"""
import os
import re
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize
from .mf_cn_factor_return import get_max_return, get_arithmetic_annual_return, get_geometry_annual_return, get_skewness

# 计算顺境收益率
def get_prosperity_return(f, idt, iid, x, args):
    fund_return, market_return = x
    mask = (market_return>np.nanmedian(market_return))
    rslt = (np.nanprod(1 + fund_return[mask], axis=0) - 1) / args["look_back_days"]
    return rslt

# 计算逆境收益率
def get_adversity_return(f, idt, iid, x, args):
    fund_return, market_return = x
    mask = (market_return<np.nanmedian(market_return))
    rslt = (np.nanprod(1 + fund_return[mask], axis=0) - 1) / args["look_back_days"]
    return rslt

def defFactor(args={}, debug=False):
    Factors = []
    
    annual_period = args.get("annual_period", 12)# 年化周期数
    
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
    FT = LDB.getTable("mf_cn_benchmark_return")
    BenchmarkReturn = FT.getFactor("return_this_month")
    ActiveReturn = FundReturn - BenchmarkReturn
    
    # ####################### 峰值收益(峰值动量) #######################
    look_back_period = {"1y": 12, "3y": 36, "5y": 60}
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
    look_back_period = {"1y": 12, "3y": 36, "5y": 60}
    MdlArgs = dict(
        annual_period = annual_period,# 年化周期数
        min_period = 12,# 最小期数
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
    look_back_period = {"1y": 12, "3y": 36, "5y": 60}
    MdlArgs = dict(
        min_period = 12,# 最小期数
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
    
    # ####################### 逆(顺)境收益率 #######################
    MarketID = "000001.SH"
    FT = JYDB.getTable("指数行情", args={"回溯天数": 0})
    MarketPrice = FT.getFactor("收盘价(元-点)")
    MarketReturn = fd.disaggregate(MarketPrice / fd.lag(MarketPrice, 1, 1) - 1, aggr_ids=[MarketID])
    look_back_period = {"1y": 12, "3y": 36, "5y": 60}
    MdlArgs = dict(
        min_period = 12,# 最小期数
        min_period_ratio = 0.5# 最小期数比例
    )
    for time_node, look_back_days in look_back_period.items():
        adversity_return = QS.FactorDB.TimeOperation(
            f"adversity_return_{time_node}",
            [FundReturn, MarketReturn],
            sys_args={
                "算子": get_adversity_return,
                "参数": {"look_back_days": look_back_days},
                "回溯期数": [look_back_days - 1] * 2,
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
        Factors.append(adversity_return)
        
        prosperity_return = QS.FactorDB.TimeOperation(
            f"prosperity_return_{time_node}",
            [FundReturn, MarketReturn],
            sys_args={
                "算子": get_prosperity_return,
                "参数": {"look_back_days": look_back_days},
                "回溯期数": [look_back_days - 1] * 2,
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
        Factors.append(prosperity_return)
    
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_return_m",
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