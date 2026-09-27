# -*- coding: utf-8 -*-
"""AKShare 文档抓取器。

负责从 AKShare Sphinx 文档站获取接口详情页面内容，
解析接口的参数、示例代码等信息。支持本地 JSON 缓存。

使用方式:
    fetcher = AKShareDocFetcher(cache_dir="D:/Data/AKShareDoc")
    detail = fetcher.fetch_interface("stock_zh_a_hist", page_path="data/stock/stock.html")
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from .models import InterfaceDetail, ParamInfo

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

REQUEST_DELAY = 0.3


class AKShareDocFetcher:
    """AKShare 文档抓取器。

    Attributes:
        base_url: AKShare 文档站基础 URL
        cache_dir: 文档内容缓存目录
        session: requests 会话对象
    """

    BASE_URL = "https://akshare.akfamily.xyz"

    def __init__(self, cache_dir: str = ""):
        """初始化抓取器。

        Args:
            cache_dir: 文档内容缓存目录路径，为空则不缓存。
        """
        self.cache_dir = cache_dir
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        if self.cache_dir:
            os.makedirs(os.path.join(self.cache_dir, "pages"), exist_ok=True)
            os.makedirs(os.path.join(self.cache_dir, "interfaces"), exist_ok=True)

    # ── 接口详情获取 ──────────────────────────────────────────────

    def fetch_interface(
        self, interface_name: str, page_path: str = "", use_cache: bool = True
    ) -> Optional[InterfaceDetail]:
        """获取指定接口的详细信息。

        Args:
            interface_name: 接口名，如 "stock_zh_a_hist"
            page_path: 文档页路径，如 "data/stock/stock.html"
            use_cache: 是否使用本地缓存

        Returns:
            接口详情对象，失败时返回 None
        """
        # 检查接口级缓存
        if use_cache:
            cached = self._load_interface_cache(interface_name)
            if cached is not None:
                logger.debug("使用缓存: %s", interface_name)
                return cached

        # 如果没有 page_path，从索引中查找
        if not page_path:
            page_path = self._find_page_path(interface_name)
            if not page_path:
                logger.warning("未找到接口 %s 所在的文档页", interface_name)
                return None

        # 抓取并解析整个页面
        interfaces = self.fetch_page(page_path, use_cache=use_cache)
        if not interfaces:
            return None

        # 查找目标接口
        for iface in interfaces:
            if iface.name == interface_name:
                self._save_interface_cache(interface_name, iface)
                return iface

        logger.warning("在页面 %s 中未找到接口 %s", page_path, interface_name)
        return None

    def fetch_page(
        self, page_path: str, use_cache: bool = True
    ) -> Optional[list[InterfaceDetail]]:
        """抓取并解析一个文档页面的所有接口。

        Args:
            page_path: 文档页路径，如 "data/stock/stock.html"
            use_cache: 是否使用页面缓存

        Returns:
            接口详情列表，失败时返回 None
        """
        # 检查页面缓存
        if use_cache:
            cached = self._load_page_cache(page_path)
            if cached is not None:
                logger.debug("使用页面缓存: %s", page_path)
                return cached

        url = f"{self.BASE_URL}/{page_path}"
        logger.info("抓取文档页: %s", url)

        html = self._request(url)
        if html is None:
            return None

        interfaces = self._parse_page(page_path, html)

        # 写入缓存
        if interfaces and self.cache_dir:
            self._save_page_cache(page_path, interfaces)

        return interfaces

    # ── Sphinx 在线搜索 ────────────────────────────────────────────

    def search_sphinx(self, keyword: str) -> list[dict]:
        """调用 AKShare Sphinx 搜索接口。

        Args:
            keyword: 搜索关键词

        Returns:
            搜索结果列表 [{title, path, snippet}]
        """
        url = f"{self.BASE_URL}/search.html"
        params = {"q": keyword, "check_keywords": "yes", "area": "default"}

        try:
            time.sleep(REQUEST_DELAY)
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            html = resp.content.decode("utf-8", errors="replace")
        except requests.RequestException as e:
            logger.error("Sphinx 搜索失败: %s", e)
            return []

        return self._parse_search_results(html)

    def _parse_search_results(self, html: str) -> list[dict]:
        """解析 Sphinx 搜索结果页面。"""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        search_items = soup.find_all("li")
        for item in search_items:
            a_tag = item.find("a")
            if not a_tag:
                continue
            href = a_tag.get("href", "")
            title = a_tag.get_text(strip=True)
            # 跳过非搜索结果的链接
            if not href or href.startswith("#") or "search" in href:
                continue
            snippet_tag = item.find("div", class_="context")
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
            results.append({
                "title": title,
                "path": href,
                "snippet": snippet[:200],
            })

        return results[:20]

    # ── 页面解析 ──────────────────────────────────────────────────

    def _parse_page(self, page_path: str, html: str) -> list[InterfaceDetail]:
        """解析文档页 HTML，提取所有接口详情。

        AKShare 文档页格式：
        - 接口以 "接口：<name>" 标记开头
        - 后跟 "目标地址："、"描述："、"限量：" 等字段
        - "输入参数" 和 "输出参数" 后跟表格
        - "接口示例" 后跟代码块
        """
        soup = BeautifulSoup(html, "html.parser")
        body = soup.find("div", attrs={"itemprop": "articleBody"})
        if body is None:
            body = soup.find("section", id="akshare")
        if body is None:
            body = soup.find("div", class_="body")
        if body is None:
            logger.warning("未找到页面正文容器: %s", page_path)
            return []

        # 提取所有文本段落
        all_text = body.get_text(separator="\n", strip=True)

        # 按 "接口：" 分割，提取接口段
        interfaces = []
        # 使用正则找到所有接口入口
        interface_pattern = re.compile(
            r"接口[：:]\s*(\w+)", re.MULTILINE
        )

        # 获取页面纯文本，按接口分段
        full_text = body.get_text(separator="\n")
        matches = list(interface_pattern.finditer(full_text))

        category = self._extract_category(page_path)

        for i, match in enumerate(matches):
            interface_name = match.group(1)
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
            section_text = full_text[start:end]

            detail = self._parse_interface_section(
                interface_name, section_text, category, page_path
            )
            if detail:
                interfaces.append(detail)

        logger.info("页面 %s 解析完成: %d 个接口", page_path, len(interfaces))
        return interfaces

    def _parse_interface_section(
        self, name: str, text: str, category: str, page_path: str
    ) -> InterfaceDetail:
        """解析单个接口的文本段落，提取结构化信息。"""
        detail = InterfaceDetail(name=name, category=category, page_path=page_path)

        # 描述
        desc_match = re.search(r"描述[：:]\s*(.+?)(?:\n|$)", text)
        if desc_match:
            detail.description = desc_match.group(1).strip()

        # 目标地址
        url_match = re.search(r"目标地址[：:]\s*(https?://\S+)", text)
        if url_match:
            detail.target_url = url_match.group(1).strip()

        # 限量
        limit_match = re.search(r"限量[：:]\s*(.+?)(?:\n|$)", text)
        if limit_match:
            detail.limit_desc = limit_match.group(1).strip()

        # 输入参数 - 在 "输入参数" 和 "输出参数" 或 "接口示例" 之间
        input_params = self._extract_params(text, "输入参数", ["输出参数", "接口示例", "说明"])
        detail.input_params = input_params

        # 输出参数 - 在 "输出参数" 和 "接口示例" 或下一个段落之间
        output_params = self._extract_params(text, "输出参数", ["接口示例", "说明", "接口："])
        detail.output_params = output_params

        # 接口示例
        example = self._extract_example(text)
        detail.example = example

        # 说明
        notes_match = re.search(r"说明[：:]\s*(.+?)(?:\n接口|$)", text, re.DOTALL)
        if notes_match:
            detail.notes = notes_match.group(1).strip()[:500]

        return detail

    def _extract_params(
        self, text: str, start_marker: str, end_markers: list[str]
    ) -> list[ParamInfo]:
        """从文本中提取参数列表。

        在 start_marker 和 end_markers 之间的内容中查找 "名称/类型/描述" 表格。
        """
        # 找到起始位置
        start_idx = text.find(start_marker)
        if start_idx < 0:
            return []

        # 找到结束位置
        remaining = text[start_idx + len(start_marker):]
        end_idx = len(remaining)
        for marker in end_markers:
            pos = remaining.find(marker)
            if 0 <= pos < end_idx:
                end_idx = pos

        param_text = remaining[:end_idx]

        # 解析参数：寻找 "名称 类型 描述" 模式
        params = []
        # 匹配类似 "symbol str symbol='603777'；股票代码..." 的行
        param_pattern = re.compile(
            r"(\w+)\s+(str|int|float|bool|list|dict|datetime|None)\s+(.+?)(?:\n|$)"
        )
        for match in param_pattern.finditer(param_text):
            params.append(ParamInfo(
                name=match.group(1),
                type=match.group(2),
                description=match.group(3).strip(),
            ))

        return params

    def _extract_example(self, text: str) -> str:
        """从文本中提取接口示例代码。"""
        # 查找 "接口示例" 后面的代码
        example_match = re.search(
            r"接口示例.*?(?:```python|>>>)\s*\n(.*?)(?:```|\n\n\n|\Z)",
            text,
            re.DOTALL,
        )
        if example_match:
            return example_match.group(1).strip()[:1000]

        # 尝试直接查找 import akshare 代码行
        code_lines = []
        in_code = False
        for line in text.split("\n"):
            stripped = line.strip()
            if "import akshare" in stripped or stripped.startswith("ak.") or "ak." in stripped:
                in_code = True
            if in_code:
                if stripped and not any(kw in stripped for kw in ["接口", "输出", "输入", "说明", "限量"]):
                    code_lines.append(stripped)
                elif code_lines:
                    break
            if len(code_lines) > 10:
                break

        return "\n".join(code_lines).strip()[:1000]

    @staticmethod
    def _extract_category(page_path: str) -> str:
        """从页面路径提取类目名称。"data/stock/stock.html" -> "stock" """
        parts = page_path.replace("\\", "/").split("/")
        if len(parts) >= 3 and parts[0] == "data":
            return parts[1]
        return ""

    def _find_page_path(self, interface_name: str) -> str:
        """从本地索引文件中查找接口所在页面路径。"""
        if not self.cache_dir:
            return ""
        index_path = os.path.join(self.cache_dir, "tree_index.json")
        if not os.path.exists(index_path):
            return ""

        try:
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("flat_index", []):
                if entry.get("name") == interface_name:
                    return entry.get("page_path", "")
        except (json.JSONDecodeError, OSError):
            pass
        return ""

    # ── HTTP 请求 ──────────────────────────────────────────────────

    def _request(self, url: str) -> Optional[str]:
        """发送 HTTP GET 请求。"""
        try:
            time.sleep(REQUEST_DELAY)
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.content.decode("utf-8", errors="replace")
        except requests.RequestException as e:
            logger.error("请求失败: %s, error=%s", url, e)
            return None

    # ── 缓存管理 ──────────────────────────────────────────────────

    def _interface_cache_path(self, name: str) -> str:
        return os.path.join(self.cache_dir, "interfaces", f"{name}.json")

    def _page_cache_path(self, page_path: str) -> str:
        safe_name = page_path.replace("/", "_").replace("\\", "_")
        return os.path.join(self.cache_dir, "pages", f"{safe_name}.json")

    def _load_interface_cache(self, name: str) -> Optional[InterfaceDetail]:
        path = self._interface_cache_path(name)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return InterfaceDetail(**data)
        except (json.JSONDecodeError, Exception):
            return None

    def _save_interface_cache(self, name: str, detail: InterfaceDetail) -> None:
        if not self.cache_dir:
            return
        path = self._interface_cache_path(name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(detail.model_dump(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("缓存写入失败: %s", e)

    def _load_page_cache(self, page_path: str) -> Optional[list[InterfaceDetail]]:
        path = self._page_cache_path(page_path)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [InterfaceDetail(**item) for item in data]
        except (json.JSONDecodeError, Exception):
            return None

    def _save_page_cache(self, page_path: str, interfaces: list[InterfaceDetail]) -> None:
        if not self.cache_dir:
            return
        path = self._page_cache_path(page_path)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    [item.model_dump() for item in interfaces],
                    f, ensure_ascii=False, indent=2,
                )
        except OSError as e:
            logger.warning("缓存写入失败: %s", e)
