# -*- coding: utf-8 -*-
"""A股特殊行情"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools


def LimitPriceFun(f, idt, iid, x, args):
    PreClose = x[0]
    Chg = np.full(shape=PreClose.shape, fill_value=0.1)
    Chg[pd.notnull(x[1])] = 0.05
    Mask = pd.Series(iid)
    Mask = Mask.str.startswith("300")
    Chg[:, Mask] = 0.2
    LimitPrice = np.round(PreClose * (1 + args["sign"] * Chg), 2)
    return LimitPrice

def _dt_diff(t1, t2, dts):
    return np.searchsorted(dts, t2) - np.searchsorted(dts, t1)

def SuspendDayNumFun(f, idt, iid, x, args):
    SuspendDate = x[0].astype("datetime64[ns]")
    TradingDTs = args["交易日"]
    iDTs = np.array([idt], dtype="datetime64[ns]").T.repeat(SuspendDate.shape[1], axis=1)
    Mask = pd.isnull(SuspendDate)
    SuspendDate[Mask] = iDTs[Mask]
    DTDiff = np.vectorize(_dt_diff, excluded=["dts"])
    SuspendDayNum = DTDiff(t1=SuspendDate.astype(int), t1=iDTs.astype(int), dts=TradingDTs.astype(int)).astype(float)
    SuspendDayNum[Mask | (iDTs<np.datetime64("2008-04-01"))] = np.nan
    return SuspendDayNum

def SuccessionNumFun(f, idt, iid, x, args):
    x = np.flipud(x[0])
    p = np.arange(x.shape[0]).astype(float).reshape((x.shape[0], 1)).repeat(x.shape[1], axis=1)
    p[x==1] = np.nan
    Rslt = np.nanmin(p, axis=0)
    Rslt[pd.isnull(Rslt)] = x.shape[0]
    return Rslt

def is_reopen_line(f, idt, iid, x, args):
    """判断是否停牌复牌一字板"""
    if_trading, high, low, listed_days = x
    if_trading_df = pd.DataFrame(if_trading, index=idt, columns=iid)
    mask = ((if_trading_df.shift(1)!=1) & (if_trading_df==1)).to_numpy()
    mask = (mask & (high==low) & (listed_days>1))
    return mask[1:]

def is_new_un_open(f, idt, iid, x, args):
    """判断是否为未打开交易的新板"""
    if_limit_up, listed_days, listed_date, high, low = x
    if listed_days[-1]>30 or listed_days[-1]<1 or np.isnan(listed_days[-1]):# 上市时间超过 30 天, 或者还为上市
        return np.nan
    if listed_days[-1]==1 and high[-1]==low[-1]:# 第一天上市涨跌停
        return 1
    try:
        start = dt.datetime.strptime(listed_date[-1], "%Y-%m-%d") + dt.timedelta(days=1)
    except TypeError:
        return np.nan
    high = pd.DataFrame(high, index=idt, columns=[iid])
    low = pd.DataFrame(low, index=idt, columns=[iid])
    if_limit_up = pd.DataFrame(if_limit_up, index=idt, columns=[iid])
    high = high[high.index >= start]
    low = low[low.index >= start]
    if_limit_up = if_limit_up[if_limit_up >= start]
    mask = ((high==low) & (if_limit_up==1))
    return (np.nan if mask.empty else (1 if mask.all()[0] else np.nan))

def is_first_listed(f, idt, iid, x, args):
    listed_days = x[0]
    rslt = np.zeros(listed_days.shape)
    rslt[listed_days==1] = 1
    return rslt

# args:
# JYDB: 聚源因子库对象
# LDB: 本地因子库对象
def defFactor(args={}):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    # 市场行情
    FT = JYDB.getTable("日行情表")
    PreClose = FT.getFactor("昨收盘(元)")
    Open, Close = FT.getFactor("今开盘(元)"), FT.getFactor("收盘价(元)")
    High, Low = FT.getFactor("最高价(元)"), FT.getFactor("最低价(元)")
        
    FT = LDB.getTable("stock_cn_info")
    ST = FT.getFactor("st")
    ListedDays = FT.getFactor("listed_days")
    ListedDate = FT.getFactor("listed_date")
    
    # 涨跌停
    LimitUpPrice = QS.FactorDB.PointOperation(
        "limit_up_price", 
        [PreClose, ST], 
        sys_args={
            "算子": LimitPriceFun, 
            "参数": {"sign": 1},
            "运算时点": "多时点", 
            "运算ID": "多ID"
        }
    )
    Factors.append(LimitUpPrice)
    LimitDownPrice = QS.FactorDB.PointOperation(
        "limit_down_price", 
        [PreClose, ST], 
        sys_args={
            "算子": LimitPriceFun, 
            "参数": {"sign": -1},
            "运算时点": "多时点", 
            "运算ID": "多ID"
        }
    )
    Factors.append(LimitDownPrice)
        
    FT = JYDB.getTable("股票日行情表现")
    LimitUp = FT.getFactor("今日是否涨停股", new_name="if_limit_up")
    Factors.append(LimitUp)
    LimitDown = FT.getFactor("今日是否跌停股", new_name="if_limit_down")
    Factors.append(LimitDown)    
    Factors.append(FT.getFactor("今日是否涨停一字板", new_name="if_limit_up_line"))
    Factors.append(FT.getFactor("今日是否跌停一字板", new_name="if_limit_down_line"))
    Factors.append(Factorize(Open >= LimitUpPrice, factor_name="if_limit_up_open"))
    Factors.append(Factorize(Open <= LimitDownPrice, factor_name="if_limit_down_open"))
    Factors.append(Factorize(High >= LimitUpPrice, factor_name="if_limit_up_high"))
    Factors.append(Factorize(Low <= LimitDownPrice, factor_name="if_limit_down_low"))
    LimitUpDayNum = QS.FactorDB.TimeOperation(
        "day_num_limit_up", 
        [LimitUp], 
        sys_args={
            "算子": SuccessionNumFun, 
            "参数": {},
            "回溯期数": [250],
            "运算时点": "单时点", 
            "运算ID": "多ID"
        }
    )
    Factors.append(LimitUpDayNum)
    LimitDownDayNum = QS.FactorDB.TimeOperation(
        "day_num_limit_down", 
        [LimitDown], 
        sys_args={
            "算子": SuccessionNumFun, 
            "参数": {},
            "回溯期数": [250],
            "运算时点": "单时点", 
            "运算ID": "多ID"
        }
    )
    Factors.append(LimitDownDayNum)
    
    # 价格特征
    Factors.append(FT.getFactor("今日是否创历史新高", new_name="if_new_highest"))
    Factors.append(FT.getFactor("今日是否创历史新低", new_name="if_new_lowest"))
    Factors.append(FT.getFactor("连张天数", new_name="day_num_up"))
    Factors.append(FT.getFactor("连跌天数", new_name="day_num_down"))
    Factors.append(FT.getFactor("是否破发", new_name="if_fall_on_debut"))
    
    # 停牌, 只在 2008-04-01 以后有效
    FT = JYDB.getTable("停牌复牌表", args={"只填起始日": False, "多重映射": False})
    SuspendDate = FT.getFactor("停牌日期")
    TradingDTs = np.array(JYDB.getTradeDay(start_date=dt.date(2008, 4, 1), end_date=dt.date.today()), dtype="datetime64[ns]")
    SuspendDayNum = QS.FactorDB.PointOperation(
        "day_num_suspend", 
        [SuspendDate], 
        sys_args={
            "算子": SuspendDayNumFun, 
            "参数": {"交易日": TradingDTs},
            "运算时点": "多时点", 
            "运算ID": "多ID"
        }
    )
    Factors.append(SuspendDayNum)
    
    FT = TDB.getTable("stock_cn_day_bar_nafilled")
    IfTrading = FT.getFactor("if_trading")
    
    # 停牌复牌一字板
    IfReopenLine = QS.FactorDB.TimeOperation(
        "if_reopen_line", 
        [IfTrading, High, Low, ListedDays], 
        sys_args={
            "算子": is_reopen_line, 
            "参数": {},
            "回溯期数": [1, 1, 1, 1],
            "运算时点": "多时点", 
            "运算ID": "多ID"
        }
    )
    Factors.append(IfReopenLine)
    
    
    UpdateArgs = {
        "因子表": "stock_cn_quote_special",
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