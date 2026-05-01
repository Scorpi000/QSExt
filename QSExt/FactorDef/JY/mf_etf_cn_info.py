# -*- coding: utf-8 -*-
"""ETF 基金行情"""
from typing import Dict

import numpy as np
import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.FactorUtils import SQLQueryTable
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
    Factors.append(rename(FT.getFactor("基金性质_R"), factor_name="fund_nature"))

    # 其他
    SQLStr = """
        SELECT 
            CONCAT(tm.SecuCode, '.OF') AS QS_ID,
            t.TradingDay AS QS_DT,
            tc.MS AS component_market -- 成份所属市场
        FROM mf_etfprlist t
        INNER JOIN SecuMain tm
        ON t.InnerCode = tm.InnerCode
        INNER JOIN lc_indexbasicinfo ti
        ON t.TargetIndexInnerCode = ti.IndexCode
        LEFT JOIN ct_systemconst tc
        ON (ti.SecuMarket = tc.DM AND tc.LB = 2015)
        WHERE t.TradingDay >= {StartDT}
        AND t.TradingDay <= {EndDT}
        AND CONCAT(tm.SecuCode, '.OF') IN {IDs}
        ORDER BY QS_ID, QS_DT
    """
    FT = SQLQueryTable(fdb=JYDB, args={"QuerySQL": SQLStr, "FieldDataTypes": {"component_market": "string"}, "TableType": "WideTable", "CalcArgs": {"LookBack": 0}})
    Factors.append(FT.getFactor("component_market"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="mf_etf_cn_info",
        IDType="ETF",
        Author="麦冬",
        Description="ETF的基本信息",
        DefScriptPath=__file__
    )
