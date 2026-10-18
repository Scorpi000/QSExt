"""以 JSON 保存 DataFactor 的表格数据，重开图时无需重新读取外部来源。"""
from datetime import date, datetime
import math

import numpy as np
import pandas as pd
from pydantic import Field, JsonValue

from QuantStudio.Core.Input import EmptyDependencies, InputModel
from QuantStudio.Factor.Factor import DataFactor, Factor

from .Components import Component
from .Protocol import TypeDescriptor


def _encode(value):
    if value is pd.NA:
        return {"missing": "NA"}
    if value is pd.NaT:
        return {"missing": "NaT"}
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return {"number": str(value)}
    if isinstance(value, (datetime, date)):
        return {"datetime" if isinstance(value, datetime) else "date": value.isoformat()}
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise ValueError(f"表格数据含不可保存的值: {type(value).__name__}")


def _decode(value):
    if not isinstance(value, dict):
        return value
    if set(value) == {"number"} and value["number"] in ("nan", "inf", "-inf"):
        return float(value["number"])
    if set(value) == {"missing"} and value["missing"] in ("NA", "NaT"):
        return pd.NA if value["missing"] == "NA" else pd.NaT
    if set(value) == {"datetime"}:
        return pd.Timestamp(value["datetime"])
    if set(value) == {"date"}:
        return date.fromisoformat(value["date"])
    raise ValueError("无效的表格数据值")


def _axis(index):
    if isinstance(index, pd.MultiIndex):
        raise ValueError("表格数据暂不支持 MultiIndex")
    return {"values": [_encode(value) for value in index], "dtype": str(index.dtype), "name": _encode(index.name)}


def serialize_tabular(data):
    """保留日期/ID 索引、数据类型、缺失值和无穷值，不使用 pickle。"""
    series = isinstance(data, pd.Series)
    frame = data.to_frame() if series else data
    return {"kind": "series" if series else "dataframe", "index": _axis(frame.index),
            "columns": _axis(frame.columns), "dtypes": [str(dtype) for dtype in frame.dtypes],
            "name": _encode(data.name) if series else None,
            "values": [[_encode(value) for value in row] for row in frame.to_numpy(dtype=object)]}


class TabularArgs(InputModel):
    Data: dict[str, JsonValue] = Field(title="表格数据快照")
    Name: str = Field(default="DataFactor", title="名称")
    FactorArgs: dict[str, JsonValue] = Field(default_factory=dict, title="因子参数")


def build_tabular(block, args, inputs):
    """从图文档中的数据快照恢复 DataFactor，保留计算日历和回溯参数。"""
    snapshot = args["Data"]

    def axis(value):
        return pd.Index([_decode(item) for item in value["values"]], dtype=value["dtype"], name=_decode(value["name"]))

    data = pd.DataFrame([[_decode(value) for value in row] for row in snapshot["values"]],
                        index=axis(snapshot["index"]), columns=axis(snapshot["columns"]))
    for index, dtype in enumerate(snapshot["dtypes"]):
        data.isetitem(index, data.iloc[:, index].astype(dtype))
    if snapshot["kind"] == "series":
        data = data.iloc[:, 0].rename(_decode(snapshot["name"]))
    elif snapshot["kind"] != "dataframe":
        raise ValueError("无效的表格数据类型")
    return DataFactor(data, args={**args["FactorArgs"], "Name": args["Name"]})


TABULAR_DATA_COMPONENT = Component(id="qs.factor.tabular", args_model=TabularArgs, input_model=EmptyDependencies,
    output_type=Factor, builder=build_tabular, title="表格数据因子", category="因子",
    infer_output=lambda args: TypeDescriptor(kind="factor", type_id="qs.factor",
        data_type=args.get("FactorArgs", {}).get("DataType", "double")))
