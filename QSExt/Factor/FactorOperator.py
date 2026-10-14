# coding=utf-8
import datetime as dt
from typing import Optional, Dict, List

import numpy as np
import pandas as pd
from pydantic import Field

from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import FactorInputModel, OperatorModelArgs, TimeOperator, TimeOperation, SectionOperator, SectionOperation
from QuantStudio.Tools import DataPreprocessingFun


class FFillArgs(OperatorModelArgs):
    """前向填充的模型参数。"""
    lookback: int = Field(default=1, ge=1, title="最大填充期数")


class RollingCorrArgs(OperatorModelArgs):
    """滚动相关性的模型参数。"""
    window: int = Field(default=1, ge=1, title="窗口长度")
    min_periods: int = Field(default=1, ge=1, title="最少有效样本")


class QuantileArgs(OperatorModelArgs):
    """分位数标准化参数。"""
    ascending: bool = Field(default=True, title="升序")


class RankArgs(QuantileArgs):
    """排名标准化参数。"""
    uniformization: bool = Field(default=True, title="归一化排名")
    offset: float = Field(default=0.5, title="偏移量")


class OrthogonalizationArgs(OperatorModelArgs):
    """正交化回归参数。"""
    constant: bool = Field(default=False, title="包含截距")
    drop_dummy_na: bool = Field(default=False, title="移除缺失分类")


# ----------------------时序运算--------------------------------
class FFill(TimeOperator):
    class __QS_ArgClass__(TimeOperator.__QS_ArgClass__):
        """填充算子的参数声明。"""
        ModelArgs: FFillArgs = Field(default_factory=FFillArgs, title="模型参数")

    class __QS_InputClass__(FactorInputModel):
        """前向填充的因子输入。"""
        f: Factor = Field(title="待填充因子")

    def __init__(self, lookback:int=1, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "ffill", "LookBack": [lookback], "DataType": "double"} | args | {"DTMode": "多时点", "IDMode": "多ID"}
        Args["ModelArgs"] = {"lookback": lookback} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        LookBack = args["lookback"]
        return pd.DataFrame(x[0]).ffill(limit=LookBack).values[LookBack:]

    def _QS_updateArgs(self, args, updates, operand_count=None):
        """模型回溯参数变化时同步时间维度。"""
        args = super()._QS_updateArgs(args, updates, operand_count)
        args["LookBack"] = [args["ModelArgs"]["lookback"]]
        return args
    
    def __call__(self, f:Factor, factor_args:dict={}, **kwargs) -> TimeOperation:
        DataType = f.getMetaData(key="DataType")
        if DataType != self._QSArgs.DataType:
            return super(FFill, self.new(args={"DataType": DataType})).__call__(f, factor_args=factor_args, **kwargs)
        else:
            return super().__call__(f, factor_args=factor_args, **kwargs)

class RollingCorr(TimeOperator):
    """滚动相关系数
    纯矩阵运算计算列相关系数，处理NaN
    核心思想：NaN置零后，通过计数矩阵修正均值和协方差
    """

    class __QS_ArgClass__(TimeOperator.__QS_ArgClass__):
        """滚动相关性的参数声明。"""
        ModelArgs: RollingCorrArgs = Field(default_factory=RollingCorrArgs, title="模型参数")

    class __QS_InputClass__(FactorInputModel):
        """滚动相关性的两个输入。"""
        x0: Factor = Field(title="左侧因子")
        x1: Factor = Field(title="右侧因子")

    def __init__(self, window:int=1, min_periods:int=1, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "rollingCorr", "LookBack": [window - 1] * 2} | args | {"DTMode": "单时点", "IDMode": "多ID", "DataType": "double"}
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

    class __QS_ArgClass__(SectionOperator.__QS_ArgClass__):
        """分位数标准化的参数声明。"""
        ModelArgs: QuantileArgs = Field(default_factory=QuantileArgs, title="模型参数")

    class __QS_InputClass__(FactorInputModel):
        """标准化的因子、掩码和分类输入。"""
        f: Factor = Field(title="待标准化因子")
        mask: Factor | None = Field(default=None, title="掩码")
        cat_data: Factor | None = Field(default=None, title="分类")

    def __init__(self, ascending:bool=True, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "calcQuantileStandardization"} | args | {"DTMode": "多时点", "DataType": "double"}
        Args["ModelArgs"] = {"ascending": ascending} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        inputs = f.dependency_values(x)
        FactorData = inputs.f
        Mask = inputs.mask.astype(bool) if inputs.mask is not None else [None] * FactorData.shape[0]
        CatData = inputs.cat_data if inputs.cat_data is not None else [None] * FactorData.shape[0]
        Rslt = np.full_like(FactorData, fill_value=np.nan)
        for i in range(FactorData.shape[0]):
            Rslt[i] = DataPreprocessingFun.standardizeQuantile(FactorData[i], mask=Mask[i], cat_data=CatData[i], perturbation=False, **args)
        return Rslt
    
    def __call__(self, f:Factor, mask:Optional[Factor]=None, cat_data:Optional[Factor]=None, factor_args:dict={}, **kwargs) -> SectionOperation:
        Factors = [f]
        if mask is not None: Factors.append(mask)
        if cat_data is not None: Factors.append(cat_data)
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)

class RankStandardization(SectionOperator):
    """截面排名标准化"""

    class __QS_ArgClass__(SectionOperator.__QS_ArgClass__):
        """排名标准化的参数声明。"""
        ModelArgs: RankArgs = Field(default_factory=RankArgs, title="模型参数")

    __QS_InputClass__ = QuantileStandardization.__QS_InputClass__

    def __init__(self, ascending:bool=True, uniformization:bool=True, offset:float=0.5, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "calcRankStandardization"} | args | {"DTMode": "多时点", "DataType": "double"}
        Args["ModelArgs"] = {"ascending": ascending, "uniformization": uniformization, "offset": offset} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        inputs = f.dependency_values(x)
        FactorData = inputs.f
        Mask = inputs.mask.astype(bool) if inputs.mask is not None else [None] * FactorData.shape[0]
        CatData = inputs.cat_data if inputs.cat_data is not None else [None] * FactorData.shape[0]
        Rslt = np.full_like(FactorData, fill_value=np.nan)
        for i in range(FactorData.shape[0]):
            Rslt[i] = DataPreprocessingFun.standardizeRank(FactorData[i], mask=Mask[i], cat_data=CatData[i], perturbation=False, **args)
        return Rslt
    
    def __call__(self, f:Factor, mask:Optional[Factor]=None, cat_data:Optional[Factor]=None, factor_args:dict={}, **kwargs) -> SectionOperation:
        Factors = [f]
        if mask is not None: Factors.append(mask)
        if cat_data is not None: Factors.append(cat_data)
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)

class ZScoreStandardization(SectionOperator):
    """截面 z-score 标准化"""

    class __QS_InputClass__(QuantileStandardization.__QS_InputClass__):
        """带独立均值和离散度权重的标准化输入。"""
        avg_weight: Factor | None = Field(default=None, title="均值权重")
        dispersion_weight: Factor | None = Field(default=None, title="离散度权重")

    def __init__(self, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "calcZScoreStandardization"} | args | {"DTMode": "多时点", "DataType": "double"}
        Args["ModelArgs"] = {} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        inputs = f.dependency_values(x)
        FactorData = inputs.f
        Mask = inputs.mask.astype(bool) if inputs.mask is not None else [None] * FactorData.shape[0]
        CatData = inputs.cat_data if inputs.cat_data is not None else [None] * FactorData.shape[0]
        AvgWeight = inputs.avg_weight if inputs.avg_weight is not None else [None] * FactorData.shape[0]
        DispersionWeight = inputs.dispersion_weight if inputs.dispersion_weight is not None else [None] * FactorData.shape[0]
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
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)

class MinMaxStandardization(SectionOperator):
    """截面 Min-Max 标准化"""

    __QS_InputClass__ = QuantileStandardization.__QS_InputClass__

    def __init__(self, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "calcMinMaxStandardization"} | args | {"DTMode": "多时点", "DataType": "double"}
        Args["ModelArgs"] = {} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        inputs = f.dependency_values(x)
        FactorData = inputs.f
        Mask = inputs.mask.astype(bool) if inputs.mask is not None else [None] * FactorData.shape[0]
        CatData = inputs.cat_data if inputs.cat_data is not None else [None] * FactorData.shape[0]
        Rslt = np.full_like(FactorData, fill_value=np.nan)
        for i in range(FactorData.shape[0]):
            Rslt[i] = DataPreprocessingFun.standardizeMinMax(FactorData[i], mask=Mask[i], cat_data=CatData[i], **args)
        return Rslt
    
    def __call__(self, f:Factor, mask:Optional[Factor]=None, cat_data:Optional[Factor]=None, factor_args:dict={}, **kwargs) -> SectionOperation:
        Factors = [f]
        if mask is not None: Factors.append(mask)
        if cat_data is not None: Factors.append(cat_data)
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)

class Orthogonalization(SectionOperator):
    """截面正交化"""

    class __QS_ArgClass__(SectionOperator.__QS_ArgClass__):
        """正交化的参数声明。"""
        ModelArgs: OrthogonalizationArgs = Field(default_factory=OrthogonalizationArgs, title="模型参数")

    class __QS_InputClass__(FactorInputModel):
        """回归对象与解释变量的命名输入。"""
        f: Factor = Field(title="待正交化因子")
        exog: tuple[Factor, ...] = Field(min_length=1, title="解释变量")
        mask: Factor | None = Field(default=None, title="掩码")
        dummy_data: Factor | None = Field(default=None, title="虚拟变量")

    def __init__(self, constant:bool=False, drop_dummy_na:bool=False, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "orthogonalize"} | args | {"DTMode": "单时点", "DataType": "double"}
        Args["ModelArgs"] = {"constant": constant, "drop_dummy_na": drop_dummy_na} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: dt.datetime, iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        inputs = f.dependency_values(x)
        Y = inputs.f
        Mask = inputs.mask == 1 if inputs.mask is not None else None
        DummyData = inputs.dummy_data
        X = np.array(inputs.exog, dtype=float).T
        Rslt = DataPreprocessingFun.orthogonalize(Y, X=X, mask=Mask, dummy_data=DummyData, **args)
        return Rslt
        
    def __call__(self, f:Factor, *exog:Factor, mask:Optional[Factor]=None, dummy_data:Optional[Factor]=None, factor_args:dict={}, **kwargs) -> SectionOperation:
        Factors = [f] + list(exog)
        if mask is not None: Factors.append(mask)
        if dummy_data is not None: Factors.append(dummy_data)
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)
