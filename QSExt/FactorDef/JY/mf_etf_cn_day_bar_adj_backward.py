# -*- coding: utf-8 -*-
"""ETF 基金后复权行情"""
from typing import Dict

import numpy as np

from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]

    where = fo.Where(dtype="double")
    notnull = fo.NotNull()
    
    FT = JYDB.getTable("复权因子表", args={"LookBack": np.inf})
    AdjFactor = FT.getFactor("比例复权因子")
    AdjFactor = where(AdjFactor, notnull(AdjFactor), 1, factor_args={"Name": "adj_factor"})
    Factors.append(AdjFactor)
    
    FT = JYDB.getTable("公募基金日行情表")
    Close = FT.getFactor("收盘价(元)")
    PreClose = FT.getFactor("昨收盘(元)")
    Factors.append(rename(PreClose * AdjFactor, factor_name="pre_close"))
    Factors.append(rename(FT.getFactor("今开盘(元)") * AdjFactor, factor_name="open"))
    Factors.append(rename(FT.getFactor("最高价(元)") * AdjFactor, factor_name="high"))
    Factors.append(rename(FT.getFactor("最低价(元)") * AdjFactor, factor_name="low"))
    Factors.append(rename(Close * AdjFactor, factor_name="close"))
    
    Amount, Volume = FT.getFactor("成交金额(元)", factor_name="amount"), rename(FT.getFactor("成交量(股)"), factor_name="volume")
    Factors.append(Volume)
    Factors.append(Amount)
    Factors.append(rename(Amount / Volume * AdjFactor, factor_name="avg"))
    Factors.append(rename(Close / PreClose - 1, factor_name="chg"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="mf_etf_cn_day_bar_adj_backward",
        IDType="ETF",
        Author="麦冬",
        Description="ETF的行情数据(后复权), 包括开高低收、交易量等",
        DefScriptPath=__file__
    )
