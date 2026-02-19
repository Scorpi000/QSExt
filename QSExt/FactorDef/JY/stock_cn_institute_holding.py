# -*- coding: utf-8 -*-
"""A股机构投资者"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.BasicOperator import rename
from QuantStudio.Core.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def sum_list(x):
    if isinstance(x, list):
        return np.nansum(np.array(x, dtype=float))
    else:
        return np.nan

def defFactor(fdi: FactorDefInput):
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    # 机构持股
    FT = JYDB.getTable("股东持股统计", args={"PublDTField": None, "IgnoreTime": True})
    InstituteHolding_A = rename(FT.getFactor("机构持有A股数量合计(股)"), factor_name="institute_holding_num_a")
    InstituteHoldingRatio_A = rename(FT.getFactor("机构持有A股比例合计(%)") / 100, factor_name="institute_holding_ratio_a")
    Factors += [InstituteHolding_A, InstituteHoldingRatio_A]
    
    InstituteHolding_AUnrestricted = FT.getFactor("机构持有无限售流通A股数量合计(股)", new_name="institute_holding_num_a_unrestricted")
    InstituteHoldingRatio_AUnrestricted = rename(FT.getFactor("机构持有无限售流通A股比例合计(%)") / 100, factor_name="institute_holding_ratio_a_unrestricted")
    Factors += [InstituteHolding_AUnrestricted, InstituteHoldingRatio_AUnrestricted]
        
    InstituteHolding = rename(FT.getFactor("机构持股数量合计(股)"), factor_name="institute_holding_num")
    InstituteHoldingRatio = rename(FT.getFactor("机构持股比例合计(%)") / 100, factor_name="institute_holding_ratio")
    Factors += [InstituteHolding, InstituteHoldingRatio]
    
    # 国家队持股
    apply_sum = fo.Applymap(func=sum_list, dtype="double")
    FT = JYDB.getTable("A股国家队持股统计", args={"PublDTField": None, "IgnoreTime": True})
    NationalHolding = apply_sum(FT.getFactor("持有A股总数(股)"), factor_args={"Name": "national_holding_num_a"})
    NationalHoldingRatio = rename(apply_sum(FT.getFactor("占总股本比例(%)")) / 100, factor_name="institute_holding_ratio_a")
    Factors += [NationalHolding, NationalHoldingRatio]
    
    NationalHolding_AUnrestricted = apply_sum(FT.getFactor("其中-无限售A股数(股)"), factor_args={"Name": "national_holding_num_a_unrestricted"})
    NationalHoldingRatio_AUnrestricted = rename(NationalHolding_AUnrestricted / NationalHolding * NationalHoldingRatio, factor_name="institute_holding_ratio_a_unrestricted")
    Factors += [NationalHolding_AUnrestricted, NationalHoldingRatio_AUnrestricted]   
    
    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_institute_holding",
        MaxLookBack=365,
        IDType="A股",
        Author="麦冬"
    )    
