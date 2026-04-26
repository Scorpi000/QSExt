# -*- coding: utf-8 -*-
"""ETF 申赎清单成份明细"""
from typing import Dict

from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    FT = JYDB.getTable("公募基金ETF申购赎回成份股信息(公募基金ID)")
    Factors.append(rename(FT.getFactor("成份股内部编码_R"), factor_name="component_code"))
    Factors.append(rename(FT.getFactor("股票数量(股)"), factor_name="volume"))
    Factors.append(rename(FT.getFactor("现金替代标志_R"), factor_name="cash_substitute"))
    Factors.append(rename(FT.getFactor("固定替代金额(元)"), factor_name="substitute_fixed"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="mf_etf_cn_pr_list_component",
        IDType="ETF",
        Author="麦冬",
        Description="ETF申购赎回清单信息",
        DefScriptPath=__file__
    )
