# coding=utf-8
"""指数成份及其权重因子"""
from typing import Dict

from QuantStudio.Factor.BasicOperator import rename
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []

    JYDB = fdi.FDB["JYDB"]

    # 指数成份
    ConstituentIndexList = fdi.ModelArgs["constituent_index_list"]
    FT = JYDB.getTable("指数成份")
    for _, iRow in ConstituentIndexList.iterrows():
        iIndexID, iInnerCode = iRow["指数代码"], iRow["聚源内码"]
        # Factors.append(rename(FT.getFactor(str(iInnerCode)), factor_name=iIndexID.replace(".", "_")))
        Factors.append(rename(FT.getFactor(iIndexID), factor_name=iIndexID.replace(".", "_")))

    # 指数成份权重
    WeightIndexList = fdi.ModelArgs["weight_index_list"]
    for _, iRow in WeightIndexList.iterrows():
        iIndexID, iInnerCode = iRow["指数代码"], iRow["聚源内码"]
        Factors.append(rename(JYDB.getTable("指数成份股权重", args={"AdditionalCondition": {"指数内部编码": str(iInnerCode)}, "LookBack": 35, "OnlyLookBackDT": True}).getFactor("权重(%)") / 100, factor_name=iIndexID.replace(".", "_") + "_weight"))
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_index_component",
        MaxLookBack=365,
        IDType="A股",
        Author="麦冬"
    )
