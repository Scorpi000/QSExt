# -*- coding: utf-8 -*-
"""公募基金收益分析因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# 计算行为相似性, PanelOperation, 单时点, 全截面
# x: [基金收益率, 指数收益率, 无风险利率]
# args: {min_periods: ..., index_info: ...}
def calcBehavioralPreference(f, idt, iid, x, args):
    Mask = (np.sum(pd.notnull(x[0]), axis=0)<args["min_periods"])
    Y = x[0] - x[2]
    X = x[1] - np.repeat(x[2][:, :1], x[1].shape[1], axis=1)
    R2 = pd.DataFrame(np.c_[X, Y]).corr(min_periods=args["min_periods"]).values[:X.shape[1], X.shape[1]:] ** 2
    Mask = (Mask | (np.sum(pd.notnull(R2), axis=0)==0))
    R2[:, Mask] = 0
    Idx = np.nanargmax(R2, axis=0)
    Rslt = args["index_info"].values[Idx]
    Rslt[Mask] = None
    return Rslt

def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    # 基金是否存续
    Exist = LDB.getTable("mf_cn_status").getFactor("if_exist")
    Mask = (Exist==1)
    
    # 基金净值和收益率
    FT = JYDB.getTable("公募基金复权净值")
    NetValueAdj = FT.getFactor("复权单位净值", args={"回溯天数": np.inf})
    NetValueAdj = fd.where(NetValueAdj, Mask, np.nan)
    FundReturn = NetValueAdj / fd.lag(NetValueAdj, 1, 1) - 1
    
    # 无风险利率
    RiskFreeRateID = "600020002"# 3月期国债利率
    FT = JYDB.getTable("宏观基础指标数据", args={"回溯天数": np.inf, "公告时点字段": None, "忽略时间": True})
    rf = fd.disaggregate(FT.getFactor("指标数据") / 100 * 10 ** FT.getFactor("量纲系数"), aggr_ids=[RiskFreeRateID])# 无风险年利率
    RiskFreeRate = rf / 360
    
    IndexFT = JYDB.getTable("指数行情", args={"回溯天数": 0})
    
    # ####################### 规模偏好 #######################
    SizeIndex = pd.Series(["大盘", "中盘", "小盘"], index=["399314.SZ", "399315.SZ", "399316.SZ"])
    SizeIndexReturn = IndexFT.getFactor("涨跌幅") / 100
    look_back_period = {"1y": 252}
    min_period_ratio = 0.67
    for iLookBack, iLookBackPeriod in look_back_period.items():
        iMinPeriod = int(iLookBackPeriod * min_period_ratio)
        Size = QS.FactorDB.PanelOperation(
            f"size_{iLookBack}",
            [FundReturn, SizeIndexReturn, RiskFreeRate],
            sys_args={
                "算子": calcBehavioralPreference,
                "参数": {"min_periods": iMinPeriod, "index_info": SizeIndex},
                "回溯期数": [iLookBackPeriod - 1] * 3,
                "描述子截面": [None, SizeIndex.index.tolist(), None],
                "运算时点": "单时点",
                "输出形式": "全截面",
                "数据类型": "string"
            }
        )
        Factors.append(Size)
    
    # ####################### 风格偏好 #######################
    StyleIndex = pd.Series(["平衡", "成长", "价值"], index=["399311.SZ", "399370.SZ", "399371.SZ"])
    StyleIndexReturn = IndexFT.getFactor("涨跌幅") / 100
    look_back_period = {"1y": 252}
    min_period_ratio = 0.67
    for iLookBack, iLookBackPeriod in look_back_period.items():
        iMinPeriod = int(iLookBackPeriod * min_period_ratio)
        Style = QS.FactorDB.PanelOperation(
            f"style_{iLookBack}",
            [FundReturn, StyleIndexReturn, RiskFreeRate],
            sys_args={
                "算子": calcBehavioralPreference,
                "参数": {"min_periods": iMinPeriod, "index_info": StyleIndex},
                "回溯期数": [iLookBackPeriod - 1] * 3,
                "描述子截面": [None, StyleIndex.index.tolist(), None],
                "运算时点": "单时点",
                "输出形式": "全截面",
                "数据类型": "string"
            }
        )
        Factors.append(Style)
    
    # ####################### 行业偏好 #######################
    IndustryIndex = pd.Series(
        ["能源", "原材料", "工业", "可选消费", "主要消费", "医药卫生", "金融地产", "信息技术", "电信", "公用事业"], 
        index=["000928.SH", "000929", "000930", "000931", "000932.SH", "000933.SH", "000934.SH", "000935.SH", "000936", "000937"]
    )
    IndustryIndexReturn = IndexFT.getFactor("涨跌幅") / 100
    look_back_period = {"1y": 252}
    min_period_ratio = 0.67
    for iLookBack, iLookBackPeriod in look_back_period.items():
        iMinPeriod = int(iLookBackPeriod * min_period_ratio)
        Industry = QS.FactorDB.PanelOperation(
            f"industry_{iLookBack}",
            [FundReturn, IndustryIndexReturn, RiskFreeRate],
            sys_args={
                "算子": calcBehavioralPreference,
                "参数": {"min_periods": iMinPeriod, "index_info": IndustryIndex},
                "回溯期数": [iLookBackPeriod - 1] * 3,
                "描述子截面": [None, IndustryIndex.index.tolist(), None],
                "运算时点": "单时点",
                "输出形式": "全截面",
                "数据类型": "string"
            }
        )
        Factors.append(Industry)
        
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_return_based_analysis",
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