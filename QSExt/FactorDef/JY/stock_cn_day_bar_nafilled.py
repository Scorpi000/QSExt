# -*- coding: utf-8 -*-
"""A股日行情(缺失填充)"""
import datetime as dt
from typing import Dict

import numpy as np
import pandas as pd

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY import stock_cn_status


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]

    where, notnull = fo.Where(dtype="double"), fo.NotNull()
    
    # 市场行情
    FT = JYDB.getTable("股票行情表现", args={"LookBack": 0})
    FT_STIB = JYDB.getTable("科创板行情表现", args={"LookBack": 0})
    AvgPrice = FT.getFactor("均价")
    AvgPrice = rename(where(AvgPrice, notnull(AvgPrice), FT_STIB.getFactor("成交均价(元)")), factor_name="avg")
    Turnover = FT.getFactor("换手率(%)")
    Turnover = rename(where(Turnover, notnull(Turnover), FT_STIB.getFactor("换手率(%)")), factor_name="turnover")
    Factors.append(AvgPrice)
    Factors.append(Turnover)
    Chg = FT.getFactor("涨跌幅(%)")
    Chg = where(Chg, notnull(Chg), FT_STIB.getFactor("涨跌幅(%)")) / 100
    FT = JYDB.getTable("股票行情表现", args={"LookBack": np.inf})
    FT_STIB = JYDB.getTable("科创板行情表现", args={"LookBack": np.inf})
    TotalCap = FT.getFactor("总市值(万元)")
    FloatCap = FT.getFactor("流通市值(万元)")
    TotalCap = where(TotalCap, notnull(TotalCap), FT_STIB.getFactor("总市值(元)") / 10000)
    FloatCap = where(FloatCap, notnull(FloatCap), FT_STIB.getFactor("流通市值(不含限售股)(元)") / 10000)

    FT = JYDB.getTable("日行情表")
    FT_STIB = JYDB.getTable("科创板日行情")
    PreClose, Open, High, Low = FT.getFactor("昨收盘(元)"), FT.getFactor("今开盘(元)"), FT.getFactor("最高价(元)"), FT.getFactor("最低价(元)")
    Volume, Amount = FT.getFactor("成交量(股)"), FT.getFactor("成交金额(元)")
    PreClose = where(PreClose, notnull(PreClose), FT_STIB.getFactor("昨收盘(元)"))
    Open = where(Open, notnull(Open), FT_STIB.getFactor("今开盘(元)"))
    High = where(High, notnull(High), FT_STIB.getFactor("最高价(元)"))
    Low = where(Low, notnull(Low), FT_STIB.getFactor("最低价(元)"))
    Volume = where(Volume, notnull(Volume), FT_STIB.getFactor("收盘成交量(股)"), factor_args={"Name": "volume"})
    Amount = where(Amount, notnull(Amount), FT_STIB.getFactor("收盘成交金额(元)"), factor_args={"Name": "amount"})

    FT = JYDB.getTable("日行情表", args={"LookBack": np.inf, "FilterCondition": "{Table}.ClosePrice>0"})
    FT_STIB = JYDB.getTable("科创板日行情", args={"LookBack": np.inf, "FilterCondition": "{Table}.ClosePrice>0"})
    Close = FT.getFactor("收盘价(元)")
    Close = where(Close, notnull(Close), FT_STIB.getFactor("收盘价(元)"))
    StockStatusDef = dep_fd.get("stock_cn_status", stock_cn_status.defFactor(fdi=fdi, dep_fd=dep_fd))
    IfListed = StockStatusDef.getFactor(factor_name="if_listed")
    Mask = (IfListed==1)

    Close = where(Close, Mask, np.nan, factor_args={"Name": "close"})
    Factors.append(where(Open, (Open > 0), Close, factor_args={"Name": "open"}))
    Factors.append(where(High, (High > 0), Close, factor_args={"Name": "high"}))
    Factors.append(where(Low, (Low > 0), Close, factor_args={"Name": "low"}))
    Factors.extend([Close, Volume, Amount])
    Factors.append(where(TotalCap, Mask, np.nan, factor_args={"Name": "total_cap"}))
    Factors.append(where(FloatCap, Mask, np.nan, factor_args={"Name": "float_cap"}))
    
    PreClose = where(PreClose, (PreClose > 0), Close / (1 + Chg))
    PreClose = where(PreClose, (PreClose > 0), np.nan, factor_args={"Name": "pre_close"})
    Factors.append(PreClose)
    Factors.append(rename(Close / PreClose - 1, factor_name="chg_rate"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_day_bar_nafilled",
        MaxLookBack=max(365, StockStatusDef.MaxLookBack),
        IDType="A股",
        Author="麦冬",
        Description="A股的行情数据(不复权), 包括开高低收、交易量等",
        DefScriptPath=__file__
    )
