# -*- coding: utf-8 -*-
"""渲染器抽象基类"""

from abc import ABCMeta, abstractmethod
from typing import Optional, Any
from matplotlib.figure import Figure
import pandas as pd


class ReportRenderer(metaclass=ABCMeta):
    """报告渲染器抽象基类，定义报表片段生成接口。

    两种具体实现：
    - HtmlRenderer: 自包含 HTML，图表 base64 内嵌
    - MarkdownRenderer: 纯文本 Markdown
    """

    @property
    def is_markdown(self) -> bool:
        return False

    @abstractmethod
    def render_section(self, title: str, content: str, level: int = 1,
                       collapsible: bool = False) -> str:
        """渲染一个章节标题 + 内容容器。

        Args:
            title: 章节标题
            content: 章节内容（HTML 或 Markdown 片段）
            level: 标题级别（1 = <h2>, 2 = <h3>...）
            collapsible: 是否可折叠
        """

    @abstractmethod
    def render_table(self, df: pd.DataFrame, title: Optional[str] = None,
                     precision: int = 4, sortable: bool = True,
                     include_histogram: bool = False) -> str:
        """渲染 DataFrame 为表格。

        Args:
            df: 要渲染的 DataFrame
            title: 表格标题
            precision: 数值精度（小数位数）
            sortable: 是否支持排序（仅 HTML 有效）
            include_histogram: 是否在数值列嵌入直方图
        """

    @abstractmethod
    def render_chart(self, fig: Figure, title: Optional[str] = None) -> str:
        """渲染 matplotlib Figure 为嵌入图像。

        Args:
            fig: matplotlib Figure 对象
            title: 图表标题
        """

    def render_plotly_chart(self, fig, title: Optional[str] = None) -> str:
        """渲染 plotly Figure 为交互式 HTML。

        Args:
            fig: plotly.graph_objects.Figure 对象
            title: 图表标题

        Returns:
            HTML 片段（默认回退到静态渲染）
        """
        return ""

    @abstractmethod
    def render_stat_card(self, label: str, value: Any,
                         format_str: str = "") -> str:
        """渲染一个 KPI 指标卡片。

        Args:
            label: 指标名称
            value: 指标值
            format_str: 格式化字符串（如 ".2%", ".2f"）
        """

    @abstractmethod
    def render_grid(self, cards: list, columns: int = 3) -> str:
        """将多个卡片按网格布局排列。

        Args:
            cards: 卡片 HTML 片段列表
            columns: 列数
        """

    @abstractmethod
    def render_text(self, text: str) -> str:
        """渲染 Markdown 文本块。"""

    @abstractmethod
    def assemble_page(self, fragments: list, title: str,
                      css: str = "", js: str = "") -> str:
        """将章节片段组装成完整页面。

        Args:
            fragments: 各章节的 HTML/Markdown 片段列表
            title: 页面标题
            css: 额外 CSS
            js: 额外 JavaScript
        """
