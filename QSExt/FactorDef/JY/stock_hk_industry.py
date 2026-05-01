# -*- coding: utf-8 -
"""港股行业分类"""
import os
import datetime as dt
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    # 申万行业, 2021 版
    Args = {"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "38"}}
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, FirstIndustryName FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 38"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="sw2021_level1"))
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, FirstIndustryCode FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 38"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="sw2021_code_level1"))
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, SecondIndustryName FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 38"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="sw2021_level2"))
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, SecondIndustryCode FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 38"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="sw2021_code_level2"))
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, ThirdIndustryName FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 38"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="sw2021_level3"))
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, ThirdIndustryCode FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 38"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="sw2021_code_level3"))
    
    # 中信行业, 2019 版
    Args = {"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "37"}}
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, FirstIndustryName FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="citic_level1"))
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, FirstIndustryCode FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="citic_code_level1"))
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, SecondIndustryName FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="citic_level2"))
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, SecondIndustryCode FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="citic_code_level2"))
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, ThirdIndustryName FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="citic_level3"))
    FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, ThirdIndustryCode FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="citic_code_level3"))

    # # 恒生行业 TODO
    # Args = {"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "37"}}
    # FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, FirstIndustryName FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    # Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="hs_level1"))
    # FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, FirstIndustryCode FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    # Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="citic_code_level1"))
    # FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, SecondIndustryName FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    # Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="citic_level2"))
    # FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, SecondIndustryCode FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    # Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="citic_code_level2"))
    # FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, ThirdIndustryName FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    # Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="citic_level3"))
    # FT = JYDB.getTable("港股公司行业划分表", args=Args | {"TransformSQL": {"行业编码_R": "SELECT IndustryNum, ThirdIndustryCode FROM CT_IndustryType WHERE IfEffected = 1 AND Standard = 37"}})
    # Factors.append(rename(FT.getFactor("行业编码_R"), factor_name="citic_code_level3"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_hk_industry",
        IDType="港股",
        Author="麦冬",
        Description="港股所属行业, 包括中信、申万、恒生等行业分类",
        DefScriptPath=__file__
    )
