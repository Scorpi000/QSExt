# -*- coding: utf-8 -*-
"""计算图注册中心序列化/反序列化辅助函数"""
import json
import datetime as dt
import importlib
import base64
from typing import Any, Optional, Dict, List, Callable

import numpy as np
import pandas as pd


def _sanitizeForJSON(value: Any) -> Any:
    """将不可 JSON 序列化的类型转换为可序列化格式

    Returns:
        JSON 可序列化的值
    """
    if value is None:
        return value
    if isinstance(value, np.integer):
        return {"__numpy_scalar__": True, "dtype": f"int{value.dtype.itemsize*8}", "value": int(value)}
    if isinstance(value, np.floating):
        v = float(value)
        meta = {"__numpy_scalar__": True, "dtype": f"float{value.dtype.itemsize*8}"}
        if np.isnan(v):
            meta["__nan__"] = True
            return meta
        if np.isinf(v):
            meta["__inf__"] = True
            meta["sign"] = 1 if v > 0 else -1
            return meta
        meta["value"] = v
        return meta
    if isinstance(value, np.bool_):
        return {"__numpy_scalar__": True, "dtype": "bool", "value": bool(value)}
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value:  # NaN
            return {"__nan__": True}
        if value == float("inf"):
            return {"__inf__": True, "sign": 1}
        if value == float("-inf"):
            return {"__inf__": True, "sign": -1}
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, np.ndarray):
        return {"__numpy__": True, "data": value.tolist(), "dtype": str(value.dtype)}
    if isinstance(value, (dt.datetime, dt.date)):
        return {"__datetime__": True, "value": value.isoformat()}
    if isinstance(value, pd.Timestamp):
        return {"__datetime__": True, "value": value.isoformat()}
    if isinstance(value, pd.Series):
        return {"__pd_series__": True, "data": _sanitizeForJSON(value.to_dict()),
                "dtype": str(value.dtype), "name": _sanitizeForJSON(value.name)}
    if isinstance(value, pd.DataFrame):
        return {"__pd_dataframe__": True, "data": _sanitizeForJSON(value.to_dict()),
                "columns": _sanitizeForJSON(list(value.columns)),
                "index": _sanitizeForJSON(list(value.index))}
    if isinstance(value, (list, tuple)):
        return {"__tuple__": True, "data": [_sanitizeForJSON(v) for v in value]} if isinstance(value, tuple) else [_sanitizeForJSON(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _sanitizeForJSON(v) for k, v in value.items()}
    if callable(value):
        return _serializeCallable(value)
    return {"__str_repr__": True, "value": str(value)}


def _desanitizeFromJSON(value: Any) -> Any:
    """_sanitizeForJSON 的逆操作，从 JSON 恢复原始类型

    Returns:
        恢复后的值
    """
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if not isinstance(value, dict):
        if isinstance(value, list):
            return [_desanitizeFromJSON(v) for v in value]
        # 纯数字（旧格式兼容）
        if isinstance(value, (int, float)):
            return value
        return value
    # numpy 标量类型标记
    if "__numpy_scalar__" in value:
        dtype_str = value.get("dtype", "int64")
        if dtype_str.startswith("int"):
            return getattr(np, dtype_str)(value.get("value", 0))
        elif dtype_str.startswith("float"):
            if value.get("__nan__"):
                return getattr(np, dtype_str)(np.nan)
            if value.get("__inf__"):
                v = np.inf if value.get("sign", 1) > 0 else -np.inf
                return getattr(np, dtype_str)(v)
            return getattr(np, dtype_str)(value.get("value", 0.0))
        elif dtype_str == "bool":
            return np.bool_(value.get("value", False))
    # 特殊类型标记
    if "__nan__" in value:
        return float("nan")
    if "__inf__" in value:
        return float("inf") if value["sign"] > 0 else float("-inf")
    if "__numpy__" in value:
        return np.array(value["data"], dtype=value["dtype"])
    if "__datetime__" in value:
        return pd.Timestamp(value["value"])
    if "__pd_series__" in value:
        data = _desanitizeFromJSON(value["data"])
        name = _desanitizeFromJSON(value.get("name"))
        dtype = value.get("dtype")
        s = pd.Series(data, name=name)
        if dtype:
            try:
                s = s.astype(dtype)
            except (ValueError, TypeError):
                pass
        return s
    if "__pd_dataframe__" in value:
        data = _desanitizeFromJSON(value["data"])
        columns = _desanitizeFromJSON(value.get("columns"))
        index = _desanitizeFromJSON(value.get("index"))
        df = pd.DataFrame(data)
        if columns is not None:
            df.columns = columns
        if index is not None:
            df.index = index
        return df
    if "__tuple__" in value:
        return tuple(_desanitizeFromJSON(v) for v in value["data"])
    if "__func_ref__" in value:
        return _deserializeFuncRef(value["__func_ref__"])
    if "__numpy_func__" in value:
        return getattr(np, value["name"])
    if "__str_repr__" in value:
        return value["value"]
    if "__dill__" in value:
        import dill
        return dill.loads(base64.b64decode(value["__dill__"]))
    # 普通 dict，递归反序列化
    return {k: _desanitizeFromJSON(v) for k, v in value.items()}


def _serializeCallable(func: Callable) -> dict:
    """序列化可调用对象

    Returns:
        JSON 可序列化的字典
    """
    # numpy ufunc
    if isinstance(func, np.ufunc):
        return {"__numpy_func__": True, "name": func.__name__}
    # 可导入的标准函数/方法
    module = getattr(func, "__module__", None)
    qualname = getattr(func, "__qualname__", None)
    if module and qualname and module != "__main__":
        try:
            # 验证可导入
            obj = importlib.import_module(module)
            for part in qualname.split("."):
                obj = getattr(obj, part)
            if obj is func:
                return {"__func_ref__": {"module": module, "qualname": qualname}}
        except (ImportError, AttributeError):
            pass
    # 无法导入的函数，使用 dill
    try:
        import dill
        return {"__dill__": base64.b64encode(dill.dumps(func)).decode("ascii")}
    except ImportError:
        return {"__str_repr__": True, "value": str(func)}


def _decryptArgs(args: dict) -> dict:
    """解密 args 中以 ``"ENC:"`` 为前缀的字段值

    与 ``__QS_ArgClass__.deserialize()`` 不同，此函数仅逐字段解密，
    不构造 ArgClass 实例，因此不触发 pydantic 校验。适用于因存储拆分
    而缺失部分必填字段（如 Operator）的场景。

    Args:
        args: 待解密的参数字典

    Returns:
        解密后的参数字典（非加密字段原样返回）
    """
    from QuantStudio.Core._encryption import decrypt_value, is_encrypted
    return {
        k: decrypt_value(v) if is_encrypted(v) else v
        for k, v in args.items()
    }


def _deserializeFuncRef(ref: dict) -> Callable:
    """从函数引用字典恢复可调用对象

    Args:
        ref: {"module": ..., "qualname": ...}

    Returns:
        可调用对象
    """
    module = importlib.import_module(ref["module"])
    obj = module
    for part in ref["qualname"].split("."):
        obj = getattr(obj, part)
    return obj


def serializeFactorArgs(factor) -> str:
    """序列化因子的 QSArgs 为 JSON 字符串（排除 Operator 字段）

    使用 ``_QSArgs.serialize()`` 进行序列化，对标记 ``secret=True`` 的
    敏感字段自动 Fernet 加密为 ``"ENC:<base64>"`` 格式。

    Args:
        factor: Factor 实例

    Returns:
        JSON 字符串
    """
    args_dict = factor._QSArgs.serialize()
    # 排除 Operator（它通过 USES_OPERATOR 关系单独存储）
    args_dict.pop("Operator", None)
    # 排除已排除的字段（Meta 单独存储）
    args_dict.pop("Meta", None)
    return json.dumps(_sanitizeForJSON(args_dict), ensure_ascii=False)


def serializeOperatorArgs(operator) -> str:
    """序列化算子的 ModelArgs 为 JSON 字符串

    使用 ``_QSArgs.serialize()`` 对算子参数集进行序列化，从结果中提取
    ``ModelArgs`` 字段。敏感字段自动加密。

    Args:
        operator: FactorOperator 实例

    Returns:
        JSON 字符串
    """
    serialized = operator._QSArgs.serialize()
    model_args = serialized.get("ModelArgs", {})
    return json.dumps(_sanitizeForJSON(model_args), ensure_ascii=False)


def serializeOperatorCalculateRef(operator) -> tuple:
    """判定算子的 CalculateRef 和 IsCustom

    Args:
        operator: FactorOperator 实例

    Returns:
        (calculate_ref_json: str | None, is_custom: bool)
    """
    calculate = getattr(operator, "calculate", None)
    if calculate is None:
        return (None, False)
    # 检查是否为类方法（非自定义）
    for cls in type(operator).__mro__:
        if "calculate" in cls.__dict__:
            # calculate 是类上定义的方法
            if cls.__dict__["calculate"] is calculate:
                return (None, False)
            break
    # 自定义算子
    ref = _serializeCallable(calculate)
    return (json.dumps(ref, ensure_ascii=False), True)
