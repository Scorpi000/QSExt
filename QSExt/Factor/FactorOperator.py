# coding=utf-8
"""内置的因子运算"""
import datetime as dt
from typing import Optional, Dict, List

import numpy as np
import pandas as pd

from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import TimeOperator, SectionOperator, SectionOperation
from QuantStudio.Tools import DataPreprocessingFun


# ----------------------时序运算--------------------------------
class FillNa(TimeOperator):
    def __init__(self, value=None, lookback=1, sys_args={}, config_file=None, **kwargs):
        if value is None:
            Args = {"名称": "fillna", "入参数": 1, "最大入参数": 1, "运算时点": "多时点", "运算ID": "多ID", "回溯期数": [lookback], "参数": {"fill_value": False, "lookback": lookback}}
        else:
            Args = {"名称": "fillna", "入参数": 2, "最大入参数": 2, "运算时点": "多时点", "运算ID": "多ID", "回溯期数": [0, 0], "参数": {"fill_value": True, "lookback": lookback}}
        Args.update(sys_args)
        self._Value = value
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        Data, Val = x
        if not args["fill_value"]:
            LookBack = args["lookback"]
            return pd.DataFrame(Data).fillna(method="pad", limit=LookBack).values[LookBack:]
        else:
            return np.where(pd.notnull(Data), Data, Val)
    
    def __call__(self, f:Factor, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        if self._Value is None:
            return super().__call__(f, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)
        else:
            return super().__call__(f, self._Value, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class RollingCorr(TimeOperator):
    """滚动相关系数
    纯矩阵运算计算列相关系数，处理NaN
    核心思想：NaN置零后，通过计数矩阵修正均值和协方差
    """

    def __init__(self, window:int=1, min_periods:int=1, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "rollingCorr", "LookBack": [window - 1] * 2} | args | {"Arity": 2, "DTMode": "单时点", "IDMode": "多ID", "DataType": "double"}
        Args["ModelArgs"] = {"window": window, "min_periods": min_periods} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        a, b = x
        # 创建有效值掩码
        mask = pd.notnull(a) & pd.notnull(b)  # 两者都有效的位置
        
        # 将NaN替换为0（不影响求和，因为后面会修正）
        a = np.where(mask, a, 0.0)
        b = np.where(mask, b, 0.0)
        
        # 计算每列的有效样本数 (n x 1)
        n_valid = mask.sum(axis=0)
        
        # 计算均值（仅对有效值）
        mean_a = a.sum(axis=0) / n_valid
        mean_b = b.sum(axis=0) / n_valid
        
        # 中心化（无效位置保持为0）
        a = np.where(mask, a - mean_a, 0.0)
        b = np.where(mask, b - mean_b, 0.0)
        
        # 计算协方差和方差（矩阵乘法）
        cov = (a * b).sum(axis=0)  # 协方差
        var_a = (a ** 2).sum(axis=0)        # a的方差
        var_b = (b ** 2).sum(axis=0)        # b的方差
        
        # 相关系数
        corr = cov / np.sqrt(var_a * var_b)
        
        # 处理无效情况（样本不足或方差为0）
        invalid = (n_valid < args["min_periods"]) | (var_a == 0) | (var_b == 0)
        corr = np.where(invalid, np.nan, corr)
        return corr

# ----------------------截面运算--------------------------------
class QuantileStandardization(SectionOperator):
    """截面分位数标准化"""

    def __init__(self, ascending:bool=True, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "calcQuantileStandardization"} | args | {"DTMode": "多时点", "DataType": "double"}
        Args["ModelArgs"] = {"ascending": ascending} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        FactorData = x[0]
        Mask = (x[1].astype(bool) if f._QSArgs.ModelArgs["mask"] else [None] * FactorData.shape[0])
        CatData = (x[-1] if f._QSArgs.ModelArgs["cat_data"] else [None] * FactorData.shape[0])
        Rslt = np.full_like(FactorData, fill_value=np.nan)
        for i in range(FactorData.shape[0]):
            Rslt[i] = DataPreprocessingFun.standardizeQuantile(FactorData[i], mask=Mask[i], cat_data=CatData[i], perturbation=False, **args)
        return Rslt
    
    def __call__(self, f:Factor, mask:Optional[Factor]=None, cat_data:Optional[Factor]=None, factor_args:dict={}, **kwargs) -> SectionOperation:
        Factors = [f]
        if mask is not None: Factors.append(mask)
        if cat_data is not None: Factors.append(cat_data)
        factor_args["ModelArgs"] = factor_args.get("ModelArgs", {}) | {"mask": (mask is not None), "cat_data": (cat_data is not None)}
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)

class RankStandardization(SectionOperator):
    """截面排名标准化"""

    def __init__(self, ascending:bool=True, uniformization:bool=True, offset:float=0.5, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "calcRankStandardization"} | args | {"DTMode": "多时点", "DataType": "double"}
        Args["ModelArgs"] = {"ascending": ascending, "uniformization": uniformization, "offset": offset} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        FactorData = x[0]
        Mask = (x[1].astype(bool) if f._QSArgs.ModelArgs["mask"] else [None] * FactorData.shape[0])
        CatData = (x[-1] if f._QSArgs.ModelArgs["cat_data"] else [None] * FactorData.shape[0])
        Rslt = np.full_like(FactorData, fill_value=np.nan)
        for i in range(FactorData.shape[0]):
            Rslt[i] = DataPreprocessingFun.standardizeRank(FactorData[i], mask=Mask[i], cat_data=CatData[i], perturbation=False, **args)
        return Rslt
    
    def __call__(self, f:Factor, mask:Optional[Factor]=None, cat_data:Optional[Factor]=None, factor_args:dict={}, **kwargs) -> SectionOperation:
        Factors = [f]
        if mask is not None: Factors.append(mask)
        if cat_data is not None: Factors.append(cat_data)
        factor_args["ModelArgs"] = factor_args.get("ModelArgs", {}) | {"mask": (mask is not None), "cat_data": (cat_data is not None)}
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)

class ZScoreStandardization(SectionOperator):
    """截面 z-score 标准化"""

    def __init__(self, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "calcZScoreStandardization"} | args | {"DTMode": "多时点", "DataType": "double"}
        Args["ModelArgs"] = {} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        FactorData = x[0]
        Mask = (x[1].astype(bool) if f._QSArgs.ModelArgs["mask"] else [None] * FactorData.shape[0])
        CatData = (x[2] if f._QSArgs.ModelArgs["cat_data"] else [None] * FactorData.shape[0])
        AvgWeight = (x[3] if f._QSArgs.ModelArgs["avg_weight"] else [None] * FactorData.shape[0])
        DispersionWeight = (x[3] if f._QSArgs.ModelArgs["dispersion_weight"] else [None] * FactorData.shape[0])
        Rslt = np.full_like(FactorData, fill_value=np.nan)
        for i in range(FactorData.shape[0]):
            Rslt[i] = DataPreprocessingFun.standardizeZScore(FactorData[i], mask=Mask[i], cat_data=CatData[i], avg_weight=AvgWeight[i], dispersion_weight=DispersionWeight[i], **args)
        return Rslt
    
    def __call__(self, f:Factor, mask:Optional[Factor]=None, cat_data:Optional[Factor]=None, avg_weight:Optional[Factor]=None, dispersion_weight:Optional[Factor]=None, factor_args:dict={}, **kwargs) -> SectionOperation:
        Factors = [f]
        if mask is not None: Factors.append(mask)
        if cat_data is not None: Factors.append(cat_data)
        if avg_weight is not None: Factors.append(avg_weight)
        if dispersion_weight is not None: Factors.append(dispersion_weight)
        factor_args["ModelArgs"] = factor_args.get("ModelArgs", {}) | {"mask": (mask is not None), "cat_data": (cat_data is not None), "avg_weight": (avg_weight is not None), "dispersion_weight": (dispersion_weight is not None)}
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)

class Orthogonalization(SectionOperator):
    """截面正交化"""

    def __init__(self, constant:bool=False, drop_dummy_na:bool=False, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "orthogonalize"} | args | {"DTMode": "单时点", "DataType": "double"}
        Args["ModelArgs"] = {"constant": constant, "drop_dummy_na": drop_dummy_na} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: dt.datetime, iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        Y, x = x[0], x[1:]
        if f._QSArgs.ModelArgs["mask"]: 
            Mask, x = (x[0]==1), x[1:]
        else:
            Mask = None
        if f._QSArgs.ModelArgs["dummy_data"]: 
            DummyData, x = x[0], x[1:]
        else:
            DummyData = None
        X = np.array(x, dtype=float).T
        Rslt = DataPreprocessingFun.orthogonalize(Y, X=X, mask=Mask, dummy_data=DummyData, **args)
        return Rslt
        
    def __call__(self, f:Factor, *exog:Factor, mask:Optional[Factor]=None, dummy_data:Optional[Factor]=None, factor_args:dict={}, **kwargs) -> SectionOperation:
        Factors = [f]
        if mask is not None: Factors.append(mask)
        if dummy_data is not None: Factors.append(dummy_data)
        if exog: Factors += exog
        else: raise __QS_Error__(f"算子 {self.__class__}: 必须至少指定一个回归因子!")
        factor_args["ModelArgs"] = factor_args.get("ModelArgs", {}) | {"mask": (mask is not None), "dummy_data": (dummy_data is not None)}
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)
