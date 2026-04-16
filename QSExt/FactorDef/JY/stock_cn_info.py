# -*- coding: utf-8 -*-
"""A股基本信息"""
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
    
    # 证券特征
    FT = JYDB.getTable("A股证券主表")
    Factors.append(rename(FT.getFactor("中文名称"), factor_name="name"))
    Factors.append(rename(FT.getFactor("证券简称"), factor_name="abbr"))
    Factors.append(rename(FT.getFactor("拼音证券简称"), factor_name="pinyin_abbr"))
    Factors.append(rename(FT.getFactor("上市板块_R"), factor_name="listed_sector"))
    Factors.append(fo.Applymap(func=lambda x: x.strftime("%Y-%m-%d") if pd.notnull(x) else None, dtype="string")(FT.getFactor("上市日期"), factor_args={"Name": "listed_date"}))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_info",
        IDType="A股",
        Author="麦冬",
        Description="A股证券基本信息，包括名称、板块、上市时间等",
        DefScriptPath=__file__
    )
