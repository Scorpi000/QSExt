# coding=utf-8
"""股票指数成长性"""
from typing import Dict

import numpy as np
import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.Factor.FactorOperator import FFill


@FactorOperatorized(operator_type="Section", args={"DTMode": "单时点"})
def calcIndexValue(f, idt, iid, x, args):
    Value, ComponentID, ComponentWeight = x
    Value = pd.Series(Value, index=f.Operator.Args.DescriptorSection[0])
    Rslt = np.full_like(ComponentID, np.nan)
    for i, iIDs in enumerate(ComponentID):
        if isinstance(iIDs, list):
            iWeight = np.array(ComponentWeight[i])
            if Value.index.intersection(iIDs).shape[0]>0:
                iValue = Value.reindex(index=iIDs).values
                iMask = (pd.notnull(iValue) & pd.notnull(iWeight))
                iWeightSum = np.sum(iWeight[iMask])
                if iWeightSum>0:
                    Rslt[i] = np.sum((iValue * iWeight)[iMask]) / iWeightSum
    return Rslt


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    LDB = fdi.FDB["LDB"]

    ComponentIDs = fdi.ModelArgs["component_ids"]

    ffill = FFill(lookback=63)

    # 指数成份
    # FT = LDB.getTable(fdi.ModelArgs["component_table"])
    # ComponentID = ffill(FT.getFactor("component_code"))
    # ComponentWeight = ffill(FT.getFactor("weight"))
    ComponentDef = dep_fd[fdi.ModelArgs["component_table"]]
    ComponentID = ffill(ComponentDef.getFactor("component_code"))
    ComponentWeight = ffill(ComponentDef.getFactor("weight"))
    
    calculateIndexValue = calcIndexValue.new(args={"DescriptorSection": [ComponentIDs, None, None]})

    FT = LDB.getTable(fdi.ModelArgs["component_factor_table"])
    for iFactorName in FT.FactorNames:
        iComponentFactor = FT.getFactor(iFactorName)
        iFactor = calculateIndexValue(iComponentFactor, ComponentID, ComponentWeight, factor_args={"Name": iFactorName})
        Factors.append(iFactor)
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable=fdi.ModelArgs.get("target_table", "index_cn_factor_from_constituent"),
        IDType="指数",
        Author="麦冬",
        Description="由指数成份因子合成的指数因子",
        DefScriptPath=__file__
    )