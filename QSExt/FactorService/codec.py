"""受限类型编码与带校验的 Arrow 标准数据封装。

不使用 pickle 或函数反序列化。对象列采用逐单元格类型标记，数值列使用
Arrow 原生数组；Panel 的三轴独立保存，保留空轴和全缺失位置。
"""

import datetime as dt
import hashlib
import io
import json
import struct

import numpy as np
import pandas as pd

from QuantStudio.Core.QSObject import Panel

MAGIC = b"QSFS1\x00"


def to_control(value):
    """将支持的值转换为不含可执行对象的 JSON 类型树。"""
    if value is None or type(value) in (str, bool, int):
        return value
    if value is pd.NA:
        return {"$type": "pd.NA"}
    if value is pd.NaT:
        return {"$type": "pd.NaT"}
    if isinstance(value, np.generic):
        if isinstance(value, np.datetime64):
            return {"$type": "numpy.datetime64", "dtype": str(value.dtype), "value": str(value)}
        return {"$type": "numpy", "dtype": str(value.dtype), "value": to_control(value.item())}
    if isinstance(value, float):
        if np.isfinite(value):
            return value
        return {"$type": "float", "value": "nan" if np.isnan(value) else ("inf" if value > 0 else "-inf")}
    if isinstance(value, pd.Timestamp):
        return {"$type": "timestamp", "value": value.isoformat(), "tz": str(value.tz) if value.tz else None}
    if isinstance(value, dt.datetime):
        return {"$type": "datetime", "value": value.isoformat()}
    if isinstance(value, dt.date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, pd.Timedelta):
        return {"$type": "pd.timedelta", "value": value.value}
    if isinstance(value, dt.timedelta):
        return {"$type": "timedelta", "days": value.days, "seconds": value.seconds, "microseconds": value.microseconds}
    if isinstance(value, np.ndarray):
        return {"$type": "ndarray", "dtype": str(value.dtype), "shape": list(value.shape), "value": to_control(value.tolist())}
    if isinstance(value, pd.MultiIndex):
        if any(isinstance(level, pd.CategoricalIndex) for level in value.levels):
            raise TypeError("暂不支持分类索引，请显式转换")
        return {"$type": "multiindex", "values": to_control(value.tolist()), "names": to_control(value.names)}
    if isinstance(value, pd.RangeIndex):
        return {"$type": "rangeindex", "start": value.start, "stop": value.stop, "step": value.step, "name": to_control(value.name)}
    if isinstance(value, pd.Index):
        if isinstance(value, pd.CategoricalIndex):
            raise TypeError("暂不支持分类索引，请显式转换")
        return {"$type": "index", "dtype": str(value.dtype), "values": to_control(value.tolist()), "name": to_control(value.name), "freq": value.freqstr if isinstance(value, (pd.DatetimeIndex, pd.TimedeltaIndex)) else None}
    if isinstance(value, pd.Series):
        if isinstance(value.dtype, pd.CategoricalDtype):
            raise TypeError("暂不支持分类 dtype，请显式转换")
        return {"$type": "series", "index": to_control(value.index), "name": to_control(value.name), "dtype": str(value.dtype), "values": to_control(value.tolist())}
    if isinstance(value, pd.DataFrame):
        return {"$type": "frame", "index": to_control(value.index), "columns": to_control(value.columns), "series": [to_control(value.iloc[:, i]) for i in range(value.shape[1])]}
    if isinstance(value, tuple):
        return {"$type": "tuple", "value": [to_control(item) for item in value]}
    if isinstance(value, list):
        return [to_control(item) for item in value]
    if isinstance(value, dict):
        # 始终编码为键值对，保留键类型并避免保留键碰撞。
        return {"$type": "dict", "items": [[to_control(key), to_control(item)] for key, item in value.items()]}
    raise TypeError(f"不支持传输的数据类型: {type(value).__name__}")


def from_control(value):
    """恢复受支持的类型标记，拒绝未知标记。"""
    if isinstance(value, list):
        return [from_control(item) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value.get("$type")
    if kind is None:
        return {key: from_control(item) for key, item in value.items()}
    if kind == "dict":
        return {from_control(key): from_control(item) for key, item in value["items"]}
    if kind == "tuple":
        return tuple(from_control(item) for item in value["value"])
    if kind == "float":
        return float(value["value"])
    if kind == "pd.NA":
        return pd.NA
    if kind == "pd.NaT":
        return pd.NaT
    if kind == "date":
        return dt.date.fromisoformat(value["value"])
    if kind == "datetime":
        return dt.datetime.fromisoformat(value["value"])
    if kind == "timestamp":
        result = pd.Timestamp(value["value"])
        return result.tz_convert(value["tz"]) if value["tz"] else result
    if kind == "timedelta":
        return dt.timedelta(days=value["days"], seconds=value["seconds"], microseconds=value["microseconds"])
    if kind == "pd.timedelta":
        return pd.Timedelta(value["value"], unit="ns")
    if kind == "numpy":
        dtype = np.dtype(value["dtype"])
        if dtype.kind not in "biufUS":
            raise TypeError("不支持的 NumPy 标量类型")
        return dtype.type(from_control(value["value"]))
    if kind == "numpy.datetime64":
        return np.array(value["value"], dtype=value["dtype"])[()]
    if kind == "ndarray":
        return np.array(from_control(value["value"]), dtype=value["dtype"]).reshape(value["shape"])
    if kind == "rangeindex":
        return pd.RangeIndex(value["start"], value["stop"], value["step"], name=from_control(value["name"]))
    if kind == "multiindex":
        return pd.MultiIndex.from_tuples(from_control(value["values"]), names=from_control(value["names"]))
    if kind == "index":
        result = pd.Index(from_control(value["values"]), dtype=value["dtype"], name=from_control(value["name"]))
        if value.get("freq") is not None:
            result.freq = value["freq"]
        return result
    if kind == "series":
        return pd.Series(from_control(value["values"]), index=from_control(value["index"]), name=from_control(value["name"]), dtype=value["dtype"])
    if kind == "frame":
        index, columns = from_control(value["index"]), from_control(value["columns"])
        data = [from_control(item) for item in value["series"]]
        result = pd.concat(data, axis=1) if data else pd.DataFrame(index=index)
        result.index, result.columns = index, columns
        return result
    raise TypeError(f"未知的类型标记: {kind}")


def dumps_control(value):
    """生成拒绝非有限 JSON 数字的 UTF-8 字节。"""
    return json.dumps(to_control(value), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def loads_control(value):
    """读取受限控制值。"""
    return from_control(json.loads(value))


def pack(value, max_bytes=256 * 1024 * 1024):
    """编码一个标准对象或对象列表，检查实际封装大小。"""
    import pyarrow as pa

    segments = []
    used = 0

    def encode(obj):
        nonlocal used
        if isinstance(obj, Panel):
            return {"kind": "panel", "axes": to_control([obj.items, obj.major_axis, obj.minor_axis]), "frames": [encode(obj.iloc[i]) for i in range(obj.shape[0])]}
        if isinstance(obj, pd.DataFrame):
            return {"kind": "frame", "index": to_control(obj.index), "columns": to_control(obj.columns), "series": [encode(obj.iloc[:, i]) for i in range(obj.shape[1])]}
        if isinstance(obj, pd.Series):
            tagged = obj.dtype == object
            if isinstance(obj.dtype, pd.CategoricalDtype):
                raise TypeError("暂不支持分类 dtype，请显式转换")
            values = [dumps_control(item) for item in obj.tolist()] if tagged else obj.array
            array = pa.array(values, type=pa.binary() if tagged else None, from_pandas=tagged)
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, pa.schema([("value", array.type)])) as writer:
                writer.write_batch(pa.record_batch([array], names=["value"]))
            data = sink.getvalue().to_pybytes()
            used += len(data)
            if used > max_bytes:
                raise ValueError("结果超过字节限制")
            idx = len(segments)
            segments.append(data)
            return {"kind": "series", "segment": idx, "tagged": tagged, "dtype": str(obj.dtype), "string_storage": obj.dtype.storage if isinstance(obj.dtype, pd.StringDtype) else None, "index": to_control(obj.index), "name": to_control(obj.name)}
        if isinstance(obj, list):
            return {"kind": "list", "values": [encode(item) for item in obj]}
        if isinstance(obj, dict):
            return {"kind": "mapping", "values": [[to_control(key), encode(item)] for key, item in obj.items()]}
        return {"kind": "control", "value": to_control(obj)}

    root = encode(value)
    manifest = json.dumps({"root": root, "segments": [{"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for data in segments]}, ensure_ascii=False, allow_nan=False).encode("utf-8")
    size = len(MAGIC) + 8 + len(manifest) + used
    if size > max_bytes:
        raise ValueError("结果超过字节限制")
    return MAGIC + struct.pack("!Q", len(manifest)) + manifest + b"".join(segments)


def unpack(data, max_bytes=256 * 1024 * 1024):
    """校验封装完整性后恢复标准对象。"""
    import pyarrow as pa

    if len(data) > max_bytes or not data.startswith(MAGIC) or len(data) < len(MAGIC) + 8:
        raise ValueError("数据封装无效或超过限制")
    offset = len(MAGIC) + 8
    size = struct.unpack("!Q", data[len(MAGIC):offset])[0]
    if size > len(data) - offset:
        raise ValueError("数据清单不完整")
    manifest = json.loads(data[offset:offset + size])
    offset += size
    segments = []
    for item in manifest["segments"]:
        if not isinstance(item["size"], int) or item["size"] < 0:
            raise ValueError("数据段长度无效")
        chunk = data[offset:offset + item["size"]]
        if len(chunk) != item["size"] or hashlib.sha256(chunk).hexdigest() != item["sha256"]:
            raise ValueError("数据段不完整或校验失败")
        segments.append(chunk)
        offset += item["size"]
    if offset != len(data):
        raise ValueError("数据封装包含多余内容")

    def decode(item):
        kind = item["kind"]
        if kind == "control":
            return from_control(item["value"])
        if kind == "list":
            return [decode(part) for part in item["values"]]
        if kind == "mapping":
            return {from_control(key): decode(part) for key, part in item["values"]}
        if kind == "series":
            values = pa.ipc.open_stream(io.BytesIO(segments[item["segment"]])).read_all().column(0)
            dtype = pd.StringDtype(storage=item["string_storage"]) if item.get("string_storage") else pd.api.types.pandas_dtype(item["dtype"])
            if not item["tagged"] and hasattr(dtype, "__from_arrow__"):
                array = dtype.__from_arrow__(values)
            else:
                values = [loads_control(part) for part in values.to_pylist()] if item["tagged"] else values.to_pandas()
                array = pd.array(values, dtype=dtype)
            return pd.Series(array, index=from_control(item["index"]), name=from_control(item["name"]))
        if kind == "frame":
            index, columns = from_control(item["index"]), from_control(item["columns"])
            columns_data = [decode(part) for part in item["series"]]
            result = pd.concat(columns_data, axis=1) if columns_data else pd.DataFrame(index=index)
            result.index, result.columns = index, columns
            return result
        if kind == "panel":
            axes = from_control(item["axes"])
            frames = [decode(part) for part in item["frames"]]
            if not axes[0].is_unique:
                raise ValueError("Panel 不支持重复因子轴")
            if not frames:
                return Panel(np.empty((0, len(axes[1]), len(axes[2]))), items=axes[0], major_axis=axes[1], minor_axis=axes[2])
            return Panel(dict(zip(axes[0], frames)), items=axes[0], major_axis=axes[1], minor_axis=axes[2])
        raise ValueError("未知标准对象")

    return decode(manifest["root"])
