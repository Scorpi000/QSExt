"""将显式执行的 DefModule 定义转换为可持久化、可编辑的图文档。"""
from contextlib import contextmanager
from datetime import date, datetime
import importlib
import importlib.abc
import importlib.util
import math
import hashlib
from pathlib import PurePosixPath
from tempfile import TemporaryDirectory
import sys
from uuid import uuid4

import pandas as pd
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from QuantStudio.Core.Node import Node
from QuantStudio.Factor.Factor import DataFactor, Factor
from QuantStudio.Factor.FactorDB import FactorDB
from QuantStudio.Factor.FactorOperation import record_factor_construction

from .Protocol import Block, Collection, CollectionItem, DefinitionRef, GraphDocument, LiteralValue, Reference, ResourceReference
from .Sources import ResourceFactor
from .Tabular import serialize_tabular


class DefinitionImportError(ValueError):
    """不可无损表达的定义必须明确拒绝，不返回残缺的画布。"""


def _same(a, b):
    if a is b:
        return True
    try:
        return bool(a == b)
    except (TypeError, ValueError):
        return False


def _json(value, path):
    if isinstance(value, BaseModel):
        return _model_args(value, path=path)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise DefinitionImportError(f"{path} 的映射键必须是字符串")
        return {key: _json(item, f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise DefinitionImportError(f"{path} 含不可保存的值 ({type(value).__name__})；请将其封装为已注册组件的默认行为")


def _model_args(model, *, fields=None, skip=(), path="args"):
    result = {}
    for name, info in (fields or type(model).model_fields).items():
        if name in skip:
            continue
        value = getattr(model, name)
        # Callable 默认值可以省略；非默认函数、句柄或二进制对象不能混入 JSON。
        try:
            result[name] = _json(value, f"{path}.{name}")
        except DefinitionImportError:
            if info.default is not PydanticUndefined and _same(value, info.default):
                continue
            raise
    for name, value in (getattr(model, "__pydantic_extra__", None) or {}).items():
        result[name] = _json(value, f"{path}.{name}")
    return result


def graph_from_nodes(outputs, registry, *, construction_inputs=None, register_operator=None, register_node=None):
    """按对象实例去重展开命名输入，不合并语义相同但独立的节点。"""
    from QuantStudio.BackTest.Strategy.Strategy import MakeAccount
    from .Compiler import validate_graph
    records = construction_inputs or {}
    blocks, seen, active, levels = [], {}, set(), {}
    definitions = [registry.get(item.definition) for item in registry.list_definitions()]

    def definition_for(target, kind):
        matches = [item for item in definitions if item.target is target and item.kind == kind]
        if len(matches) != 1:
            label = f"{target.__module__}.{target.__qualname__}"
            raise DefinitionImportError(f"组件 {label} {'未注册' if not matches else '对应多个定义，无法确定映射'}；请在 COMPONENTS 中提供唯一映射")
        return matches[0]

    def binding(value):
        if isinstance(value, Node):
            return visit(value)
        if isinstance(value, (tuple, list)):
            return Collection(items=[CollectionItem(id=uuid4().hex, value=binding(item)) for item in value])
        return LiteralValue(value=_json(value, "inputs"))

    def visit(node):
        if node.InstanceID in active:
            raise DefinitionImportError(f"定义存在循环依赖: {node.Name}")
        if node.InstanceID in seen:
            return Reference(block=seen[node.InstanceID])
        active.add(node.InstanceID)
        id_ = f"n{len(seen) + 1}"
        seen[node.InstanceID] = id_
        result_args = _model_args(node.Args, fields=Factor.__QS_ArgClass__.model_fields) if isinstance(node, Factor) else {}
        if isinstance(node, ResourceFactor):
            registry.get("qs.factor.source")
            values = node.Args
            definition, operation = DefinitionRef(id="qs.factor.source"), "build"
            args = {"name": node.Name, "table": values.Table, "factor_name": values.FactorName,
                    "data_type": values.DataType, "table_args": values.TableArgs, "factor_args": values.FactorArgs}
            inputs = {"resource": ResourceReference(id=values.Resource.id)}
            # 因子本身的截面、计算日历和元信息也必须保留。
            args["factor_args"] = {**values.FactorArgs, **result_args}
            result_args = {}
        elif type(node) is DataFactor:
            if isinstance(node.Args.Data, (pd.DataFrame, pd.Series)):
                definition, operation, inputs = DefinitionRef(id="qs.factor.tabular"), "build", {}
                args = {"Name": node.Name, "Data": serialize_tabular(node.Args.Data),
                        "FactorArgs": _model_args(node.Args, skip=("Data", "Name"))}
                result_args = {}
            elif isinstance(node.Args.Data, float) and not math.isfinite(node.Args.Data):
                definition, operation = DefinitionRef(id="qs.factor.special_constant"), "apply"
                args = {"value": "nan" if math.isnan(node.Args.Data) else "inf" if node.Args.Data > 0 else "-inf",
                        "name": node.Name, "data_type": node.Args.DataType, "lookback": node.Args.LookBack}
                inputs = {}
            else:
                definition = DefinitionRef(id="qs.factor.constant")
                operation, inputs = "build", {}
                args = _model_args(node.Args)
                result_args = {}
            registry.get(definition)
        else:
            operator = getattr(node, "_Operator", None)
            if operator is not None:
                captured = records.get(node.InstanceID)
                if captured is None:
                    shared = records.get((id(node.Dependencies), type(operator)))
                    if shared is not None and shared[0] is node.Dependencies:
                        captured = shared[1]
                dependencies = captured if captured is not None else node.Dependencies
                if captured is None and set(type(dependencies).model_fields) - {"extra_deps"} != set(operator.InputClass.model_fields):
                    raise DefinitionImportError(f"{node.Name} 缺少公开输入记录，请在 record_factor_construction 中执行定义函数")
                extra = getattr(node.Dependencies, "extra_deps", ())
                if extra:
                    raise DefinitionImportError(f"{node.Name} 含未声明的 extra_deps，不能转换为组件输入")
                inputs = {name: binding(getattr(dependencies, name)) for name in operator.InputClass.model_fields}
                if type(operator) is MakeAccount and any(item.id == "qs.strategy.account" for item in definitions):
                    definition, operation = DefinitionRef(id="qs.strategy.account"), "apply"
                    args = _json(operator.Args.ModelArgs, "args")
                    args["start_dt"] = _json(operator.Args.StartDT[0], "args.start_dt")
                    account = registry.get(definition)
                    if "start_dt" not in account.args_model.model_fields and args["start_dt"] is None:
                        del args["start_dt"]
                else:
                    if sum(item.target is type(operator) and item.kind == "operator" for item in definitions) > 1:
                        definition_for(type(operator), "operator")
                    try:
                        if "calculate" in vars(operator):
                            raise DefinitionImportError(f"自定义算子 {node.Name} 需要显式组件适配，不能仅按 {type(operator).__name__} 还原")
                        item = definition_for(type(operator), "operator")
                        args = _model_args(operator.Args)
                    except DefinitionImportError:
                        if register_operator is None:
                            raise
                        item, args = register_operator(operator, registry)
                    definition, operation = DefinitionRef(id=item.id, version=item.version), "apply"
            else:
                matches = [item for item in definitions if item.target is type(node) and item.kind == "node"]
                if not matches and register_node is not None:
                    item = register_node(node, registry)
                else:
                    item = definition_for(type(node), "node")
                definition, operation = DefinitionRef(id=item.id, version=item.version), "build"
                args, result_args = _model_args(node.Args), {}
                inputs = {name: binding(getattr(node.Dependencies, name)) for name in type(node.Dependencies).model_fields}
        block = Block(id=id_, definition=definition, operation=operation, args=args, result_args=result_args, inputs=inputs)
        blocks.append(block)
        refs = []
        def collect(value):
            if isinstance(value, Reference):
                refs.append(value.block)
            elif isinstance(value, Collection):
                for item in value.items:
                    collect(item.value)
        for value in inputs.values():
            collect(value)
        levels[id_] = 1 + max((levels[ref] for ref in refs), default=-1)
        active.remove(node.InstanceID)
        return Reference(block=id_)

    named = {name: visit(node) for name, node in outputs.items()}
    rows, positions = {}, {}
    for block in blocks:
        level = levels[block.id]
        row = rows.get(level, 0)
        positions[block.id] = {"x": level * 320, "y": row * 180}
        rows[level] = row + 1
    document = GraphDocument(blocks=blocks, outputs=named, extensions={"qsweb": {"layout": {"positions": positions, "collapsed": []}}})
    errors = [item for item in validate_graph(document, registry, allow_partial=False) if item.severity == "error"]
    if errors:
        raise DefinitionImportError("转换结果无法通过校验: " + "; ".join(item.message for item in errors))
    return document


class DefinitionDatabase(FactorDB):
    """构图用的授权来源；getFactor 延迟读取，显式 readData 按需访问数据源。"""

    def __init__(self, name, resource, describe_table=None):
        super().__init__(args={"Name": name})
        self.resource, self.describe_table = resource, describe_table

    def getTable(self, table_name, args=None):
        return _DefinitionTable(self, table_name, args or {})

    @property
    def TableNames(self):
        raise DefinitionImportError("定义脚本需显式指定表名；导入阶段不枚举业务数据源")


class _DefinitionTable:
    def __init__(self, database, name, args):
        self.FactorDB, self.Name, self.args = database, name, _json(args, "table_args")

    def _table(self):
        if self.FactorDB.describe_table is None:
            raise DefinitionImportError(f"来源 {self.FactorDB.Name}/{self.Name} 需要数据源元信息")
        return self.FactorDB.describe_table(self.FactorDB.resource, self.Name, self.args)

    @property
    def FactorNames(self):
        return self._table().FactorNames

    def getFactorMetaData(self, *args, **kwargs):
        return self._table().getFactorMetaData(*args, **kwargs)

    def readData(self, *args, **kwargs):
        """用户执行定义时，使用同一授权访问器读取实际数据。"""
        return self._table().readData(*args, **kwargs)

    def getFactor(self, factor_name, args=None):
        values = dict(args or {})
        dtype = values.get("Meta", {}).get("DataType", "double")
        if self.FactorDB.describe_table is not None:
            dtype = str(self.getFactorMetaData(factor_names=[factor_name], key="DataType").loc[factor_name])
        return ResourceFactor.from_dependencies({}, args={**values, "Name": values.get("Name", factor_name),
            "Resource": self.FactorDB.resource, "Table": self.Name, "FactorName": factor_name,
            "DataType": dtype, "TableArgs": self.args, "FactorArgs": _json(values, "factor_args")})


class _SourceModules(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, files):
        self.namespace = "_qs_def_import_" + uuid4().hex
        self.sources = {}
        for path, code in files.items():
            item = PurePosixPath(path)
            if item.suffix != ".py" or item.is_absolute() or any(not part.isidentifier() for part in item.with_suffix("").parts):
                raise DefinitionImportError(f"无效的 Python 脚本路径: {path}")
            parts = item.with_suffix("").parts
            name = ".".join((self.namespace, *(parts[:-1] if parts[-1] == "__init__" else parts)))
            self.sources[name] = (code, parts[-1] == "__init__", path)

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self.namespace or fullname.startswith(self.namespace + "."):
            package = fullname not in self.sources or self.sources[fullname][1]
            if fullname not in self.sources and not any(name.startswith(fullname + ".") for name in self.sources):
                return None
            return importlib.util.spec_from_loader(fullname, self, is_package=package)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        source = self.sources.get(module.__name__)
        module.__file__ = f"{self.namespace}/{source[2] if source else '__init__.py'}"
        if source:
            module.__qs_source_digest__ = hashlib.sha256(source[0].encode()).hexdigest()
            exec(compile(source[0], module.__file__, "exec"), module.__dict__)
            from .NodeSnapshots import node_class_fingerprint
            module.__qs_node_signatures__ = {value: node_class_fingerprint(value) for value in vars(module).values()
                                            if isinstance(value, type) and issubclass(value, Node)
                                            and value.__module__ == module.__name__}


@contextmanager
def definition_modules(files):
    """隔离每次上传的模块命名空间，依赖文件不会跨用户或跨导入复用。"""
    from QSExt.DefModule.Source import normalize_definition_sources
    files, _ = normalize_definition_sources(files)
    finder = _SourceModules(files)
    sys.meta_path.insert(0, finder)
    try:
        def load(path):
            parts = PurePosixPath(path).with_suffix("").parts
            if parts[-1] == "__init__":
                parts = parts[:-1]
            return importlib.import_module(".".join((finder.namespace, *parts)))
        yield load
    finally:
        sys.meta_path.remove(finder)
        for name in list(sys.modules):
            if name == finder.namespace or name.startswith(finder.namespace + "."):
                sys.modules.pop(name, None)


def import_definition(files, entry, registry, definition_input, *, model_args=None, register_operator=None,
                      register_node=None, prepare_input=None):
    """转换 notebook 后复用统一入口，错误位置映射回原始单元。"""
    from QSExt.DefModule.Source import normalize_definition_sources, format_definition_error
    if entry not in files:
        raise DefinitionImportError("入口脚本未上传")
    try:
        sources, source_maps = normalize_definition_sources(files)
    except ValueError as error:
        raise DefinitionImportError(str(error)) from error
    try:
        document = _import_definition(sources, str(PurePosixPath(entry).with_suffix(".py")), registry,
            definition_input, model_args=model_args, register_operator=register_operator,
            register_node=register_node, prepare_input=prepare_input)
    except Exception as error:
        message = format_definition_error(error, source_maps)
        if message != str(error):
            raise DefinitionImportError(message) from error
        raise
    imported = document.extensions["qsweb"]["definition_import"]
    imported["entry"] = entry
    if source_maps:
        imported["source_maps"] = source_maps
    return document


def _import_definition(files, entry, registry, definition_input, *, model_args=None, register_operator=None,
                       register_node=None, prepare_input=None):
    """用户明确导入时执行定义函数，展开模块依赖并冻结本次构图结果。"""
    from QSExt.DefModule.DefContent import build_graph_def
    if entry not in files:
        raise DefinitionImportError("入口脚本未上传")
    with definition_modules(files) as load, record_factor_construction() as records:
        module = load(entry)
        if not any(callable(getattr(module, name, None)) for name in ("defNode", "defFactor", "defStrategy")):
            raise DefinitionImportError("脚本必须定义 defNode、defFactor 或 defStrategy")
        built = build_graph_def([(module, model_args or {}, {})], definition_input, prepare_input=prepare_input)
        result = built.requested[0]
        outputs = dict(zip(result.OutputNames, result.NodeList))
        if not outputs:
            raise DefinitionImportError("定义脚本未返回计算节点")
        document = graph_from_nodes(outputs, registry, construction_inputs=records, register_operator=register_operator,
                                    register_node=register_node)
        # 构建只在用户明确导入时执行，保证保存的是可还原节点。
        from .Compiler import compile_graph
        from .Resources import ResourceCatalog
        resources, visited = {}, set()
        def collect_resources(node):
            if node.InstanceID in visited:
                return
            visited.add(node.InstanceID)
            if isinstance(node, ResourceFactor):
                resources[node.Args.Resource.id] = node.Args.Resource
            for child in node.Deps:
                collect_resources(child)
        for node in outputs.values():
            collect_resources(node)
        from .Workbench import construction_scope
        with TemporaryDirectory(prefix="qs-definition-check-") as directory:
            try:
                with construction_scope(definition_input.DTs, definition_input.SectionIDs, directory):
                    compile_graph(document, registry, resources=ResourceCatalog(resources.values())).execution_nodes()
            finally:
                if directory in sys.path:
                    sys.path.remove(directory)
                for name, imported in list(sys.modules.items()):
                    if name.startswith("_qs_def_import_") and str(getattr(imported, "__file__", "")).startswith(directory):
                        sys.modules.pop(name, None)
        document.extensions["qsweb"]["definition_import"] = {"entry": entry, "files": dict(files), "model_args": model_args or {},
            "protocol_version": 1, "outputs": result.OutputNames,
            "sources": _json(built.sources, "sources"),
            "meta": _json(result.Meta, "meta"),
            "max_lookback": built.max_lookback, "description": result.Meta.Description}
        return document
