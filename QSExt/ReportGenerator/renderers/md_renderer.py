# -*- coding: utf-8 -*-
"""Markdown 输出渲染器"""

from typing import Optional, Any

import pandas as pd
from matplotlib.figure import Figure

from .base import ReportRenderer


class MarkdownRenderer(ReportRenderer):
    """Markdown 格式渲染器，生成纯 Markdown 文本。

    复用 QSExt.Tools.Markdown 转换 HTML 表格。
    """

    @property
    def is_markdown(self) -> bool:
        return True

    def render_section(self, title: str, content: str, level: int = 1,
                       collapsible: bool = False) -> str:
        prefix = "#" * (level + 1)
        return f"\n{prefix} {title}\n\n{content}\n"

    def render_table(self, df: pd.DataFrame, title: Optional[str] = None,
                     precision: int = 4, sortable: bool = True,
                     include_histogram: bool = False) -> str:
        df_display = df.copy()
        for col in df_display.select_dtypes(include=["float", "int"]).columns:
            df_display[col] = df_display[col].map(
                lambda x: f"{x:.{precision}f}" if isinstance(x, (int, float)) and pd.notnull(x) else ""
            )

        html = df_display.to_html(border=0, escape=False, index=True)
        from QSExt.Tools.Markdown import html_table_to_markdown
        try:
            md = html_table_to_markdown(html)
        except Exception:
            try:
                md = df.to_markdown(floatfmt=f".{precision}f")
            except Exception:
                md = df.to_string(float_format=lambda x: f"{x:.{precision}f}")

        title_md = f"**{title}**\n\n" if title else ""
        return f"{title_md}{md}\n"

    def render_chart(self, fig: Figure, title: Optional[str] = None) -> str:
        # Markdown 不嵌入图表，静默跳过
        return ""

    def render_stat_card(self, label: str, value: Any,
                         format_str: str = "") -> str:
        if format_str and isinstance(value, (int, float)):
            try:
                value = format(value, format_str)
            except (ValueError, TypeError):
                value = str(value)
        return f"| **{label}** | {value} |\n"

    def render_grid(self, cards: list, columns: int = 3) -> str:
        # 提取 label 和 value 重组为单行表格
        labels, values = [], []
        for card in cards:
            parts = card.strip().strip("|").split("|")
            if len(parts) >= 2:
                labels.append(parts[0].strip().strip("*"))
                values.append(parts[1].strip())
        header = "| " + " | ".join(labels) + " |\n"
        sep = "|" + "|".join(["---"] * len(labels)) + "|\n"
        row = "| " + " | ".join(values) + " |\n"
        return header + sep + row + "\n"

    def render_text(self, text: str) -> str:
        return f"{text}\n\n"

    def assemble_page(self, fragments: list, title: str,
                      css: str = "", js: str = "") -> str:
        return (
            f"# {title}\n\n"
            f"{'---'}\n\n"
            f"{''.join(fragments)}\n"
        )
