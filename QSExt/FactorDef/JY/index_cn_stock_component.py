# -*- coding: utf-8 -*-
"""指数成份"""
from typing import Dict

import numpy as np
import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    FT = JYDB.getTable("指数成份股权重(指数ID)", args={"LookBack": 0})
    ComponentID = rename(FT.getFactor("成份股内部编码_R"), factor_name="component_code")
    Factors.append(ComponentID)
    
    FT = JYDB.getTable("指数成份股权重(指数ID)", args={"LookBack": 0, "MultiMapping": True, "Operator": lambda s: (s.astype(float) / 100).tolist(), "OperatorDataType": "object"})
    PositionWeight = rename(FT.getFactor("权重(%)"), factor_name="weight")
    Factors.append(PositionWeight)
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="index_cn_stock_component",
        IDType="指数",
        Author="麦冬",
        Description="指数成份权重",
        DefScriptPath=__file__
    )
