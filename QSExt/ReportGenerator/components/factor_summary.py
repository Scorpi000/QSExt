# -*- coding: utf-8 -*-
"""因子概况卡片组件"""

from typing import Any

from .base import Component


class FactorSummary(Component):
    """因子基本信息展示卡片。

    YAML 中使用:
        component: factor_summary
        data:
          source: meta
          key: factor_info     # 由场景 prepare_data_context 注入
    """

    name = "factor_summary"

    def render(self, data: Any, params: dict, theme: "Theme",  # noqa: F821
               renderer: "ReportRenderer") -> str:  # noqa: F821
        if data is None:
            data = {}

        name = data.get("name", "未知因子")
        description = data.get("description", "")
        tags = data.get("tags", [])
        dt_start = data.get("dt_start", "")
        dt_end = data.get("dt_end", "")
        count = data.get("count", 1)

        tag_html = ""
        if tags:
            tag_spans = "".join(
                f'<span class="tag">{t}</span>' for t in tags
            )
            tag_html = f'<div class="factor-tags">{tag_spans}</div>'

        items = [
            ("因子名称", name),
            ("测试区间", f"{dt_start} ~ {dt_end}" if dt_start else "未指定"),
        ]
        if description:
            items.append(("描述", description))

        is_md = renderer.is_markdown

        if is_md:
            # Markdown：简洁的无序列表
            lines = [f"- **{label}**: {value}" for label, value in items]
            if tags:
                lines.append(f"- **标签**: {', '.join(tags)}")
            content = "\n".join(lines) + "\n"
        else:
            items_html = "".join(
                f'<div class="factor-info-item">'
                f'<span class="info-label">{label}: </span>'
                f'<span class="info-value">{value}</span>'
                f'</div>'
                for label, value in items
            )
            content = f'<div class="factor-summary">{items_html}{tag_html}</div>'

        title = params.get("title", "因子概况")
        return renderer.render_section(title, content, level=2)
