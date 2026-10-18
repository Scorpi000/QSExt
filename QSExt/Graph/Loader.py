"""从服务组件目录读取 COMPONENTS 列表，统一完成注册和静态检查。"""
import hashlib
import importlib
from importlib.abc import MetaPathFinder
from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import sys

from .Components import as_component, component_id, register_component
from .Definitions import DefinitionRegistry


class _SourceLoader(SourceFileLoader):
    """直接读取源码，避免快速修改后命中旧的时间戳字节码缓存。"""

    def get_code(self, fullname):
        """编译当前源文件，不生成或读取 pyc。"""
        return self.source_to_code(self.get_data(self.path), self.path)


class _ComponentFinder(MetaPathFinder):
    """限定在当前加载命名空间内，支持组件包和相对导入。"""

    def __init__(self, namespace, root):
        self.namespace, self.root = namespace, root

    def find_spec(self, fullname, path=None, target=None):
        """为服务内部模块提供源码加载器，其余导入交给 Python。"""
        if fullname != self.namespace and not fullname.startswith(self.namespace + "."):
            return None
        relative = fullname[len(self.namespace):].lstrip(".")
        location = self.root.joinpath(*relative.split(".")) if relative else self.root
        if location.is_dir():
            source = location / "__init__.py"
            if not source.is_file():
                spec = importlib.util.spec_from_loader(fullname, loader=None, is_package=True)
                spec.submodule_search_locations = [str(location)]
                return spec
        else:
            source = location.with_suffix(".py")
        if source.is_file():
            return importlib.util.spec_from_file_location(fullname, source, loader=_SourceLoader(fullname, str(source)))
        return None


def load_component_directory(directory):
    """加载所有 Python 模块中显式列出的组件，失败时不发布部分目录。

    Args:
        directory: 组件根目录，文件名不限于 definition.py。

    Returns:
        已冻结且带有源文件摘要的定义目录。

    Raises:
        ValueError: 目录缺失、没有组件列表或某个组件定义无效。
    """
    root = Path(directory).expanduser().resolve()
    files = sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts) if root.is_dir() else []
    if not files:
        raise ValueError(f"组件目录不存在或没有 Python 定义文件：{root}")
    sources = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    signature = hashlib.sha256((str(root) + repr(sources)).encode()).hexdigest()[:20]
    namespace = "qs_components_" + signature
    registry = DefinitionRegistry()
    finder = _ComponentFinder(namespace, root)
    previous = set(sys.modules)
    sys.meta_path.insert(0, finder)
    file, index = root, None
    try:
        modules = {}
        for file in files:
            parts = file.relative_to(root).with_suffix("").parts
            if parts[-1] == "__init__":
                parts = parts[:-1]
            name = ".".join((namespace, *parts))
            modules[file] = importlib.import_module(name)
        items = []
        for file, module in modules.items():
            index = None
            if "COMPONENTS" not in vars(module) and file.name != "__init__.py":
                continue
            category = getattr(module, "CATEGORY", None)
            if category is not None and (not isinstance(category, str) or not category.strip()):
                raise ValueError("CATEGORY 必须为非空字符串")
            if file.name == "__init__.py" and file.parent != root and category is not None:
                registry.directory_categories[file.parent.relative_to(root).as_posix()] = category.strip()
            if "COMPONENTS" not in vars(module):
                continue
            if not isinstance(module.COMPONENTS, list):
                raise TypeError("COMPONENTS 必须为列表")
            registry.source_categories[file.relative_to(root).as_posix()] = category or ""
            for index, value in enumerate(module.COMPONENTS):
                item = as_component(value)
                items.append((file, index, item, category))
                # 先登记所有出口类型，使文件顺序不影响下游报告的类型检查。
                output = item.target or item.output_type
                registry.types.register(component_id(output), output)
        if not items:
            raise ValueError("组件目录没有非空的 COMPONENTS 列表")
        for file, index, item, category in items:
            definition = register_component(registry, item, category)
            registry.locations[(definition.id, definition.version)] = file.relative_to(root).as_posix()
            registry.describe_definition(definition.id, definition.version)
        registry.sources = sources
        return registry.freeze()
    except Exception as error:
        for name in list(sys.modules):
            if name not in previous and (name == namespace or name.startswith(namespace + ".")):
                sys.modules.pop(name, None)
        position = f" COMPONENTS[{index}]" if index is not None else ""
        raise ValueError(f"加载组件定义失败：{file}{position}：{error}") from error
    finally:
        sys.meta_path.remove(finder)
