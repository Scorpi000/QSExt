#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AKShare 文档索引预抓取脚本。

本脚本构建 AKShare 接口的本地搜索索引，供 akshare_doc MCP 服务使用。

数据来源（按优先级）：
    1. akshare 内置离线检索 API（1.18.96，完全离线，结构化数据）
    2. Sphinx 文档页面 HTML 解析（回退方案）

使用方法:
    # 使用默认缓存目录（DocPortalSettings.CacheDirs["akshare"]，
    # 可用 QS_AKSHARE_DOC_CACHE 或 QS_DOC_PORTAL_CACHE_ROOT 环境变量覆盖）
    python -m QSExt.DocPortal.scripts.scrape_akshare_doc

    # 指定自定义缓存目录
    python -m QSExt.DocPortal.scripts.scrape_akshare_doc --cache-dir E:/Cache/AKShareDoc

    # 只抓取特定类目
    python -m QSExt.DocPortal.scripts.scrape_akshare_doc --categories stock bond fund

生成文件:
    <cache_dir>/tree_index.json  — 包含所有接口的索引文件

前置要求:
    推荐安装 akshare (pip install akshare) 以获得最佳索引质量。
    未安装时自动回退到解析在线文档页面。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from QSExt.DocPortal.config import DocPortalSettings
from QSExt.DocPortal.doc_portal.akshare.scraper import DOC_CATEGORIES, scrape_and_save


def main():
    parser = argparse.ArgumentParser(
        description="AKShare 文档索引预抓取脚本 — 构建本地接口搜索索引"
    )
    parser.add_argument(
        "--cache-dir",
        default=DocPortalSettings.getCacheDir("akshare"),
        help="本地缓存目录路径 (默认取 DocPortalSettings.CacheDirs['akshare'])",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=None,
        choices=list(DOC_CATEGORIES.keys()),
        help="要抓取的类目 (默认: 全部)",
    )
    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    categories = args.categories or list(DOC_CATEGORIES.keys())

    print(f"缓存目录: {args.cache_dir}")
    print(f"抓取类目: {', '.join(categories)} ({len(categories)} 个)")

    # 检查 akshare 是否可用
    try:
        import akshare
        print(f"akshare 版本: {akshare.__version__}")
        if hasattr(akshare, "search"):
            print("数据来源: akshare 内置离线检索 API (推荐)")
        else:
            print("数据来源: Sphinx 文档页面解析 (建议升级 akshare 到 1.18.96)")
    except ImportError:
        print("数据来源: Sphinx 文档页面解析 (未安装 akshare)")

    print("-" * 50)

    # 执行抓取
    index_data = scrape_and_save(
        cache_dir=args.cache_dir,
        categories=categories,
    )

    # 打印统计信息
    total_interfaces = len(index_data.get("flat_index", []))
    cat_count = len(index_data.get("categories", {}))

    print("-" * 50)
    print(f"抓取完成!")
    print(f"  来源: {index_data.get('source', 'unknown')}")
    print(f"  类目数: {cat_count}")
    print(f"  接口总数: {total_interfaces}")
    print(f"  索引文件: {os.path.join(args.cache_dir, 'tree_index.json')}")
    print(f"\n启动 MCP 服务:")
    print(f"  python mcp/akshare_doc.py --cache-dir {args.cache_dir}")


if __name__ == "__main__":
    main()
