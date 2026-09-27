# -*- coding: utf-8 -*-
"""AKShare 文档索引预抓取模块。

抓取 AKShare 数据字典的所有类别页面，构建本地搜索索引。
优先使用 akshare 包内置的离线检索 API（1.18.96），
未安装时回退到 Sphinx 文档页面解析。

使用方式:
    from QSExt.DocPortal.doc_portal.akshare.scraper import scrape_and_save
    scrape_and_save("D:/Data/AKShareDoc")
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from .fetcher import AKShareDocFetcher
from .models import AKShareCategory

logger = logging.getLogger(__name__)

# AKShare 数据字典类别及其文档页路径
DOC_CATEGORIES: dict[str, dict[str, str]] = {
    "stock": {
        "display_name": "AKShare 股票数据",
        "page_path": "data/stock/stock.html",
    },
    "futures": {
        "display_name": "AKShare 期货数据",
        "page_path": "data/futures/futures.html",
    },
    "bond": {
        "display_name": "AKShare 债券数据",
        "page_path": "data/bond/bond.html",
    },
    "option": {
        "display_name": "AKShare 期权数据",
        "page_path": "data/option/option.html",
    },
    "fx": {
        "display_name": "AKShare 外汇数据",
        "page_path": "data/fx/fx.html",
    },
    "currency": {
        "display_name": "AKShare 货币数据",
        "page_path": "data/currency/currency.html",
    },
    "spot": {
        "display_name": "AKShare 现货数据",
        "page_path": "data/spot/spot.html",
    },
    "interest_rate": {
        "display_name": "AKShare 利率数据",
        "page_path": "data/interest_rate/interest_rate.html",
    },
    "fund_private": {
        "display_name": "AKShare 私募基金数据",
        "page_path": "data/fund/fund_private.html",
    },
    "fund_public": {
        "display_name": "AKShare 公募基金数据",
        "page_path": "data/fund/fund_public.html",
    },
    "index": {
        "display_name": "AKShare 指数数据",
        "page_path": "data/index/index.html",
    },
    "macro": {
        "display_name": "AKShare 宏观数据",
        "page_path": "data/macro/macro.html",
    },
    "dc": {
        "display_name": "AKShare 加密货币数据",
        "page_path": "data/dc/dc.html",
    },
    "bank": {
        "display_name": "AKShare 银行数据",
        "page_path": "data/bank/bank.html",
    },
    "article": {
        "display_name": "AKShare 论文数据",
        "page_path": "data/article/article.html",
    },
    "energy": {
        "display_name": "AKShare 能源数据",
        "page_path": "data/energy/energy.html",
    },
    "event": {
        "display_name": "AKShare 迁徙数据",
        "page_path": "data/event/event.html",
    },
    "hf": {
        "display_name": "AKShare 高频数据",
        "page_path": "data/hf/hf.html",
    },
    "nlp": {
        "display_name": "AKShare 自然语言处理",
        "page_path": "data/nlp/nlp.html",
    },
    "qdii": {
        "display_name": "AKShare QDII 数据",
        "page_path": "data/qdii/qdii.html",
    },
    "others": {
        "display_name": "AKShare 另类数据",
        "page_path": "data/others/others.html",
    },
    "qhkc": {
        "display_name": "AKShare 奇货可查",
        "page_path": "data/qhkc/index.html",
    },
    "tool": {
        "display_name": "AKShare 工具箱",
        "page_path": "data/tool/tool.html",
    },
    # akshare 内置 API 中额外的类目（Sphinx 文档中无对应页面）
    "cal": {
        "display_name": "AKShare 日历数据",
        "page_path": "",
    },
    "futures_derivative": {
        "display_name": "AKShare 期货衍生品数据",
        "page_path": "",
    },
    "reits": {
        "display_name": "AKShare REITs 数据",
        "page_path": "",
    },
    "stock_feature": {
        "display_name": "AKShare 股票特色数据",
        "page_path": "",
    },
    "stock_fundamental": {
        "display_name": "AKShare 股票基本面数据",
        "page_path": "",
    },
}


def scrape_and_save(
    cache_dir: str,
    categories: Optional[list[str]] = None,
) -> dict:
    """抓取 AKShare 文档并保存索引。

    优先使用 akshare 内置的离线检索 API，未安装时回退到 Sphinx 页面解析。

    Args:
        cache_dir: 缓存目录路径
        categories: 要抓取的类目列表，默认全部

    Returns:
        生成的索引数据字典
    """
    os.makedirs(cache_dir, exist_ok=True)

    if categories is None:
        categories = list(DOC_CATEGORIES.keys())

    # 尝试使用 akshare 内置 API
    akshare_index = _try_akshare_api(categories)

    if akshare_index:
        logger.info("使用 akshare 内置 API 构建索引")
        index_data = akshare_index
    else:
        logger.info("akshare 未安装或 API 不可用，回退到 Sphinx 页面解析")
        fetcher = AKShareDocFetcher(cache_dir=cache_dir)
        index_data = _scrape_from_sphinx(fetcher, cache_dir, categories)

    # 去重（多个 DOC_CATEGORIES 别名映射到同一个 akshare 类目时会产生重复）
    _deduplicate_index(index_data)

    # 保存索引文件
    index_path = os.path.join(cache_dir, "tree_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    total = len(index_data.get("flat_index", []))
    logger.info("索引文件已保存: %s (共 %d 个接口)", index_path, total)
    return index_data


def _deduplicate_index(index_data: dict) -> None:
    """去重 flat_index 中的重复接口条目。

    当多个 DOC_CATEGORIES 别名映射到同一个 akshare 类目时（如 fund_private/fund_public → fund），
    flat_index 中会出现重复。保留第一个出现的条目。
    """
    seen: set[str] = set()
    unique = []
    for entry in index_data.get("flat_index", []):
        name = entry.get("name", "")
        if name not in seen:
            seen.add(name)
            unique.append(entry)
    removed = len(index_data.get("flat_index", [])) - len(unique)
    if removed > 0:
        logger.info("去重: 移除 %d 条重复记录", removed)
        index_data["flat_index"] = unique
        # 同步更新各 category 的 interface_count
        cat_counts: dict[str, int] = {}
        for entry in unique:
            cat = entry.get("category", "")
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        for cat_name, cat_info in index_data.get("categories", {}).items():
            cat_info["interface_count"] = cat_counts.get(cat_name, 0)


def _sync_category_map(available_cats: set[str], requested: list[str]) -> None:
    """将 akshare list_categories 发现但 DOC_CATEGORIES 中缺失的类目补充进来。"""
    for cat in available_cats:
        if cat not in DOC_CATEGORIES and cat in requested:
            # 推测文档页路径：fund 的部分拆分为 fund_private/fund_public
            page_path = f"data/{cat}/{cat}.html"
            DOC_CATEGORIES[cat] = {
                "display_name": f"AKShare {cat} 数据",
                "page_path": page_path,
            }


def _try_akshare_api(categories: list[str]) -> Optional[dict]:
    """尝试使用 akshare 内置的离线检索 API 构建索引。

    Returns:
        索引数据字典，如果 akshare 不可用则返回 None
    """
    try:
        import akshare as ak
    except ImportError:
        return None

    # 检查是否支持 search 接口
    if not hasattr(ak, "search"):
        logger.warning("当前 akshare 版本不支持 search 接口，请升级到 1.18.96")
        return None

    try:
        import pandas as pd

        index_data = {
            "version": 1,
            "source": "akshare_api",
            "categories": {},
            "flat_index": [],
        }

        # 获取类目列表
        try:
            cat_df = ak.list_categories()
            available_cats = set(cat_df.iloc[:, 0].tolist()) if not cat_df.empty else set()
            cat_counts = dict(zip(cat_df.iloc[:, 0], cat_df.iloc[:, 1])) if not cat_df.empty else {}
        except Exception:
            available_cats = set()
            cat_counts = {}

        # 同步更新 DOC_CATEGORIES 中从 list_categories 发现的新类目
        if available_cats:
            _sync_category_map(available_cats, categories)

        # 构建 DOC_CATEGORIES 名称到 akshare API 类目名的映射
        # DOC_CATEGORIES 使用 Sphinx 文档目录名，akshare API 使用自己的类目名
        cat_alias = {
            "fund_private": "fund",
            "fund_public": "fund",
            "qhkc": "qhkc_web",
        }

        for cat_name in categories:
            # 对于 akshare API，使用映射后的类目名
            api_cat = cat_alias.get(cat_name, cat_name)

            if available_cats and api_cat not in available_cats:
                logger.debug("跳过不存在的类目: %s (api: %s)", cat_name, api_cat)
                continue

            # 用类目名作为关键词搜索，确保获取该类目全部接口
            try:
                search_df = ak.search(api_cat, category=api_cat, limit=500, documented_only=False)
            except Exception as e:
                logger.warning("搜索类目 %s 失败: %s", cat_name, e)
                # 回退：不指定 category
                try:
                    search_df = ak.search(api_cat, limit=500, documented_only=False)
                    # 只保留该类目的接口
                    if not search_df.empty and "类目" in search_df.columns:
                        search_df = search_df[search_df["类目"] == api_cat]
                except Exception:
                    continue

            if search_df.empty:
                continue

            cat_info = DOC_CATEGORIES.get(cat_name, {})
            flat_entries = []

            for _, row in search_df.iterrows():
                entry = {
                    "name": str(row.get("接口名", "")),
                    "category": cat_name,
                    "description": str(row.get("描述", "")) if pd.notna(row.get("描述")) else "",
                    "page_path": cat_info.get("page_path", ""),
                    "documented": bool(row.get("有无文档", True)),
                    "score": float(row.get("匹配分", 0)) if "匹配分" in row.index else 0,
                }
                if entry["name"]:
                    flat_entries.append(entry)

            index_data["categories"][cat_name] = {
                "display_name": cat_info.get("display_name", cat_name),
                "page_path": cat_info.get("page_path", ""),
                "interface_count": len(flat_entries),
            }
            index_data["flat_index"].extend(flat_entries)

            logger.info("类目 %s: %d 个接口", cat_name, len(flat_entries))

        if not index_data["flat_index"]:
            return None

        return index_data

    except Exception as e:
        logger.error("使用 akshare API 构建索引失败: %s", e)
        return None


def _scrape_from_sphinx(
    fetcher: AKShareDocFetcher, cache_dir: str, categories: list[str]
) -> dict:
    """从 Sphinx 文档页面解析构建索引。"""
    index_data = {
        "version": 1,
        "source": "sphinx_html",
        "categories": {},
        "flat_index": [],
    }

    for cat_name in categories:
        cat_info = DOC_CATEGORIES.get(cat_name)
        if not cat_info:
            logger.warning("未知类目: %s", cat_name)
            continue

        page_path = cat_info["page_path"]
        logger.info("抓取类目: %s (%s)", cat_name, page_path)

        interfaces = fetcher.fetch_page(page_path)
        if not interfaces:
            logger.warning("类目 %s 未获取到接口", cat_name)
            continue

        flat_entries = []
        for iface in interfaces:
            flat_entries.append({
                "name": iface.name,
                "category": cat_name,
                "description": iface.description,
                "page_path": page_path,
                "documented": iface.documented,
            })

        index_data["categories"][cat_name] = {
            "display_name": cat_info["display_name"],
            "page_path": page_path,
            "interface_count": len(flat_entries),
        }
        index_data["flat_index"].extend(flat_entries)

        logger.info("类目 %s: %d 个接口", cat_name, len(flat_entries))

    return index_data
