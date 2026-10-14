# coding=utf-8
"""机器学习模型相关的因子运算算子"""
import datetime as dt
from typing import Optional, List, Tuple

import numpy as np
from pydantic import Field

from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import FactorInputModel, SectionOperator, SectionOperation


class Label2Class(SectionOperator):
    """二分类标签生成算子

    根据因子值的分位数将截面数据分为两类，支持按类别分组和掩码过滤。

    Args:
        labels: 分类标签，第一个为高值标签，第二个为低值标签
        top_bottom_ratio: 高低值的分位数比例，(高值比例, 低值比例)
    """

    class __QS_InputClass__(FactorInputModel):
        """分类标签的公开因子输入。"""
        f: Factor = Field(title="待分类因子")
        mask: Factor | None = Field(default=None, title="掩码")
        cat_data: Factor | None = Field(default=None, title="分类")

    def __init__(self, labels: Tuple[int, int] = (1, -1), top_bottom_ratio: Tuple[float, float] = (0.3, 0.3), args: dict = {}, config_file: Optional[str] = None, **kwargs):
        Args = {"Name": "label2Class"} | args | {"DTMode": "多时点", "DataType": "double"}
        Args["ModelArgs"] = {
            "labels": labels,
            "top_bottom_ratio": top_bottom_ratio
        } | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        inputs = f.dependency_values(x)
        FactorData = inputs.f
        Mask = inputs.mask.astype(bool) if inputs.mask is not None else None
        CatData = inputs.cat_data
        Labels = args["labels"]
        TopBottomRatio = args["top_bottom_ratio"]

        Rslt = np.full_like(FactorData, fill_value=np.nan)

        for i in range(FactorData.shape[0]):
            iFactorData = FactorData[i]
            if Mask is not None:
                iMask = Mask[i]
                iFactorData = iFactorData[iMask]

            if CatData is not None:
                iCatData = CatData[i][Mask[i]] if Mask is not None else CatData[i]
                AllCat = np.unique(iCatData)
                for jCat in AllCat:
                    jMask = (iCatData == jCat)
                    jFactorData = iFactorData[jMask]
                    Rslt[i][jMask & (iFactorData >= np.nanpercentile(jFactorData, (1 - TopBottomRatio[0]) * 100))] = Labels[0]
                    Rslt[i][jMask & (iFactorData <= np.nanpercentile(jFactorData, TopBottomRatio[1] * 100))] = Labels[1]
            else:
                Rslt[i][iFactorData >= np.nanpercentile(iFactorData, (1 - TopBottomRatio[0]) * 100)] = Labels[0]
                Rslt[i][iFactorData <= np.nanpercentile(iFactorData, TopBottomRatio[1] * 100)] = Labels[1]

        return Rslt

    def __call__(self, f: Factor, mask: Optional[Factor] = None, cat_data: Optional[Factor] = None, factor_args: dict = {}, **kwargs) -> SectionOperation:
        Factors = [f]
        if mask is not None: Factors.append(mask)
        if cat_data is not None: Factors.append(cat_data)
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)


class LabelQuantile(SectionOperator):
    """分位数标签生成算子

    根据因子值的分位数将截面数据分为多类，支持按类别分组。

    Args:
        top_bottom_ratio: 高低值的分位数比例
    """

    class __QS_InputClass__(FactorInputModel):
        """分位数标签的公开因子输入。"""
        f: Factor = Field(title="待分类因子")
        partition_factor: Factor | None = Field(default=None, title="分组因子")

    def __init__(self, top_bottom_ratio: float = 0.3, args: dict = {}, config_file: Optional[str] = None, **kwargs):
        Args = {"Name": "labelQuantile"} | args | {"DTMode": "多时点", "DataType": "double"}
        Args["ModelArgs"] = {
            "top_bottom_ratio": top_bottom_ratio
        } | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        FactorData = x[0]
        PartitionFactor = x[1] if len(x) > 1 else None
        TopBottomRatio = args["top_bottom_ratio"]

        Rslt = np.full_like(FactorData, fill_value=np.nan)

        for i in range(FactorData.shape[0]):
            iFactorData = FactorData[i]
            if PartitionFactor is not None:
                iPartitionFactor = PartitionFactor[i]
                AllCat = np.unique(iPartitionFactor[iPartitionFactor > 0])
                for jCat in AllCat:
                    jMask = (iPartitionFactor == jCat)
                    jData = iFactorData[jMask]
                    jSelectedNum = int(jData.shape[0] * TopBottomRatio)
                    if jSelectedNum == 0:
                        jSubMask = (iFactorData >= np.nanmedian(jData))
                        Rslt[i][jMask & jSubMask] = 1
                        Rslt[i][jMask & (~jSubMask)] = -1
                    else:
                        Rslt[i][jMask & (iFactorData >= np.nanpercentile(jData, (1 - TopBottomRatio) * 100))] = 1
                        Rslt[i][jMask & (iFactorData <= np.nanpercentile(jData, TopBottomRatio * 100))] = -1

        return Rslt

    def __call__(self, f: Factor, partition_factor: Optional[Factor] = None, factor_args: dict = {}, **kwargs) -> SectionOperation:
        Factors = [f]
        if partition_factor is not None: Factors.append(partition_factor)
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)
