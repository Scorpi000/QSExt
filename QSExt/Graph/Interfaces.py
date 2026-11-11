"""计算图公开参数与有类型的因子输入；静态解析后仍为普通计算图。"""
from copy import deepcopy
from typing import Any

from pydantic import Field, ValidationError, model_validator

from QuantStudio.Core.Input import InputModel
from QuantStudio.Factor.Factor import DataFactor, Factor
from .Protocol import Diagnostic, FieldDescriptor, GraphDocument, JsonValue, ProtocolModel
from .Subgraphs import ParameterEndpoint, parameter_fields, references, set_parameter

FACTOR_INPUT_ID = "qs.input.factor"


class GraphParameter(ProtocolModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=4000)
    group: str = Field(default="参数", max_length=200)
    order: int = 0
    value: JsonValue
    targets: list[ParameterEndpoint] = Field(min_length=1, max_length=500)


class GraphInterface(ProtocolModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=4000)
    parameters: list[GraphParameter] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def unique_parameters(self):
        for key in ("id", "name"):
            values = [getattr(parameter, key) for parameter in self.parameters]
            if len(values) != len(set(values)):
                raise ValueError(f"图参数的 {key} 不能重复")
        return self


class FactorInputArgs(InputModel):
    name: str = Field(default="factor_input", min_length=1, title="输入名称")
    title: str = Field(default="因子输入", title="显示标题")
    description: str = Field(default="", title="说明")
    group: str = Field(default="输入", title="面板分组")
    order: int = Field(default=0, title="显示顺序")
    required: bool = Field(default=True, title="必填")
    default_value: Any = Field(default=None, title="可选输入的默认常量")


class FactorInputBindings(InputModel):
    value: Factor | None = Field(default=None, title="输入因子")


def build_factor_input(block, args, inputs):
    """绑定到已有因子，或为可选输入构造默认常量因子。"""
    if inputs["value"] is not None:
        return inputs["value"]
    if args["required"]:
        raise ValueError(f"请绑定图输入：{args['title'] or args['name']}")
    value = args["default_value"]
    data_type = "double" if isinstance(value, (int, float)) else "string" if isinstance(value, str) else "object"
    return DataFactor(value, args={"Name": args["name"], "DataType": data_type})


def factor_input_component():
    from .Components import Component
    return Component(id=FACTOR_INPUT_ID, title="因子输入占位", args_model=FactorInputArgs,
        input_model=FactorInputBindings, output_type=Factor, builder=build_factor_input)


def graph_interface(document):
    raw = document.extensions.get("interface")
    return GraphInterface.model_validate(raw) if raw is not None else GraphInterface()


def target_key(target):
    return target.block, target.location, tuple(target.path)


def _needed(document, targets):
    blocks = {block.id: block for block in document.blocks}
    if targets is None:
        return set(blocks)
    needed = set()
    def visit(id_):
        if id_ in needed or id_ not in blocks:
            return
        needed.add(id_)
        for binding in blocks[id_].inputs.values():
            for reference in references(binding):
                visit(reference.block)
    for name in [targets] if isinstance(targets, str) else targets:
        if name in document.outputs:
            visit(document.outputs[name].block)
    return needed


def interface_candidates(document, registry):
    """沿用子图的字段描述与参数地址，包含尚未填写的声明字段。"""
    from .Compiler import _analyze
    from .Metadata import describe_fields
    _, _, views, _, _ = _analyze(document, registry, None, True)
    candidates = []
    for block in document.blocks:
        if block.id not in views:
            continue
        view = views[block.id]
        descriptor = registry.describe_definition(block.definition.id, block.definition.version).model_copy(update={
            "args": describe_fields(view.args_model, registry.types, view.captured_args | block.args)})
        candidates.extend(parameter_fields(block, descriptor, registry, include_missing=True))
    return candidates


def _type_group(type_):
    if type_.kind in ("integer", "number"):
        return "number"
    if type_.kind == "union":
        groups = sorted(set(str(_type_group(item)) for item in type_.alternatives if item.kind != "null"))
        return groups[0] if len(groups) == 1 else tuple(groups)
    return type_.kind


def resolve_graph_interface(document, registry, *, targets=None, allow_partial=True, input_origins=None):
    """将公开参数写入独立构图副本；所保存文档中的参数值保持不变。"""
    prepared = GraphDocument.model_validate(document).model_copy(deep=True)
    diagnostics = []
    try:
        interface = graph_interface(prepared)
    except (ValueError, TypeError) as error:
        diagnostics.append(Diagnostic(code="invalid_graph_interface", message=f"计算图接口定义无效：{error}",
            path=["extensions", "interface"]))
        prepared.extensions.pop("interface", None)
        return prepared, diagnostics
    prepared.extensions.pop("interface", None)
    blocks = {block.id: block for block in prepared.blocks}
    needed = _needed(prepared, targets)
    candidates = {target_key(item.target): item for item in interface_candidates(prepared, registry)} if interface.parameters else {}
    occupied = []
    for parameter in interface.parameters:
        fields = []
        for index, target in enumerate(parameter.targets):
            if targets is not None and target.block not in needed:
                continue
            key = target_key(target)
            candidate = candidates.get(key)
            path = ["extensions", "interface", "parameters", parameter.id, "targets", index]
            if candidate is None:
                diagnostics.append(Diagnostic(code="invalid_graph_parameter_target", block_id=target.block,
                    message=f"图参数“{parameter.title or parameter.name}”的字段不存在或不可公开", path=path))
                continue
            if any(key[:2] == previous[:2] and
                   (key[2][:len(previous[2])] == previous[2] or previous[2][:len(key[2])] == key[2])
                   for previous in occupied):
                diagnostics.append(Diagnostic(code="duplicate_graph_parameter_target", block_id=target.block,
                    message="同一字段及其父子字段只能绑定一个图参数", path=path))
                continue
            occupied.append(key)
            fields.append(candidate.field)
            set_parameter(blocks[target.block], target, deepcopy(parameter.value))
        groups = {_type_group(info.type) for info in fields if info.type.kind != "unknown"}
        if len(groups) > 1:
            diagnostics.append(Diagnostic(code="incompatible_graph_parameter_targets",
                message=f"图参数“{parameter.title or parameter.name}”绑定的字段类型不兼容",
                path=["extensions", "interface", "parameters", parameter.id]))
    names = set()
    for block in prepared.blocks:
        if block.id not in needed or block.definition.id != FACTOR_INPUT_ID:
            continue
        try:
            args = FactorInputArgs.model_validate(block.args)
        except ValidationError:
            continue  # 普通参数校验返回完整字段诊断。
        owner, path = (input_origins or {}).get(block.id, (None, ()))
        scoped_name = (owner, tuple(path[:-1]), args.name)
        if scoped_name in names:
            diagnostics.append(Diagnostic(code="duplicate_graph_input_name", block_id=block.id,
                message=f"图输入名称重复：{args.name}", path=["args", "name"]))
        names.add(scoped_name)
        binding = block.inputs.get("value")
        if args.required and (binding is None or getattr(binding, "kind", None) == "literal" and binding.value is None):
            diagnostics.append(Diagnostic(code="unbound_graph_input", block_id=block.id,
                severity="warning" if allow_partial else "error", message=f"请绑定图输入：{args.title or args.name}",
                path=["inputs", "value"]))
    return prepared, diagnostics


def describe_graph_interface(document, registry):
    """返回通用面板需要的输入、字段映射及当前值；不运行构造器。"""
    document = GraphDocument.model_validate(document)
    prepared, diagnostics = resolve_graph_interface(document, registry)
    try:
        interface = graph_interface(document)
    except (ValueError, TypeError):
        interface = GraphInterface()
    candidates = interface_candidates(prepared, registry)
    by_target = {target_key(item.target): item for item in candidates}
    parameters = []
    for parameter in interface.parameters:
        fields = [by_target[target_key(target)].field for target in parameter.targets if target_key(target) in by_target]
        if fields:
            field = fields[0].model_copy(update={"name": parameter.name, "title": parameter.title or parameter.name,
                "description": parameter.description, "default": parameter.value, "default_available": True})
            parameters.append({"parameter": parameter, "field": field, "fields": fields})
    inputs = []
    for block in prepared.blocks:
        if block.definition.id != FACTOR_INPUT_ID:
            continue
        try:
            args = FactorInputArgs.model_validate(block.args)
        except ValidationError:
            continue
        inputs.append({"block": block.id, **args.model_dump(mode="json"),
            "bound": "value" in block.inputs and getattr(block.inputs["value"], "kind", None) != "literal"})
    return interface, inputs, parameters, candidates, diagnostics
