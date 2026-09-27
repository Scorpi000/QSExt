# -*- coding: utf-8 -*-
"""文档检索模块运行时配置。

缓存目录按数据源分别配置，可被 `QS_*` 环境变量覆盖（见下），
各数据源的 MCP 入口脚本也支持 `--cache-dir` 命令行参数（优先级最高）。

配置覆盖优先级（从低到高）：
    1. 本模块默认值
    2. `QS_DOC_PORTAL_CACHE_ROOT` 环境变量（缓存根目录）
    3. `QS_AKSHARE_DOC_CACHE` / `QS_TINYSOFT_DOC_CACHE` 环境变量（单数据源缓存目录）
    4. 命令行 `--cache-dir` 参数

Attributes:
    CACHE_ROOT: 缓存根目录，各数据源默认在其下按数据源名建子目录
    CACHE_DIRS: 数据源名 -> 缓存目录
"""

from __future__ import annotations

import os

CACHE_ROOT = os.getenv("QS_DOC_PORTAL_CACHE_ROOT", r"D:\Data\DocPortal")

CACHE_DIRS: dict[str, str] = {
    "akshare": os.getenv("QS_AKSHARE_DOC_CACHE", os.path.join(CACHE_ROOT, "AKShareDoc")),
    "tinysoft": os.getenv("QS_TINYSOFT_DOC_CACHE", os.path.join(CACHE_ROOT, "TinySoftDoc")),
}


class DocPortalSettings:
    """文档检索模块配置。

    Attributes:
        CacheRoot: 缓存根目录
        CacheDirs: 数据源名 -> 缓存目录

    Examples:
        >>> from QSExt.DocPortal.config import DocPortalSettings
        >>> settings = DocPortalSettings()
        >>> settings.CacheDirs["akshare"]
        'D:\\\\Data\\\\DocPortal\\\\AKShareDoc'
    """

    __QS_Object__ = None

    CacheRoot = CACHE_ROOT
    CacheDirs = CACHE_DIRS

    @classmethod
    def getCacheDir(cls, source: str) -> str:
        """获取指定数据源的缓存目录。

        Args:
            source: 数据源名，如 "akshare"、"tinysoft"

        Returns:
            该数据源的缓存目录路径；未配置时返回缓存根目录下的同名子目录
        """
        return cls.CacheDirs.get(source, os.path.join(cls.CacheRoot, source))
