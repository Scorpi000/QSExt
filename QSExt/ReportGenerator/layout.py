# -*- coding: utf-8 -*-
"""布局渲染器

解释 YAML 中声明的报告布局，遍历节点树，从 DataContext 获取数据，
实例化并驱动组件渲染，最终组装完整页面。
"""

from typing import Any

from QSExt.ReportGenerator.components.registry import ComponentRegistry


class LayoutRenderer:
    """解释 YAML 布局 → 驱动组件树渲染。

    遍历 report config 中声明的 sections 树，
    为每个组件解析数据、实例化、渲染、组装页面。
    """

    def render(self, report_config: dict, data_ctx: "DataContext",  # noqa: F821
               theme: "Theme", fmt: str = "html",
               global_params: dict = None) -> str:  # noqa: F821
        """渲染完整报告。

        Args:
            report_config: config.yaml 中 report 段落的 dict
            data_ctx: 数据上下文
            theme: 主题
            fmt: 输出格式 ("html" | "markdown")
            global_params: 注入到所有组件 params 的全局参数（优先级低于 YAML 中的 params）

        Returns:
            完整的报告字符串
        """
        renderer = self._get_renderer(fmt)

        # 生成页面标题
        factor_names = data_ctx.get("meta", "factor_names") or ["未知"]
        title_template = report_config.get(
            "page_title", "{factor_name} 测试报告"
        )
        title = title_template.format(
            factor_name=", ".join(factor_names),
            factor_count=len(factor_names)
        )

        fragments = []

        # 渲染页眉
        header_cfg = report_config.get("header")
        if header_cfg:
            header_html = self._render_section_node(
                header_cfg, data_ctx, theme, renderer, global_params
            )
            if header_html:
                fragments.append(header_html)

        # 渲染章节（跳过数据源不存在的章节）
        sections_cfg = report_config.get("sections", [])
        for sec_cfg in sections_cfg:
            if not self._section_has_data(sec_cfg, data_ctx):
                continue
            sec_html = self._render_section_node(
                sec_cfg, data_ctx, theme, renderer, global_params
            )
            if sec_html:
                fragments.append(sec_html)

        return renderer.assemble_page(fragments, title)

    @staticmethod
    def _get_renderer(fmt: str) -> "ReportRenderer":  # noqa: F821
        if fmt == "markdown":
            from QSExt.ReportGenerator.renderers.md_renderer import (
                MarkdownRenderer
            )
            return MarkdownRenderer()
        else:
            from QSExt.ReportGenerator.renderers.html_renderer import (
                HtmlRenderer
            )
            return HtmlRenderer()

    def _render_section_node(self, node: dict, data_ctx: "DataContext",  # noqa: F821
                             theme: "Theme",  # noqa: F821
                             renderer: "ReportRenderer",
                             global_params: dict = None) -> str:  # noqa: F821
        """渲染一个布局节点（section 或其他带 children 的节点）。

        递归处理：
        1. 如果有 children → 预解析每个 child 的数据引用，然后交 Section 渲染
        2. 叶子节点 → 解析数据，实例化组件，调用 render
        """
        comp_name = node.get("component", "section")
        params = dict(node.get("params", {}))
        title = node.get("title", params.get("title", ""))
        children = node.get("children", [])
        data_ref = node.get("data", {})

        # 如果没有指定 title 在 params 中，加入
        if title and "title" not in params:
            params["title"] = title

        # 合并全局参数（YAML params 优先）
        if global_params:
            params = {**global_params, **params}

        # 如果有 children → section 容器
        if children:
            # 递归解析所有嵌套 children 的数据引用 → 注入 _resolved_data
            def _resolve_children(nested_children):
                resolved = []
                for c in nested_children:
                    c = dict(c)  # 浅拷贝
                    c_data = c.get("data", {})
                    if isinstance(c_data, dict) and "source" in c_data:
                        c["_resolved_data"] = self._resolve_data(
                            c_data, data_ctx
                        )
                    # 合并全局参数（YAML params 优先）
                    if global_params:
                        c_params = c.get("params", {})
                        if isinstance(c_params, dict):
                            c["params"] = {**global_params, **c_params}
                    if c.get("children"):
                        c["params"] = dict(c.get("params", {}))
                        c["params"]["children"] = _resolve_children(
                            c["children"]
                        )
                    resolved.append(c)
                return resolved

            params["children"] = _resolve_children(children)
            comp_cls = ComponentRegistry.get(comp_name)()
            return comp_cls.render(params["children"], params, theme, renderer)

        # 叶子节点：解析数据并渲染
        else:
            comp = ComponentRegistry.get(comp_name)()
            data = self._resolve_data(data_ref, data_ctx)
            return comp.render(data, params, theme, renderer)

    def _resolve_data(self, data_ref: dict, data_ctx: "DataContext") -> Any:  # noqa: F821
        """从 DataContext 解析数据。

        YAML 格式：
            data:
              source: 0-Rank IC 分析    # module key in output dict
              key: 统计数据              # data key within module
        """
        if not data_ref:
            return None
        source = data_ref.get("source")
        key = data_ref.get("key")
        if source:
            return data_ctx.get(source, key)
        return data_ref  # 直接传值

    def _section_has_data(self, node: dict, data_ctx: "DataContext") -> bool:  # noqa: F821
        """检查一个布局节点是否有可用的数据。

        递归遍历节点的 children，只要有一个 child 的 data.source
        在 DataContext 中存在且非空，即返回 True。
        若节点本身没有 children，直接检查自身的 data 引用。

        特殊处理：data.source 为 "meta" 的引用始终视为有数据。
        """
        children = node.get("children", [])
        if children:
            return any(
                self._section_has_data(child, data_ctx)
                for child in children
            )

        # 叶子节点：检查数据引用
        data_ref = node.get("data", {})
        if not isinstance(data_ref, dict) or "source" not in data_ref:
            # 没有 data 引用的节点（如纯文本 section）始终渲染
            return True

        source = data_ref.get("source", "")
        if source == "meta":
            return True

        key = data_ref.get("key")
        data = data_ctx.get(source, key)
        if data is None:
            return False
        # DataFrame/Series 检查是否为空
        import pandas as pd
        if isinstance(data, (pd.DataFrame, pd.Series)):
            return not data.empty
        # dict 检查是否为空
        if isinstance(data, dict):
            return len(data) > 0
        return True
