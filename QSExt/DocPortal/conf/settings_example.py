# -*- coding: utf-8 -*-
"""DocPortal 配置示例。

缓存目录由 `QSExt.DocPortal.config` 统一管理，可在项目级 settings.py 中
通过环境变量覆盖（推荐），或直接修改 config.py 中的默认值。

环境变量:
    QS_DOC_PORTAL_CACHE_ROOT  — 缓存根目录，各数据源默认在其下按数据源名建子目录
    QS_AKSHARE_DOC_CACHE      — AKShare 文档缓存目录
    QS_TINYSOFT_DOC_CACHE     — 天软文档缓存目录

使用方式:
    set QS_DOC_PORTAL_CACHE_ROOT=D:\\Data\\DocPortal
"""

import os

# 缓存根目录
QS_DOC_PORTAL_CACHE_ROOT = r"D:\Data\DocPortal"

# 单数据源缓存目录（留空则使用 <CACHE_ROOT>/<数据源名>）
QS_AKSHARE_DOC_CACHE = os.path.join(QS_DOC_PORTAL_CACHE_ROOT, "AKShareDoc")
QS_TINYSOFT_DOC_CACHE = os.path.join(QS_DOC_PORTAL_CACHE_ROOT, "TinySoftDoc")
