# -*- coding: utf-8 -*-
"""主题基类"""

from typing import List


class Theme:
    """报告主题：颜色、字体、间距等视觉参数。

    通过继承覆盖属性来创建新主题，YAML 中 theme: "dark" 即可切换。
    """
    name: str = "default"

    # ---- 颜色 ----
    primary_color: str = "#2B579A"
    accent_color: str = "#4472C4"
    bg_color: str = "#FFFFFF"
    text_color: str = "#333333"
    muted_text_color: str = "#666666"
    border_color: str = "#E0E0E0"

    # ---- 图表配色（按序循环，多系列时自动分色）----
    chart_colors: List[str] = [
        "#4472C4", "#ED7D31", "#A5A5A5", "#FFC000",
        "#5B9BD5", "#70AD47", "#264478", "#9B59B6"
    ]

    # ---- 排版 ----
    font_family: str = "Microsoft YaHei, \"PingFang SC\", sans-serif"
    base_font_size: str = "14px"
    title_size: str = "1.6em"
    section_size: str = "1.25em"
    table_font_size: str = "0.9em"
    card_value_size: str = "1.4em"
    card_label_size: str = "0.8em"

    # ---- 间距 ----
    page_padding: str = "24px"
    section_margin: str = "28px 0 16px 0"
    card_padding: str = "16px 20px"
    card_margin: str = "8px"

    # ---- 圆角 ----
    card_radius: str = "8px"
    table_radius: str = "6px"

    # ---- 表格 ----
    table_header_bg: str = "#F5F7FA"
    table_stripe_bg: str = "#FAFBFC"
    table_hover_bg: str = "#F0F4F8"

    def apply_layout(self, fragments: List[str], layout: str,
                     columns: int = 3) -> str:
        """将片段按布局类型打包为 HTML 结构。

        Args:
            fragments: HTML 片段列表
            layout: 布局类型 (single / two_column / grid)
            columns: grid 布局的列数
        """
        if layout == "single":
            return f'<div class="layout-single">{"".join(fragments)}</div>'
        elif layout == "two_column":
            left = fragments[0] if len(fragments) > 0 else ""
            right = fragments[1] if len(fragments) > 1 else ""
            return (
                f'<div class="layout-two-col">'
                f'<div class="col-left">{left}</div>'
                f'<div class="col-right">{right}</div>'
                f'</div>'
            )
        elif layout == "grid":
            return (
                f'<div class="layout-grid" style="grid-template-columns:'
                f'repeat({columns}, 1fr);">{"".join(fragments)}</div>'
            )
        else:
            return "".join(fragments)

    def get_base_css(self) -> str:
        """生成基础 CSS 样式表"""
        return f"""
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: {self.font_family};
                font-size: {self.base_font_size};
                color: {self.text_color};
                background: {self.bg_color};
                padding: {self.page_padding};
                line-height: 1.6;
            }}
            .page-title {{
                font-size: {self.title_size};
                color: {self.primary_color};
                text-align: center;
                margin-bottom: 24px;
                padding-bottom: 12px;
                border-bottom: 2px solid {self.primary_color};
            }}
            .section {{
                margin: {self.section_margin};
            }}
            .section-title {{
                font-size: {self.section_size};
                color: {self.primary_color};
                margin-bottom: 12px;
                padding-left: 8px;
                border-left: 4px solid {self.accent_color};
            }}
            .section-title.collapsible {{
                cursor: pointer;
                user-select: none;
            }}
            .section-title.collapsible::after {{
                content: " ▼";
                font-size: 0.7em;
            }}
            .section-title.collapsible.collapsed::after {{
                content: " ▶";
            }}
            .section-content.collapsed {{ display: none; }}

            .layout-single {{ width: 100%; }}
            .layout-two-col {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 16px;
            }}
            .layout-grid {{
                display: grid;
                gap: 12px;
            }}

            .stat-grid {{
                display: flex;
                flex-wrap: wrap;
                gap: {self.card_margin};
            }}
            .stat-card {{
                flex: 1;
                min-width: 140px;
                background: {self.bg_color};
                border: 1px solid {self.border_color};
                border-radius: {self.card_radius};
                padding: {self.card_padding};
                text-align: center;
            }}
            .stat-card .stat-value {{
                font-size: {self.card_value_size};
                font-weight: 600;
                color: {self.primary_color};
            }}
            .stat-card .stat-label {{
                font-size: {self.card_label_size};
                color: {self.muted_text_color};
                margin-top: 4px;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                font-size: {self.table_font_size};
                border-radius: {self.table_radius};
                overflow: hidden;
                border: 1px solid {self.border_color};
            }}
            thead th {{
                background: {self.table_header_bg};
                color: {self.text_color};
                padding: 8px 12px;
                text-align: left;
                font-weight: 600;
                border-bottom: 2px solid {self.border_color};
            }}
            tbody td {{
                padding: 6px 12px;
                border-bottom: 1px solid {self.border_color};
            }}
            tbody tr:nth-child(even) {{
                background: {self.table_stripe_bg};
            }}
            tbody tr:hover {{
                background: {self.table_hover_bg};
            }}

            .chart-container {{
                text-align: center;
                margin: 16px 0;
            }}
            .chart-container img {{
                max-width: 100%;
                height: auto;
            }}
            .chart-title {{
                font-size: 1em;
                color: {self.muted_text_color};
                margin-bottom: 8px;
            }}
            .table-title {{
                font-size: 1em;
                color: {self.muted_text_color};
                margin-bottom: 8px;
            }}

            .factor-summary {{
                display: flex;
                gap: 16px;
                align-items: flex-start;
                flex-wrap: wrap;
            }}
            .factor-info-item {{
                margin: 4px 16px 4px 0;
            }}
            .factor-info-item .info-label {{
                font-size: 0.8em;
                color: {self.muted_text_color};
            }}
            .factor-info-item .info-value {{
                font-weight: 600;
            }}
        </style>
        """
