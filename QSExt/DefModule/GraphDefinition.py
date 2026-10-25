"""通用节点定义与一次构图内共享的模块依赖解析。"""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import inspect
import json
import re
import warnings

from pydantic import Field
from QuantStudio.Core import __QS_Args__
from QuantStudio.Core.Node import Node
from QuantStudio.Factor.Factor import Factor
from . import DefContent as dc


class GraphDef(__QS_Args__):
    NodeList: list[Node] = Field(default_factory=list)
    Meta: dc.DefMeta
    OutputNames: list[str] = Field(default_factory=list)

    @property
    def FactorList(self):
        return dc._classify([node for node in self.NodeList if isinstance(node, Factor)])[0]

    @property
    def StrategyList(self):
        return dc._classify([node for node in self.NodeList if isinstance(node, Factor)])[1]

    @property
    def OtherNodeList(self):
        return [node for node in self.NodeList if not isinstance(node, Factor)]

    def getNode(self, output_name):
        if output_name not in self.OutputNames:
            raise KeyError(f"未找到公开输出 {output_name!r}，可用: {self.OutputNames}")
        return self.NodeList[self.OutputNames.index(output_name)]

    def as_legacy(self):
        if self.OtherNodeList:
            raise TypeError("旧因子/策略流程不支持普通节点输出，请使用 build_graph_def 或计算图导入")
        return dc.Def(FactorList=self.FactorList, StrategyList=self.StrategyList, Meta=self.Meta)


def definition_meta(module, override=None):
    """GRAPH_META 是权威声明；旧协议重叠字段必须一致。"""
    if hasattr(module, "__GRAPH_META__"):
        meta = deepcopy(module.__GRAPH_META__)
    else:
        meta = deepcopy(getattr(module, "__FACTOR_META__", {}) or {})
        strategy = getattr(module, "__STRATEGY_META__", {}) or {}
        if not isinstance(meta, dict) or not isinstance(strategy, dict):
            raise TypeError(f"{module.__name__}: 元信息必须是字典")
        for name, value in strategy.items():
            if name in meta and meta[name] != value:
                raise ValueError(f"{module.__name__}: 元信息 {name} 冲突，请使用 __GRAPH_META__ 消歧")
            meta[name] = deepcopy(value)
    if not isinstance(meta, dict):
        raise TypeError(f"{module.__name__}: 元信息必须是字典")
    meta.update(deepcopy(override or {}))
    validated = dc.DefMeta(**meta)
    return {name: getattr(validated, name) if name in type(validated).model_fields else value for name, value in meta.items()}


def _canonical(value):
    def encode(item):
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise TypeError("构图参数的映射键必须是字符串")
            return ["dict", [[key, encode(value)] for key, value in sorted(item.items())]]
        if isinstance(item, (tuple, list)):
            return [type(item).__name__, [encode(value) for value in item]]
        if isinstance(item, (datetime, date)):
            return [type(item).__name__, item.isoformat()]
        if item is None or type(item) in (str, bool, int, float):
            return [type(item).__name__, item]
        raise TypeError(f"构图参数不能规范化: {type(item).__name__}")
    return json.dumps(encode(value), ensure_ascii=False, allow_nan=False)


def _refs(value, args):
    if isinstance(value, str):
        if value.startswith("$$"):
            return value[1:]
        if value.startswith("$"):
            if value[1:] not in args:
                raise KeyError(f"缺少模型参数引用 {value}")
            return deepcopy(args[value[1:]])
    if isinstance(value, dict):
        return {key: _refs(item, args) for key, item in value.items()}
    if isinstance(value, list):
        return [_refs(item, args) for item in value]
    if isinstance(value, tuple):
        return tuple(_refs(item, args) for item in value)
    return value


@dataclass
class _Request:
    key: str
    module: object
    args: dict
    meta: dict
    deps: list = field(default_factory=list)
    lookback: int = 365


@dataclass
class GraphBuildResult:
    requested: list[GraphDef]
    definitions: dict[str, GraphDef]
    max_lookback: int
    sources: list[dict]


class GraphDefinitionPlan:
    """先分析完整依赖闭包，再准备日历和资源，最后执行入口。"""

    def __init__(self, modules):
        self.requests = {}
        self.stack = []
        self.roots = [self._plan(module, args, meta) for module, args, meta in modules]

    def _plan(self, module, args, override):
        meta = definition_meta(module, override)
        identity = f"{module.__name__}[{getattr(module, '__file__', '')}]"
        key = identity + "@" + _canonical([args, meta])
        if key in self.stack:
            raise RuntimeError("检测到模块循环依赖: " + " -> ".join([*self.stack, key]))
        if key in self.requests:
            return self.requests[key]
        # 参数不断变化的递归同样不能构成有限的模块 DAG。
        if any(item.split("@", 1)[0] == identity for item in self.stack):
            raise RuntimeError("检测到参数递归循环依赖: " + " -> ".join([*self.stack, key]))
        request = _Request(key, module, deepcopy(args), meta,
                           lookback=dc.DefMeta(**meta).MaxLookBack)
        self.stack.append(key)
        try:
            declarations = []
            for entry in meta.get("NodeDeps", []):
                declarations.append(("node", entry["Module"], entry))
            for kind, field_name in (("factor", "FactorDeps"), ("strategy", "StrategyDeps")):
                for path, entries in meta.get(field_name, {}).items():
                    # 保留旧协议同组 ModelArgs 的合并行为。
                    params = {}
                    for entry in entries:
                        if isinstance(entry, dict):
                            params.update(entry.get("ModelArgs", {}))
                    for entry in entries:
                        item = dict(entry) if isinstance(entry, dict) else {"Name": entry}
                        declarations.append((kind, path, {**item, "ModelArgs": params}))
            for kind, path, entry in declarations:
                dep = self._plan(dc.resolve_dep_module(path, module),
                                 _refs(entry.get("ModelArgs", {}), args), {})
                raw_name = entry.get("Output") if kind == "node" else entry.get("Name", entry.get("name"))
                if not isinstance(raw_name, str) or not raw_name:
                    raise ValueError(f"{module.__name__}: {path} 缺少输出名称")
                name = _refs(raw_name, args)
                alias = entry.get("Alias", raw_name)
                if not isinstance(alias, str) or not alias:
                    raise ValueError(f"{module.__name__}: 依赖别名必须是非空字符串")
                request.deps.append((kind, alias, name, dep))
                request.lookback = max(request.lookback, dep.lookback)
            self.requests[key] = request
            return request
        finally:
            self.stack.pop()

    @property
    def max_lookback(self):
        return max((item.lookback for item in self.roots), default=0)

    def execute(self, di, prepare_input=None, factor_resolver=None):
        for request in self.requests.values():
            missing = set(request.meta.get("DBDeps", {})) - di.FDB.keys()
            if missing:
                raise KeyError(f"{request.module.__name__}: 未配置依赖因子库 {sorted(missing)}")
        if prepare_input is not None:
            prepare_input(self, di)
        for request in self.requests.values():
            if request.meta.get("RequireDates") and not di.DTs:
                raise ValueError(f"{request.module.__name__}: 构图需要日期，请填写运行日期区间")
        results = {}

        def run(request):
            if request.key in results:
                return results[request.key]
            nodes, factors, strategies = {}, {}, {}
            for kind, alias, name, dep in request.deps:
                result = run(dep)
                available = (result.FactorList if kind == "factor" else
                             result.StrategyList if kind == "strategy" else result.NodeList)
                if kind == "node":
                    selected = [(alias, result.getNode(name))]
                elif name == "*":
                    selected = [(node.Name, node) for node in available]
                else:
                    matching = [node for node in available if node.Name == name]
                    if len(matching) != 1:
                        raise KeyError(f"{request.module.__name__}: {alias} 的 {kind} 输出 {name!r} 不存在或不唯一")
                    selected = [(alias, matching[0])]
                for label, node in selected:
                    if kind == "factor" and factor_resolver is not None:
                        node = factor_resolver(node, result)
                    if label in nodes:
                        raise ValueError(f"{request.module.__name__}: 依赖别名冲突 {label}")
                    nodes[label] = node
                    if kind == "factor":
                        factors[label] = node
                    elif kind == "strategy":
                        strategies[label] = node
            values = {name: deepcopy(request.args) if name == "ModelArgs" else
                      dict(value) if isinstance(value, dict) else list(value) if isinstance(value, list) else value
                      for name, value in ((name, getattr(di, name)) for name in type(di).model_fields)}
            values.update(ModelArgs=deepcopy(request.args), Nodes=nodes, Factors=factors, Strategies=strategies)
            local = type(di)(**values)
            entry = next((getattr(request.module, name) for name in ("defNode", "defFactor", "defStrategy")
                          if callable(getattr(request.module, name, None))), None)
            if entry is None:
                raise TypeError(f"{request.module.__name__}: 脚本必须定义 defNode、defFactor 或 defStrategy")
            items = dc._call_definition(entry, local)
            if not isinstance(items, list):
                if entry is not getattr(request.module, "defNode", None) and isinstance(items, Factor):
                    items = [items]
                else:
                    raise TypeError(f"{request.module.__file__}:return 必须是 list[Node]")
            unique, names, seen = [], [], set()
            for index, node in enumerate(items):
                if not isinstance(node, Node):
                    raise TypeError(f"{request.module.__file__}:return[{index}] 必须是 Node，实际为 {type(node).__name__}")
                if node.InstanceID in seen:
                    warnings.warn(f"{request.module.__name__}: 忽略重复返回的节点 return[{index}]", stacklevel=2)
                    continue
                seen.add(node.InstanceID)
                base = node.Name or f"output_{index + 1}"
                name, suffix = base, 2
                while name in names:
                    name, suffix = f"{base}_{suffix}", suffix + 1
                names.append(name)
                unique.append(node)
            result = GraphDef(NodeList=unique, OutputNames=names,
                              Meta=dc.DefMeta(**{**request.meta, "MaxLookBack": request.lookback}))
            results[request.key] = result
            return result

        requested = [run(item) for item in self.roots]
        sources = []
        for request in self.requests.values():
            try:
                source = inspect.getsource(request.module)
            except (OSError, TypeError):
                source = re.sub(r"^_qs_def_import_[a-f0-9]+\.", "", request.module.__name__)
            sources.append({"module": re.sub(r"^_qs_def_import_[a-f0-9]+\.", "", request.module.__name__),
                            "sha256": getattr(request.module, "__qs_source_digest__", hashlib.sha256(source.encode()).hexdigest()),
                            "model_args": deepcopy(request.args)})
        return GraphBuildResult(requested, results, self.max_lookback, sources)


def build_graph_def(modules, di, *, prepare_input=None):
    return GraphDefinitionPlan(modules).execute(di, prepare_input=prepare_input)
