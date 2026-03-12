# coding=utf-8
"""简单多因子模型"""
import os
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.Factor.FactorOperator import QuantileStandardization, Orthogonalization
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QuantStudio.Tools.DateTimeFun import getMonthLastDateTime
# from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStockStatus
# from QSExt.FactorDef.JY.stock_cn_industry import defFactor as defStockIndustry
# from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar
# from QSExt.FactorDef.JY.stock_cn_day_bar_adj_backward_nafilled import defFactor as defStockDayBarAdj
# import QSExt.FactorDef.JY as SourcePkg


@FactorOperatorized(operator_type="Panel", args={"Arity": 3, "LookBack":[30, 30, 30], "DTMode": "单时点", "OutputMode": "全截面"})
def calcMonthIC(f, idt, iid, x, args):
    MonthDTs = getMonthLastDateTime(idt)
    if MonthDTs[-1]==idt[-1]: PrePos = idt.index(MonthDTs[-2])
    else: PrePos = idt.index(MonthDTs[-1])
    Ret = x[1][-1] / x[1][PrePos] - 1
    Mask = (x[0][PrePos]==1)
    Data = x[2][PrePos]
    return pd.Series(Data[Mask]).corr(pd.Series(Ret[Mask]), method="spearman")

@FactorOperatorized(operator_type="Time", args={"Arity": 1, "LookBack": [365], "DTMode": "单时点", "IDMode": "多ID"})
def calcMonthICAvg(f, idt, iid, x, args):
    MonthDTs = getMonthLastDateTime(idt)
    Index = pd.Series(np.arange(0, len(idt)), index=idt)
    return np.nanmean(x[0][Index[MonthDTs].tolist()], axis=0)

@FactorOperatorized(operator_type="Time", args={"Arity": 1, "LookBack": [365], "DTMode": "单时点", "IDMode": "多ID"})
def calcMonthIR(f, idt, iid, x, args):
    MonthDTs = getMonthLastDateTime(idt)
    Index = pd.Series(np.arange(0, len(idt)), index=idt)
    MonthIndex = Index[MonthDTs].tolist()
    ICAvg = np.nanmean(x[0][MonthIndex], axis=0)
    ICStd = np.nanstd(x[0][MonthIndex], axis=0)
    return ICAvg / ICStd


def defFactor(fdi: FactorDefInput):
    Factors = []

    LDB = fdi.FDB["LDB"]

    # StockStatusDef = defStockStatus(fdi=fdi)
    # IsListed = StockStatusDef.getFactor(factor_name="if_listed", def_path="...")
    # StockIndustryDef = defStockIndustry(fdi=fdi)
    # Industry = StockIndustryDef.getFactor(factor_name="citic2019_level1", def_path="...")
    # StockDayBar = defStockDayBar(fdi=fdi)
    # TotalCap = StockDayBar.getFactor(factor_name="total_cap", def_path="...")
    # StockDayBarAdj = defStockDayBarAdj(fdi=fdi)
    # Price = StockDayBarAdj.getFactor(factor_name="close", def_path="...")

    FT = LDB.getTable("stock_cn_status")
    IsListed = FT.getFactor("if_listed")
    FT = LDB.getTable("stock_cn_industry")
    Industry = FT.getFactor("citic2019_level1")
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    TotalCap = FT.getFactor("total_cap")
    FT = LDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    Price = FT.getFactor("close")

    FactorInfo = fdi.ModelArgs["factor_info"]
    Descriptors = {}
    for iTable in pd.unique(FactorInfo["因子表"]):
        # iDef = getattr(SourcePkg, iTable).defFactor(fdi=fdi)
        iFT = LDB.getTable(iTable)
        for jFactor in FactorInfo[FactorInfo["因子表"]==iTable].index:
            # Descriptors[jFactor] = iDef.getFactor(factor_name=jFactor, def_path="...")
            Descriptors[jFactor] = iFT.getFactor(jFactor)

    # 分位数变换标准化
    Mask = (IsListed==1)
    for iFactor in Descriptors:
        Descriptors[iFactor] = QuantileStandardization(ascending=(FactorInfo.loc[iFactor, "排序方向"]=="降序"))(Descriptors[iFactor], mask=Mask, cat_data=None)

    # 合并因子形成大类风格因子
    StyleFactors = {}
    for iStyle in pd.unique(FactorInfo["大类风格"]):
        iMask = (FactorInfo["大类风格"]==iStyle)
        iDescriptors = [Descriptors[iFactor] for iFactor in FactorInfo[iMask].index]
        iWeights = FactorInfo["权重"][iMask].values
        StyleFactors[iStyle] = fo.Mean(weights=iWeights, ignore_nan_weight=False)(*iDescriptors)

    # 大类风格因子的标准化
    for iStyle in StyleFactors:
        StyleFactors[iStyle] = QuantileStandardization(ascending=True)(StyleFactors[iStyle], mask=Mask, cat_data=None, factor_args={"Name": iStyle})
    Factors += list(StyleFactors.values())

    # 大类风格因子关于行业和市值进行正交化
    orthogonalize = Orthogonalization(constant=False, drop_dummy_na=False)
    TotalCap = QuantileStandardization(ascending=True)(TotalCap, mask=Mask, cat_data=None)
    StyleFactors_O = {}
    for iStyle in StyleFactors:
        if iStyle!="Size":
            StyleFactors_O[iStyle] = orthogonalize(StyleFactors[iStyle], TotalCap, mask=Mask, dummy_data=Industry)
        else:
            StyleFactors_O[iStyle] = orthogonalize(StyleFactors[iStyle], None, mask=Mask, dummy_data=Industry)

    # 正交化后的大类风格因子的标准化
    for iStyle in StyleFactors_O:
        StyleFactors_O[iStyle] = QuantileStandardization(ascending=True)(StyleFactors_O[iStyle], mask=Mask, cat_data=None, factor_args={"Name": iStyle+"_O"})
    Factors += list(StyleFactors_O.values())

    # ---------------------------------等权合并大类风格因子形成综合得分----------------------------------------------------
    Score_EW = fo.Mean(weights=None, ignore_nan_weight=False)(*list(StyleFactors.values()), factor_args={"Name": "score_ew"})
    Score_EW_O = fo.Mean(weights=None, ignore_nan_weight=False)(*list(StyleFactors_O.values()), factor_args={"Name": "score_ew_o"})
    Factors += [Score_EW, Score_EW_O]

    # 计算因子的月度IC
    StyleICs, StyleICs_O = {}, {}
    for iStyle in StyleFactors:
        StyleICs[iStyle] = calcMonthIC(IsListed, Price, StyleFactors[iStyle], factor_args={"Name": "IC_"+iStyle})
        StyleICs_O[iStyle] = calcMonthIC(IsListed, Price, StyleFactors[iStyle], factor_args={"Name": "IC_"+iStyle+"_O"})

    # 计算IC的年度均值
    StyleICAvgs, StyleICAvgs_O = {}, {}
    for iStyle in StyleFactors:
        StyleICAvgs[iStyle] = calcMonthICAvg(StyleICs[iStyle], factor_args={"Name": "ICAvg_"+iStyle})
        StyleICAvgs_O[iStyle] = calcMonthICAvg(StyleICs_O[iStyle], factor_args={"Name": "ICAvg_"+iStyle+"_O"})

    # ---------------------------------IC 加权合并大类风格因子形成综合得分------------------------------------------------
    nansum = fo.Sum(all_nan=np.nan)
    Score_IC = rename(nansum(*[StyleFactors[iStyle] * StyleICAvgs[iStyle] * (StyleICAvgs[iStyle] > 0) for iStyle in StyleFactors]) / nansum(*[StyleICAvgs[iStyle] * (StyleICAvgs[iStyle]>0) for iStyle in StyleFactors]), factor_name="score_ic")
    Score_IC_O = rename(nansum(*[StyleFactors_O[iStyle] * StyleICAvgs_O[iStyle] * (StyleICAvgs_O[iStyle] > 0) for iStyle in StyleFactors_O]) / nansum(*[StyleICAvgs_O[iStyle] * (StyleICAvgs_O[iStyle] > 0) for iStyle in StyleFactors_O]), factor_name="score_ic_o")
    Factors += [Score_IC, Score_IC_O]

    # 计算IC_IR
    StyleIRs, StyleIRs_O = {}, {}
    for iStyle in StyleFactors:
        StyleIRs[iStyle] = calcMonthIR(StyleICs[iStyle], factor_args={"Name": "IR_"+iStyle})
        StyleIRs_O[iStyle] = calcMonthIR(StyleICs_O[iStyle], factor_args={"Name": "IR_"+iStyle+"_O"})

    # -----------------------------------IC_IR 加权合并大类风格因子形成综合得分-------------------------------------------
    Score_IR = rename(nansum(*[StyleFactors[iStyle] * StyleIRs[iStyle] * (StyleIRs[iStyle] > 0) for iStyle in StyleFactors]) / nansum(*[StyleIRs[iStyle] * (StyleIRs[iStyle] > 0) for iStyle in StyleFactors]), factor_name="score_ir")
    Score_IR_O = rename(nansum(*[StyleFactors_O[iStyle] * StyleIRs_O[iStyle] * (StyleIRs_O[iStyle] > 0) for iStyle in StyleFactors_O]) / nansum(*[StyleIRs_O[iStyle] * (StyleIRs_O[iStyle] > 0) for iStyle in StyleFactors_O]), factor_name="score_ir_o")
    Factors += [Score_IR, Score_IR_O]

    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_multi_factor_simple",
        IDType="A股",
        MaxLookBack=365 * 2,
        Author="麦冬",
        Description="基于固定权重或者 IC 加权的股票简单多因子模型",
        DefScriptPath=__file__
    )
