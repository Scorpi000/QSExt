# -*- coding: utf-8 -*-
"""A股基本信息"""
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Core.BasicOperator import rename
import QuantStudio.Core.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput):
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    # 证券特征
    FT = JYDB.getTable("A股证券主表")
    Factors.append(rename(FT.getFactor("中文名称"), factor_name="name"))
    Factors.append(rename(FT.getFactor("证券简称"), factor_name="abbr"))
    Factors.append(rename(FT.getFactor("拼音证券简称"), factor_name="pinyin_abbr"))
    Factors.append(rename(FT.getFactor("上市板块_R"), factor_name="listed_sector"))
    Factors.append(fo.Strftime(dt_format="%Y-%m-%d")(FT.getFactor("上市日期"), factor_args={"Name": "listed_date"}))
    
    FT = JYDB.getTable("公司概况")
    Factors.append(rename(FT.getFactor("省份_R"), factor_name="province"))
    Factors.append(rename(FT.getFactor("地区代码_R"), factor_name="city"))
    
    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_info",
        IDType="A股",
        Author="麦冬"
    )
