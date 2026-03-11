# coding=utf-8
"""内置的因子运算"""
import json
import datetime as dt
from typing import Optional, Dict, List

import numpy as np
import pandas as pd

from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import PointOperator, TimeOperator, SectionOperator, SectionOperation
from QuantStudio.Tools import DataPreprocessingFun


# ----------------------单点运算--------------------------------
class IsNull(PointOperator):
    def __init__(self, sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "isnull", "入参数": 1, "最大入参数": 1, "数据类型": "double", "运算时点": "多时点", "运算ID": "多ID", "参数": {}}
        Args.update(sys_args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        return pd.isnull(x[0])
    
    def __call__(self, f, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(f, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class Sign(PointOperator):
    def __init__(self, sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "sign", "入参数": 1, "最大入参数": 1, "数据类型": "double", "运算时点": "多时点", "运算ID": "多ID", "参数": {}}
        Args.update(sys_args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        return np.sign(x[0].astype(float))
    
    def __call__(self, f, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(f, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class Ceil(PointOperator):
    def __init__(self, sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "ceil", "入参数": 1, "最大入参数": 1, "数据类型": "double", "运算时点": "多时点", "运算ID": "多ID", "参数": {}}
        Args.update(sys_args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        return np.ceil(x[0].astype(float))
    
    def __call__(self, f, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(f, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class Floor(PointOperator):
    def __init__(self, sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "floor", "入参数": 1, "最大入参数": 1, "数据类型": "double", "运算时点": "多时点", "运算ID": "多ID", "参数": {}}
        Args.update(sys_args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        return np.floor(x[0].astype(float))
    
    def __call__(self, f, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(f, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class Fix(PointOperator):
    def __init__(self, sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "fix", "入参数": 1, "最大入参数": 1, "数据类型": "double", "运算时点": "多时点", "运算ID": "多ID", "参数": {}}
        Args.update(sys_args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        return np.fix(x[0].astype(float))
    
    def __call__(self, f, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(f, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class Clip(PointOperator):
    def __init__(self, sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "clip", "入参数": 1, "最大入参数": 3, "数据类型": "double", "运算时点": "多时点", "运算ID": "多ID", "参数": {}}
        Args.update(sys_args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        return np.clip(x[0].astype(float), x[1].astype(float), x[2].astype(float))
    
    def __call__(self, f, a_min, a_max, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(f, a_min, a_max, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class NanProd(PointOperator):
    def __init__(self, all_nan:float=1, dtype:str="double", sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "nanprod", "入参数": 1, "最大入参数": -1, "数据类型": dtype, "运算时点": "多时点", "运算ID": "多ID", "参数": {"all_nan": all_nan}}
        Args.update(sys_args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        Data = np.array(x)
        Rslt = np.nanprod(Data, axis=0)
        Mask = (np.sum(pd.notnull(Data), axis=0)==0)
        Rslt[Mask] = args["all_nan"]
        return Rslt
    
    def __call__(self, *factors, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(*factors, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class FromTimestamp(PointOperator):
    def __init__(self, unit:float=1e9, sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "fromtimestamp", "入参数": 1, "最大入参数": 1, "数据类型": "object", "运算时点": "多时点", "运算ID": "多ID", "参数": {"unit": unit}}
        Args.update(sys_args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        return pd.DataFrame(x[0]).applymap(lambda x: dt.datetime.fromtimestamp(x / args["unit"]) if pd.notnull(x) else None).values

    def __call__(self, f, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(f, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class Strftime(PointOperator):
    """时间格式化"""

    def __init__(self, dt_format:str="%Y%m%d", args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "strftime"} | args | {"Arity": 1, "DataType": "string", "DTMode": "多时点", "IDMode": "多ID"}
        Args["ModelArgs"] = {"dt_format": dt_format} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        DTFormat = args["dt_format"]
        return pd.DataFrame(x[0]).map(lambda x: x.strftime(DTFormat) if pd.notnull(x) else None).values

class Strptime(PointOperator):
    """字符串转时间"""

    def __init__(self, dt_format:str="%Y%m%d", args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "strptime"} | args | {"Arity": 1, "DataType": "object", "DTMode": "多时点", "IDMode": "多ID"}
        Args["ModelArgs"] = {"dt_format": dt_format} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        DTFormat = args["dt_format"]
        return pd.DataFrame(x[0]).map(lambda x: dt.datetime.strptime(x, DTFormat) if pd.notnull(x) else None).values

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

class RollingSkew(TimeOperator):
    def __init__(self, window:int=1, min_periods:int=1, win_type:Optional[str]=None, auto_lookback:bool=True, sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "rollingSkew", "入参数": 1, "最大入参数": 1, "数据类型": "double", "运算时点": "多时点", "运算ID": "多ID", "回溯期数": [1-1], "参数": {"window": window, "min_periods": min_periods, "win_type": win_type}}
        if auto_lookback and (window is not None):
            Args["回溯期数"] = [window-1]
        Args.update(sys_args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        return pd.DataFrame(x[0]).rolling(**args).skew().values[self.Args["回溯期数"][0]:]
    
    def __call__(self, f:Factor, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(f, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class RollingKurt(TimeOperator):
    def __init__(self, window:int=1, min_periods:int=1, win_type:Optional[str]=None, auto_lookback:bool=True, sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "rollingKurt", "入参数": 1, "最大入参数": 1, "数据类型": "double", "运算时点": "多时点", "运算ID": "多ID", "回溯期数": [1-1], "参数": {"window": window, "min_periods": min_periods, "win_type": win_type}}
        if auto_lookback and (window is not None):
            Args["回溯期数"] = [window-1]
        Args.update(sys_args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        return pd.DataFrame(x[0]).rolling(**args).kurt().values[self.Args["回溯期数"][0]:]
    
    def __call__(self, f:Factor, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(f, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class RollingProd(TimeOperator):
    def __init__(self, window:int=1, min_periods:int=1, auto_lookback:bool=True, sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "rollingProd", "入参数": 1, "最大入参数": 1, "数据类型": "double", "运算时点": "单时点", "运算ID": "多ID", "回溯期数": [1-1], "参数": {"window": window, "min_periods": min_periods}}
        if auto_lookback and (window is not None):
            Args["回溯期数"] = [window-1]
        Args.update(args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        Rslt = np.nanprod(x[0], axis=0)
        Rslt[np.sum(pd.notnull(x[0]), axis=0) < args["min_periods"]] = np.nan
        return Rslt
    
    def __call__(self, f:Factor, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(f, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class Diff(TimeOperator):
    def __init__(self, n:int=1, auto_lookback:bool=True, sys_args={}, config_file=None, **kwargs):
        Args = {"名称": "diff", "入参数": 1, "最大入参数": 1, "运算时点": "多时点", "运算ID": "多ID", "回溯期数": [1], "参数": {"n": int(n)}}
        if auto_lookback:
            Args["回溯期数"] = [int(n)]
        Args.update(sys_args)
        return super().__init__(sys_args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        nDT = x[0].shape[0] - self.Args["回溯期数"][0]
        return np.diff(x[0], n=args["n"], axis=0)[-nDT:]
    
    def __call__(self, f:Factor, factor_name:Optional[str]=None, factor_args:Dict={}, **kwargs):
        return super().__call__(f, args={}, factor_name=factor_name, factor_args=factor_args, **kwargs)

class ToJson(PointOperator):
    """将因子值转换成 json 字符串"""
    
    def __init__(self, args={}, config_file=None, **kwargs):
        Args = {"Name": "tojson"} | args | {"DataType": "string", "DTMode": "多时点", "IDMode": "多ID"}
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f, idt, iid, x, args):
        return pd.DataFrame(x[0]).map(lambda v: json.dumps(v, ensure_ascii=False) if pd.notnull(v) else None).values

# ----------------------截面运算--------------------------------
class QuantileStandardization(SectionOperator):
    """截面分位数标准化"""

    def __init__(self, ascending:bool=True, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "calcQuantileStandardization"} | args | {"DTMode": "多时点", "OutputMode": "全截面", "DataType": "double"}
        Args["ModelArgs"] = {"ascending": ascending} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        FactorData = x[0]
        Mask = (x[1].astype(bool) if args["mask"] else [None] * FactorData.shape[0])
        CatData = (x[-1] if args["cat_data"] else [None] * FactorData.shape[0])
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

class Orthogonalization(SectionOperator):
    """截面正交化"""

    def __init__(self, constant:bool=False, drop_dummy_na:bool=False, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "orthogonalize"} | args | {"DTMode": "单时点", "OutputMode": "全截面", "DataType": "double"}
        Args["ModelArgs"] = {"constant": constant, "drop_dummy_na": drop_dummy_na} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)
    
    def calculate(self, f: Factor, idt: dt.datetime, iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        Y, x = x[0], x[1:]
        if args["mask"]: 
            Mask, x = (x[0]==1), x[1:]
        else:
            Mask = None
        if args["dummy_data"]: 
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
