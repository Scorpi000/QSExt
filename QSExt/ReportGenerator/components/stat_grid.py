# -*- coding: utf-8 -*-
"""KPI 指标卡片组组件"""

from typing import Any, List

import pandas as pd
from .base import Component


class StatGrid(Component):
    """KPI 指标卡片组。

    YAML 中使用:
        component: stat_grid
        data:
          source: 0-Rank IC 分析
          key: 统计数据
        params:
          title: "IC 概览"       # 可选标题
          columns: 4             # 每行卡片数
          metrics:               # 要展示的指标列表
            - {label: "IC 均值", field: "IC均值", format: ".4f"}
            - {label: "ICIR",    field: "ICIR",   format: ".2f"}
            - {label: "胜率",    field: "胜率",    format: ".1%"}
    """

    name = "stat_grid"

    def render(self, data: Any, params: dict, theme: "Theme",  # noqa: F821
               renderer: "ReportRenderer") -> str:  # noqa: F821
        metrics: List[dict] = params.get("metrics", [])
        if not metrics:
            return ""

        cards = []
        for m in metrics:
            label = m.get("label", "")
            field = m.get("field", "")
            fmt = m.get("format", "")

            value = self._extract_value(data, field)
            cards.append(renderer.render_stat_card(label, value, fmt))

        columns = params.get("columns", 3)
        title = params.get("title", "")
        is_md = renderer.is_markdown
        title_html = ""
        if title:
            if is_md:
                title_html = f"**{title}**\n\n"
            else:
                title_html = f'<div class="table-title">{title}</div>\n'

        grid_html = renderer.render_grid(cards, columns=columns)
        return title_html + grid_html

    @staticmethod
    def _extract_value(data: Any, field: str) -> Any:
        """从 DataFrame/Series/dict 中提取指定字段的值。

        兼容两种 DataFrame 结构：
        - 标准：index=统计量名, columns=因子名
        - 转置：index=因子名, columns=统计量名（QuantStudio IC 模块输出）
        """
        if data is None:
            return "N/A"
        if isinstance(data, pd.DataFrame):
            if data.empty:
                return "N/A"
            # 优先按 index 查找（标准结构）
            if field in data.index:
                s = data.loc[field]
                if isinstance(s, pd.DataFrame):
                    # 重复列名导致 DataFrame，取第一行第一列
                    return s.iloc[0, 0] if s.size > 0 else "N/A"
                if isinstance(s, pd.Series):
                    return s.iloc[0] if len(s) > 0 else "N/A"
                return s
            # 按 columns 查找（转置结构）
            if field in data.columns:
                col = data[field]
                if isinstance(col, pd.DataFrame):
                    # 重复列名，取第一列
                    col = col.iloc[:, 0]
                return col.iloc[0] if len(col) > 0 else "N/A"
            return "N/A"
        if isinstance(data, pd.Series):
            if field in data.index:
                return data.loc[field]
            return "N/A"
        if isinstance(data, dict):
            return data.get(field, "N/A")
        return "N/A"
