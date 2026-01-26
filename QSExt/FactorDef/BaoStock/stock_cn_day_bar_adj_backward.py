# -*- coding: utf-8 -*-
"""A股日行情"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
from QuantStudio.Core.BaoStockDB import BaoStockDB
from QuantStudio.Core.BasicOperator import Factorize
import QuantStudio.Core.FactorOperator as fo


# args:
# BSDB: BaoStock 因子库对象
def defFactor(args={}):
    Factors = []
    
    BSDB = args.get("BSDB", BaoStockDB().connect())
    
    FT = BSDB.getTable("A股K线数据", args={"LookBack": 0, "APIArgs": {"adjustflag": "3"}})
    Close = FT.getFactor("close")
    Turnover = FT.getFactor("turn")
    Chg = Factorize(FT.getFactor("pctChg") / 100, factor_name="chg")
    PreClose, Open, High, Low = FT.getFactor("preclose"), FT.getFactor("open"), FT.getFactor("high"), FT.getFactor("low")
    Volume, Amount = FT.getFactor("volume"), FT.getFactor("amount")
    
    Factors = [
        PreClose, Open, High, Low, Close, Chg, Volume, Amount, 
        fo.AsType(dtype="double")(Turnover, factor_args={"Name": "turnover"})
    ]
    
    UpdateArgs = {
        "因子表": "stock_cn_day_bar_adj_backward",
        "默认起始日": dt.datetime(2002, 1, 1),
        "最长回溯期": 365,
        "IDs": "股票"
    }
    
    return Factors, UpdateArgs


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    BSDB = QS.FactorDB.JYDB().connect()
    TDB = QS.FactorDB.HDF5DB().connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = BSDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler =BSDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = BSDB.getStockID()
    
    Args = {"BSDB": BSDB}
    Factors, UpdateArgs = defFactor(args=Args)
    
    
    
    TDB.disconnect()
    JYDB.disconnect()