# coding=utf-8
"""指数成份及其权重因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput):
    Factors = []

    JYDB = fdi.FDB["JYDB"]

    # 指数成份
    FT = JYDB.getTable("指数成份")
    Factors.append(rename(FT.getFactor("46"), factor_name="sh50"))
    Factors.append(rename(FT.getFactor("3145"), factor_name="hs300"))
    Factors.append(rename(FT.getFactor("4978"), factor_name="zz500"))
    Factors.append(rename(FT.getFactor("4982"), factor_name="zz800"))
    Factors.append(rename(FT.getFactor("39144"), factor_name="zz1000"))

    # 指数成份权重
    Factors.append(rename(JYDB.getTable("指数成份股权重", args={"AdditionalCondition": {"指数内部编码": "46"}, "LookBack": 35, "OnlyLookBackDT": True}).getFactor("权重(%)") / 100, factor_name="sh50_weight"))
    Factors.append(rename(JYDB.getTable("指数成份股权重", args={"AdditionalCondition": {"指数内部编码": "3145"}, "LookBack": 35, "OnlyLookBackDT": True}).getFactor("权重(%)") / 100, factor_name="hs300_weight"))
    Factors.append(rename(JYDB.getTable("指数成份股权重", args={"AdditionalCondition": {"指数内部编码": "4978"}, "LookBack": 35, "OnlyLookBackDT": True}).getFactor("权重(%)") / 100, factor_name="zz500_weight"))
    Factors.append(rename(JYDB.getTable("指数成份股权重", args={"AdditionalCondition": {"指数内部编码": "4982"}, "LookBack": 35, "OnlyLookBackDT": True}).getFactor("权重(%)") / 100, factor_name="zz800_weight"))
    Factors.append(rename(JYDB.getTable("指数成份股权重", args={"AdditionalCondition": {"指数内部编码": "39144"}, "LookBack": 35, "OnlyLookBackDT": True}).getFactor("权重(%)") / 100, factor_name="zz1000_weight"))

    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_index_component",
        MaxLookBack=365,
        IDType="A股",
        Author="麦冬"
    )
