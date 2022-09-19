# coding=utf-8
"""内置的因子运算(机器学习模型相关)"""
import datetime as dt
import uuid

import numpy as np
import pandas as pd

from QuantStudio import __QS_Error__
from QuantStudio.FactorDataBase.FactorDB import Factor
from QuantStudio.FactorDataBase.FactorOperation import PointOperation, TimeOperation, SectionOperation, PanelOperation
from QuantStudio.FactorDataBase.FactorTools import _genMultivariateOperatorInfo, _genOperatorData
from QuantStudio.Tools.AuxiliaryFun import distributeEqual

# 生成二分类的标签因子
def _label2Class(f, idt, iid, x, args):
    Data = _genOperatorData(f,idt,iid,x,args)
    OperatorArg = args["OperatorArg"].copy()
    Labels = OperatorArg["labels"]
    TopBottomRatio = OperatorArg["top_bottom_ratio"]
    FactorData = Data[0]
    StartInd = 1
    Mask = OperatorArg.pop("mask")
    if Mask is not None:
        Mask = (Data[StartInd]==1)
        StartInd += 1
        FactorData = FactorData[Mask]
    Rslt = np.full(shape=FactorData.shape, fill_value=np.nan)
    CatData = OperatorArg.pop("cat_data")
    if CatData is not None:
        CatData = Data[StartInd]
        StartInd += 1
        if Mask is not None: CatData = CatData[Mask]
        AllCat = np.unique(CatData)
        for jCat in AllCat:
            jMask = (CatData==jCat)
            jFactorData = FactorData[jMask]
            Rslt[jMask & (FactorData >= np.nanpercentile(jFactorData, (1-TopBottomRatio[0])*100))] = Labels[0]
            Rslt[jMask & (FactorData <= np.nanpercentile(jFactorData, TopBottomRatio[1]*100))] = Labels[1]
    else:
        Rslt[FactorData >= np.nanpercentile(FactorData, (1-TopBottomRatio[0])*100)] = Labels[0]
        Rslt[FactorData <= np.nanpercentile(FactorData, TopBottomRatio[1]*100)] = Labels[1]
    if Mask is not None:
        Rslt, MaskedRslt = np.full(shape=(len(iid), ), fill_value=np.nan), Rslt
        Rslt[Mask] = MaskedRslt
    return Rslt


def label2Class(f, labels=(1, -1), top_bottom_ratio=(0.3, 0.3), mask=None, cat_data=None, **kwargs):
    Factors = [f]
    OperatorArg = {}
    if mask is not None:
        Factors.append(mask)
        OperatorArg["mask"] = 1
    else:
        OperatorArg["mask"] = None
    if isinstance(cat_data,Factor):
        Factors.append(cat_data)
        OperatorArg["cat_data"] = 1
    else:
        OperatorArg["cat_data"] = None
    Descriptors, Args = _genMultivariateOperatorInfo(*Factors)
    Args["OperatorArg"] = {"labels": labels, "top_bottom_ratio": top_bottom_ratio}
    Args["OperatorArg"].update(OperatorArg)
    return SectionOperation(kwargs.pop("factor_name", str(uuid.uuid1())),Descriptors,{"算子":_label2Class,"参数":Args,"运算时点":"多时点","输出形式":"全截面"}, **kwargs)


# 生成标签因子
def _labelQuantile(f, idt, iid, x, args):
    Data = _genOperatorData(f,idt,iid,x,args)[0]
    Thresholds = args["OperatorArg"]["thresholds"]
    Rslt = np.zeros()
    AllCat = np.unique(PartitionFactor[PartitionFactor>0])
    YLabel = np.zeros(Return.shape)
    for jCat in AllCat:
        jMask = (PartitionFactor==jCat)
        jReturn = Return[jMask]
        jSelectedNum = int(jReturn.shape[0] * TopBottomRatio)
        if jSelectedNum==0:
            jSubMask = (Return>=np.nanmedian(jReturn))
            YLabel[jMask & jSubMask] = 1
            YLabel[jMask & (~jSubMask)] = -1
        else:
            YLabel[jMask & (Return >= np.nanpercentile(jReturn, (1-TopBottomRatio)*100))] = 1
            YLabel[jMask & (Return <= np.nanpercentile(jReturn, TopBottomRatio*100))] = -1
    return YLabel

def labelQuantile(f, thresholds, labels, mask=None, cat_data=None, **kwargs):
    Factors = [f]
    Descriptors, Args = _genMultivariateOperatorInfo(*Factors)
    Args["OperatorArg"] = {"thresholds": thresholds}
    return SectionOperation(kwargs.pop("factor_name", str(uuid.uuid1())),Descriptors,{"算子":_labelQuantile,"参数":Args,"运算时点":"多时点","输出形式":"全截面"}, **kwargs)