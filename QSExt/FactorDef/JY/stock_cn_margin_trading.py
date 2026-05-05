# -*- coding: utf-8 -*-
"""A股融资融券"""
import datetime as dt
from typing import Dict

import numpy as np
import pandas as pd

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    FT = JYDB.getTable("融资融券标的证券")
    Factors.append(rename(FT.getFactor("融资买入标的"), factor_name="finance_target"))
    Factors.append(rename(FT.getFactor("融券卖出标的"), factor_name="security_target"))
    
    StockDayBarDef = dep_fd.get("stock_cn_day_bar_nafilled", defStockDayBar(fdi=fdi, dep_fd=dep_fd))
    MarketCap = StockDayBarDef.getFactor(factor_name="total_cap") * 10000
    
    FT = JYDB.getTable("融资融券交易明细")
    FinanceValue = rename(FT.getFactor("融资余额(元)"), factor_name="finance_value")
    Factors.append(FinanceValue)
    SecurityValue = rename(FT.getFactor("融券余额(元)"), factor_name="security_value")
    Factors.append(SecurityValue)
    TradingValue = rename(FT.getFactor("融资融券余额(元)"), factor_name="trading_value")
    Factors.append(TradingValue)
    
    notnull, where = fo.NotNull(), fo.Where()
    FinanceSecurityDiff = where(FinanceValue, notnull(FinanceValue), 0) - where(SecurityValue, notnull(SecurityValue), 0)
    FinanceSecurityDiff = where(FinanceSecurityDiff, notnull(FinanceValue) | notnull(SecurityValue), np.nan, factor_args={"Name": "finance_security_diff"})
    
    Factors.append(rename(FinanceValue / MarketCap, factor_name="finance_cap_ratio"))
    Factors.append(rename(SecurityValue / MarketCap, factor_name="security_cap_ratio"))
    Factors.append(rename(TradingValue / MarketCap, factor_name="trading_cap_ratio"))
    Factors.append(rename(FinanceSecurityDiff / MarketCap, factor_name="finance_security_diff_cap_ratio"))   
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_margin_trading",
        MaxLookBack=max(365, StockDayBarDef.MaxLookBack),
        IDType="A股",
        Author="麦冬",
        DefScriptPath=__file__
    )
