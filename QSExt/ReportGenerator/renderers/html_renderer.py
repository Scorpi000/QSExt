# -*- coding: utf-8 -*-
"""HTML 输出渲染器"""

import io
import base64
from typing import Optional, Any

import pandas as pd
from matplotlib.figure import Figure

from .base import ReportRenderer


class HtmlRenderer(ReportRenderer):
    """HTML 格式渲染器，生成自包含 HTML 页面（图表 base64 内嵌）。

    复用的 QSExt 工具：
    - QSExt.Tools.HTML.add_sort_to_html_table
    - QSExt.Tools.HTML.add_filter_to_html_table
    - QSExt.Tools.Visualization.dataframe2html_with_histograms
    """

    def render_section(self, title: str, content: str, level: int = 1,
                       collapsible: bool = False) -> str:
        tag = f"h{level + 1}"
        cls = "section-title"
        if collapsible:
            cls += " collapsible"
            onclick = ' onclick="this.classList.toggle(\'collapsed\');' \
                      'this.nextElementSibling.classList.toggle(\'collapsed\');"'
        else:
            onclick = ""
        return (
            f'<div class="section">\n'
            f'  <{tag} class="{cls}"{onclick}>{title}</{tag}>\n'
            f'  <div class="section-content">\n{content}\n  </div>\n'
            f'</div>\n'
        )

    def render_table(self, df: pd.DataFrame, title: Optional[str] = None,
                     precision: int = 4, sortable: bool = True,
                     include_histogram: bool = False) -> str:
        # 格式化数值
        df_display = df.copy()
        for col in df_display.select_dtypes(include=["float", "int"]).columns:
            df_display[col] = df_display[col].map(
                lambda x: f"{x:.{precision}f}" if isinstance(x, (int, float)) and pd.notnull(x) else ""
            )

        if include_histogram:
            from QSExt.Tools.Visualization import dataframe2html_with_histograms
            html = dataframe2html_with_histograms(
                df, number_format=f"{{:.{precision}f}}"
            )
        else:
            html = df_display.to_html(classes="report-table", border=0,
                                       escape=False, index=True)

        if sortable:
            from QSExt.Tools.HTML import add_sort_to_html_table
            try:
                html = add_sort_to_html_table(html)
            except Exception:
                pass  # 排序注入失败时静默降级

        title_html = ""
        if title:
            title_html = f'<div class="table-title">{title}</div>\n'
        return f'<div class="table-container">\n{title_html}{html}\n</div>'

    def render_chart(self, fig: Figure, title: Optional[str] = None) -> str:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode("utf-8")
        buf.close()

        return (
            f'<div class="chart-container">\n'
            f'<img src="data:image/png;base64,{img_b64}" '
            f'alt="{title or "chart"}">\n'
            f'</div>'
        )

    def render_stat_card(self, label: str, value: Any,
                         format_str: str = "") -> str:
        if format_str and isinstance(value, (int, float)):
            try:
                value = format(value, format_str)
            except (ValueError, TypeError):
                value = str(value)
        else:
            value = str(value) if value is not None else "N/A"
        return (
            f'<div class="stat-card">'
            f'<div class="stat-value">{value}</div>'
            f'<div class="stat-label">{label}</div>'
            f'</div>'
        )

    def render_grid(self, cards: list, columns: int = 3) -> str:
        return (
            f'<div class="stat-grid" style="grid-template-columns:'
            f'repeat({columns}, 1fr);">{"".join(cards)}</div>'
        )

    def render_text(self, text: str) -> str:
        # 简单的换行转 <br>
        return f'<p>{text.replace(chr(10), "<br>")}</p>'

    def assemble_page(self, fragments: list, title: str,
                      css: str = "", js: str = "") -> str:
        # 导入主题获取基础 CSS
        from QSExt.ReportGenerator.themes.base import Theme
        theme = Theme()
        base_css = theme.get_base_css()
        return (
            f'<!DOCTYPE html>\n'
            f'<html lang="zh-CN">\n<head>\n'
            f'<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,'
            f'initial-scale=1.0">\n'
            f'<title>{title}</title>\n'
            f'{base_css}\n'
            f'{css}\n'
            f'</head>\n<body>\n'
            f'<h1 class="page-title">{title}</h1>\n'
            f'{"".join(fragments)}\n'
            f'{js}\n'
            f'</body>\n</html>'
        )
