# -*- coding: utf-8 -*-
"""申万行业指数基本信息"""
from typing import Dict

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
    Factors.append(rename(fo.AsType(dtype="string")(FT.getFactor("行业类别")), factor_name="industry_code"))
    FT = JYDB.getTable("指数基本情况", args={"TransformSQL": {"行业类别_R": "SELECT CAST(IndustryCode AS INT), IndustryName FROM {TablePrefix}CT_IndustryType WHERE Standard = 38"}})
    Factors.append(rename(FT.getFactor("行业类别_R"), factor_name="industry_name"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="index_sw_industry_cn_info",
        IDType="申万行业指数",
        Author="麦冬",
        Description="申万行业指数基本信息",
        DefScriptPath=__file__
    )
