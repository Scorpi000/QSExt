"""普通 Node 的源码与声明快照；读取目录不执行上传源码。"""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import sys

from QuantStudio.Core.Node import Node
from .Definitions import Definition
from .Import import DefinitionImportError, _json, _model_args
from .Metadata import describe_fields
from .OperatorSnapshots import _snapshot_model
from .Protocol import FieldDescriptor, TypeDescriptor


def node_class_fingerprint(cls):
    """记录源码加载后的类行为，用于拒绝入口对类进行运行时替换。"""
    result = []
    for name, value in vars(cls).items():
        function = value.__func__ if isinstance(value, (staticmethod, classmethod)) else value
        try:
            literal = json.dumps(_json(value, name), sort_keys=True, ensure_ascii=False)
        except DefinitionImportError:
            literal = None
        result.append((name, id(value), id(getattr(function, "__code__", None)), literal))
    return tuple(result)


def node_snapshot(node, registry, files, owner):
    cls = type(node)
    namespace = cls.__module__.split(".")[0]
    if not namespace.startswith("_qs_def_import_") or "<locals>" in cls.__qualname__:
        raise DefinitionImportError(f"节点 {node.Name} 需要已注册组件或上传源码中的模块级 Node 类")
    module = sys.modules.get(cls.__module__)
    source = str(getattr(module, "__file__", ""))[len(namespace) + 1:]
    if source not in files:
        raise DefinitionImportError(f"节点 {node.Name} 的实现源码未上传")
    current = module
    for part in cls.__qualname__.split("."):
        current = getattr(current, part, None)
    if current is not cls:
        raise DefinitionImportError(f"节点 {node.Name} 的类无法按源码路径还原")
    for base in cls.__mro__:
        declaring = sys.modules.get(base.__module__)
        original = getattr(declaring, "__qs_node_signatures__", {}).get(base)
        if original is not None and original != node_class_fingerprint(base):
            raise DefinitionImportError(f"节点 {node.Name} 的类在定义入口中被修改，不能按源码还原；请使用显式参数")
    framework = {"_Dependencies", "_InstanceID", "_QS_Logger", "_ConfigFile", "_QSArgs", "_QS_ID"}
    extra = set(vars(node)) - framework
    for base in cls.__mro__:
        slots = vars(base).get("__slots__", ())
        for name in (slots,) if isinstance(slots, str) else slots:
            if name not in ("__dict__", "__weakref__") and hasattr(node, name):
                extra.add(name)
    if extra:
        raise DefinitionImportError(f"节点 {node.Name} 存在未建模实例状态 {sorted(extra)}，请声明为参数或提供组件适配器")
    _model_args(node.Args)
    bundle = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def stable(id_):
        return id_.replace(namespace, f"user.{owner}.source.{bundle}") if id_ else id_

    def normalize(value):
        if isinstance(value, dict):
            return {key: stable(item) if key == "type_id" else normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    target = cls.__module__[len(namespace) + 1:] + "." + cls.__qualname__
    key = hashlib.sha256((bundle + ":" + target).encode()).hexdigest()
    inputs = normalize([item.model_dump(mode="json") for item in describe_fields(cls.__QS_DepClass__, registry.types)])
    descriptors = normalize([item.model_dump(mode="json") for item in describe_fields(cls.__QS_ArgClass__, registry.types)])
    ancestry = {}
    for base in cls.__mro__:
        if issubclass(base, Node):
            descriptor = registry.types.describe(base)
            ancestry[stable(descriptor.type_id)] = [stable(registry.types.describe(parent).type_id)
                                                  for parent in base.__mro__[1:] if issubclass(parent, Node)]
    snapshot = {"kind": "node", "id": f"user.{owner}.node.{key}", "key": key, "version": 1,
                "namespace": namespace, "source": source, "module": cls.__module__, "qualname": cls.__qualname__,
                "runtime_namespace": "_qs_def_import_" + hashlib.sha256((owner + ":" + bundle).encode()).hexdigest()[:32],
                "title": cls.__name__, "description": cls.__doc__ or "", "args": descriptors, "inputs": inputs,
                "output": normalize(registry.types.describe(cls).model_dump(mode="json")), "ancestry": ancestry,
                "model_options": {"extra": cls.__QS_ArgClass__.model_config.get("extra", "forbid")}}
    return snapshot


def register_node_snapshot(registry, snapshot, directory, *, files=None):
    directory = Path(directory)
    args_model = _snapshot_model("PrivateNodeArgs", [FieldDescriptor.model_validate(item) for item in snapshot["args"]],
                                 snapshot.get("model_options"))
    inputs_model = _snapshot_model("PrivateNodeInputs", [FieldDescriptor.model_validate(item) for item in snapshot["inputs"]])
    registry.types.ancestry.update(snapshot.get("ancestry", {}))

    def builder(block, args, inputs):
        from .Workbench import get_construction_context
        runtime = get_construction_context()
        module_directory = Path(runtime.module_directory) if runtime and runtime.module_directory else directory
        namespace = snapshot.get("runtime_namespace", snapshot["namespace"])
        if namespace not in sys.modules:
            source = directory / snapshot["namespace"]
            if runtime and runtime.module_directory:
                package = module_directory / namespace
                if source.is_dir():
                    shutil.copytree(source, package, dirs_exist_ok=True)
                elif files is not None:
                    # 导入校验发生在原子发布之前，只在本次构图临时目录准备源码。
                    package.mkdir(parents=True, exist_ok=True)
                    (package / "__init__.py").touch()
                    for name, code in files.items():
                        relative = PurePosixPath(name)
                        if relative.suffix != ".py" or relative.is_absolute() or any(
                            not part.isidentifier() for part in relative.with_suffix("").parts
                        ):
                            raise DefinitionImportError(f"无效的节点源码路径: {name}")
                        path = package.joinpath(*relative.parts)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        parent = path.parent
                        while parent != package:
                            (parent / "__init__.py").touch(exist_ok=True)
                            parent = parent.parent
                        path.write_text(code, encoding="utf-8")
                else:
                    raise DefinitionImportError("私有节点源码缺失")
                if str(module_directory) not in sys.path:
                    sys.path.insert(0, str(module_directory))
                importlib.import_module(namespace)
            else:
                # 直接 compile_graph 也可读取不可变源码，无需修改已发布目录。
                spec = importlib.util.spec_from_file_location(namespace, source / "__init__.py",
                                                              submodule_search_locations=[str(source)])
                package_module = importlib.util.module_from_spec(spec)
                sys.modules[namespace] = package_module
                try:
                    spec.loader.exec_module(package_module)
                except BaseException:
                    sys.modules.pop(namespace, None)
                    raise
        module_name = namespace + snapshot["module"][len(snapshot["namespace"]):]
        cls = importlib.import_module(module_name)
        for part in snapshot["qualname"].split("."):
            cls = getattr(cls, part)
        if not isinstance(cls, type) or not issubclass(cls, Node):
            raise DefinitionImportError("私有节点实现不是 Node 子类")
        return cls.from_dependencies(inputs, args=args)

    definition = registry.register(Definition(snapshot["id"], snapshot["version"], snapshot["title"], snapshot["description"],
        "node", args_model, inputs_model, TypeDescriptor.model_validate(snapshot["output"]), builder, ("build",),
        category="自动导入节点"))
    path = f"_auto_operators/{directory.name}/{snapshot['namespace']}/{snapshot['source']}"
    registry.locations[(definition.id, definition.version)] = path
    registry.source_categories[path] = Path(snapshot["source"]).stem
    registry.directory_categories["_auto_operators"] = "自动导入组件"
    return definition
