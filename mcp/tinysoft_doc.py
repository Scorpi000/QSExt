# -*- coding: utf-8 -*-
"""天软(Tinysoft)在线文档 MCP 服务入口。

提供 5 个 MCP 工具供 AI Agent 查询天软 TSDN 文档站内容：
- search_docs: 本地索引搜索文档
- get_doc_content: 获取指定文档详情
- browse_categories: 浏览文档分类目录
- get_function_list: 获取函数列表
- search_online: 天软在线全文搜索

使用方式:
    # stdio 模式（默认）
    python mcp/tinysoft_doc.py

    # 指定缓存目录（默认取 DocPortalSettings.CacheDirs["tinysoft"] 或
    # QS_TINYSOFT_DOC_CACHE 环境变量）
    python mcp/tinysoft_doc.py --cache-dir D:/Data/TinySoftDoc

    # 启动前重建全部缓存（清除旧索引与文档内容缓存并重新抓取）
    python mcp/tinysoft_doc.py --rebuild-cache

缓存说明:
    本服务本身不会自动更新缓存。tree_index.json 在服务启动时加载一次，
    docs/<doc_id>.json 一旦写入便永久复用。若天软文档有更新，需重启服务
    并加上 --rebuild-cache 才会刷新。

    重建需要网络访问天软文档站，耗时较长，期间服务不响应。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from fastmcp import FastMCP

# 将项目根目录加入 Python 路径（支持直接以脚本方式运行）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from QSExt.DocPortal.config import DocPortalSettings
from QSExt.DocPortal.doc_portal.tinysoft.fetcher import TinysoftDocFetcher
from QSExt.DocPortal.doc_portal.tinysoft.models import CategoryType
from QSExt.DocPortal.doc_portal.tinysoft.scraper import build_flat_index

logger = logging.getLogger(__name__)

# ── 全局状态 ────────────────────────────────────────────────────────

mcp = FastMCP(name="tinysoft_doc")
fetcher: TinysoftDocFetcher = None  # type: ignore[assignment]
flat_index: list[dict] = []
tree_data: dict = {}
synonym_map: dict[str, list[str]] = {}  # keyword -> [synonyms]


def _load_synonyms() -> None:
    """加载同义词映射表。"""
    global synonym_map
    synonym_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synonyms.json")
    if not os.path.exists(synonym_path):
        logger.warning("同义词表未找到，跳过加载")
        return
    with open(synonym_path, "r", encoding="utf-8") as f:
        synonym_map = json.load(f)
    logger.info("同义词表加载完成: %d 组", len(synonym_map))


def _expand_keywords(keyword: str) -> list[str]:
    """将关键词展开为同义词列表（含原词）。"""
    kw_lower = keyword.lower()
    expanded = {keyword}
    for group_key, synonyms in synonym_map.items():
        all_terms = [group_key] + synonyms
        if any(kw_lower == t.lower() or kw_lower in t.lower() or t.lower() in kw_lower for t in all_terms):
            expanded.update(all_terms)
    return list(expanded)


def _load_index(cache_dir: str) -> None:
    """加载本地索引数据到全局变量。"""
    global flat_index, tree_data

    index_path = os.path.join(cache_dir, "tree_index.json")
    if not os.path.exists(index_path):
        logger.warning("索引文件不存在: %s，请先运行 python -m QSExt.DocPortal.scripts.scrape_tinysoft_doc", index_path)
        flat_index = []
        tree_data = {}
        return

    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    flat_index = data.get("flat_index", [])
    tree_data = data.get("categories", {})
    logger.info("索引加载完成: %d 条记录, %d 个板块", len(flat_index), len(tree_data))

    _load_synonyms()


def _format_doc_content(doc, fmt: str = "text") -> str:
    """将 DocContent 格式化为 Agent 可读的文本。

    支持两种文档类型：
    1. 函数文档：显示简述、定义、参数、范例、相关函数
    2. 数据表文档：显示数据说明、基本概况、字段说明、更新日志、访问代码、取数示例
    """
    if fmt == "markdown":
        parts = []
        if doc.breadcrumb:
            parts.append(f"**路径:** {' > '.join(doc.breadcrumb)}")
        parts.append(f"# {doc.title}")
        parts.append("")

        # 函数文档段落
        if doc.summary:
            parts.append(f"## 简述\n{doc.summary}\n")
        if doc.definition:
            parts.append(f"## 定义\n`{doc.definition}`\n")
        if doc.parameters and not doc.field_description:
            # 如果没有字段说明，则显示参数（函数文档）
            parts.append(f"## 参数\n{doc.parameters}\n")

        # 数据表文档段落
        if doc.data_description:
            parts.append(f"## 数据说明\n{doc.data_description}\n")
        if doc.basic_info:
            parts.append(f"## 基本概况\n{doc.basic_info}\n")
        if doc.field_description:
            parts.append(f"## 字段说明\n{doc.field_description}\n")
        if doc.update_log:
            parts.append(f"## 更新日志\n{doc.update_log}\n")
        if doc.data_update_info:
            parts.append(f"## 数据更新情况\n{doc.data_update_info}\n")
        if doc.access_code:
            parts.append(f"## 访问代码\n{doc.access_code}\n")

        # 范例/取数示例
        if doc.examples:
            parts.append("## 范例")
            for ex in doc.examples:
                parts.append(f"```tsl\n{ex}\n```\n")

        # 相关函数/文档
        if doc.related:
            parts.append("## 相关")
            for r in doc.related:
                parts.append(f"- {r['name']} (ID: {r['id']})")
        return "\n".join(parts)
    else:
        parts = []
        if doc.breadcrumb:
            parts.append(f"[路径] {' > '.join(doc.breadcrumb)}")
        parts.append(f"[标题] {doc.title}")

        # 函数文档段落
        if doc.summary:
            parts.append(f"\n[简述/数据说明]\n{doc.summary}")
        if doc.definition:
            parts.append(f"\n[定义]\n{doc.definition}")
        if doc.parameters and not doc.field_description:
            parts.append(f"\n[参数]\n{doc.parameters}")

        # 数据表文档段落
        if doc.data_description and not doc.summary:
            parts.append(f"\n[数据说明]\n{doc.data_description}")
        if doc.basic_info:
            parts.append(f"\n[基本概况]\n{doc.basic_info}")
        if doc.field_description:
            parts.append(f"\n[字段说明]\n{doc.field_description}")
        if doc.update_log:
            parts.append(f"\n[更新日志]\n{doc.update_log}")
        if doc.data_update_info:
            parts.append(f"\n[数据更新情况]\n{doc.data_update_info}")
        if doc.access_code:
            parts.append(f"\n[访问代码]\n{doc.access_code}")

        # 范例/取数示例
        if doc.examples:
            parts.append("\n[范例/取数示例]")
            for i, ex in enumerate(doc.examples, 1):
                parts.append(f"--- 范例 {i} ---\n{ex}")

        # 相关函数/文档
        if doc.related:
            parts.append("\n[相关]")
            for r in doc.related:
                parts.append(f"  - {r['name']} (ID: {r['id']})")
        return "\n".join(parts)


# ── MCP 工具 ────────────────────────────────────────────────────────


@mcp.tool()
def search_docs(keyword: str, category: str = "all", max_results: int = 10,
                 enable_online: bool = True) -> str:
    """搜索天软(TinySoft)文档。

    在本地索引中按文档标题、名称、路径进行多字段加权匹配搜索。
    支持同义词扩展（如搜"股价"可匹配 "StockClose"），按相关度评分排序。
    当本地结果不足时自动调用在线搜索补充。

    Args:
        keyword: 搜索关键词（支持中英文，如 "DataType"、"矩阵"、"Stock"）
        category: 搜索范围 — "tsl"(语言基础) | "dotnet"(.NET函数) | "kb"(知识库) | "all"(全部)
        max_results: 最大返回结果数量，默认 10
        enable_online: 本地结果不足时是否自动在线搜索补充，默认 True

    Returns:
        匹配的文档列表，包含 ID、标题、路径、所属板块、匹配分数
    """
    # 1. 同义词展开
    keywords = _expand_keywords(keyword)
    keywords_lower = [kw.lower() for kw in keywords]

    # 2. 加权评分
    scored = []
    for entry in flat_index:
        if entry.get("is_folder"):
            continue
        if category != "all" and entry["category"] != category:
            continue

        score = 0
        name_lower = entry["name"].lower()
        path_lower = entry["path"].lower()
        title_lower = entry.get("title", entry["name"]).lower()

        for kw in keywords_lower:
            if kw in title_lower:
                score += 60
            if kw in name_lower:
                score += 40
            if kw in path_lower:
                score += 10

        if score > 0:
            scored.append((score, entry))

    # 3. 按分数降序排列
    scored.sort(key=lambda x: -x[0])
    results = [entry for _, entry in scored[:max_results]]

    # 4. 在线兜底
    online_supplement = []
    if len(results) < 3 and enable_online:
        try:
            total, online_results = fetcher.search_online(keyword, page=1)
            if online_results:
                existing_ids = {r["id"] for r in results}
                for r in online_results:
                    if r.id not in existing_ids:
                        online_supplement.append({
                            "id": r.id,
                            "name": r.title,
                            "category": "online",
                            "path": r.snippet[:80] + "..." if len(r.snippet) > 80 else r.snippet,
                            "score": 0,
                        })
                        if len(results) + len(online_supplement) >= max_results:
                            break
        except Exception as e:
            logger.warning("在线搜索兜底失败: %s", e)

    # 5. 格式化输出
    all_results = results + online_supplement
    if not all_results:
        return f"未找到与 '{keyword}' 相关的文档。建议尝试：\n1. 使用不同的关键词\n2. 使用 search_online 工具进行在线搜索"

    lines = [f"找到 {len(all_results)} 条相关结果：\n"]
    for i, r in enumerate(all_results, 1):
        score_info = f"  score={r.get('score', '')}" if r.get('score') else ""
        lines.append(f"{i}. [{r['category']}] {r['name']}{score_info}")
        lines.append(f"   ID: {r['id']}  |  路径: {r['path']}")

    if online_supplement:
        lines.append(f"\n（含 {len(online_supplement)} 条在线搜索补充结果）")
    lines.append(f"\n使用 get_doc_content(doc_id=<ID>) 获取文档详细内容。")

    return "\n".join(lines)


@mcp.tool()
def get_doc_content(doc_id: int, format: str = "text") -> str:
    """获取指定天软(TinySoft)文档的完整内容。

    通过文档 ID 获取文档的详细信息，包括简述、函数定义、参数说明、
    代码示例和相关函数。内容来自本地缓存或实时抓取。

    Args:
        doc_id: 文档 ID（从 search_docs 或 browse_categories 结果中获取）
        format: 返回格式 — "text"(纯文本，默认) | "markdown"(Markdown格式)

    Returns:
        文档的完整内容
    """
    doc = fetcher.fetch_doc(doc_id, use_cache=True)
    if doc is None:
        return f"获取文档失败 (ID: {doc_id})。可能原因：\n1. 文档 ID 不存在\n2. 网络连接失败\n3. 天软服务器暂时不可用"

    return _format_doc_content(doc, format)


@mcp.tool()
def browse_categories(category: str = "all", depth: int = 2) -> str:
    """浏览天软(TinySoft)文档的分类目录结构。

    返回文档的树形目录结构，支持按板块浏览和控制展开深度。
    适合了解文档整体结构和查找特定分类下的文档。

    Args:
        category: 板块名 — "tsl"(TSL语言基础) | "dotnet"(.NET函数大全) | "kb"(知识库) | "all"(全部)
        depth: 目录展开层数，默认 2 层。设为 1 只看顶层分类

    Returns:
        树形目录结构的文本表示
    """
    categories_to_show = {}
    if category == "all":
        categories_to_show = tree_data
    elif category in tree_data:
        categories_to_show = {category: tree_data[category]}
    else:
        available = ", ".join(tree_data.keys())
        return f"未知板块: '{category}'。可用板块: {available}"

    parts = []
    for cat_name, cat_info in categories_to_show.items():
        cat_type = cat_info.get("type_id", "")
        parts.append(f"═══ {cat_name.upper()} (type={cat_type}) ═══\n")
        _render_tree(cat_info.get("tree", []), parts, depth=depth, current_depth=1)

    return "\n".join(parts)


def _load_cached_signature(doc_id: int) -> str:
    """从本地 JSON 缓存读取函数签名（definition 字段）。"""
    if not fetcher or not fetcher.cache_dir:
        return ""
    cache_path = os.path.join(fetcher.cache_dir, "docs", f"{doc_id}.json")
    if not os.path.exists(cache_path):
        return ""
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        definition = data.get("definition", "")
        return definition.strip() if definition else ""
    except (json.JSONDecodeError, OSError):
        return ""


def _render_tree(nodes: list[dict], parts: list[str], depth: int, current_depth: int, prefix: str = "") -> None:
    """递归渲染目录树为缩进文本。"""
    for i, node in enumerate(nodes):
        is_last = i == len(nodes) - 1
        connector = "└── " if is_last else "├── "
        name = node["name"]
        doc_id = node["id"]
        is_folder = node.get("is_folder", False)

        if is_folder:
            marker = "📁"
            parts.append(f"{prefix}{connector}{marker} {name} (ID: {doc_id})")
        else:
            marker = "📄"
            # 对非文件夹节点尝试加载签名
            sig = _load_cached_signature(doc_id)
            if sig:
                parts.append(f"{prefix}{connector}{marker} {name}  =>  `{sig}`")
            else:
                parts.append(f"{prefix}{connector}{marker} {name} (ID: {doc_id})")

        if is_folder and node.get("children") and current_depth < depth:
            extension = "    " if is_last else "│   "
            _render_tree(node["children"], parts, depth, current_depth + 1, prefix + extension)


@mcp.tool()
def get_function_list(sub_category: str = "", keyword: str = "",
                      offset: int = 0, limit: int = 30) -> str:
    """获取天软(TinySoft)的 .NET 函数大全中的函数列表。

    专门用于浏览和搜索天软 .NET 函数大全中的函数。支持按子分类
    过滤、按函数名关键字过滤、分页浏览。

    Args:
        sub_category: 子分类路径，如 "系统相关函数/数据类型函数" 或 "金融函数"
        keyword: 按函数名过滤的关键字，如 "Stock"、"Matrix"
        offset: 跳过前 N 条结果，默认 0
        limit: 返回数量上限，默认 30

    Returns:
        匹配的函数列表，含总数和分页信息
    """
    dotnet_data = tree_data.get("dotnet")
    if dotnet_data is None:
        return "未加载 .NET 函数大全板块索引。请先运行爬虫脚本。"

    functions = []
    _collect_functions(dotnet_data.get("tree", []), functions, path="")

    if sub_category:
        sub_lower = sub_category.lower()
        functions = [f for f in functions if sub_lower in f["path"].lower()]

    if keyword:
        kw_lower = keyword.lower()
        functions = [f for f in functions if kw_lower in f["name"].lower()]

    if not functions:
        return f"未找到匹配的函数。sub_category='{sub_category}', keyword='{keyword}'"

    total = len(functions)
    page_funcs = functions[offset:offset + limit]

    lines = [f"共 {total} 个函数（显示 {offset + 1}-{min(offset + limit, total)}）：\n"]
    for f in page_funcs:
        lines.append(f"- {f['name']}  (ID: {f['id']}, 路径: {f['path']})")

    if offset + limit < total:
        lines.append(f"\n还有更多结果，使用 offset={offset + limit} 查看下一页。")
    lines.append(f"\n使用 get_doc_content(doc_id=<ID>) 查看函数详细说明。")

    return "\n".join(lines)


def _collect_functions(nodes: list[dict], functions: list[dict], path: str) -> None:
    """递归收集函数叶子节点。"""
    for node in nodes:
        current_path = f"{path}/{node['name']}" if path else node["name"]
        if node.get("is_folder") and node.get("children"):
            _collect_functions(node["children"], functions, current_path)
        else:
            functions.append({
                "id": node["id"],
                "name": node["name"],
                "path": current_path,
            })


@mcp.tool()
def search_online(keyword: str, page: int = 1) -> str:
    """调用天软(TinySoft)在线搜索（实时网络请求）。

    直接调用天软文档站的搜索引擎进行全文搜索，结果更全面但需要网络。
    当本地 search_docs 找不到结果时，建议使用此工具。

    Args:
        keyword: 搜索关键词
        page: 页码（从 1 开始），每页约 10 条结果

    Returns:
        搜索结果列表，包含标题、摘要和文档 ID
    """
    total, results = fetcher.search_online(keyword, page=page)

    if not results:
        return f"在线搜索未找到与 '{keyword}' 相关的结果。"

    lines = [f"在线搜索 '{keyword}' 共找到约 {total} 条结果（第 {page} 页）：\n"]
    for i, r in enumerate(results, 1):
        snippet = r.snippet[:100] + "..." if len(r.snippet) > 100 else r.snippet
        lines.append(f"{i}. {r.title}")
        lines.append(f"   ID: {r.id}  |  摘要: {snippet}")

    if total > page * 10:
        lines.append(f"\n还有更多结果，使用 page={page + 1} 查看下一页。")
    lines.append(f"\n使用 get_doc_content(doc_id=<ID>) 获取文档详细内容。")

    return "\n".join(lines)


# ── 启动 ────────────────────────────────────────────────────────────


def get_default_cache_dir() -> str:
    """获取默认缓存目录路径。"""
    return DocPortalSettings.getCacheDir("tinysoft")


def rebuild_cache(cache_dir: str) -> None:
    """重建全部本地缓存：清除旧缓存并重新抓取索引。

    依次清除 docs/（文档内容）下的缓存文件，然后调用爬虫重新生成
    tree_index.json。需要网络访问天软文档站。

    Args:
        cache_dir: 缓存目录路径

    Raises:
        RuntimeError: 抓取失败时抛出（网络异常等）
    """
    import shutil

    from QSExt.DocPortal.doc_portal.tinysoft.scraper import scrape_and_save

    docs_dir = os.path.join(cache_dir, "docs")
    if os.path.isdir(docs_dir):
        count = len(os.listdir(docs_dir))
        shutil.rmtree(docs_dir)
        logger.info("已清除旧缓存目录 docs/ (%d 个文件)", count)

    index_path = os.path.join(cache_dir, "tree_index.json")
    if os.path.exists(index_path):
        os.remove(index_path)
        logger.info("已删除旧索引文件: %s", index_path)

    logger.info("开始重建缓存（需抓取天软文档站目录树）...")
    index_data = scrape_and_save(cache_dir=cache_dir)
    logger.info(
        "缓存重建完成: %d 个板块, %d 个节点",
        len(index_data.get("categories", {})),
        len(index_data.get("flat_index", [])),
    )


def init_server(cache_dir: str, rebuild: bool = False) -> None:
    """初始化 MCP 服务。

    Args:
        cache_dir: 缓存目录路径
        rebuild: 是否在启动前重建缓存（清除旧缓存并重新抓取）
    """
    global fetcher
    fetcher = TinysoftDocFetcher(cache_dir=cache_dir)

    if rebuild:
        rebuild_cache(cache_dir)

    _load_index(cache_dir)
    logger.info("天软(TinySoft)文档 MCP 服务初始化完成, cache_dir=%s", cache_dir)




if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="天软文档 MCP 服务")
    parser.add_argument(
        "--cache-dir",
        default=get_default_cache_dir(),
        help="本地缓存目录路径 (默认: D:\\Data\\TinySoftDoc 或 TINYSOFT_DOC_CACHE 环境变量)",
    )
    parser.add_argument(
        "--rebuild-cache",
        action="store_true",
        help=(
            "启动前重建全部缓存：清除旧索引与文档内容缓存并重新抓取。"
            "需要网络访问天软文档站，耗时较长，期间服务不会响应"
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    if args.rebuild_cache:
        try:
            init_server(args.cache_dir, rebuild=True)
        except Exception as e:
            # 重建失败不应导致服务无法启动：回退到加载现有缓存
            logger.error("缓存重建失败: %s: %s", type(e).__name__, e)
            logger.warning("回退为使用现有缓存启动（如缓存不存在则索引为空）")
            init_server(args.cache_dir)
    else:
        init_server(args.cache_dir)

    mcp.run(transport="stdio")
