# -*- coding: utf-8 -*-
"""公募基金表现稳定性因子(月频)"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# 计算收益率高于沪深 300 的月数/总月数, TimeOperation, 单时点, 多ID
# x: [基金收益率, 无风险利率, 市场收益率]
# args: {min_periods: ...}
def beyond_hs300_ratio_fun(f, idt, iid, x, args):
    NaMask = (pd.notnull(x[0]) & pd.notnull(x[1]))
    TotalNum = np.sum(NaMask, axis=0)
    Rslt = np.sum((x[0]>x[1]) & NaMask, axis=0) / TotalNum
    Rslt[(np.sum(np.notnull(x[0]), axis=0)<args["min_periods"]) | (TotalNum<=0)] = np.nan
    return Rslt

# 计算收益率高于同类平均数的月数/总月数, PanelOperation, 单时点, 全截面
# x: [基金收益率, 基金分类]
# args: {min_periods: ...}
def beyond_peer_ratio_fun(f, idt, iid, x, args):
    nPeriod = x[0].shape[0]
    Return = pd.DataFrame(x[0].T)
    Return.insert(0, "Cate", x[1][0])
    Return = Return.merge(Return.groupby(by=["Cate"]).mean(), how="left", left_on=["Cate"], right_index=True).iloc[:, 1:].values
    TotalNum = np.sum(pd.notnull(Return[:, :nPeriod]), axis=1)
    Rslt = np.sum(Return[:, :nPeriod]>Return[:, nPeriod:], axis=1) / TotalNum
    Rslt[(np.sum(np.notnull(x[0]), axis=0)<args["min_periods"]) | pd.isnull(x[1][0]) | (TotalNum<=0)] = np.nan
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
    
    # 基金净值和收益率
    FT = JYDB.getTable("公募基金复权净值")
    NetValueAdj = FT.getFactor("复权单位净值", args={"回溯天数": np.inf})
    NetValueAdj = fd.where(NetValueAdj, Mask, np.nan)
    FundReturn = NetValueAdj / fd.lag(NetValueAdj, 1, 1) - 1
    
    # ####################### 收益率高于沪深 300 的月数/总月数 #######################
    look_back_period = {"1y": 12, "3y": 36, "5y": 60}# 回溯期
    min_period = 12# 最小期数
    min_period_ratio = 0.5# 最小期数比例
    MarketID = "000300.SH"
    FT = JYDB.getTable("指数行情", args={"回溯天数": 0})
    MarketPrice = FT.getFactor("收盘价(元-点)")
    MarektReturn = fd.disaggregate(MarketPrice / fd.lag(MarketPrice, 1, 1) - 1, aggr_ids=[MarketID])
    for iLookBack, iLookBackPeriods in look_back_period.items():
        iMinPeriods = max(min_period, int(iLookBackPeriods * min_period_ratio))
        beyond_hs300_ratio = QS.FactorDB.TimeOperation(
            f"beyond_hs300_ratio_{iLookBack}",
            [FundReturn, MarektReturn],
            sys_args={
                "算子": beyond_hs300_ratio_fun,
                "参数": {"min_periods": iMinPeriods},
                "回溯期数": [iLookBackPeriods - 1] * 2,
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
        Factors.append(beyond_hs300_ratio)
    
    # ####################### 收益率高于同类平均数的月数/总月数 #######################
    look_back_period = {"1y": 12, "3y": 36, "5y": 60}# 回溯期
    min_period = 12# 最小期数
    min_period_ratio = 0.5# 最小期数比例
    for iLookBack, iLookBackPeriods in look_back_period.items():
        iMinPeriods = max(min_period, int(iLookBackPeriods * min_period_ratio))
        beyond_peer_ratio = QS.FactorDB.PanelOperation(
            f"beyond_peer_ratio_{iLookBack}",
            [FundReturn, MarektReturn],
            sys_args={
                "算子": beyond_peer_ratio_fun,
                "参数": {"min_periods": iMinPeriods},
                "回溯期数": [iLookBackPeriods - 1, 1-1],
                "运算时点": "单时点",
                "输出形式": "全截面",
                "数据类型": "double"
            }
        )
        Factors.append(beyond_peer_ratio)
        
    
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_performance_stability_m",
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