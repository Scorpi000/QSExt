# -*- coding: utf-8 -*-
"""天软文档抓取器。

负责从天软 TSDN 文档站获取文档内容，包括目录树解析、单篇文档抓取、在线搜索。
所有抓取内容自动缓存到本地文件系统，减少重复请求。

使用方式:
    fetcher = TinysoftDocFetcher(cache_dir="D:/Data/TinySoftDoc")
    tree = fetcher.fetch_tree(1)  # 获取 TSL 语言基础目录树
    doc = fetcher.fetch_doc(19939)  # 获取 DataType 函数文档
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from .models import CategoryType, DocContent, DocNode, SearchResultItem

logger = logging.getLogger(__name__)

# 请求头，模拟浏览器访问
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 请求间隔（秒），避免过于频繁的请求
REQUEST_DELAY = 0.3


class TinysoftDocFetcher:
    """天软文档抓取器。

    Attributes:
        base_url: 天软文档站基础 URL
        cache_dir: 文档内容缓存目录
        session: requests 会话对象
    """

    BASE_URL = "https://www.tinysoft.com.cn:9443/tsdn/helpdoc"

    def __init__(self, cache_dir: str = ""):
        """初始化抓取器。

        Args:
            cache_dir: 文档内容缓存目录路径，为空则不缓存。
        """
        self.cache_dir = cache_dir
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.verify = False  # 天软站点 SSL 证书可能不标准

        if self.cache_dir:
            os.makedirs(os.path.join(self.cache_dir, "docs"), exist_ok=True)

    # ── 目录树抓取 ──────────────────────────────────────────────────

    def fetch_tree(self, category_type: int) -> list[DocNode]:
        """抓取指定板块的完整目录树。

        Args:
            category_type: 板块类型 ID（1=TSL, 242=.NET, 10002=知识库）

        Returns:
            目录树的根节点列表
        """
        url = f"{self.BASE_URL}/tree.tsl?type={category_type}&treename="
        logger.info("抓取目录树: type=%d, url=%s", category_type, url)

        resp = self._request(url)
        if resp is None:
            return []

        soup = BeautifulSoup(resp, "html.parser")
        nav_tree = soup.find("div", id="navTree")
        if nav_tree is None:
            logger.warning("未找到目录树容器 #navTree")
            return []

        # nav_tree 是 <div>，实际的树在内部的 <ul> 中
        top_ul = nav_tree.find("ul", recursive=False)
        if top_ul is None:
            logger.warning("未找到顶层 <ul> 元素")
            return []

        nodes = self._parse_tree_nodes(top_ul)
        logger.info("目录树抓取完成: type=%d, 共 %d 个顶层节点", category_type, len(nodes))
        return nodes

    def _parse_tree_nodes(self, element: Tag) -> list[DocNode]:
        """递归解析目录树 HTML 为 DocNode 列表。

        天软目录树使用 <ul><li><span class="folder|file"><a> 结构。
        """
        nodes = []
        for li in element.find_all("li", recursive=False):
            span = li.find("span", recursive=False)
            if span is None:
                continue

            a_tag = span.find("a", recursive=False)
            if a_tag is None:
                continue

            name = a_tag.get_text(strip=True)
            href = a_tag.get("href", "")
            doc_id = self._extract_id_from_href(href)
            is_folder = "folder" in (span.get("class") or [])

            # 递归解析子节点
            children = []
            sub_ul = li.find("ul", recursive=False)
            if sub_ul:
                children = self._parse_tree_nodes(sub_ul)

            node = DocNode(id=doc_id, name=name, is_folder=is_folder, children=children)
            nodes.append(node)

        return nodes

    @staticmethod
    def _extract_id_from_href(href: str) -> int:
        """从 display.tsl?id=xxx 链接中提取文档 ID。"""
        match = re.search(r"id=(\d+)", href)
        return int(match.group(1)) if match else 0

    # ── 文档内容抓取 ────────────────────────────────────────────────

    def fetch_doc(self, doc_id: int, use_cache: bool = True) -> Optional[DocContent]:
        """获取指定文档的完整内容。

        Args:
            doc_id: 文档 ID
            use_cache: 是否使用本地缓存

        Returns:
            文档内容对象，失败时返回 None
        """
        # 检查缓存
        if use_cache:
            cached = self._load_doc_cache(doc_id)
            if cached is not None:
                logger.debug("使用缓存: doc_id=%d", doc_id)
                return cached

        url = f"{self.BASE_URL}/display.tsl?id={doc_id}"
        logger.info("抓取文档: id=%d, url=%s", doc_id, url)

        resp = self._request(url)
        if resp is None:
            return None

        doc = self._parse_doc_content(doc_id, resp)

        # 写入缓存
        if doc and self.cache_dir:
            self._save_doc_cache(doc_id, doc)

        return doc

    def _parse_doc_content(self, doc_id: int, html: str) -> Optional[DocContent]:
        """解析文档页面 HTML 为 DocContent。

        天软文档的 HTML 结构特点：
        - 核心内容在 <div id="help_content"> 内
        - 段落标记有多种形式：
          1. <div class="DescriteTitle">简述</div> — "简述" 段落
          2. 纯文本 <div> 仅含段落名如 "定义"、"参数"、"相关"
          3. <div class="DescriteIcon"> 标记段落图标
        - 段落内容紧跟在标记后的兄弟元素中
        """
        soup = BeautifulSoup(html, "html.parser")
        help_div = soup.find("div", id="help_content")
        if help_div is None:
            logger.warning("未找到文档内容容器 #help_content, doc_id=%d", doc_id)
            return None

        # 面包屑导航
        breadcrumb = []
        breadcrumb_area = help_div.find("a", attrs={"style": re.compile("text-decoration")})
        if breadcrumb_area:
            parent = breadcrumb_area.parent
            if parent:
                for a in parent.find_all("a"):
                    text = a.get_text(strip=True)
                    if text:
                        breadcrumb.append(text)

        # 标题
        h3 = help_div.find("h3")
        title = h3.get_text(strip=True) if h3 else ""
        title = re.sub(r"复制链接", "", title).strip()

        # 用"段落标记 → 内容"方式解析所有直接子元素
        # 支持两种文档类型：
        # 1. 函数文档：简述、定义、参数、范例、相关
        # 2. 数据表文档：数据说明、字段说明、基本概况、更新日志、数据更新情况、数据范例、访问代码、取数示例、参考
        section_names = {
            # 函数文档段落
            "简述", "定义", "参数", "范例", "相关",
            # 数据表文档段落
            "数据说明", "字段说明", "基本概况", "更新日志", "数据更新情况",
            "数据范例", "访问代码", "取数示例", "参考"
        }
        sections: dict[str, list[str]] = {name: [] for name in section_names}
        current_section = ""
        current_related_links: list[dict] = []

        # 获取实际内容容器
        # 函数文档：内容直接在 help_div 中，使用 DescriteTitle class 标记段落
        # 数据表文档：内容在 demo div 的 li 元素中，使用 <span style="font-weight:bolder;color:blue"> 标记段落
        demo_div = help_div.find("div", class_="demo")

        if demo_div:
            # 数据表文档：解析 li 中的内容
            li = demo_div.find("li")
            if li:
                # 找到包含所有内容的 div（通常是 style="clear:both;"）
                content_div = li.find("div", style=re.compile("clear:both"))
                if content_div is None:
                    content_div = li

                # 遍历所有子元素，识别段落标记和内容
                for child in content_div.children:
                    # 处理文本节点（NavigableString）
                    if isinstance(child, NavigableString):
                        if current_section:
                            text = str(child).strip()
                            if text and text not in ("\n", "\r\n"):
                                sections[current_section].append(text)
                        continue

                    # 以下处理 Tag 节点
                    # 检查是否为段落标记：<span style="font-weight:bolder;color:blue">段落名</span>
                    if child.name == "span" and "font-weight:bolder" in (child.get("style") or ""):
                        section_text = child.get_text(strip=True)
                        if section_text in section_names:
                            current_section = section_text
                            continue

                    # 收集当前段落的内容（跳过 img 和 br 标记）
                    if current_section and child.name not in ("img", "br"):
                        rendered = self._tag_to_text(child)
                        if rendered and rendered.strip():
                            sections[current_section].append(rendered)
        else:
            # 函数文档：解析 help_div 中的内容
            for child in help_div.children:
                if not isinstance(child, Tag):
                    continue

                classes = child.get("class") or []
                text = child.get_text(strip=True)

                # 检查是否为段落标记（DescriteTitle class）
                if "DescriteTitle" in classes and text in section_names:
                    current_section = text
                    continue

                # 纯文本 div 且内容恰好是段落名
                if not classes and text in section_names:
                    current_section = text
                    continue

                # 跳过 DescriteIcon 标记
                if "DescriteIcon" in classes:
                    continue

                # 收集当前段落的内容
                if current_section:
                    if current_section == "相关":
                        # "相关" 段落中提取链接
                        for a in child.find_all("a"):
                            href = a.get("href", "")
                            rid = self._extract_id_from_href(href)
                            name = a.get_text(strip=True)
                            if rid and name:
                                current_related_links.append({"id": rid, "name": name})
                    else:
                        rendered = self._tag_to_text(child)
                        if rendered:
                            sections[current_section].append(rendered)

        # 组装结果
        # 支持两种文档类型的段落映射
        summary = "\n".join(sections["简述"] or sections["数据说明"])
        definition = "\n".join(sections["定义"])
        parameters = "\n".join(sections["参数"] or sections["字段说明"])

        # 处理范例：函数文档用"范例"，数据表文档用"取数示例"
        examples_raw = "\n".join(sections["范例"] or sections["取数示例"])
        # 从范例文本中按代码块分割
        examples = [ex.strip() for ex in re.split(r"\n(?=//)", examples_raw) if ex.strip()] if examples_raw else []
        # 如果没有 // 开头的分割点，尝试按 text-container 分割
        if not examples:
            for tc in help_div.find_all("div", class_="text-container"):
                text = self._tag_to_text(tc)
                if text:
                    examples.append(text)
        related = current_related_links

        # 组装 raw_content（包含所有非空段落）
        raw_parts = []
        for name in section_names:
            content = "\n".join(sections[name])
            if content or name in ("相关", "参考"):
                raw_parts.append(f"【{name}】\n{content}")
        if related:
            related_text = ", ".join(f"{r['name']}(ID:{r['id']})" for r in related)
            raw_parts.append(f"【相关函数/文档】{related_text}")

        raw_content = "\n\n".join(raw_parts) if raw_parts else help_div.get_text(separator="\n", strip=True)

        if not title and breadcrumb:
            title = breadcrumb[-1]

        # 提取数据表文档特有字段
        data_description = "\n".join(sections["数据说明"])
        field_description = "\n".join(sections["字段说明"])
        basic_info = "\n".join(sections["基本概况"])
        update_log = "\n".join(sections["更新日志"])
        data_update_info = "\n".join(sections["数据更新情况"])
        access_code = "\n".join(sections["访问代码"])

        return DocContent(
            id=doc_id,
            title=title,
            breadcrumb=breadcrumb,
            summary=summary,
            definition=definition,
            parameters=parameters,
            examples=examples,
            related=related,
            raw_content=raw_content,
            data_description=data_description,
            field_description=field_description,
            basic_info=basic_info,
            update_log=update_log,
            data_update_info=data_update_info,
            access_code=access_code,
        )

    def _extract_examples(self, help_div: Tag) -> list[str]:
        """提取代码示例列表。"""
        examples = []
        for container in help_div.find_all("div", class_="text-container"):
            text = self._tag_to_text(container)
            if text:
                examples.append(text)
        return examples

    def _extract_related(self, help_div: Tag) -> list[dict]:
        """提取相关文档列表。"""
        related = []
        # "相关" 段落通常包含指向其他文档的链接
        related_section = None
        for dt in help_div.find_all("div", class_="DescriteTitle"):
            if dt.get_text(strip=True) == "相关":
                # 找到相关部分的 ul
                parent = dt.parent
                if parent:
                    ul = parent.find("ul")
                    if ul:
                        related_section = ul
                break

        if related_section:
            for li in related_section.find_all("li"):
                a = li.find("a")
                if a:
                    href = a.get("href", "")
                    rid = self._extract_id_from_href(href)
                    name = a.get_text(strip=True)
                    if rid and name:
                        related.append({"id": rid, "name": name})

        return related

    @staticmethod
    def _tag_to_text(tag: Tag) -> str:
        """将 HTML 标签转换为纯文本，保留换行和表格结构。"""
        # 处理 <br/> 为换行
        for br in tag.find_all("br"):
            br.replace_with("\n")

        # 处理表格
        for table in tag.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                rows.append(" | ".join(cells))
            table_text = "\n".join(rows)
            table.replace_with(table_text)

        text = tag.get_text(separator="", strip=False)
        # 清理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # ── 在线搜索 ────────────────────────────────────────────────────

    def search_online(self, keyword: str, page: int = 1) -> tuple[int, list[SearchResultItem]]:
        """调用天软在线搜索接口。

        Args:
            keyword: 搜索关键词
            page: 页码（从 1 开始）

        Returns:
            (总结果数, 搜索结果列表) 的元组
        """
        encoded_kw = quote(keyword.encode("gb2312", errors="replace"))
        url = f"{self.BASE_URL}/searchcontent.tsl?KeyWord={encoded_kw}&pid={page}"
        logger.info("在线搜索: keyword=%s, page=%d", keyword, page)

        resp = self._request(url)
        if resp is None:
            return 0, []

        return self._parse_search_results(resp)

    def _parse_search_results(self, html: str) -> tuple[int, list[SearchResultItem]]:
        """解析搜索结果页面。"""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # 提取总结果数
        total = 0
        sub_info = soup.find("div", class_="sub_info")
        if sub_info:
            match = re.search(r"约(\d+)个", sub_info.get_text())
            if match:
                total = int(match.group(1))

        # 提取搜索结果
        for area in soup.find_all("div", class_="searchArea"):
            title_div = area.find("div", class_="title")
            snippet_div = area.find("div", class_="search_cnt")

            if title_div is None:
                continue

            a_tag = title_div.find("a")
            if a_tag is None:
                continue

            href = a_tag.get("href", "")
            doc_id = self._extract_id_from_href(href)
            title = a_tag.get_text(strip=True)
            snippet = snippet_div.get_text(strip=True) if snippet_div else ""
            # 移除搜索结果中的高亮标签残留
            snippet = re.sub(r"<.*?>", "", snippet)

            results.append(SearchResultItem(id=doc_id, title=title, snippet=snippet))

        return total, results

    # ── HTTP 请求 ───────────────────────────────────────────────────

    def _request(self, url: str) -> Optional[str]:
        """发送 HTTP GET 请求并返回解码后的 HTML 内容。

        Args:
            url: 请求 URL

        Returns:
            解码为 UTF-8 的 HTML 字符串，失败时返回 None
        """
        try:
            time.sleep(REQUEST_DELAY)
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()

            # GB2312 解码（天软文档站使用 GB2312 编码）
            try:
                content = resp.content.decode("gb2312")
            except UnicodeDecodeError:
                # GB2312 解码失败时尝试 GBK（GBK 是 GB2312 的超集）
                content = resp.content.decode("gbk", errors="replace")

            return content

        except requests.RequestException as e:
            logger.error("请求失败: url=%s, error=%s", url, e)
            return None

    # ── 缓存管理 ────────────────────────────────────────────────────

    def _doc_cache_path(self, doc_id: int) -> str:
        """获取文档缓存文件路径。"""
        return os.path.join(self.cache_dir, "docs", f"{doc_id}.json")

    def _load_doc_cache(self, doc_id: int) -> Optional[DocContent]:
        """从本地缓存加载文档内容。"""
        path = self._doc_cache_path(doc_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return DocContent(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("缓存文件损坏: %s, error=%s", path, e)
            return None

    def _save_doc_cache(self, doc_id: int, doc: DocContent) -> None:
        """将文档内容保存到本地缓存。"""
        path = self._doc_cache_path(doc_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc.model_dump(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("缓存写入失败: %s, error=%s", path, e)
