#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""天软(Tinysoft)文档目录树预抓取脚本。

本脚本从天软 TSDN 文档站抓取三大核心板块的目录树结构，生成 tree_index.json 索引文件。
该索引文件供 tinysoft_doc MCP 服务使用，实现快速的本地文档搜索。

抓取的板块:
    - TSL 语言基础 (type=1): TSL 语言语法、关键字、数据类型等基础文档
    - .NET 函数大全 (type=242): 完整的 TSL 函数参考（数千个函数）
    - 知识库 (type=10002): 矩阵专题、代码优化、数据字典等实用知识

使用方法:
    # 使用默认缓存目录（DocPortalSettings.CacheDirs["tinysoft"]，
    # 可用 QS_TINYSOFT_DOC_CACHE 或 QS_DOC_PORTAL_CACHE_ROOT 环境变量覆盖）
    python -m QSExt.DocPortal.scripts.scrape_tinysoft_doc

    # 指定自定义缓存目录
    python -m QSExt.DocPortal.scripts.scrape_tinysoft_doc --cache-dir E:/Cache/TinySoftDoc

    # 只抓取特定板块
    python -m QSExt.DocPortal.scripts.scrape_tinysoft_doc --categories tsl dotnet

生成文件:
    <cache_dir>/tree_index.json  — 包含目录树结构和扁平搜索索引的 JSON 文件
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from QSExt.DocPortal.config import DocPortalSettings
from QSExt.DocPortal.doc_portal.tinysoft.models import CategoryType
from QSExt.DocPortal.doc_portal.tinysoft.scraper import scrape_and_save


def main():
    parser = argparse.ArgumentParser(
        description="天软文档目录树预抓取脚本 — 抓取 TSDN 文档站结构并生成本地索引"
    )
    parser.add_argument(
        "--cache-dir",
        default=DocPortalSettings.getCacheDir("tinysoft"),
        help="本地缓存目录路径 (默认取 DocPortalSettings.CacheDirs['tinysoft'])",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=["tsl", "dotnet", "kb"],
        choices=["tsl", "dotnet", "kb"],
        help="要抓取的板块 (默认: tsl dotnet kb)",
    )
    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # 构建板块映射
    cat_map = {
        "tsl": CategoryType.TSL,
        "dotnet": CategoryType.DOTNET,
        "kb": CategoryType.KB,
    }
    categories = {name: cat_map[name] for name in args.categories}

    print(f"缓存目录: {args.cache_dir}")
    print(f"抓取板块: {', '.join(categories.keys())}")
    print("-" * 50)

    # 执行抓取
    index_data = scrape_and_save(
        cache_dir=args.cache_dir,
        categories=categories,
    )

    # 打印统计信息
    total_nodes = len(index_data.get("flat_index", []))
    cat_count = len(index_data.get("categories", {}))

    print("-" * 50)
    print(f"抓取完成!")
    print(f"  板块数: {cat_count}")
    print(f"  节点总数: {total_nodes}")
    print(f"  索引文件: {os.path.join(args.cache_dir, 'tree_index.json')}")
    print(f"\n启动 MCP 服务:")
    print(f"  python mcp/tinysoft_doc.py --cache-dir {args.cache_dir}")


if __name__ == "__main__":
    main()
