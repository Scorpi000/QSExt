# -*- coding: utf-8 -*-
"""A股后复权日行情(缺失填充)"""
import datetime as dt
from typing import Dict

import numpy as np
import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY import stock_cn_status


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    # 市场行情
    FT = JYDB.getTable("股票行情表现", args={"LookBack": 0})
    AvgPrice = FT.getFactor("均价")
    Turnover = rename(FT.getFactor("换手率(%)"), factor_name="turnover")
    Factors.append(Turnover)
    Chg = FT.getFactor("涨跌幅(%)") / 100
    
    where = fo.Where(dtype="double")
    notnull = fo.NotNull()
    FT = JYDB.getTable("复权因子表", args={"LookBack": np.inf})
    AdjFactor = FT.getFactor("比例复权因子")
    AdjFactor = where(AdjFactor, notnull(AdjFactor), 1, factor_args={"Name": "adj_factor"})
    Factors.append(AdjFactor)
    
    FT = JYDB.getTable("日行情表")
    PreClose, Open, High, Low = FT.getFactor("昨收盘(元)"), FT.getFactor("今开盘(元)"), FT.getFactor("最高价(元)"), FT.getFactor("最低价(元)")
    
    FT = JYDB.getTable("日行情表", args={"LookBack": np.inf, "FilterCondition": "{Table}.ClosePrice>0"})
    Close = FT.getFactor("收盘价(元)")
    StockStatusDef = dep_fd.get("stock_cn_status", stock_cn_status.defFactor(fdi=fdi, dep_fd=dep_fd))
    IfListed = StockStatusDef.getFactor(factor_name="if_listed")
    Mask = (IfListed==1)
    Close = where(Close, Mask, np.nan)
    AdjClose = rename(Close * AdjFactor, factor_name="close")
    
    Factors.append(where(Open * AdjFactor, (Open > 0), Close, factor_args={"Name": "open"}))
    Factors.append(where(High * AdjFactor, (High > 0), Close, factor_args={"Name": "high"}))
    Factors.append(where(Low * AdjFactor, (Low > 0), Close, factor_args={"Name": "low"}))
    Factors.append(AdjClose)
    Factors.append(rename(AvgPrice * AdjFactor, factor_name="avg"))
    
    PreClose = where(PreClose, (PreClose > 0), Close / (1 + Chg))
    PreClose = where(PreClose, (PreClose > 0), np.nan)
    Factors.append(rename(PreClose * AdjFactor, factor_name="pre_close"))
    Factors.append(rename(Close / PreClose - 1, factor_name="chg_rate"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_day_bar_adj_backward_nafilled",
        MaxLookBack=max(365, StockStatusDef.MaxLookBack),
        IDType="A股",
        Author="麦冬",
        Description="A股的行情数据(后复权), 包括开高低收、交易量等",
        DefScriptPath=__file__
    )