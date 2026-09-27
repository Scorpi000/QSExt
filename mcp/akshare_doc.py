# -*- coding: utf-8 -*-
"""AKShare 在线文档 MCP 服务入口。

提供 5 个 MCP 工具供 AI Agent 查询 AKShare 文档和接口信息：
- search_interfaces: 搜索 AKShare 接口
- get_interface_info: 获取指定接口详情（参数、示例等）
- browse_categories: 浏览数据字典分类目录
- get_category_page: 获取某类目文档页面内容
- search_online: AKShare Sphinx 在线搜索

使用方式:
    # stdio 模式（默认）
    python mcp/akshare_doc.py

    # 指定缓存目录（默认取 DocPortalSettings.CacheDirs["akshare"] 或
    # QS_AKSHARE_DOC_CACHE 环境变量）
    python mcp/akshare_doc.py --cache-dir D:/Data/AKShareDoc

    # 启动前重建全部缓存（清除旧索引与接口/页面缓存并重新抓取）
    python mcp/akshare_doc.py --rebuild-cache

缓存说明:
    本服务本身不会自动更新缓存。tree_index.json 在服务启动时加载一次，
    interfaces/<接口名>.json 与 pages/<页路径>.json 一旦写入便永久复用。
    若 AKShare 文档有更新，需重启服务并加上 --rebuild-cache 才会刷新。

    重建优先使用 akshare 内置离线检索 API（1.18.96 的 ak.search/ak.list_categories），
    该路径完全离线、耗时约数秒；未安装 akshare 时回退到抓取 Sphinx 在线文档，
    该路径需要网络且耗时较长。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Optional

from fastmcp import FastMCP

# 将项目根目录加入 Python 路径（支持直接以脚本方式运行）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from QSExt.DocPortal.config import DocPortalSettings
from QSExt.DocPortal.doc_portal.akshare.fetcher import AKShareDocFetcher
from QSExt.DocPortal.doc_portal.akshare.models import InterfaceDetail, ParamInfo

logger = logging.getLogger(__name__)

# ── 全局状态 ────────────────────────────────────────────────────────

mcp = FastMCP(name="akshare_doc")
fetcher: AKShareDocFetcher = None  # type: ignore[assignment]
flat_index: list[dict] = []
categories_data: dict = {}
_has_akshare_api: bool = False  # akshare 是否支持 interface_info


def _load_index(cache_dir: str) -> None:
    """加载本地索引数据到全局变量。"""
    global flat_index, categories_data

    index_path = os.path.join(cache_dir, "tree_index.json")
    if not os.path.exists(index_path):
        logger.warning(
            "索引文件不存在: %s，请先运行 python -m QSExt.DocPortal.scripts.scrape_akshare_doc",
            index_path,
        )
        flat_index = []
        categories_data = {}
        return

    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    flat_index = data.get("flat_index", [])
    categories_data = data.get("categories", {})
    logger.info(
        "索引加载完成: %d 个接口, %d 个类目",
        len(flat_index),
        len(categories_data),
    )


def _format_interface_detail(detail, fmt: str = "text") -> str:
    """将 InterfaceDetail 格式化为 Agent 可读的文本。"""
    parts = []

    if fmt == "markdown":
        if detail.page_path:
            parts.append(f"**文档页:** {detail.page_path}")
        parts.append(f"# {detail.name}")
        parts.append("")
        if detail.description:
            parts.append(f"## 描述\n{detail.description}\n")
        if detail.target_url:
            parts.append(f"## 数据源\n{detail.target_url}\n")
        if detail.limit_desc:
            parts.append(f"## 限量\n{detail.limit_desc}\n")
        if detail.input_params:
            parts.append("## 输入参数\n")
            parts.append("| 名称 | 类型 | 描述 |")
            parts.append("|------|------|------|")
            for p in detail.input_params:
                parts.append(f"| {p.name} | {p.type} | {p.description} |")
            parts.append("")
        if detail.output_params:
            parts.append("## 输出参数\n")
            parts.append("| 名称 | 类型 | 描述 |")
            parts.append("|------|------|------|")
            for p in detail.output_params:
                parts.append(f"| {p.name} | {p.type} | {p.description} |")
            parts.append("")
        if detail.notes:
            parts.append(f"## 说明\n{detail.notes}\n")
        if detail.example:
            parts.append(f"## 接口示例\n```python\n{detail.example}\n```\n")
    else:
        if detail.page_path:
            parts.append(f"[文档页] {detail.page_path}")
        parts.append(f"[接口名] {detail.name}")
        if detail.description:
            parts.append(f"\n[描述]\n{detail.description}")
        if detail.target_url:
            parts.append(f"\n[数据源]\n{detail.target_url}")
        if detail.limit_desc:
            parts.append(f"\n[限量]\n{detail.limit_desc}")
        if detail.input_params:
            parts.append("\n[输入参数]")
            for p in detail.input_params:
                parts.append(f"  - {p.name} ({p.type}): {p.description}")
        if detail.output_params:
            parts.append("\n[输出参数]")
            for p in detail.output_params:
                parts.append(f"  - {p.name} ({p.type}): {p.description}")
        if detail.notes:
            parts.append(f"\n[说明]\n{detail.notes}")
        if detail.example:
            parts.append(f"\n[接口示例]\n{detail.example}")

    return "\n".join(parts)


# ── MCP 工具 ────────────────────────────────────────────────────────


@mcp.tool()
def search_interfaces(
    keyword: str,
    category: str = "all",
    max_results: int = 15,
    enable_online: bool = True,
) -> str:
    """搜索 AKShare 数据接口。

    在本地索引中按接口名、描述、类目进行多字段加权匹配搜索。
    当本地结果不足时自动调用 Sphinx 在线搜索补充。

    Args:
        keyword: 搜索关键词（支持中英文，如 "股票 历史行情"、"stock_zh_a_hist"、"可转债"）
        category: 搜索范围 — 类目名如 "stock" | "bond" | "fund" | "all"(全部)
        max_results: 最大返回结果数量，默认 15
        enable_online: 本地结果不足时是否自动在线搜索补充，默认 True

    Returns:
        匹配的接口列表，包含接口名、类目、描述
    """
    keyword_lower = keyword.lower()
    keywords = [kw.strip() for kw in keyword_lower.split() if kw.strip()]

    # 加权评分搜索
    scored = []
    for entry in flat_index:
        if category != "all" and entry["category"] != category:
            continue

        name_lower = entry["name"].lower()
        desc_lower = entry.get("description", "").lower()
        cat_lower = entry["category"].lower()

        score = 0
        for kw in keywords:
            # 接口名完全匹配 — 最高分
            if kw == name_lower:
                score += 100
            # 接口名包含关键词
            elif kw in name_lower:
                score += 60
            # 描述包含关键词
            if kw in desc_lower:
                score += 40
            # 类目匹配
            if kw in cat_lower:
                score += 10

        # 如果关键词作为一个整体也试一下（不拆分）
        if keyword_lower in name_lower:
            score += 30
        if keyword_lower in desc_lower:
            score += 20

        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: -x[0])
    results = [entry for _, entry in scored[:max_results]]

    # 在线兜底
    online_supplement = []
    if len(results) < 3 and enable_online:
        try:
            online_results = fetcher.search_sphinx(keyword)
            existing_names = {r["name"] for r in results}
            for r in online_results:
                # 从路径中提取可能的接口名
                title = r.get("title", "")
                if title not in existing_names:
                    online_supplement.append({
                        "name": title,
                        "category": "online",
                        "description": r.get("snippet", ""),
                        "score": 0,
                    })
                    if len(results) + len(online_supplement) >= max_results:
                        break
        except Exception as e:
            logger.warning("在线搜索兜底失败: %s", e)

    all_results = results + online_supplement
    if not all_results:
        return (
            f"未找到与 '{keyword}' 相关的接口。建议尝试：\n"
            f"1. 使用不同的关键词\n"
            f"2. 使用 search_online 工具进行在线搜索\n"
            f"3. 使用 browse_categories 查看可用类目"
        )

    lines = [f"找到 {len(all_results)} 个相关接口：\n"]
    for i, r in enumerate(all_results, 1):
        desc = r.get("description", "")
        if len(desc) > 80:
            desc = desc[:80] + "..."
        lines.append(f"{i}. **{r['name']}**  [{r.get('category', '')}]")
        if desc:
            lines.append(f"   {desc}")

    if online_supplement:
        lines.append(f"\n（含 {len(online_supplement)} 条在线搜索补充结果）")
    lines.append("\n使用 get_interface_info(name=<接口名>) 获取接口的完整参数和示例代码。")

    return "\n".join(lines)


@mcp.tool()
def get_interface_info(name: str, format: str = "text") -> str:
    """获取指定 AKShare 接口的完整详情。

    通过接口名获取接口的详细信息，包括描述、输入参数、输出参数、
    调用示例代码等。优先使用 akshare 内置 API（结构化数据），回退到 Sphinx 文档解析。

    Args:
        name: 接口名，如 "stock_zh_a_hist"、"bond_cb_jsl"
        format: 返回格式 — "text"(纯文本，默认) | "markdown"(Markdown格式)

    Returns:
        接口的完整信息
    """
    detail = None

    # 优先使用 akshare 内置 API
    if _has_akshare_api:
        detail = _fetch_via_akshare_api(name)

    # 回退到 Sphinx 页面解析
    if detail is None:
        page_path = ""
        for entry in flat_index:
            if entry["name"] == name:
                page_path = entry.get("page_path", "")
                break

        detail = fetcher.fetch_interface(name, page_path=page_path, use_cache=True)
        if detail is None:
            detail = fetcher.fetch_interface(name, use_cache=True)

    if detail is None:
        return (
            f"获取接口详情失败: {name}\n"
            f"可能原因：\n1. 接口名不存在\n2. 网络连接失败\n"
            f"建议先使用 search_interfaces 搜索确认接口名。"
        )

    return _format_interface_detail(detail, format)


def _fetch_via_akshare_api(name: str) -> Optional[InterfaceDetail]:
    """通过 akshare interface_info API 获取接口详情。"""
    try:
        import akshare as ak
        info = ak.interface_info(name)
    except Exception as e:
        logger.debug("akshare interface_info 失败: %s, error=%s", name, e)
        return None

    if not info:
        return None

    # 转换为 InterfaceDetail
    input_params = []
    for p in info.get("params", []):
        input_params.append(ParamInfo(
            name=p.get("name", ""),
            type=p.get("type", ""),
            description=p.get("desc", ""),
        ))

    output_params = []
    for p in info.get("outputs", []):
        output_params.append(ParamInfo(
            name=p.get("name", ""),
            type=p.get("type", ""),
            description=p.get("desc", ""),
        ))

    return InterfaceDetail(
        name=info.get("name", name),
        category=info.get("category", ""),
        description=info.get("desc", ""),
        target_url=info.get("url", ""),
        limit_desc=info.get("limit_desc", ""),
        module=info.get("module", ""),
        input_params=input_params,
        output_params=output_params,
        example=info.get("example", ""),
        documented=info.get("documented", True),
    )


@mcp.tool()
def browse_categories(detail: bool = False) -> str:
    """浏览 AKShare 数据字典的分类目录。

    返回所有数据类别及其接口数量统计，帮助了解 AKShare 的数据覆盖范围。
    详细的分类说明请参见 AKShare 官方文档：https://akshare.akfamily.xyz/data/index.html

    Args:
        detail: 是否显示每个类目的文档页路径，默认 False

    Returns:
        分类目录列表及接口统计
    """
    if not categories_data:
        return "未加载类目索引。请先运行爬虫脚本：python -m QSExt.DocPortal.scripts.scrape_akshare_doc"

    lines = ["AKShare 数据字典分类目录：\n"]

    total_count = 0
    for cat_name, cat_info in sorted(categories_data.items(), key=lambda x: x[0]):
        count = cat_info.get("interface_count", 0)
        display = cat_info.get("display_name", cat_name)
        total_count += count
        line = f"  - **{cat_name}** ({count} 个接口) — {display}"
        if detail:
            line += f"\n    文档页: {cat_info.get('page_path', '')}"
        lines.append(line)

    lines.append(f"\n共计 {len(categories_data)} 个类目, {total_count} 个接口")
    lines.append("\n使用 search_interfaces(keyword, category=<类目名>) 搜索特定类目下的接口。")
    lines.append("使用 get_category_page(category=<类目名>) 查看某类目的完整文档。")

    return "\n".join(lines)


@mcp.tool()
def get_category_page(category: str, max_length: int = 8000) -> str:
    """获取 AKShare 某类目的文档页面内容。

    抓取指定类目的数据字典页面，返回所有接口的概要信息。
    适合在搜索前先浏览某个类目下有哪些接口。

    Args:
        category: 类目名称，如 "stock"、"bond"、"fund"。使用 browse_categories 查看可用类目
        max_length: 返回内容的最大字符数，默认 8000

    Returns:
        该类目下所有接口的概要列表
    """
    if category not in categories_data:
        available = ", ".join(sorted(categories_data.keys()))
        return f"未知类目: '{category}'。可用类目: {available}"

    cat_info = categories_data[category]
    page_path = cat_info.get("page_path", "")

    if not page_path:
        return f"类目 '{category}' 无文档页路径信息。"

    interfaces = fetcher.fetch_page(page_path, use_cache=True)
    if not interfaces:
        return f"获取类目 '{category}' 的文档页内容失败。"

    display_name = cat_info.get("display_name", category)
    lines = [f"# {display_name}  ({len(interfaces)} 个接口)\n"]

    total_len = len(lines[0])
    for iface in interfaces:
        desc = iface.description[:100] + "..." if len(iface.description) > 100 else iface.description
        entry = f"- **{iface.name}**: {desc}"
        if total_len + len(entry) > max_length:
            lines.append(f"\n... (内容过长已截断，共 {len(interfaces)} 个接口)")
            break
        lines.append(entry)
        total_len += len(entry)

    lines.append(f"\n使用 get_interface_info(name=<接口名>) 获取接口详细参数和示例。")

    return "\n".join(lines)


@mcp.tool()
def search_online(keyword: str) -> str:
    """调用 AKShare 文档站的 Sphinx 在线搜索（实时网络请求）。

    直接在 AKShare 文档站进行全文搜索。当本地 search_interfaces 找不到结果时使用。
    注意：Sphinx 搜索返回的是文档页标题和摘要，不是具体的接口名。

    Args:
        keyword: 搜索关键词

    Returns:
        搜索结果列表
    """
    results = fetcher.search_sphinx(keyword)

    if not results:
        return f"在线搜索未找到与 '{keyword}' 相关的结果。"

    lines = [f"在线搜索 '{keyword}' 找到 {len(results)} 条结果：\n"]
    for i, r in enumerate(results, 1):
        snippet = r.get("snippet", "")
        if len(snippet) > 100:
            snippet = snippet[:100] + "..."
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   路径: {r.get('path', '')}")
        if snippet:
            lines.append(f"   摘要: {snippet}")

    return "\n".join(lines)


# ── 启动 ────────────────────────────────────────────────────────────


def get_default_cache_dir() -> str:
    """获取默认缓存目录路径。"""
    return DocPortalSettings.getCacheDir("akshare")


def rebuild_cache(cache_dir: str) -> None:
    """重建全部本地缓存：清除旧缓存并重新抓取索引。

    依次清除 interfaces/（接口详情）与 pages/（文档页）下的缓存文件，然后调用
    爬虫重新生成 tree_index.json。

    Args:
        cache_dir: 缓存目录路径

    Raises:
        RuntimeError: 抓取失败时抛出（网络异常等）
    """
    import shutil

    from QSExt.DocPortal.doc_portal.akshare.scraper import scrape_and_save

    for sub in ("interfaces", "pages"):
        sub_dir = os.path.join(cache_dir, sub)
        if os.path.isdir(sub_dir):
            count = len(os.listdir(sub_dir))
            shutil.rmtree(sub_dir)
            logger.info("已清除旧缓存目录 %s/ (%d 个文件)", sub, count)

    index_path = os.path.join(cache_dir, "tree_index.json")
    if os.path.exists(index_path):
        os.remove(index_path)
        logger.info("已删除旧索引文件: %s", index_path)

    logger.info("开始重建缓存（优先使用 akshare 内置离线 API）...")
    index_data = scrape_and_save(cache_dir=cache_dir)
    logger.info(
        "缓存重建完成: %d 个类目, %d 个接口",
        len(index_data.get("categories", {})),
        len(index_data.get("flat_index", [])),
    )


def init_server(cache_dir: str, rebuild: bool = False) -> None:
    """初始化 MCP 服务。

    Args:
        cache_dir: 缓存目录路径
        rebuild: 是否在启动前重建缓存（清除旧缓存并重新抓取）
    """
    global fetcher, _has_akshare_api
    fetcher = AKShareDocFetcher(cache_dir=cache_dir)

    if rebuild:
        rebuild_cache(cache_dir)

    _load_index(cache_dir)

    # 检测 akshare 是否支持 interface_info
    try:
        import akshare as ak
        _has_akshare_api = hasattr(ak, "interface_info")
    except ImportError:
        _has_akshare_api = False

    logger.info(
        "AKShare 文档 MCP 服务初始化完成, cache_dir=%s, akshare_api=%s",
        cache_dir, _has_akshare_api,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AKShare 文档 MCP 服务")
    parser.add_argument(
        "--cache-dir",
        default=get_default_cache_dir(),
        help="本地缓存目录路径 (默认: D:\\Data\\AKShareDoc 或 AKSHARE_DOC_CACHE 环境变量)",
    )
    parser.add_argument(
        "--rebuild-cache",
        action="store_true",
        help=(
            "启动前重建全部缓存：清除旧索引、接口详情与文档页缓存并重新抓取。"
            "使用 akshare 内置离线 API 时耗时数秒，期间服务不会响应"
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
