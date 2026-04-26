# -*- coding: utf-8 -*-
"""ETF 基金行情"""
import datetime as dt
from typing import Dict

import numpy as np
import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]

    FT = JYDB.getTable("公募基金ETF申购赎回清单信息")
    TargetIndex = FT.getFactor("标的指数内部编码")
    
    # ETF 所属市场
    SQLStr = "SELECT CONCAT(t.SecuCode, '.OF') AS ID, t1.MS AS Market FROM secumain t LEFT JOIN ct_systemconst t1 ON (t.SecuMarket=t1.DM AND t1.LB=201) WHERE t.InnerCode IN (SELECT DISTINCT InnerCode FROM mf_etfprlist) ORDER BY ID"
    IDInfo = pd.read_sql(SQLStr, JYDB.Connection, index_col=["ID"]).iloc[:, 0]
    Factors.append(QS.FactorDB.DataFactor(name="market", data=IDInfo))
    
    # ETF 成份所属市场
    SQLStr = "SELECT t.IndexCode AS ID, t1.MS AS Market FROM lc_indexbasicinfo t LEFT JOIN ct_systemconst t1 ON (t.SecuMarket=t1.DM AND t1.LB=2015) WHERE t.IndexCode IN (SELECT DISTINCT TargetIndexInnerCode FROM mf_etfprlist WHERE TargetIndexInnerCode IS NOT NULL)"
    IndexInfo = pd.read_sql(SQLStr, JYDB.Connection, index_col=["ID"]).iloc[:, 0]
    Factors.append(fd.map_value(TargetIndex, IndexInfo, data_type="string", factor_name="component_market"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="mf_etf_cn_info",
        IDType="ETF",
        Author="麦冬",
        Description="ETF的基本信息",
        DefScriptPath=__file__
    )
