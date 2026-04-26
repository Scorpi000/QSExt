# -*- coding: utf-8 -*-
"""申万行业指数行情"""
from typing import Dict

from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    FT = JYDB.getTable("申万指数行情")
    Factors.append(rename(FT.getFactor("昨收盘(元-点)"), factor_name="pre_close"))
    Factors.append(rename(FT.getFactor("今开盘(元-点)"), factor_name="open"))
    Factors.append(rename(FT.getFactor("最高价(元-点)"), factor_name="high"))
    Factors.append(rename(FT.getFactor("最低价(元-点)"), factor_name="low"))
    Factors.append(rename(FT.getFactor("收盘价(元-点)"), factor_name="close"))
    Factors.append(rename(FT.getFactor("成交量"), factor_name="volume"))
    Factors.append(rename(FT.getFactor("成交金额(元)"), factor_name="amount"))
    Factors.append(rename(FT.getFactor("成交笔数"), factor_name="turnover_deals"))
    Factors.append(rename(FT.getFactor("指数市盈率"), factor_name="pe"))
    Factors.append(rename(FT.getFactor("指数市净率"), factor_name="pb"))
    Factors.append(rename(FT.getFactor("总市值(万元)"), factor_name="total_cap"))
    Factors.append(rename(FT.getFactor("A股流通市值(万元)"), factor_name="float_cap"))
    Factors.append(rename(FT.getFactor("涨跌幅") / 100, factor_name="chg"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="index_sw_industry_cn_day_bar",
        IDType="申万行业指数",
        Author="麦冬",
        Description="申万行业指数日行情",
        DefScriptPath=__file__
    )
