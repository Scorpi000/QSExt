# -*- coding: utf-8 -*-
"""公募基金持仓分析因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# 计算组合平均指标, SectionOperation, 单时点, 全截面
# x: [成份ID, 权重, 指标]
# args: {ComponentIDs: ...}
def calcPortfolioAvgIndicator(f, idt, iid, x, args):
    PortfolioIndicator = pd.Series(x[2], index=args["ComponentIDs"])
    PortfolioWeight = pd.Series(x[1], index=args["ComponentIDs"])
    Rslt = np.full(shape=x[0].shape, fill_value=np.nan)
    for i, iIDs in enumerate(x[0]):
        if (not isinstance(iIDs, list)) or (PortfolioIndicator.index.intersection(iIDs).shape[0]==0):
            continue
        iWeight = PortfolioWeight.loc[iIDs].values
        iIndicator = PortfolioIndicator.loc[iIDs].values * iWeight
        iTotalWeight = np.nansum(iWeight[pd.notnull(iIndicator)])
        if iTotalWeight<=0: continue
        Rslt[i] = np.nansum(iIndicator) / iTotalWeight
    return Rslt
    

def defFactor(args={}, debug=False):
    Factors = []
    
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
    
    # 无风险利率
    RiskFreeRateID = "600020002"# 3月期国债利率
    FT = JYDB.getTable("宏观基础指标数据", args={"回溯天数": np.inf, "公告时点字段": None, "忽略时间": True})
    rf = fd.disaggregate(FT.getFactor("指标数据") / 100 * 10 ** FT.getFactor("量纲系数"), aggr_ids=[RiskFreeRateID])# 无风险年利率
    RiskFreeRate = rf / 360
    
    # 持股集中度
    
    # 持股比例稳定性
    
    # 行业配置稳定性
    
    # 规模风格稳定性
    
    # 成长/价值风格稳定性
    
    # 基金风格稳定性
    
    # 组合平均 ROE, 盈市率, 净市率
    FT = LDB.getTable("mf_cn_stock_component_penetrated", args={"回溯天数": np.inf, "因子值类型": "list"})
    ComponentCode = FT.getFactor("component_code")
    
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    FloatCap = FT.getFactor("float_cap")
    ComponentIDs = FT.getID()
    
    FT = LDB.getTable("stock_cn_factor_value")
    EP = FT.getFactor("ep_ttm")
    AvgEP = QS.FactorDB.SectionOperation(
        "avg_ep",
        [ComponentCode, FloatCap, EP],
        sys_args={
            "算子": calcPortfolioAvgIndicator,
            "参数": {"ComponentIDs": ComponentIDs},
            "描述子截面": [None, ComponentIDs, ComponentIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"     
        }
    )
    Factors.append(AvgEP)
    
    BP = FT.getFactor("bp_lr")
    AvgBP = QS.FactorDB.SectionOperation(
        "avg_bp",
        [ComponentCode, FloatCap, BP],
        sys_args={
            "算子": calcPortfolioAvgIndicator,
            "参数": {"ComponentIDs": ComponentIDs},
            "描述子截面": [None, ComponentIDs, ComponentIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"     
        }
    )
    Factors.append(AvgBP)
    
    FT = LDB.getTable("stock_cn_factor_quality")
    ROE = FT.getFactor("roe_ttm")
    AvgROE = QS.FactorDB.SectionOperation(
        "avg_roe",
        [ComponentCode, FloatCap, ROE],
        sys_args={
            "算子": calcPortfolioAvgIndicator,
            "参数": {"ComponentIDs": ComponentIDs},
            "描述子截面": [None, ComponentIDs, ComponentIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"     
        }
    )
    Factors.append(AvgROE)
    
    
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_holding_based_analysis",
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