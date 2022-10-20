# coding=utf-8
"""简单多因子模型"""
import os
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_multi_factor_classic",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def MonthICFun(f, idt, iid, x, args):
    MonthDTs = QS.Tools.DateTime.getMonthLastDateTime(idt)
    if MonthDTs[-1]==idt[-1]: PrePos = idt.index(MonthDTs[-2])
    else: PrePos = idt.index(MonthDTs[-1])
    Ret = x[1][-1] / x[1][PrePos] - 1
    Mask = (x[0][PrePos]==1)
    Data = x[2][PrePos]
    return pd.Series(Data[Mask]).corr(pd.Series(Ret[Mask]), method="spearman")

def MonthICAvgFun(f, idt, iid, x, args):
    MonthDTs = QS.Tools.DateTime.getMonthLastDateTime(idt)
    Index = pd.Series(np.arange(0, len(idt)), index=idt)
    return np.nanmean(x[0][Index[MonthDTs].tolist()], axis=0)

def MonthIRFun(f, idt, iid, x, args):
    MonthDTs = QS.Tools.DateTime.getMonthLastDateTime(idt)
    Index = pd.Series(np.arange(0, len(idt)), index=idt)
    MonthIndex = Index[MonthDTs].tolist()
    ICAvg = np.nanmean(x[0][MonthIndex], axis=0)
    ICStd = np.nanstd(x[0][MonthIndex], axis=0)
    return ICAvg / ICStd

def defFactor(args={}):
    Factors = []

    LDB = args["LDB"]

    FT = LDB.getTable("stock_cn_info")
    IsListed = FT.getFactor("if_listed")
    FT = LDB.getTable("stock_industry")
    Industry = FT.getFactor("citic_level1")
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    TotalCap = FT.getFactor("total_cap")
    FT = LDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    Price = FT.getFactor("close")

    FactorInfo = QS.Tools.File.readCSV2Pandas(args["factor_info_file"], encoding="utf8").set_index(["因子名称"])
    Descriptors = {}
    for iTable in pd.unique(FactorInfo["因子表"]):
        iFT = LDB.getTable(iTable)
        for jFactor in FactorInfo[FactorInfo["因子表"]==iTable].index:
            Descriptors[jFactor] = iFT.getFactor(jFactor)

    # 分位数变换标准化
    Mask = (IsListed==1)
    for iFactor in Descriptors:
        Descriptors[iFactor] = fd.standardizeQuantile(Descriptors[iFactor], mask=Mask, cat_data=None, ascending=(FactorInfo.loc[iFactor,"排序方向"]=="降序"))

    # 合并因子形成大类风格因子
    StyleFactors = {}
    for iStyle in pd.unique(FactorInfo["大类风格"]):
        iMask = (FactorInfo["大类风格"]==iStyle)
        iDescriptors = [Descriptors[iFactor] for iFactor in FactorInfo[iMask].index]
        iWeights = FactorInfo["权重"][iMask].values
        StyleFactors[iStyle] = fd.nanmean(*iDescriptors, weights=iWeights, ignore_nan_weight=False)

    # 大类风格因子的标准化
    for iStyle in StyleFactors:
        StyleFactors[iStyle] = Factorize(fd.standardizeQuantile(StyleFactors[iStyle], mask=Mask, cat_data=None, ascending=True), factor_name=iStyle)
    Factors += list(StyleFactors.values())

    # 大类风格因子关于行业和市值进行正交化
    TotalCap = fd.standardizeQuantile(TotalCap, mask=Mask, cat_data=None, ascending=True)
    StyleFactors_O = {}
    for iStyle in StyleFactors:
        if iStyle!="Size":
            StyleFactors_O[iStyle] = fd.orthogonalize(StyleFactors[iStyle], TotalCap, mask=Mask, constant=False, dummy_data=Industry, drop_dummy_na=False)
        else:
            StyleFactors_O[iStyle] = fd.orthogonalize(StyleFactors[iStyle], None, mask=Mask, constant=False, dummy_data=Industry, drop_dummy_na=False)

    # 正交化后的大类风格因子的标准化
    for iStyle in StyleFactors_O:
        StyleFactors_O[iStyle] = Factorize(fd.standardizeQuantile(StyleFactors_O[iStyle], mask=Mask, cat_data=None, ascending=True), iStyle+"_O")
    Factors += list(StyleFactors_O.values())

    # ---------------------------------等权合并大类风格因子形成综合得分----------------------------------------------------
    Score_EW = Factorize(fd.nanmean(*list(StyleFactors.values()), weights=None, ignore_nan_weight=False), "Score_EW")
    Score_EW_O = Factorize(fd.nanmean(*list(StyleFactors_O.values()), weights=None, ignore_nan_weight=False), "Score_EW_O")
    Factors += [Score_EW, Score_EW_O]

    # 计算因子的月度IC
    StyleICs, StyleICs_O = {}, {}
    for iStyle in StyleFactors:
        StyleICs[iStyle] = QS.FactorDB.PanelOperation("IC_"+iStyle, [IsListed, Price, StyleFactors[iStyle]], {"算子":MonthICFun, "回溯期数":[30,30,30]})
        StyleICs_O[iStyle] = QS.FactorDB.PanelOperation("IC_"+iStyle+"_O", [IsListed, Price, StyleFactors_O[iStyle]], {"算子":MonthICFun, "回溯期数":[30,30,30]})

    # 计算IC的年度均值
    StyleICAvgs, StyleICAvgs_O = {}, {}
    for iStyle in StyleFactors:
        StyleICAvgs[iStyle] = QS.FactorDB.TimeOperation("ICAvg_"+iStyle, [StyleICs[iStyle]], {"算子":MonthICAvgFun, "回溯期数":[365], "运算ID":"多ID"})
        StyleICAvgs_O[iStyle] = QS.FactorDB.TimeOperation("ICAvg_"+iStyle+"_O", [StyleICs_O[iStyle]], {"算子":MonthICAvgFun, "回溯期数":[365], "运算ID":"多ID"})

    # ---------------------------------IC 加权合并大类风格因子形成综合得分------------------------------------------------
    Score_IC = Factorize(fd.nansum(*[StyleFactors[iStyle]*StyleICAvgs[iStyle]*(StyleICAvgs[iStyle]>0) for iStyle in StyleFactors]) / fd.nansum(*[StyleICAvgs[iStyle]*(StyleICAvgs[iStyle]>0) for iStyle in StyleFactors]), factor_name="Score_IC")
    Score_IC_O = Factorize(fd.nansum(*[StyleFactors_O[iStyle]*StyleICAvgs_O[iStyle]*(StyleICAvgs_O[iStyle]>0) for iStyle in StyleFactors_O]) / fd.nansum(*[StyleICAvgs_O[iStyle]*(StyleICAvgs_O[iStyle]>0) for iStyle in StyleFactors_O]), factor_name="Score_IC_O")
    Factors += [Score_IC, Score_IC_O]

    # 计算IC_IR
    StyleIRs, StyleIRs_O = {}, {}
    for iStyle in StyleFactors:
        StyleIRs[iStyle] = QS.FactorDB.TimeOperation("IR_"+iStyle, [StyleICs[iStyle]], {"算子":MonthIRFun, "回溯期数":[365], "运算ID":"多ID"})
        StyleIRs_O[iStyle] = QS.FactorDB.TimeOperation("IR_"+iStyle+"_O", [StyleICs_O[iStyle]], {"算子":MonthIRFun, "回溯期数":[365], "运算ID":"多ID"})

    # -----------------------------------IC_IR 加权合并大类风格因子形成综合得分-------------------------------------------
    Score_IR = Factorize(fd.nansum(*[StyleFactors[iStyle]*StyleIRs[iStyle]*(StyleIRs[iStyle]>0) for iStyle in StyleFactors]) / fd.nansum(*[StyleIRs[iStyle]*(StyleIRs[iStyle]>0) for iStyle in StyleFactors]), factor_name="Score_IR")
    Score_IR_O = Factorize(fd.nansum(*[StyleFactors_O[iStyle]*StyleIRs_O[iStyle]*(StyleIRs_O[iStyle]>0) for iStyle in StyleFactors_O]) / fd.nansum(*[StyleIRs_O[iStyle]*(StyleIRs_O[iStyle]>0) for iStyle in StyleFactors_O]), factor_name="Score_IR_O")
    Factors += [Score_IR, Score_IR_O]

    return Factors

if __name__=="__main__":
    pass
