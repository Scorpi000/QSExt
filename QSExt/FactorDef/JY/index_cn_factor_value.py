# coding=utf-8
"""股票指数估值因子"""
from typing import Dict

import numpy as np
import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    FT = JYDB.getTable("指数估值指标", args={"LookBack": 0})
    Factors.append(rename(FT.getFactor("滚动市盈率"), factor_name="pe_ttm"))
    Factors.append(rename(FT.getFactor("静态市盈率(LYR)"), factor_name="pe_lyr"))
    Factors.append(rename(FT.getFactor("市净率(LF)"), factor_name="pb_lr"))
    Factors.append(rename(FT.getFactor("静态市现率(LYR)"), factor_name="pcf_lyr"))
    Factors.append(rename(FT.getFactor("滚动市现率"), factor_name="pcf_ttm"))
    Factors.append(rename(FT.getFactor("静态市销率(LYR)"), factor_name="ps_lyr"))
    Factors.append(rename(FT.getFactor("滚动市销率"), factor_name="ps_ttm"))
    Factors.append(rename(FT.getFactor("滚动股息率(%)") / 100, factor_name="dp_ttm"))
    Factors.append(rename(FT.getFactor("静态股息率(%)") / 100, factor_name="dp_lyr"))
    Factors.append(rename(FT.getFactor("风险溢价(%)") / 100, factor_name="risk_premium"))
    Factors.append(rename(FT.getFactor("风险溢价(比值)"), factor_name="risk_premium_ratio"))
    Factors.append(rename(FT.getFactor("历史PEG"), factor_name="peg"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="index_cn_factor_value",
        IDType="指数",
        Author="麦冬",
        Description="股票指数估值因子",
        DefScriptPath=__file__
    )
