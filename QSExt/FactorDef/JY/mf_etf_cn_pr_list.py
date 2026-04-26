# -*- coding: utf-8 -*-
"""ETF 申赎清单"""
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
    Factors.append(rename(FT.getFactor("上一交易日期"), factor_name="pre_trading_day"))
    Factors.append(rename(FT.getFactor("现金差额(元)"), factor_name="cash_balance"))
    Factors.append(rename(FT.getFactor("最小申赎单位资产净值(元)"), factor_name="least_unit_nv"))
    Factors.append(rename(FT.getFactor("基金份额净值(元)"), factor_name="share_nv"))
    Factors.append(rename(FT.getFactor("IOPV收盘价"), factor_name="iopv"))
    Factors.append(rename(FT.getFactor("预估现金部分(元)"), factor_name="cash_forecasted"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="mf_etf_cn_pr_list",
        IDType="ETF",
        Author="麦冬",
        Description="ETF申购赎回清单信息",
        DefScriptPath=__file__
    )
