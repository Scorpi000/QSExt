# -*- coding: utf-8 -*-
"""港股日行情"""
from typing import Dict

import numpy as np
import pandas as pd

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    # 市场行情
    FT = JYDB.getTable("港股行情库表")
    PreClose, Open, High, Low, Close = FT.getFactor("昨收盘(元)"), FT.getFactor("开盘价(元)"), FT.getFactor("最高价(元)"), FT.getFactor("最低价(元)"), FT.getFactor("收盘价(元)")
    Volume, Amount = FT.getFactor("成交量(股)"), FT.getFactor("成交金额(元)")
    ChgRate = FT.getFactor("涨跌幅(%)") / 100
    Factors.extend([
        rename(PreClose, factor_name="pre_close"),
        rename(Open, factor_name="open"),
        rename(High, factor_name="high"),
        rename(Low, factor_name="low"),
        rename(Close, factor_name="close"),
        rename(Volume, factor_name="volume"),
        rename(Amount, factor_name="amount"),
        rename(ChgRate, factor_name="chg_rate"),
        rename(Amount / Volume, factor_name="avg")
    ])
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_hk_day_bar",
        MaxLookBack=365,
        IDType="港股",
        Author="麦冬",
        Description="港股的行情数据(不复权), 包括开高低收、交易量等",
        DefScriptPath=__file__
    )
