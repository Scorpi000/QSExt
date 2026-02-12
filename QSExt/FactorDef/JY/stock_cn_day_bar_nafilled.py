# -*- coding: utf-8 -*-
"""A股日行情(缺失填充)"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.BasicOperator import rename
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStockStatus


def defFactor(fdi: FactorDefInput):
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    # 市场行情
    FT = JYDB.getTable("股票行情表现", args={"LookBack": 0})
    AvgPrice = rename(FT.getFactor("均价"), factor_name="avg")
    Turnover = rename(FT.getFactor("换手率(%)"), factor_name="turnover")
    Factors.append(AvgPrice)
    Factors.append(Turnover)
    Chg = FT.getFactor("涨跌幅(%)") / 100
    FT = JYDB.getTable("股票行情表现", args={"LookBack": np.inf})
    TotalCap = FT.getFactor("总市值(万元)")
    FloatCap = FT.getFactor("流通市值(万元)")
    
    FT = JYDB.getTable("日行情表")
    PreClose, Open, High, Low = FT.getFactor("昨收盘(元)"), FT.getFactor("今开盘(元)"), FT.getFactor("最高价(元)"), FT.getFactor("最低价(元)")
    Volume, Amount = rename(FT.getFactor("成交量(股)"), factor_name="volume"), rename(FT.getFactor("成交金额(元)"), factor_name="amount")
    
    Close = FT.getFactor("收盘价(元)", args={"LookBack": np.inf, "FilterCondition": "{Table}.ClosePrice>0"})
    StockStatusDef = defStockStatus(fdi=fdi)
    IfListed = StockStatusDef.getFactor(factor_name="if_listed", def_path="...")
    Mask = (IfListed==1)

    where = fo.Where(dtype="double")
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
    Factors.append(rename(Close / PreClose - 1, "chg_rate"))
    
    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_day_bar_nafilled",
        IDType="A股",
        Author="麦冬"
    )
