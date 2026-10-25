"""私有算子的元信息快照；目录查询不反序列化或执行 Python。"""
from copy import deepcopy
from datetime import date, datetime, time
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, create_model

from QuantStudio.Core.Input import InputModel
from QuantStudio.Core.Node import Node
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import FactorOperator
from QuantStudio.Tools.DataTypeFun import serialize_value

from .Definitions import Definition
from .Import import _json, DefinitionImportError
from .Metadata import describe_fields
from .Protocol import FieldDescriptor, TypeDescriptor


def portable_operator_args(operator):
    """JSON 参数仍可编辑，函数等 Python 值保留在不可变算子快照中。"""
    def fields(model):
        return {name: getattr(model, name) for name in type(model).model_fields} | (model.__pydantic_extra__ or {})
    result = {}
    for name, value in fields(operator.Args).items():
        if name == "ModelArgs" and isinstance(value, (dict, BaseModel)):
            result[name] = {}
            for key, item in (fields(value) if isinstance(value, BaseModel) else value).items():
                try:
                    result[name][key] = _json(item, f"args.ModelArgs.{key}")
                except DefinitionImportError:
                    pass
        else:
            try:
                result[name] = _json(value, f"args.{name}")
            except DefinitionImportError:
                pass
    return result


def operator_snapshot(operator, registry, files, owner):
    """捕获实际构图算子，而非只保存通用 Point/TimeOperator 的类名。"""
    args = portable_operator_args(operator)
    def plain(value):
        if isinstance(value, BaseModel):
            return {name: plain(getattr(value, name)) for name in type(value).model_fields} | {
                key: plain(item) for key, item in (value.__pydantic_extra__ or {}).items()}
        if isinstance(value, dict):
            return {key: plain(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [plain(item) for item in value]
        return value
    calculate_module = getattr(operator.calculate, "__module__", "")
    calculate_name = getattr(operator.calculate, "__qualname__", type(operator.calculate).__qualname__)
    namespace = next((name.split(".")[0] for name in (type(operator).__module__, calculate_module)
                      if name.startswith("_qs_def_import_")), None)
    source = None
    if namespace:
        for module_name in (type(operator).__module__, calculate_module):
            filename = str(getattr(sys.modules.get(module_name), "__file__", ""))
            if filename.startswith(namespace + "/"):
                source = filename[len(namespace) + 1:]
                break
    descriptor_inputs = describe_fields(operator.InputClass, registry.types)
    identity = {"files": files, "class": f"{type(operator).__module__}.{type(operator).__qualname__}",
                "args": plain(operator.Args), "calculate": operator.calculate,
                "inputs": [item.model_dump(mode="json") for item in descriptor_inputs], "call_layout": operator._CallLayout,
                "calculate_name": f"{calculate_module}.{calculate_name}"}
    canonical = json.dumps(serialize_value(identity), sort_keys=True, ensure_ascii=False)
    if namespace:
        canonical = canonical.replace(namespace, "uploaded_definition")
    key = hashlib.sha256(canonical.encode()).hexdigest()
    descriptor_args = describe_fields(type(operator.Args), registry.types)
    for item in descriptor_args:
        if item.name in args:
            item.default = deepcopy(args[item.name])
            item.default_available = item.has_default = True
            item.default_factory = item.required = False
        elif not item.type.persistable:
            item.required = False
            item.has_default = True
    def model_options(model):
        return {"extra": model.model_config.get("extra", "forbid"), "fields": {
            name: model_options(field.annotation) for name, field in model.model_fields.items()
            if isinstance(field.annotation, type) and issubclass(field.annotation, BaseModel)}}
    serialized = operator.serialize()
    try:
        FactorOperator.deserialize(serialized)
    except Exception as error:
        raise DefinitionImportError(f"自定义算子 {operator.Name} 无法保存为可还原快照: {error}") from error
    snapshot = {"id": f"user.{owner}.operator.{key}", "version": 1, "key": key,
        "title": operator.Args.Name, "description": type(operator).__doc__ or "",
        "namespace": namespace, "source": source, "args": [item.model_dump(mode="json") for item in descriptor_args],
        "inputs": [item.model_dump(mode="json") for item in descriptor_inputs],
        "model_options": model_options(type(operator.Args)), "operator": serialized}
    return snapshot, args


def _snapshot_model(name, fields, options=None):
    """从 JSON 声明恢复编辑校验用模型，不导入用户模块。"""
    model_options = options or {}
    def annotation(info, nested_options=None):
        primitive = {"boolean": bool, "integer": int, "number": float, "string": str, "null": type(None),
                     "factor": Factor, "node": Node, "operator": FactorOperator}
        if info.choices:
            return Literal[tuple(info.choices)]
        if info.format in ("date-time", "date", "time"):
            return {"date-time": datetime, "date": date, "time": time}[info.format]
        if info.kind == "array":
            return tuple[annotation(info.items or TypeDescriptor()), ...]
        if info.kind == "mapping":
            return dict[str, annotation(info.items or TypeDescriptor())]
        if info.kind == "union":
            return Union[tuple(annotation(item) for item in info.alternatives)]
        if info.kind == "model":
            return _snapshot_model(name + "Nested", info.members, nested_options)
        return primitive.get(info.kind, Any)
    parameters = {}
    for item in fields:
        default = ... if item.required else deepcopy(item.default) if item.default_available else None
        field_options = {"title": item.title, "description": item.description, **item.constraints}
        if not item.type.persistable and item.type.kind != "model":
            field_options["json_schema_extra"] = {"readOnly": True}
        for key in ("min_length", "max_length"):
            if getattr(item, key) is not None:
                field_options[key] = getattr(item, key)
        parameters[item.name] = (annotation(item.type, model_options.get("fields", {}).get(item.name)), Field(default=default, **field_options))
    model = create_model(name, __base__=InputModel,
                         __config__=ConfigDict(extra=model_options.get("extra", "forbid")), **parameters)
    model.__graph_snapshot_fields__ = tuple(fields)
    return model


def register_operator_snapshot(registry, snapshot, directory):
    """登记仅含声明的私有组件；builder 只在明确构图执行时恢复算子。"""
    directory = Path(directory)
    args = [FieldDescriptor.model_validate(item) for item in snapshot["args"]]
    inputs = [FieldDescriptor.model_validate(item) for item in snapshot["inputs"]]
    args_model = _snapshot_model("PrivateOperatorArgs", args, snapshot.get("model_options"))
    input_model = _snapshot_model("PrivateOperatorInputs", inputs)

    def builder(block, values, dependencies):
        from .Workbench import get_construction_context
        namespace = snapshot["namespace"]
        if namespace and namespace not in sys.modules:
            runtime = get_construction_context()
            module_directory = Path(runtime.module_directory) if runtime and runtime.module_directory else directory
            if module_directory != directory:
                shutil.copytree(directory / namespace, module_directory / namespace, dirs_exist_ok=True)
            if str(module_directory) not in sys.path:
                sys.path.insert(0, str(module_directory))
            # 先载入源码中的类和模型，再恢复由框架生成的可信序列化快照。
            importlib.import_module(namespace)
        operator = FactorOperator.deserialize(snapshot["operator"]).new(args=values)
        return operator.bind(**dependencies) if block.operation == "bind" else operator(**dependencies, factor_args=block.result_args)

    definition = registry.register(Definition(snapshot["id"], snapshot["version"], snapshot["title"], snapshot["description"],
        "operator", args_model, input_model, TypeDescriptor(kind="factor", type_id="qs.factor"), builder,
        ("apply", "bind"), category="自动导入算子"))
    relative = f"{snapshot['namespace']}/{snapshot['source']}" if snapshot.get("source") else "manifest.json"
    path = f"_auto_operators/{directory.name}/{relative}"
    registry.locations[(definition.id, definition.version)] = path
    registry.source_categories[path] = Path(snapshot["source"]).stem if snapshot.get("source") else snapshot["title"]
    registry.directory_categories["_auto_operators"] = "自动导入组件"
    return definition
