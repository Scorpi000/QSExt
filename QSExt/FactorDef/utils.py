# -*- coding: utf-8 -*-
"""FactorDef 工具函数"""

import fnmatch
import importlib
import pkgutil


def expand_glob(pattern: str) -> list:
    """展开 glob 模式为完整模块路径列表。

    使用 pkgutil.iter_modules 遍历包下模块（不扫文件系统）。

    模式格式: 'package.subpkg.glob_pattern'
    例如: 'QSExt.FactorDef.stock_cn_*'
      → ['QSExt.FactorDef.stock_cn_factor_example1', ...]

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
