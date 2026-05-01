# -*- coding: utf-8 -*-
"""港股后复权日行情"""
import datetime as dt
from typing import Dict

import numpy as np
import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_hk_day_bar import defFactor as defStockDayBar


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]

    where, notnull = fo.Where(dtype="double"), fo.NotNull()

    StockDayBarDef = dep_fd.get("stock_hk_day_bar", defStockDayBar(fdi=fdi, dep_fd=dep_fd))
    PreClose = StockDayBarDef.getFactor("pre_close")
    Open = StockDayBarDef.getFactor("open")
    High = StockDayBarDef.getFactor("high")
    Low = StockDayBarDef.getFactor("low")
    Close = StockDayBarDef.getFactor("close")
    AvgPrice = StockDayBarDef.getFactor("avg")

    FT = JYDB.getTable("港股复权因子(新)", args={"LookBack": np.inf})
    AdjFactor = FT.getFactor("比例复权因子")
    AdjFactor = where(AdjFactor, notnull(AdjFactor), 1, factor_args={"Name": "adj_factor"})
    Factors.append(AdjFactor)

    Factors.append(rename(PreClose * AdjFactor, factor_name="pre_close"))
    Factors.append(rename(Open * AdjFactor, factor_name="open"))
    Factors.append(rename(High * AdjFactor, factor_name="high"))
    Factors.append(rename(Low * AdjFactor, factor_name="low"))
    Factors.append(rename(Close * AdjFactor, factor_name="close"))
    Factors.append(rename(AvgPrice * AdjFactor, factor_name="avg"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_hk_day_bar_adj_backward",
        MaxLookBack=max(365, StockDayBarDef.MaxLookBack),
        IDType="港股",
        Author="麦冬",
        Description="港股的行情数据(后复权), 包括开高低收、交易量等",
        DefScriptPath=__file__
    )