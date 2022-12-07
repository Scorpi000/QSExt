# -*- coding: utf-8 -*-
"""A股沪深港通"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

def mask(f, idt, iid, x, args):
    """所有填充的数据, 需要用 is_component 做过滤, 防止不是成份股的也填上数据"""
    data, is_component = x
    data[is_component!=1] = np.nan
    return data

# args:
# JYDB: 聚源因子库对象
# LDB: 本地因子库对象
def defFactor(args={}):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    Close = FT.getFactor("close")
    Avg = FT.getFactor("avg")
    
    # 沪股通成份股
    FT = JYDB.getTable("沪股通成分股", args={"只填起始日": False, "多重映射": True})
    IsComponent = FT.getFactor("成份标志")
    
    # 深股通成份股
    FT = JYDB.getTable("深股通成分股", args={"只填起始日": False, "多重映射": True})
    IsComponent = fd.where(IsComponent, fd.notnull(IsComponent), FT.getFactor("成份标志"))
    
    # 沪深港通资金流
    FT = JYDB.getTable("沪(深)股通持股统计")
    Holding = FT.getFactor("持股数量(股)")
    Holding = QS.FactorDB.PointOperation(
        "holding_volume",
        [Holding, IsComponent],
        sys_args={
            "算子": mask,
            "参数": {},
            "运算时点": "多时点",
            "运算ID": "多ID",
            "数据类型": "double"
        }
    )
    
    HoldingRatio = FT.getFactor("持股占比(%)") / 100
    HoldingRatio = QS.FactorDB.PointOperation(
        "holding_ratio",
        [HoldingRatio, IsComponent],
        sys_args={
            "算子": mask,
            "参数": {},
            "运算时点": "多时点",
            "运算ID": "多ID",
            "数据类型": "double"
        }
    )
    
    HoldingNafilled = FT.getFactor("持股数量(股)", args={"回溯天数": np.inf})
    HoldingNafilled = QS.FactorDB.PointOperation(
        "holding_volume_nafilled",
        [HoldingNafilled, IsComponent],
        sys_args={
            "算子": mask,
            "参数": {},
            "运算时点": "多时点",
            "运算ID": "多ID",
            "数据类型": "double"
        }
    )
    
    HoldingRatioNafilled = FT.getFactor("持股占比(%)", args={"回溯天数": np.inf}) / 100
    HoldingRatioNafilled = QS.FactorDB.PointOperation(
        "holding_ratio_nafilled",
        [HoldingRatio, IsComponent],
        sys_args={
            "算子": mask,
            "参数": {},
            "运算时点": "多时点",
            "运算ID": "多ID",
            "数据类型": "double"
        }
    )
    
    HoldingRatioChgRate = fd.rolling_change_rate(HoldingRatioNafilled, window=2, factor_name="holding_ratio_chg_rate")
    HoldingChg = Factorize(HoldingNafilled - fd.lag(HoldingNafilled, 1, 1), factor_name="holding_volume_chg")
    HoldingRatioChg = Factorize(HoldingRatioNafilled - fd.lag(HoldingRatioNafilled, 1, 1), factor_name="holding_ratio_chg")
    
    NetFlowIn = Factorize(HoldingChg * Avg, factor_name="net_flowin")# 净流入
    HoldingAmt = Factorize(Holding * Close, factor_name="holding_amount")
    HoldingAmtNafilled = Factorize(HoldingNafilled * Close, factor_name="holding_amount")
    HoldingAmtChg = Factorize(HoldingAmtNafilled - fd.lag(HoldingAmtNafilled, 1, 1), factor_name="holding_amount_chg")
        
    Factors += [Holding, HoldingChg, HoldingRatio, HoldingRatioChg, HoldingAmt, HoldingAmtChg, HoldingRatioChgRate, NetFlowIn]
    
    UpdateArgs = {
        "因子表": "stock_cn_shszc",
        "默认起始日": dt.datetime(2002, 1, 1),
        "最长回溯期": 365,
        "IDs": "股票"
    }    
    
    return Factors, UpdateArgs


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB()
    JYDB.connect()
    
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = JYDB.getStockID()
    
    Args = {"JYDB": JYDB, "LDB": TDB}
    Factors, UpdateArgs = defFactor(args=Args)
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTs)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
        factor_db=TDB, table_name=TargetTable,
        if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    JYDB.disconnect()