# -*- coding: utf-8 -*-
"""指数行情"""
from typing import Dict

from QuantStudio.Factor.BasicOperator import rename
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    FT = JYDB.getTable("指数行情")
    PreClose = rename(FT.getFactor("昨收盘(元-点)"), factor_name="pre_close")
    Factors.append(PreClose)
    Factors.append(rename(FT.getFactor("今开盘(元-点)"), factor_name="open"))
    Factors.append(rename(FT.getFactor("最高价(元-点)"), factor_name="high"))
    Factors.append(rename(FT.getFactor("最低价(元-点)"), factor_name="low"))
    Close = rename(FT.getFactor("收盘价(元-点)"), factor_name="close")
    Factors.append(Close)
    Factors.append(rename(FT.getFactor("成交量"), factor_name="volume"))
    Factors.append(rename(FT.getFactor("成交金额(元)"), factor_name="amount"))
    Factors.append(rename(Close / PreClose - 1, factor_name="chg_rate"))
    Factors.append(rename(FT.getFactor("流通市值"), factor_name="float_cap"))

    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="index_cn_day_bar",
        MaxLookBack=365,
        IDType="指数",
        Author="麦冬",
        Description="指数的行情数据, 包括开高低收、成交量等",
        DefScriptPath=__file__
    )
