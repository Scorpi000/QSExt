# -*- coding: utf-8 -*-
"""章节布局容器组件"""

from typing import Any, Optional

from .base import Component
from .registry import ComponentRegistry


class Section(Component):
    """章节布局容器。

    负责：
    1. 渲染章节标题（使用 renderer.render_section）
    2. 遍历 children 节点，逐个实例化组件并渲染
    3. 按 layout 类型（single/two_column/grid）打包子元素 HTML

    YAML 中使用:
        - id: my_section
          title: "章节标题"
          params:
            layout: two_column
            columns: 2
            collapsible: false
          children:
            - component: chart
              span: left
              data: ...
            - component: data_table
              span: right
              data: ...
    """

    name = "section"

    def render(self, data: Any, params: dict, theme: "Theme",  # noqa: F821
               renderer: "ReportRenderer") -> str:  # noqa: F821
        layout: str = params.get("layout", "single")
        columns: int = params.get("columns", 3)
        collapsible: bool = params.get("collapsible", False)
        title: str = params.get("title", "")
        children: list = params.get("children", [])

        if not children:
            return ""

        # 渲染子元素
        fragments = []
        for child in children:
            frag = self._render_child(child, theme, renderer)
            if frag:
                fragments.append(frag)

        if not fragments:
            return ""

        # 布局打包：Markdown 格式跳过 HTML 布局 div，直接拼接
        if renderer.is_markdown:
            content = "".join(fragments)
        else:
            content = theme.apply_layout(fragments, layout, columns=columns)

        if title:
            return renderer.render_section(
                title, content, level=1, collapsible=collapsible
            )
        return content

    @staticmethod
    def _render_child(child: dict, theme: "Theme",  # noqa: F821
                      renderer: "ReportRenderer") -> str:  # noqa: F821
        """渲染单个子节点"""
        comp_name = child.get("component", "")
        if not comp_name:
            return ""

        try:
            comp_cls = ComponentRegistry.get(comp_name)
        except KeyError:
            return renderer.render_text(
                f"> ⚠ 未知组件: '{comp_name}'"
            )

        comp = comp_cls()
        child_data = child.get("data", {})
        child_params = child.get("params", {})

        # 解析数据：
        # 1. 优先使用 _resolved_data（由 LayoutRenderer 或测试预先注入）
        # 2. 如果 data 是 {source, key} 引用格式 → 由 LayoutRenderer 预处理
        # 3. 否则直接传入
        if "_resolved_data" in child:
            child_data = child["_resolved_data"]
        elif isinstance(child_data, dict) and "source" in child_data:
            # 未经 LayoutRenderer 预处理的数据引用 → 无法解析
            return renderer.render_text(
                f"> ⚠ 组件 '{comp_name}' 数据未解析 "
                f"(source: {child_data.get('source')})"
            )

        return comp.render(child_data, child_params, theme, renderer)
