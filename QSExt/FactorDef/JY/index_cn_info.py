# -*- coding: utf-8 -*-
"""指数特征"""
from typing import Dict

import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    FT = JYDB.getTable("指数证券主表")
    Factors.append(rename(FT.getFactor("中文名称"), factor_name="name"))
    Factors.append(rename(FT.getFactor("证券简称"), factor_name="abbr"))
    Factors.append(rename(FT.getFactor("拼音证券简称"), factor_name="pinyin_abbr"))
    
    FT = JYDB.getTable("指数基本情况")
    Factors.append(rename(FT.getFactor("指数类别_R"), factor_name="index_type"))
    Factors.append(fo.Applymap(func=lambda x: x.strftime("%Y-%m-%d") if pd.notnull(x) else None, dtype="string")(FT.getFactor("基日"), factor_args={"Name": "base_date"}))
    Factors.append(rename(FT.getFactor("基点(点)"), factor_name="base_point"))
    Factors.append(rename(FT.getFactor("成份证券类别_R"), factor_name="component_type"))
    Factors.append(rename(FT.getFactor("成份证券市场_R"), factor_name="component_market"))
    Factors.append(rename(FT.getFactor("成份证券数量"), factor_name="component_num"))
    Factors.append(rename(FT.getFactor("成份证券调整周期_R"), factor_name="component_adj_period"))
    Factors.append(rename(FT.getFactor("指数计算类别_R"), factor_name="index_price_type"))
    Factors.append(rename(FT.getFactor("指数设计类别_R"), factor_name="design_type"))
    Factors.append(rename(FT.getFactor("对应主指数内码_R"), factor_name="main_code"))
    Factors.append(rename(FT.getFactor("与主指数关系_R"), factor_name="main_relationship"))
    Factors.append(rename(FT.getFactor("行业标准_R"), factor_name="industry_standard"))
    Factors.append(rename(FT.getFactor("加权方式_R"), factor_name="weight_method"))

    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="index_cn_info",
        IDType="指数",
        Author="麦冬",
        Description="申万行业指数日行情",
        DefScriptPath=__file__
    )
