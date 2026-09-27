# -*- coding: utf-8 -*-
"""天软文档目录树预抓取模块。

抓取天软 TSDN 文档站三个核心板块（TSL语言基础、.NET函数大全、知识库）的目录树结构，
生成 tree_index.json 索引文件，供 MCP 服务快速加载使用。

使用方式:
    from QSExt.DocPortal.doc_portal.tinysoft.scraper import scrape_and_save
    scrape_and_save("D:/Data/TinySoftDoc")
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from .fetcher import TinysoftDocFetcher
from .models import CategoryType, DocNode

logger = logging.getLogger(__name__)


def build_flat_index(nodes: list[DocNode], category: str = "", path: str = "") -> list[dict]:
    """将树形目录结构展平为扁平索引列表，便于搜索。

    递归遍历所有节点，将每个节点的 ID、名称、路径等信息提取出来。

    Args:
        nodes: 目录树节点列表
        category: 所属板块名称
        path: 当前路径（用于构建面包屑）

    Returns:
        扁平的索引条目列表
    """
    entries = []
    for node in nodes:
        current_path = f"{path}/{node.name}" if path else node.name
        entry = {
            "id": node.id,
            "name": node.name,
            "category": category,
            "path": current_path,
            "is_folder": node.is_folder,
        }
        entries.append(entry)

        if node.children:
            entries.extend(build_flat_index(node.children, category, current_path))

    return entries


def scrape_and_save(
    cache_dir: str,
    categories: Optional[dict[str, int]] = None,
) -> dict:
    """抓取天软文档目录树并保存到本地。

    Args:
        cache_dir: 缓存目录路径
        categories: 要抓取的板块 {名称: type_id}，默认抓取三个核心板块

    Returns:
        生成的索引数据字典
    """
    if categories is None:
        categories = {
            "tsl": CategoryType.TSL,
            "dotnet": CategoryType.DOTNET,
            "kb": CategoryType.KB,
        }

    os.makedirs(cache_dir, exist_ok=True)
    fetcher = TinysoftDocFetcher(cache_dir=cache_dir)

    index_data = {
        "version": 1,
        "categories": {},
        "flat_index": [],
    }

    total_nodes = 0
    for cat_name, cat_type in categories.items():
        logger.info("开始抓取板块: %s (type=%d)", cat_name, cat_type)
        tree = fetcher.fetch_tree(cat_type)

        # 序列化树结构
        tree_data = [node.model_dump() for node in tree]
        index_data["categories"][cat_name] = {
            "type_id": cat_type,
            "tree": tree_data,
        }

        # 构建扁平索引
        flat = build_flat_index(tree, category=cat_name)
        index_data["flat_index"].extend(flat)

        node_count = count_nodes(tree)
        total_nodes += node_count
        logger.info("板块 %s 抓取完成: %d 个节点", cat_name, node_count)

    # 保存索引文件
    index_path = os.path.join(cache_dir, "tree_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    logger.info("索引文件已保存: %s (共 %d 个节点)", index_path, total_nodes)
    return index_data


def count_nodes(nodes: list[DocNode]) -> int:
    """递归计算节点总数。"""
    count = 0
    for node in nodes:
        count += 1
        if node.children:
            count += count_nodes(node.children)
    return count
