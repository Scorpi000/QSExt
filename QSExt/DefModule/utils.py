# -*- coding: utf-8 -*-
"""DefModule 工具函数 —— 合并自原策略定义工具模块（超集）"""

import fnmatch
import importlib
import pkgutil
import types


def expand_glob(pattern: str) -> list:
    """展开 glob 模式为完整模块路径列表。

    使用 pkgutil.iter_modules 遍历包下模块（不扫文件系统）。

    模式格式: 'package.subpkg.glob_pattern'
    例如: 'QSExt.DefModule.examples.stock_cn_factor_*'
      → ['QSExt.DefModule.examples.stock_cn_factor_example1', ...]

    不含通配符时原样返回。
    """
    parts = pattern.split(".")
    for i, p in enumerate(parts):
        if "*" in p or "?" in p:
            pkg_name = ".".join(parts[:i])
            glob_pat = p
            break
    else:
        return [pattern]  # 不含通配符

    pkg = importlib.import_module(pkg_name)
    result = []
    for info in pkgutil.iter_modules(pkg.__path__, prefix=pkg_name + "."):
        stem = info.name.rsplit(".", 1)[-1]
        if fnmatch.fnmatch(stem, glob_pat):
            result.append(info.name)
    return sorted(result)


def load_notebook_as_module(path: str) -> types.ModuleType:
    """通过统一定义协议加载 notebook，不执行定义区域之后的调试单元。

    Args:
        path: notebook 的绝对或相对路径。

    Returns:
        包含元信息与 defNode/defFactor/defStrategy 入口的模块。

    Raises:
        ValueError: 定义区域无效、缺少入口或代码加载失败。
    """
    import hashlib
    from pathlib import Path
    import sys
    from QSExt.DefModule.Source import extract_notebook_source, format_definition_error

    file = Path(path).resolve()
    code, mapping = extract_notebook_source(file.read_text(encoding="utf-8-sig"), str(file))
    generated = str(file.with_suffix(".py"))
    name = "_qs_notebook_" + hashlib.sha256(str(file).encode()).hexdigest()[:32]
    module = types.ModuleType(name)
    module.__file__ = str(file)
    module.__package__ = ""
    module.__qs_source_digest__ = hashlib.sha256(code.encode()).hexdigest()
    module.__qs_source_map__ = mapping
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(code, generated, "exec"), module.__dict__)
        if not any(callable(getattr(module, entry, None)) for entry in ("defNode", "defFactor", "defStrategy")):
            raise ValueError(f"{file}: notebook 必须定义 defNode、defFactor 或 defStrategy")
    except Exception as error:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise ValueError(format_definition_error(error, {generated: mapping})) from error
    return module
