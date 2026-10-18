"""将 Python 声明显式转换为传输元信息，不调用业务构造器。"""
from types import UnionType
import datetime as dt
from enum import Enum
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, TypeAdapter, JsonValue
from pydantic_core import PydanticUndefined

from QuantStudio.Core.Node import Node
from QuantStudio.Core.NodeTemplate import NodeTemplate
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import FactorOperator
from .Protocol import FieldDescriptor, ResourceDescriptor, TypeDescriptor


def json_value(value):
    """验证实际 JSON 值，不把任意 Python 对象转成字符串。"""
    return TypeAdapter(JsonValue, config=ConfigDict(allow_inf_nan=False)).validate_python(value)


class TypeRegistry:
    """将本地类型映射到稳定类型 ID，并保留本地继承检查。"""

    def __init__(self):
        self._types = {"qs.node": Node, "qs.factor": Factor, "qs.operator": FactorOperator,
                       "qs.template": NodeTemplate, "qs.resource": ResourceDescriptor}

    def register(self, type_id, python_type):
        """登记自定义类型，禁止一个 ID 对应不同类型。"""
        if type_id in self._types and self._types[type_id] is not python_type:
            raise ValueError(f"类型 ID 已注册: {type_id}")
        self._types[type_id] = python_type

    def describe(self, annotation):
        """转换声明；不能传输的 Python 类型会被明确标记。"""
        origin, args = get_origin(annotation), get_args(annotation)
        if origin is Annotated:
            return self.describe(args[0])
        if annotation is Any:
            return TypeDescriptor()
        if annotation in (None, type(None)):
            return TypeDescriptor(kind="null")
        if origin in (Union, UnionType):
            alternatives = [self.describe(item) for item in args]
            return TypeDescriptor(kind="union", alternatives=alternatives, persistable=all(item.persistable for item in alternatives))
        if origin is Literal:
            result = self.describe(type(args[0]))
            result.choices = [json_value(item) for item in args]
            return result
        if origin in (tuple, list, set):
            items = self.describe(args[0]) if args else TypeDescriptor()
            return TypeDescriptor(kind="array", items=items, persistable=items.persistable)
        if origin is dict or annotation is dict:
            items = self.describe(args[1]) if args else TypeDescriptor()
            return TypeDescriptor(kind="mapping", items=items, persistable=items.persistable)
        for python_type, kind in ((bool, "boolean"), (int, "integer"), (float, "number"), (str, "string")):
            if annotation is python_type:
                return TypeDescriptor(kind=kind)
        if isinstance(annotation, type):
            for python_type, format_ in ((dt.datetime, "date-time"), (dt.date, "date"), (dt.time, "time")):
                if annotation is python_type:
                    return TypeDescriptor(kind="string", format=format_)
            if issubclass(annotation, Enum):
                values = [json_value(item.value) for item in annotation]
                descriptor = self.describe(type(values[0])) if values else TypeDescriptor()
                descriptor.choices = values
                return descriptor
            exact = next((key for key, value in self._types.items() if value is annotation), None)
            for base, kind in ((Factor, "factor"), (Node, "node"), (FactorOperator, "operator"),
                               (NodeTemplate, "template"), (ResourceDescriptor, "resource")):
                if issubclass(annotation, base):
                    return TypeDescriptor(kind=kind, type_id=exact or f"{annotation.__module__}.{annotation.__qualname__}")
            if issubclass(annotation, BaseModel):
                fields = {name: self.describe(field.annotation) for name, field in annotation.model_fields.items()}
                return TypeDescriptor(kind="model", fields=fields, members=describe_fields(annotation, self),
                                      persistable=all(item.persistable for item in fields.values()))
        return TypeDescriptor(kind="python", type_id=getattr(annotation, "__qualname__", str(annotation)), persistable=False)

    def accepts(self, expected, actual):
        """检查可推断的类型，unknown 留给完整构造时校验。"""
        if "unknown" in (expected.kind, actual.kind):
            return True
        if expected.kind == "union":
            return any(self.accepts(item, actual) for item in expected.alternatives)
        if actual.kind == "union":
            return all(self.accepts(expected, item) for item in actual.alternatives)
        if expected.kind == "node" and actual.kind == "factor":
            if expected.type_id in (None, "qs.node"):
                return True
        if expected.kind != actual.kind:
            return expected.kind == "number" and actual.kind == "integer"
        if expected.type_id and actual.type_id:
            expected_class, actual_class = self._types.get(expected.type_id), self._types.get(actual.type_id)
            if expected_class and actual_class:
                return issubclass(actual_class, expected_class)
            return expected.type_id == actual.type_id
        if expected.kind == "array" and expected.items and actual.items:
            return self.accepts(expected.items, actual.items)
        return True

    def accepts_value(self, expected, value):
        """对实际构造结果检查核心类别及已注册的具体子类。"""
        if expected.kind == "unknown":
            return True
        expected_class = self._types.get(expected.type_id)
        if expected_class:
            return isinstance(value, expected_class)
        for kind, python_type in (("factor", Factor), ("node", Node), ("operator", FactorOperator),
                                  ("template", NodeTemplate), ("resource", ResourceDescriptor)):
            if expected.kind == kind:
                return isinstance(value, python_type)
        return self.accepts(expected, self.describe(type(value)))


def describe_fields(model, types=None, values=None):
    """提取模型字段，不执行默认工厂或模型实例化。

    Args:
        model: Pydantic 模型类。
        types: 本地类型目录。
        values: 需要标记为已绑定的字段值。
    Returns:
        按模型声明顺序组织的传输字段列表。
    """
    types, values = types or TypeRegistry(), values or {}
    snapshot = getattr(model, "__graph_snapshot_fields__", None)
    if snapshot is not None:
        return [field.model_copy(deep=True, update={"bound": field.name in values}) for field in snapshot]
    result = []
    for name, field in model.model_fields.items():
        default, available = None, False
        if field.default is not PydanticUndefined:
            try:
                default, available = json_value(field.default), True
            except ValueError:
                pass
        constraints = {}
        for metadata in field.metadata:
            for key in ("gt", "ge", "lt", "le", "multiple_of", "pattern"):
                value = getattr(metadata, key, None)
                if value is not None:
                    constraints[key] = json_value(value)
        result.append(FieldDescriptor(name=name, title=field.title or name, description=field.description or "",
            type=types.describe(field.annotation), required=field.is_required(), has_default=not field.is_required(),
            default=default, default_available=available, default_factory=field.default_factory is not None,
            min_length=next((m.min_length for m in field.metadata if hasattr(m, "min_length")), None),
            max_length=next((m.max_length for m in field.metadata if hasattr(m, "max_length")), None),
            constraints=constraints, bound=name in values))
    return result
