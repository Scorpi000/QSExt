# -*- coding: utf-8 -*-
"""ETF 基金不复权行情"""
from typing import Dict

from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    FT = JYDB.getTable("公募基金ETF申购赎回清单信息")
    Factors.append(rename(FT.getFactor("一级市场基金代码"), factor_name="primary_market_code"))
    Factors.append(rename(FT.getFactor("标的指数内部编码_R"), factor_name="target_index"))
    Factors.append(rename(FT.getFactor("IOPV收盘价"), factor_name="iopv"))
    
    FT = JYDB.getTable("公募基金日行情表")
    PreClose = rename(FT.getFactor("昨收盘(元)"), factor_name="pre_close")
    Factors.append(PreClose)
    Factors.append(rename(FT.getFactor("今开盘(元)"), factor_name="open"))
    Factors.append(rename(FT.getFactor("最高价(元)"), factor_name="high"))
    Factors.append(rename(FT.getFactor("最低价(元)"), factor_name="low"))
    Close = rename(FT.getFactor("收盘价(元)"), factor_name="close")
    Factors.append(Close)
    Amount, Volume = rename(FT.getFactor("成交金额(元)"), factor_name="amount"), rename(FT.getFactor("成交量(股)"), factor_name="volume")
    Factors.append(Volume)
    Factors.append(Amount)
    Factors.append(rename(Amount / Volume, factor_name="avg"))
    Factors.append(rename(Close / PreClose - 1, factor_name="chg"))
    
    FT = JYDB.getTable("上市基金历史行情")# 数据不全
    Factors.append(rename(FT.getFactor("换手率(%)") / 100, factor_name="turnover_rate"))
    Factors.append(rename(FT.getFactor("贴水(元)"), factor_name="discount"))
    Factors.append(rename(FT.getFactor("贴水率(%)") / 100, factor_name="discount_ratio"))
    
    FT = JYDB.getTable("公募基金份额变动", args={"AdditionalCondition": {"统计区间": "996"}})
    Factors.append(rename(FT.getFactor("期末份额(份)"), factor_name="total_shares"))
    Factors.append(rename(FT.getFactor("流通份额(份)"), factor_name="float_shares"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="mf_etf_cn_day_bar",
        IDType="ETF",
        Author="麦冬",
        Description="ETF的行情数据(不复权), 包括开高低收、交易量等",
        DefScriptPath=__file__
    )
