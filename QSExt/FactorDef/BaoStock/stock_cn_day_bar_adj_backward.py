# -*- coding: utf-8 -*-
"""A股日行情"""
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Core.BasicOperator import rename
import QuantStudio.Core.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput):
    Factors = []
    
    BSDB = fdi.FDB["BSDB"]
    
    FT = BSDB.getTable("A股K线数据", args={"LookBack": 0, "APIArgs": {"adjustflag": "3"}})
    Close = FT.getFactor("close")
    Turnover = FT.getFactor("turn")
    Chg = rename(FT.getFactor("pctChg") / 100, factor_name="chg")
    PreClose, Open, High, Low = FT.getFactor("preclose"), FT.getFactor("open"), FT.getFactor("high"), FT.getFactor("low")
    Volume, Amount = FT.getFactor("volume"), FT.getFactor("amount")
    
    Factors = [
        PreClose, Open, High, Low, Close, Chg, Volume, Amount, 
        rename(Turnover, factor_name="turnover")
    ]
    
    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_day_bar_adj_backward",
        IDType="A股",
        Author="麦冬"
    )