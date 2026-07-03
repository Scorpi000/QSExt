# -*- coding: utf-8 -*-
"""数据表组件"""

import pandas as pd
from .base import Component


class DataTable(Component):
    """数据表组件。

    YAML 中使用:
        component: data_table
        params:
          title: "表格标题"      # 可选
          precision: 4          # 数值精度
          sortable: true        # 是否支持排序
          include_histogram: false  # 是否嵌入直方图
    """

    name = "data_table"

    def render(self, data: pd.DataFrame, params: dict, theme: "Theme",  # noqa: F821
               renderer: "ReportRenderer") -> str:  # noqa: F821
        if data is None or (isinstance(data, pd.DataFrame) and data.empty):
            return renderer.render_text("> ⚠ 表格数据为空")

        precision = params.get("precision", 4)
        sortable = params.get("sortable", True)
        include_histogram = params.get("include_histogram", False)
        title = params.get("title")
        transpose = params.get("transpose", False)

        if transpose and isinstance(data, pd.DataFrame):
            data = data.T

        return renderer.render_table(
            data, title=title, precision=precision,
            sortable=sortable, include_histogram=include_histogram
        )
