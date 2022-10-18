# -*- coding: utf-8 -*-
"""A股日行情(缺失填充)"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_day_bar_nafilled",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def ifTrading(f, idt, iid, x, args):
    Close, SuspendDate, SuspendTime = x
    DTs = np.array([idt]).T.repeat(Close.shape[1], axis=1)
    IfTrading = np.ones(shape=Close.shape)
    Mask = (DTs>=dt.datetime(2008, 4, 1))
    IfTrading[(~Mask) & pd.isnull(Close)] = 0
    IfTrading[Mask & (pd.isnull(Close) | pd.notnull(SuspendDate))] = 0
    try:
        IfTrading[Mask & pd.notnull(Close) & (SuspendTime != "9:30:00") & (SuspendDate == DTs.astype(SuspendDate.dtype))] = 1
    else:
        IfTrading[Mask & pd.notnull(Close) & (SuspendTime != "9:30:00") & (SuspendDate == DTs)] = 1
    IfTrading[IfTrading != 1] = np.nan
    return IfTrading

# args:
# JYDB: 聚源因子库对象
# LDB: 本地因子库对象
def defFactor(args={}):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    # 市场行情
    FT = JYDB.getTable("股票行情表现", args={"回溯天数": 0})
    NullClose = FT.getFactor("收盘价")
    AvgPrice = FT.getFactor("均价", new_name="avg")
    Turnover = FT.getFactor("换手率(%)", new_name="turnover")
    Chg = FT.getFactor("涨跌幅(%)") / 100
    TotalCap = FT.getFactor("总市值(万元)", args={"回溯天数": np.inf})
    FloatCap = FT.getFactor("流通市值(万元)", args={"回溯天数": np.inf})
    
    # 交易状态
    FT = JYDB.getTable("停牌复牌表", args={"只填起始日": False, "多重映射": False})
    SuspendDate = FT.getFactor("停牌日期")
    SuspendTime = FT.getFactor("停牌时间")
    IfTrading = QS.FactorDB.PointOperation("if_trading", [NullClose, SuspendDate, SuspendTime], sys_args={"算子": ifTrading, "运算时点": "多时点", "运算ID": "多ID"})
    Factors.append(IfTrading)
    
    FT = JYDB.getTable("日行情表")
    PreClose, Open, High, Low = FT.getFactor("昨收盘(元)"), FT.getFactor("今开盘(元)"), FT.getFactor("最高价(元)"), FT.getFactor("最低价(元)")
    Volume, Amount = FT.getFactor("成交量(股)", new_name="volume"), FT.getFactor("成交金额(元)", new_name="amount")
    
    Close = FT.getFactor("收盘价(元)", args={"回溯天数": np.inf, "筛选条件": "{Table}.ClosePrice>0"})
    IfListed = LDB.getTable("stock_cn_info").getFactor("if_listed")
    Mask = (IfListed==1)
    Close = fd.where(Close, Mask, np.nan, factor_name="close")
    
    Factors.append(fd.where(Open, (Open > 0), Close, factor_name="open"))
    Factors.append(fd.where(High, (High > 0), Close, factor_name="high"))
    Factors.append(fd.where(Low, (Low > 0), Close, factor_name="low"))
    Factors.extend([Close, AvgPrice, Volume, Amount, Turnover])
    Factors.append(fd.where(TotalCap, Mask, np.nan, factor_name="total_cap"))
    Factors.append(fd.where(FloatCap, Mask, np.nan, factor_name="float_cap"))
    
    PreClose = fd.where(PreClose, (PreClose > 0), Close / (1+Chg))
    PreClose = fd.where(PreClose, (PreClose > 0), np.nan, factor_name="pre_close")
    Factors.append(PreClose)
    Factors.append(Factorize(Close / PreClose - 1, "chg_rate"))
    
    return Factors


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
    Factors = defFactor(args=Args)
    
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