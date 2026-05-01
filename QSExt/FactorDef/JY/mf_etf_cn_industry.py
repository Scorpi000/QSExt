# -*- coding: utf-8 -
"""ETF行业分类"""
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
from QSExt.Factor.FactorOperator import FFill


@FactorOperatorized(operator_type="Section", args={"DTMode": "单时点"})
def calcIndexIndustry(f, idt, iid, x, args):
    Value, ComponentID, ComponentWeight = x
    Value = pd.Series(Value, index=f.Operator.Args.DescriptorSection[0])
    Rslt = np.full_like(ComponentID, np.nan)
    for i, iIDs in enumerate(ComponentID):
        if isinstance(iIDs, list):
            iWeight = np.array(ComponentWeight[i])
            if Value.index.intersection(iIDs).shape[0]>0:
                iValue = Value.loc[iIDs].values
                iMask = (pd.notnull(iValue) & pd.notnull(iWeight))
                iWeightSum = np.sum(iWeight[iMask])
                if iWeightSum>0:
                    Rslt[i] = np.sum((iValue * iWeight)[iMask]) / iWeightSum
    return Rslt


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    LDB = fdi.FDB["LDB"]

    where, notnull = fo.Where(dtype="string"), fo.NotNull()

    ComponentIDs = fdi.ModelArgs["component_ids"]

    ffill = FFill(lookback=63)

    # 指数成份
    FT = LDB.getTable(fdi.ModelArgs["component_table"])
    ComponentID = ffill(FT.getFactor("component_code"))
    ComponentWeight = ffill(FT.getFactor("weight"))
    
    FT = LDB.getTable(fdi.ModelArgs["component_industry_table"])
    iComponentIndustry = FT.getFactor("industry")
    iFactor = calculateIndexValue(iComponentIndustry, ComponentID, ComponentWeight, factor_args={"Name": iFactorName})
    
    
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_industry",
        IDType="A股",
        Author="麦冬",
        Description="A股所属行业, 包括中信、申万、Barra、证监会等行业分类",
        DefScriptPath=__file__
    )
