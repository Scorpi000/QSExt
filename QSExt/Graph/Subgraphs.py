"""可持久化的单出口子图组件；只做静态提取、映射和展开。"""
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Literal

from pydantic import Field

from .Definitions import Definition
from .Metadata import describe_fields
from .Protocol import (Collection, FieldDescriptor, GraphDocument, JsonValue, ProtocolModel,
                       Reference, ResourceReference)


class InputEndpoint(ProtocolModel):
    block: str = Field(min_length=1)
    field: str = Field(min_length=1)
    members: list[str] = Field(default_factory=list)


class ParameterEndpoint(ProtocolModel):
    block: str = Field(min_length=1)
    location: Literal["args", "result_args"] = "args"
    path: list[str] = Field(min_length=1)


class SubgraphInput(ProtocolModel):
    field: FieldDescriptor
    target: InputEndpoint


class SubgraphParameter(ProtocolModel):
    field: FieldDescriptor
    target: ParameterEndpoint


class SubgraphRecipe(ProtocolModel):
    schema_version: Literal[1] = 1
    document: GraphDocument
    inputs: list[SubgraphInput] = Field(default_factory=list)
    parameters: list[SubgraphParameter] = Field(default_factory=list)
    dependencies: list[dict[str, JsonValue]] = Field(default_factory=list)

    @property
    def digest(self):
        value = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


def references(value):
    if isinstance(value, Reference):
        yield value
    elif isinstance(value, Collection):
        for item in value.items:
            yield from references(item.value)


def set_input(block, target, value=None):
    if not target.members:
        if value is None:
            block.inputs.pop(target.field, None)
        else:
            block.inputs[target.field] = deepcopy(value)
        return
    collection = block.inputs.get(target.field)
    for index, member_id in enumerate(target.members):
        if not isinstance(collection, Collection):
            raise ValueError("子图输入映射的集合不存在")
        member = next((item for item in collection.items if item.id == member_id), None)
        if member is None:
            raise ValueError("子图输入映射的成员不存在")
        if index == len(target.members) - 1:
            member.value = deepcopy(value)
        else:
            collection = member.value


def set_parameter(block, target, value):
    current = getattr(block, target.location)
    for key in target.path[:-1]:
        current = current.setdefault(key, {})
        if not isinstance(current, dict):
            raise ValueError("子图参数映射的父级必须是对象")
    current[target.path[-1]] = deepcopy(value)


def parameter_fields(block, descriptor, registry):
    """列出可公开的声明字段，模型字段递归，数组和映射作为整体。"""
    from QuantStudio.Factor.Factor import Factor
    groups = [("args", descriptor.args, block.args)]
    if block.operation == "apply":
        groups.append(("result_args", describe_fields(Factor.__QS_ArgClass__, registry.types), block.result_args))

    def walk(location, fields, values, path=()):
        for info in fields:
            keys = (*path, info.name)
            present = info.name in values
            value = values.get(info.name, info.default)
            if info.type.kind == "model" and isinstance(value, dict):
                yield from walk(location, info.type.members, value, keys)
            elif info.type.persistable and (present or info.default_available):
                name = block.id + "." + location + "." + ".".join(keys)
                metadata = info.model_copy(deep=True, update={"name": name, "title": name,
                    "default": deepcopy(value), "default_available": True, "has_default": True,
                    "required": False, "default_factory": False, "bound": False})
                yield SubgraphParameter(field=metadata,
                    target=ParameterEndpoint(block=block.id, location=location, path=list(keys)))
    for location, fields, values in groups:
        yield from walk(location, fields, values)


def extract_subgraph(document, selected, registry, *, output=None, parameters=(), input_names=None):
    """提取选区；只支持完整 Node/Factor 的一个出口，不自动捕获外部节点。"""
    from .Compiler import GraphError, describe_block, validate_graph
    document = GraphDocument.model_validate(document).model_copy(deep=True)
    selected = set(selected)
    blocks = {block.id: block for block in document.blocks}
    if not selected or selected - blocks.keys():
        raise ValueError("请选择存在的节点构成子图")
    # 面向选区描述接口；无关的未完成节点不影响提取。
    descriptors = {id_: describe_block(document, id_, registry) for id_ in selected}
    required_outputs = {ref.block for id_, block in blocks.items() if id_ not in selected
                        for value in block.inputs.values() for ref in references(value) if ref.block in selected}
    required_outputs.update(ref.block for ref in document.outputs.values() if ref.block in selected)
    consumed = {ref.block for id_ in selected for value in blocks[id_].inputs.values()
                for ref in references(value) if ref.block in selected}
    candidates = required_outputs or (selected - consumed)
    if len(required_outputs) > 1:
        raise ValueError("首版子图组件只支持一个输出；选区有多个对外出口，请调整选区")
    output = output or (next(iter(candidates)) if len(candidates) == 1 else None)
    if output not in selected or required_outputs - {output}:
        raise ValueError("请选择一个输出节点，并保留选区现有的对外出口")
    if descriptors[output].outputs["result"].kind not in ("node", "factor"):
        raise ValueError("子图出口必须是完整节点或因子，请先应用算子或构造模板")
    reachable = set()

    def visit(id_):
        if id_ in reachable:
            return
        reachable.add(id_)
        for value in blocks[id_].inputs.values():
            for ref in references(value):
                if ref.block in selected:
                    visit(ref.block)
    visit(output)
    if reachable != selected:
        raise ValueError("选区包含不通向所选输出的节点，请调整选区或输出")
    original = document.model_copy(deep=True)
    document.blocks = [block for block in document.blocks if block.id in selected]
    document.outputs = {"result": Reference(block=output)}
    layout = original.extensions.get("qsweb", {}).get("layout", {})
    positions = {id_: deepcopy(pos) for id_, pos in layout.get("positions", {}).items() if id_ in selected}
    if positions:
        left, top = min(pos["x"] for pos in positions.values()), min(pos["y"] for pos in positions.values())
        positions = {id_: {"x": pos["x"] - left, "y": pos["y"] - top} for id_, pos in positions.items()}
    document.extensions = {"qsweb": {"layout": {"positions": positions, "collapsed": []}}}
    inputs, available, bindings, dependencies = [], [], {}, []
    used_names = set()

    def expose(block, info, members, value):
        base = info.name if not members else info.name + "_" + str(len(inputs) + 1)
        name = base
        suffix = 2
        while name in used_names:
            name = f"{base}_{suffix}"
            suffix += 1
        used_names.add(name)
        metadata = info.model_copy(deep=True, update={"name": name, "title": name, "bound": False,
            "required": True, "has_default": False, "default_available": False, "default_factory": False, "default": None})
        target = InputEndpoint(block=block.id, field=info.name, members=members)
        inputs.append(SubgraphInput(field=metadata, target=target))
        if value is not None:
            bindings[name] = deepcopy(value)
        set_input(block, target)

    def walk(block, info, value, members=()):
        if value is None and block.operation in ("bind", "template"):
            return
        if isinstance(value, Collection):
            array = info.type if info.type.kind == "array" else next(
                (item for item in info.type.alternatives if item.kind == "array"), None)
            if array is None:
                raise ValueError("集合输入不符合节点声明")
            for member in value.items:
                nested = info.model_copy(deep=True, update={"type": array.items or info.type})
                walk(block, nested, member.value, (*members, member.id))
        elif isinstance(value, ResourceReference) or isinstance(value, Reference) and value.block not in selected or value is None:
            expose(block, info, list(members), value)

    for block in document.blocks:
        definition = registry.get(block.definition)
        descriptor = descriptors[block.id]
        if definition.kind in ("operator_apply", "template_apply"):
            anchor = "operator" if definition.kind == "operator_apply" else "template"
            ref = block.inputs.get(anchor)
            if not isinstance(ref, Reference) or ref.block not in selected:
                raise ValueError("应用已有算子或模板时，请将其定义节点一并纳入选区")
        block.args = deepcopy(definition.default_args) | block.args
        if block.operation == "apply":
            block.result_args = deepcopy(definition.default_result_args) | block.result_args
        defaults = deepcopy(definition.default_extensions.get("qsweb", {}))
        rules = block.extensions.get("qsweb", {}).get("factor_parameters", defaults.get("factor_parameters", {}))
        has_rules = "factor_parameters" in block.extensions.get("qsweb", {}) or "factor_parameters" in defaults
        block.extensions = {"qsweb": {"factor_parameters": deepcopy(rules)}} if has_rules else {}
        available.extend(parameter_fields(block, descriptor, registry))
        for info in descriptor.inputs:
            if info.name in block.inputs:
                walk(block, info, block.inputs[info.name])
            elif info.required and not info.bound and block.operation not in ("bind", "template"):
                expose(block, info, [], None)
        dependencies.append({"id": definition.id, "version": definition.version,
            "digest": definition.recipe.digest if definition.recipe else registry.sources.get(
                registry.locations.get((definition.id, definition.version), ""), "")})
    aliases = input_names or {}
    if set(aliases) - used_names:
        raise ValueError("公开输入不存在")
    names = set()
    renamed_bindings = {}
    for item in inputs:
        original_name = item.field.name
        name = aliases.get(original_name, original_name)
        if not name.isidentifier() or name.startswith("_") or len(name) > 200 or name in names:
            raise ValueError("公开输入名称须以字母或汉字开头，仅含字母、汉字、数字和下划线，且不能重复")
        names.add(name)
        item.field.name = item.field.title = name
        if original_name in bindings:
            renamed_bindings[name] = bindings[original_name]
    bindings = renamed_bindings
    requested = {item.field.name: item for item in available}
    if set(parameters) - requested.keys():
        raise ValueError("公开参数不存在或无法保存")
    exposed = []
    names = set()
    for source, name in dict(parameters).items():
        if not name.isidentifier() or name.startswith("_") or len(name) > 200 or name in names:
            raise ValueError("公开参数名称须以字母或汉字开头，仅含字母、汉字、数字和下划线，且不能重复")
        names.add(name)
        item = requested[source].model_copy(deep=True)
        item.field.name = item.field.title = name
        exposed.append(item)
    recipe = SubgraphRecipe(document=document, inputs=inputs, parameters=exposed, dependencies=dependencies)
    diagnostics = validate_graph(document, registry)
    errors = [item for item in diagnostics if item.severity == "error"]
    if errors:
        raise GraphError(errors)
    return recipe, available, bindings


def register_subgraph(registry, id_, recipe, *, title, description="", version=1):
    """从已授权目录解析内部定义，不恢复 Python 对象。"""
    from .Compiler import describe_block, validate_graph, GraphError
    from .OperatorSnapshots import _snapshot_model
    recipe = SubgraphRecipe.model_validate(recipe).model_copy(deep=True)
    if set(recipe.document.outputs) != {"result"}:
        raise ValueError("子图必须声明唯一 result 输出")
    by_id = {block.id: block for block in recipe.document.blocks}
    for block in recipe.document.blocks:
        registry.get(block.definition)
    for dependency in recipe.dependencies:
        source = registry.get(dependency["id"], dependency["version"])
        digest = source.recipe.digest if source.recipe else registry.sources.get(
            registry.locations.get((source.id, source.version), ""), "")
        if dependency.get("digest") and dependency["digest"] != digest:
            raise ValueError(f"子图依赖定义已变更，请重新封装: {source.id}@{source.version}")
    for group in (recipe.inputs, recipe.parameters):
        if len({item.field.name for item in group}) != len(group):
            raise ValueError("子图接口名称重复")
    targets = set()
    for item in recipe.inputs:
        key = (item.target.block, item.target.field, tuple(item.target.members))
        if key in targets:
            raise ValueError("子图输入映射重复")
        targets.add(key)
        set_input(by_id[item.target.block], item.target)
    for item in recipe.parameters:
        set_parameter(by_id[item.target.block], item.target, item.field.default)
    errors = [item for item in validate_graph(recipe.document, registry) if item.severity == "error"]
    if errors:
        raise GraphError(errors)
    output = describe_block(recipe.document, recipe.document.outputs["result"].block, registry).outputs["result"]
    if output.kind not in ("node", "factor"):
        raise ValueError("子图输出必须为完整节点或因子")

    def builder(block, args, inputs):
        raise RuntimeError("子图必须在构造前展开")
    return registry.register(Definition(id_, version, title, description, "subgraph",
        _snapshot_model("子图参数", [item.field for item in recipe.parameters]),
        _snapshot_model("子图输入", [item.field for item in recipe.inputs]),
        output, builder, ("build",), category="子图组件",
        default_args={item.field.name: deepcopy(item.field.default) for item in recipe.parameters}, recipe=recipe))


@dataclass
class Expansion:
    document: GraphDocument
    origins: dict = field(default_factory=dict)

    def diagnostic(self, item):
        if item.block_id not in self.origins:
            return item
        owner, path = self.origins[item.block_id]
        return item.model_copy(update={"block_id": owner, "path": ["subgraph", *path, *item.path],
            "message": f"内部节点 {' / '.join(path)}：{item.message}"})


def expand_subgraphs(document, registry, *, targets=None, reserved_ids=()):
    """展开为普通图，保留根节点的外层 ID，内部 ID 使用无冲突命名空间。"""
    document = GraphDocument.model_validate(document).model_copy(deep=True)
    result = Expansion(document)
    occupied = {block.id for block in document.blocks} | set(reserved_ids)
    needed = set()
    by_id = {block.id: block for block in document.blocks}

    def visit(id_):
        if id_ in needed or id_ not in by_id:
            return
        needed.add(id_)
        for value in by_id[id_].inputs.values():
            for ref in references(value):
                visit(ref.block)
    if targets is None:
        needed.update(by_id)
    else:
        for name in ([targets] if isinstance(targets, str) else targets):
            if name in document.outputs:
                visit(document.outputs[name].block)

    def expand(block, owner, path, stack):
        definition = registry.get(block.definition)
        if definition.recipe is None:
            if path:
                result.origins[block.id] = (owner, path)
            return [block]
        key = (definition.id, definition.version)
        if key in stack or len(stack) >= 32:
            raise ValueError("子图组件存在递归依赖或嵌套超过 32 层")
        recipe = definition.recipe.model_copy(deep=True)
        internal = {item.id: item for item in recipe.document.blocks}
        args = definition.default_args | block.args
        for item in recipe.parameters:
            if item.field.name in args:
                set_parameter(internal[item.target.block], item.target, args[item.field.name])
        root = recipe.document.outputs["result"].block
        ids = {root: block.id}
        for item in recipe.document.blocks:
            if item.id != root:
                base = "subgraph:" + json.dumps([block.id, item.id], ensure_ascii=False, separators=(",", ":"))
                id_ = base
                while id_ in occupied:
                    id_ += ":"
                occupied.add(id_)
                ids[item.id] = id_
        # 先重写配方内引用，再安装外部绑定，避免内外同名节点的引用混淆。
        captured = definition.recipe.document
        for item in recipe.document.blocks:
            original_id = item.id
            original = next(value for value in captured.blocks if value.id == original_id)
            for name, value in original.inputs.items():
                rewrite = deepcopy(value)
                for ref in references(rewrite):
                    ref.block = ids[ref.block]
                item.inputs[name] = rewrite
        for item in recipe.inputs:
            set_input(internal[item.target.block], item.target, block.inputs.get(item.field.name))
        expanded = []
        for item in recipe.document.blocks:
            original_id = item.id
            item.id = ids[original_id]
            expanded.extend(expand(item, owner, (*path, original_id), (*stack, key)))
            if len(expanded) + len(occupied) > 20000:
                raise ValueError("展开子图节点数量超过限制")
        return expanded
    expanded = []
    for block in document.blocks:
        if block.id not in needed:
            expanded.append(block)
            continue
        try:
            expanded.extend(expand(block, block.id, (), ()))
        except KeyError:
            # 不可用定义由静态分析器报告。
            expanded.append(block)
    document.blocks = expanded
    return result


def replace_subgraph(document, selected, definition, recipe, bindings, *, instance_id):
    """原位收缩选区；所有向外引用都必须来自组件唯一出口。"""
    from .Protocol import Block, DefinitionRef
    document = GraphDocument.model_validate(document).model_copy(deep=True)
    selected = set(selected)
    by_id = {block.id: block for block in document.blocks}
    # 离开选区后再次进入选区的路径，在收缩后会形成循环。
    def returns(id_, seen):
        if id_ in selected:
            return True
        if id_ in seen or id_ not in by_id:
            return False
        seen.add(id_)
        return any(returns(ref.block, seen) for value in by_id[id_].inputs.values() for ref in references(value))
    for block in document.blocks:
        if block.id in selected:
            for value in block.inputs.values():
                for ref in references(value):
                    if ref.block not in selected and returns(ref.block, set()):
                        raise ValueError("替换会形成循环，请将选区外连接路径上的节点一并选中；仍可仅保存组件")
    if instance_id in by_id:
        raise ValueError("组件实例 ID 已存在")
    root = recipe.document.outputs["result"].block
    for block in document.blocks:
        if block.id not in selected:
            for value in block.inputs.values():
                for ref in references(value):
                    if ref.block in selected:
                        if ref.block != root or ref.port != "result":
                            raise ValueError("选区出口无法映射")
                        ref.block = instance_id
    for ref in document.outputs.values():
        if ref.block in selected:
            if ref.block != root or ref.port != "result":
                raise ValueError("图输出无法映射")
            ref.block = instance_id
    document.blocks = [block for block in document.blocks if block.id not in selected]
    document.blocks.append(Block(id=instance_id, definition=DefinitionRef(id=definition.id, version=definition.version),
        operation="build", args=deepcopy(definition.default_args), inputs=bindings))
    layout = document.extensions.setdefault("qsweb", {}).setdefault("layout", {})
    positions = layout.setdefault("positions", {})
    old = [positions[id_] for id_ in selected if id_ in positions]
    positions[instance_id] = {"x": sum(p["x"] for p in old) / len(old),
                              "y": sum(p["y"] for p in old) / len(old)} if old else {"x": 80, "y": 80}
    for id_ in selected:
        positions.pop(id_, None)
    layout["collapsed"] = [id_ for id_ in layout.get("collapsed", []) if id_ not in selected]
    return document
