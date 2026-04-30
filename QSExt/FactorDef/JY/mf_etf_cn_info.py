# -*- coding: utf-8 -*-
"""ETF 基金行情"""
from typing import Dict

import numpy as np
import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]

    strftime = fo.Applymap(func=lambda x: x.strftime("%Y-%m-%d") if pd.notnull(x) else None, dtype="string")

    # 证券特征
    FT = JYDB.getTable("公募基金证券主表")
    Factors.append(rename(FT.getFactor("中文名称"), factor_name="name"))
    Factors.append(rename(FT.getFactor("证券简称"), factor_name="abbr"))
    Factors.append(rename(FT.getFactor("拼音证券简称"), factor_name="pinyin_abbr"))
    Factors.append(rename(FT.getFactor("证券市场_R"), factor_name="listed_market"))
    Factors.append(strftime(FT.getFactor("上市日期"), factor_args={"Name": "listed_date"}))
    
    # 基金特征
    FT = JYDB.getTable("公募基金概况")
    Factors.append(strftime(FT.getFactor("设立日期"), factor_args={"Name": "establish_date"}))
    Factors.append(strftime(FT.getFactor("存续期截止日"), factor_args={"Name": "expire_date"}))
    Factors.append(rename(FT.getFactor("基金类别代码_R"), factor_name="fund_type"))

    # # ETF 成份所属市场
    # FT = JYDB.getTable("公募基金ETF申购赎回清单信息")
    # TargetIndex = FT.getFactor("标的指数内部编码")
    # SQLStr = "SELECT t.IndexCode AS ID, t1.MS AS Market FROM lc_indexbasicinfo t LEFT JOIN ct_systemconst t1 ON (t.SecuMarket=t1.DM AND t1.LB=2015) WHERE t.IndexCode IN (SELECT DISTINCT TargetIndexInnerCode FROM mf_etfprlist WHERE TargetIndexInnerCode IS NOT NULL)"
    # IndexInfo = pd.read_sql(SQLStr, JYDB.Connection, index_col=["ID"]).iloc[:, 0]
    # Factors.append(fd.map_value(TargetIndex, IndexInfo, data_type="string", factor_name="component_market"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="mf_etf_cn_info",
        IDType="ETF",
        Author="麦冬",
        Description="ETF的基本信息",
        DefScriptPath=__file__
    )
