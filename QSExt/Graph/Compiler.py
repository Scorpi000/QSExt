"""静态校验图文档，并将选定输出的依赖闭包编译为核心对象。"""
from dataclasses import dataclass, field
import re
from typing import Any

from pydantic import ValidationError

from QuantStudio.Core.Input import Binding, InputError
from QuantStudio.Core.Node import Node

from .Metadata import describe_fields
from .Protocol import (Collection, Diagnostic, GraphDocument, LiteralValue, Reference,
                       ResourceReference, TypeDescriptor)
from .Resources import ResourceCatalog


class GraphError(ValueError):
    """携带机器可读诊断的图校验或构造错误。"""

    def __init__(self, diagnostics):
        self.diagnostics = tuple(diagnostics)
        super().__init__("; ".join(item.message for item in diagnostics if item.severity == "error"))


@dataclass(frozen=True)
class SourceMapping:
    """一个画布出口到一个运行节点的映射，支持组合构造器。"""

    block_id: str
    port: str
    instance_id: str
    role: str


@dataclass
class Compilation:
    """编译结果；模板和算子可以导出，但不能作为引擎目标。"""

    outputs: dict[str, Any]
    diagnostics: tuple[Diagnostic, ...]
    resources: tuple
    source_map: tuple[SourceMapping, ...]
    objects: dict[str, Any] = field(repr=False)

    def execution_nodes(self):
        """获取执行根节点；混有模板或算子时明确拒绝。"""
        if any(not isinstance(value, Node) for value in self.outputs.values()):
            raise TypeError("执行输出必须全部为完整 Node")
        return list(self.outputs.values())

    def blocks_for_instance(self, instance_id):
        """将引擎事件定位到全部相关画布对象。"""
        return tuple(dict.fromkeys(item.block_id for item in self.source_map if item.instance_id == instance_id))


def _walk_references(value, path=(), member_id=None):
    if isinstance(value, Reference):
        yield value, path, member_id
    elif isinstance(value, Collection):
        for index, item in enumerate(value.items):
            if item.value is not None:
                yield from _walk_references(item.value, path + ("items", index, "value"), item.id)


def _document_snapshot(document):
    """重新验证编辑后的协议对象，同时隔离构造器对文档的修改。"""
    value = document.model_dump(mode="python", warnings=False) if isinstance(document, GraphDocument) else document
    return GraphDocument.model_validate(value)


def _target_names(document, targets):
    return list(document.outputs) if targets is None else [targets] if isinstance(targets, str) else list(targets)


@dataclass
class _View:
    definition: Any
    args_model: type
    inputs: list
    output: TypeDescriptor
    captured: dict = field(default_factory=dict)
    captured_args: dict = field(default_factory=dict)
    source_definition: Any = None


def _analyze(document, registry, targets, allow_partial):
    blocks = {block.id: block for block in document.blocks}
    diagnostics, order, active, visited, views = [], [], set(), set(), {}

    def report(code, message, block_id=None, path=(), member_id=None, severity="error"):
        diagnostics.append(Diagnostic(code=code, message=message, block_id=block_id,
                                      path=list(path), member_id=member_id, severity=severity))

    def visit(id_):
        if id_ in active:
            report("cycle", "构图依赖存在循环", id_)
            return
        if id_ in visited:
            return
        if id_ not in blocks:
            report("unknown_block", f"引用的画布对象不存在: {id_}")
            return
        active.add(id_)
        block = blocks[id_]
        for name, value in block.inputs.items():
            for reference, path, member in _walk_references(value, ("inputs", name)):
                if reference.block not in blocks:
                    report("unknown_block", f"引用的画布对象不存在: {reference.block}", id_, path, member)
                if reference.port != "result":
                    report("unknown_port", f"未声明的出口: {reference.port}", id_, path, member)
                visit(reference.block)
        active.remove(id_)
        visited.add(id_)
        order.append(id_)

    target_names = _target_names(document, targets)
    if targets is None:
        for id_ in blocks:
            visit(id_)
    for name in target_names:
        reference = document.outputs.get(name)
        if reference is None:
            report("unknown_output", f"图输出不存在: {name}", path=("outputs", name))
            continue
        if reference.port != "result":
            report("unknown_port", f"未声明的出口: {reference.port}", path=("outputs", name))
        visit(reference.block)

    def validate_value(value, expected, id_, path, complete, member=None):
        if isinstance(value, Reference):
            upstream = views.get(value.block)
            if upstream and not registry.types.accepts(expected, upstream.output):
                report("input_type", f"输入需要 {expected.kind}，上游输出为 {upstream.output.kind}", id_, path, member)
        elif isinstance(value, ResourceReference):
            if not registry.types.accepts(expected, TypeDescriptor(kind="resource", type_id="qs.resource")):
                report("input_type", "该槽位不接受资源描述", id_, path, member)
        elif isinstance(value, LiteralValue):
            actual = registry.types.describe(type(value.value))
            if isinstance(value.value, list):
                actual = TypeDescriptor(kind="array")
            if value.value is not None and (expected.kind == "factor" or
                    expected.kind == "union" and any(item.kind == "factor" for item in expected.alternatives)):
                return  # 因子算子支持核心层的常量归一化。
            if not registry.types.accepts(expected, actual):
                report("input_type", f"常量不符合 {expected.kind} 类型", id_, path, member)
            elif expected.choices and value.value not in expected.choices:
                report("literal_choice", "常量不在允许的取值中", id_, path, member)
        elif isinstance(value, Collection):
            array_type = expected if expected.kind == "array" else next((item for item in expected.alternatives if item.kind == "array"), None)
            if array_type is None:
                report("input_type", "该槽位不是集合输入", id_, path, member)
                return
            for index, item in enumerate(value.items):
                item_path = path + ("items", index, "value")
                if item.value is None:
                    report("unbound_member", "集合成员尚未绑定", id_, item_path, item.id,
                           "error" if complete else "warning")
                else:
                    validate_value(item.value, array_type.items or TypeDescriptor(), id_, item_path, complete, item.id)

    def validate_parameters(model, values, id_, prefix=("args",)):
        # 静态校验只消费声明，不能构造嵌套模型并触发默认工厂。
        for name, value in values.items():
            if name not in model.model_fields:
                if model.model_config.get("extra") != "allow":
                    report("unknown_arg", f"参数未声明: {name}", id_, prefix + (name,))
                continue
            model_field = model.model_fields[name]
            expected = registry.types.describe(model_field.annotation)
            actual = TypeDescriptor(kind="array") if isinstance(value, list) else registry.types.describe(type(value))
            if expected.kind == "model" and isinstance(value, dict):
                actual = TypeDescriptor(kind="model")
                validate_parameters(model_field.annotation, value, id_, prefix + (name,))
            if not registry.types.accepts(expected, actual):
                report("arg_type", f"参数不符合 {expected.kind} 类型", id_, prefix + (name,))
                continue
            if expected.choices and value not in expected.choices:
                report("literal_choice", "参数不在允许的取值中", id_, prefix + (name,))
            for metadata in model_field.metadata:
                checks = (("ge", lambda v: value >= v), ("gt", lambda v: value > v),
                          ("le", lambda v: value <= v), ("lt", lambda v: value < v),
                          ("min_length", lambda v: len(value) >= v), ("max_length", lambda v: len(value) <= v),
                          ("multiple_of", lambda v: value % v == 0),
                          ("pattern", lambda v: re.search(v, value) is not None))
                for key, check in checks:
                    limit = getattr(metadata, key, None)
                    if limit is not None:
                        try:
                            valid = check(limit)
                        except (TypeError, ValueError):
                            valid = False
                        if not valid:
                            report("arg_constraint", f"参数不满足 {key}={limit}", id_, prefix + (name,))

    for id_ in order:
        block = blocks[id_]
        try:
            definition = registry.get(block.definition)
        except KeyError:
            report("unknown_definition", f"定义或行为版本未注册: {block.definition.id}@{block.definition.version}", id_, ("definition",))
            continue
        if block.operation not in definition.operations:
            report("unsupported_operation", f"定义不支持操作: {block.operation}", id_, ("operation",))
        if block.result_args and block.operation != "apply":
            report("unexpected_result_args", "仅 apply 操作可以指定结果因子参数", id_, ("result_args",))
        try:
            output = definition.output_type(block.operation, block.args)
        except Exception as error:
            report("metadata_error", f"无法推断出口元信息: {error}", id_, ("args",))
            output = TypeDescriptor()
        view = _View(definition, definition.args_model, describe_fields(definition.input_model, registry.types),
                     output, source_definition=definition)
        anchor = "operator" if definition.kind == "operator_apply" else "template"
        if definition.kind in ("operator_apply", "template_apply"):
            reference = block.inputs.get(anchor)
            parent = views.get(reference.block) if isinstance(reference, Reference) else None
            expected_kind = "operator" if anchor == "operator" else "template"
            if parent and parent.output.kind == expected_kind:
                source = parent.source_definition
                view.source_definition = source
                view.captured = dict(parent.captured)
                view.inputs += [item.model_copy(deep=True) for item in parent.inputs if item.name not in ("operator", "template")]
                if anchor == "template":
                    view.args_model = parent.args_model
                    view.captured_args = dict(parent.captured_args)
                    if block.operation == "build":
                        view.output = source.output.model_copy(deep=True)
            elif parent is None and reference is not None:
                report("dynamic_inputs_unknown", "无法从上游配方确定输入声明", id_, ("inputs", anchor))
        views[id_] = view
        complete = not allow_partial and block.operation not in ("bind", "template")
        validate_parameters(view.args_model, block.args, id_)
        for name, model_field in view.args_model.model_fields.items():
            if model_field.is_required() and name not in block.args and name not in view.captured_args:
                report("unbound_arg", f"参数尚未指定: {name}", id_, ("args", name), severity="error" if complete else "warning")
        fields = {item.name: item for item in view.inputs}
        for name, value in block.inputs.items():
            info = fields.get(name)
            if info is None:
                report("unknown_input", f"输入未声明: {name}", id_, ("inputs", name))
                continue
            prior = view.captured.get(name)
            array = info.type.kind == "array" or any(item.kind == "array" for item in info.type.alternatives)
            if prior is not None and not array and block.operation == "apply":
                report("bound_input", "调用时不能覆盖已绑定的单值槽位，请先 unbind 或使用 bind 替换", id_, ("inputs", name))
            validate_value(value, info.type, id_, ("inputs", name), complete)
            if isinstance(value, Collection):
                count = sum(item.value is not None for item in value.items)
                if block.operation == "apply" and isinstance(prior, Collection):
                    count += sum(item.value is not None for item in prior.items)
                if info.min_length is not None and count < info.min_length:
                    report("collection_min", f"集合至少需要 {info.min_length} 个已绑定成员", id_, ("inputs", name), severity="error" if complete else "warning")
                if info.max_length is not None and count > info.max_length:
                    report("collection_max", f"集合最多允许 {info.max_length} 个成员", id_, ("inputs", name))
        for name, info in fields.items():
            if name in block.inputs or name in view.captured:
                continue
            if info.required:
                report("unbound_input", f"输入尚未指定: {name}", id_, ("inputs", name), severity="error" if complete else "warning")
        if block.operation in ("bind", "template"):
            view.captured.update({name: value for name, value in block.inputs.items() if name != anchor or definition.kind not in ("operator_apply", "template_apply")})
        if block.operation == "template":
            view.captured_args.update(block.args)
    return blocks, order, views, diagnostics, target_names


def validate_graph(document, registry, *, targets=None, allow_partial=True):
    """仅检查结构和声明，不调用构造器、默认工厂或资源解析器。

    Args:
        document: 图模型或可解析的字典。
        registry: 可信定义目录。
        targets: 选定输出名称；None 检查整个文档。
        allow_partial: 是否将缺失输入标为草稿警告。
    Returns:
        诊断元组；结构和类型错误即使在草稿中仍为 error。
    """
    document = _document_snapshot(document)
    return tuple(_analyze(document, registry, targets, allow_partial)[3])


def describe_block(document, block_id, registry):
    """获取实例槽位描述，静态展开上游模板或绑定算子的声明。"""
    document = _document_snapshot(document)
    _, _, views, diagnostics, _ = _analyze(document, registry, None, True)
    if block_id not in views:
        raise GraphError(diagnostics)
    from .Protocol import DefinitionDescriptor, DefinitionRef
    view = views[block_id]
    block = next(item for item in document.blocks if item.id == block_id)
    fields = [item.model_copy(deep=True) for item in view.inputs]
    for item in fields:
        item.bound = item.name in view.captured or item.name in block.inputs
    return DefinitionDescriptor(definition=DefinitionRef(id=view.definition.id, version=view.definition.version),
        title=view.definition.title, description=view.definition.description, operations=list(view.definition.operations),
        args=describe_fields(view.args_model, registry.types, view.captured_args | block.args), inputs=fields,
        outputs={"result": view.output}, dynamic_inputs=view.definition.kind in ("operator_apply", "template_apply"))


def compile_graph(document, registry, *, targets=None, resources=None):
    """只构造目标依赖闭包，不执行计算、不解析资源句柄。

    Args:
        document: 图模型或 JSON 字典。
        registry: 可信代码定义目录。
        targets: 输出名称；None 编译所有声明输出。
        resources: 仅保存资源语义描述的内存目录。
    Returns:
        包含核心对象、诊断、资源需求和来源映射的 Compilation。
    Raises:
        GraphError: 结构、输入或构造验证失败。
    """
    document = _document_snapshot(document)
    target_names = _target_names(document, targets)
    blocks, order, views, diagnostics, _ = _analyze(document, registry, target_names, False)
    if any(item.severity == "error" for item in diagnostics):
        raise GraphError(diagnostics)
    resources = resources or ResourceCatalog()
    objects, used_resources, source_map = {}, {}, []

    def resolve(value, id_, path, member=None):
        if isinstance(value, Reference):
            return objects[value.block]
        if isinstance(value, LiteralValue):
            return value.value
        if isinstance(value, Collection):
            return tuple(resolve(item.value, id_, path + ("items", index, "value"), item.id)
                         for index, item in enumerate(value.items) if item.value is not None)
        if isinstance(value, ResourceReference):
            try:
                resource = resources.describe(value.id)
            except KeyError as error:
                raise GraphError([Diagnostic(code="unknown_resource", message=f"资源未登记: {value.id}",
                    block_id=id_, path=list(path), member_id=member)]) from error
            used_resources[resource.id] = resource
            return resource
        raise TypeError("未声明的绑定值")

    def map_nodes(id_, node, role, seen):
        if node.InstanceID in seen:
            return
        seen.add(node.InstanceID)
        source_map.append(SourceMapping(id_, "result", node.InstanceID, role))
        for edge in node.iter_dependency_edges():
            map_nodes(id_, edge.node, "dependency", seen)

    for id_ in order:
        block, view = blocks[id_], views[id_]
        try:
            error_scope = "inputs"
            inputs = {name: resolve(value, id_, ("inputs", name)) for name, value in block.inputs.items()}
            # 通用算子/模板应用的完整字段由核心对象自行验证。
            if view.definition.kind not in ("operator", "operator_apply", "node", "template_apply"):
                inputs_model = view.definition.input_model(**inputs)
                inputs = {name: getattr(inputs_model, name) for name in type(inputs_model).model_fields}
            args = dict(block.args)
            error_scope = "args"
            if view.definition.kind == "factory" and block.operation not in ("bind", "template"):
                args_model = view.args_model(**args)
                args = {name: getattr(args_model, name) for name in type(args_model).model_fields}
            error_scope = "construction"
            result = view.definition.builder(block, args, inputs)
            expected = view.output
            if not registry.types.accepts_value(expected, result):
                raise TypeError(f"构造器出口不符合声明: {expected.kind}")
            objects[id_] = result
            if isinstance(result, Node):
                map_nodes(id_, result, "result", set())
        except GraphError:
            raise
        except (InputError, ValidationError) as error:
            errors = error.diagnostics if isinstance(error, InputError) else Binding._errors(error)
            for item in errors:
                path = list(item["path"])
                member = None
                if error_scope == "construction" and path:
                    error_scope = "inputs" if path[0] in {info.name for info in view.inputs} else "args" if path[0] in view.args_model.model_fields else "construction"
                if error_scope == "inputs" and len(path) > 1 and isinstance(path[1], int):
                    binding = block.inputs.get(path[0])
                    if isinstance(binding, Collection):
                        members = [value for value in binding.items if value.value is not None]
                        if path[1] < len(members):
                            member = members[path[1]].id
                diagnostics.append(Diagnostic(code=item["code"], message=f"输入验证失败: {item['message']}",
                    block_id=id_, path=[error_scope] + path, member_id=member))
            raise GraphError(diagnostics) from error
        except Exception as error:
            diagnostics.append(Diagnostic(code="construction_error", message=str(error), block_id=id_))
            raise GraphError(diagnostics) from error
    return Compilation({name: objects[document.outputs[name].block] for name in target_names}, tuple(diagnostics),
                       tuple(used_resources.values()), tuple(source_map), objects)
