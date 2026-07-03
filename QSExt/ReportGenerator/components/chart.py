# -*- coding: utf-8 -*-
"""图表组件

将 DataFrame 渲染为 matplotlib Figure，通过 base64 PNG 嵌入报告。

扩展新图表类型：
    1. 写生成函数 _render_xxx(data, params, theme) → Figure
    2. Chart.register_chart_type("xxx", _render_xxx)
    3. YAML 中使用 type: xxx
"""

from typing import Callable, Dict

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .base import Component

# ---- 中文字体配置 ----
# 尝试多个常见中文字体，避免 CJK 字符缺失警告
_CJK_FONTS = [
    "Microsoft YaHei", "SimHei", "PingFang SC",
    "WenQuanYi Micro Hei", "Noto Sans CJK SC", "AR PL UMing CN",
]
_available_fonts = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
for _font in _CJK_FONTS:
    if _font in _available_fonts:
        matplotlib.rcParams["font.family"] = _font
        break
else:
    # 无中文字体时使用 sans-serif，配合负号显示
    matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["axes.unicode_minus"] = False


# ============================================================
# 图表生成函数（纯函数：DataFrame + params + theme → Figure）
# ============================================================

def _render_ic_bar(data: pd.DataFrame, params: dict,
                   theme: "Theme") -> Figure:  # noqa: F821
    """IC 柱状图 + 移动平均线"""
    fig = Figure(figsize=params.get("figsize", (16, 6)))
    ax = fig.add_subplot(111)

    colors = theme.chart_colors
    n_cols = len(data.columns)
    width = 0.8 / max(n_cols, 1)

    for i, col in enumerate(data.columns):
        series = data[col].dropna()
        if series.empty:
            continue
        x = np.arange(len(series))
        bars = ax.bar(x + i * width, series.values, width,
                      color=colors[i % len(colors)],
                      alpha=0.7, label=str(col))

    ax.set_title(params.get("title", "IC 分析"))
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_xlabel("时点")
    ax.set_ylabel("IC")
    fig.tight_layout()
    return fig


def _render_ic_decay_bar(data: pd.DataFrame, params: dict,
                         theme: "Theme") -> Figure:  # noqa: F821
    """IC 衰减柱状图：仅展示 IC平均值 列"""
    fig = Figure(figsize=params.get("figsize", (14, 6)))
    ax = fig.add_subplot(111)

    # 仅选取 IC平均值 列（兼容多因子合并后的列名）
    value_col = None
    for c in data.columns:
        if "IC平均值" in str(c) or "IC" in str(c):
            value_col = c
            break
    if value_col is None:
        value_col = data.columns[0]

    values = data[value_col].dropna()
    x = np.arange(len(values))
    color = theme.chart_colors[0]

    ax.bar(x, values, 0.6, color=color, alpha=0.8)
    ax.set_title(params.get("title", "IC 衰减分析"))
    ax.set_xticks(x)
    ax.set_xticklabels([str(i) for i in data.index], rotation=0)
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_xlabel("调仓周期（月）")
    ax.set_ylabel("IC 均值")
    fig.tight_layout()
    return fig


def _render_nav_curve(data: pd.DataFrame, params: dict,
                      theme: "Theme") -> Figure:  # noqa: F821
    """净值曲线"""
    fig = Figure(figsize=params.get("figsize", (16, 7)))
    ax = fig.add_subplot(111)

    colors = theme.chart_colors

    for i, col in enumerate(data.columns):
        series = data[col].dropna()
        if series.empty:
            continue
        ax.plot(series.index, series.values,
                color=colors[i % len(colors)],
                linewidth=1.5, label=str(col), alpha=0.85)

    ax.axhline(y=1, color="gray", linestyle="--", linewidth=0.8)
    ax.set_title(params.get("title", "净值走势"))
    ax.legend(loc="upper left", fontsize=9, ncol=2)
    ax.set_ylabel("净值")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.2f}"))
    fig.tight_layout()
    return fig


def _render_long_excess_nav(data: pd.DataFrame, params: dict,
                            theme: "Theme") -> Figure:  # noqa: F821
    """多头超额净值曲线：各分位数组合的超额净值走势"""
    fig = Figure(figsize=params.get("figsize", (10, 6)))
    ax = fig.add_subplot(111)

    colors = theme.chart_colors
    # 选取分位数列（排除基准和多空列）
    cols = [c for c in data.columns
            if str(c).startswith("P") and "-" not in str(c)
            and str(c) != "基准"]

    for i, col in enumerate(cols):
        series = data[col].dropna()
        if series.empty:
            continue
        ax.plot(series.index, series.values,
                color=colors[i % len(colors)],
                linewidth=1.5, label=str(col), alpha=0.85)

    ax.axhline(y=1, color="gray", linestyle="--", linewidth=0.8)
    ax.set_title(params.get("title", "多头超额净值"))
    ax.legend(loc="upper left", fontsize=9, ncol=2)
    ax.set_ylabel("超额净值")
    fig.tight_layout()
    return fig


def _render_long_short_nav(data: pd.DataFrame, params: dict,
                           theme: "Theme") -> Figure:  # noqa: F821
    """多空净值曲线：选取多空组合（含 - 的列名）"""
    fig = Figure(figsize=params.get("figsize", (10, 6)))
    ax = fig.add_subplot(111)

    # 选取多空列：列名含 "-"
    ls_cols = [c for c in data.columns if "-" in str(c)]
    col = ls_cols[0] if ls_cols else data.columns[-1]
    series = data[col].dropna()
    color = theme.chart_colors[1]

    ax.plot(series.index, series.values, color=color, linewidth=1.8, label=str(col))
    ax.axhline(y=1, color="gray", linestyle="--", linewidth=0.8)
    ax.fill_between(
        series.index, 1, series.values,
        where=(series.values >= 1),
        alpha=0.15, color=theme.chart_colors[2]
    )
    ax.fill_between(
        series.index, 1, series.values,
        where=(series.values < 1),
        alpha=0.15, color=theme.chart_colors[3]
    )
    ax.set_title(params.get("title", "多空净值"))
    ax.legend(loc="upper left", fontsize=9)
    ax.set_ylabel("净值")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.2f}"))
    fig.tight_layout()
    return fig


def _render_turnover_area(data: pd.DataFrame, params: dict,
                          theme: "Theme") -> Figure:  # noqa: F821
    """换手率面积图"""
    fig = Figure(figsize=params.get("figsize", (16, 5)))
    ax = fig.add_subplot(111)

    colors = theme.chart_colors

    for i, col in enumerate(data.columns):
        series = data[col].dropna()
        if series.empty:
            continue
        ax.fill_between(range(len(series)), series.values,
                        alpha=0.3, color=colors[i % len(colors)],
                        label=str(col))
        ax.plot(range(len(series)), series.values,
                color=colors[i % len(colors)],
                linewidth=1.5, alpha=0.8)

    ax.set_title(params.get("title", "因子换手率"))
    ax.legend(loc="upper right", fontsize=9)
    ax.set_ylabel("换手率")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.2f}"))
    fig.tight_layout()
    return fig


def _render_heatmap(data: pd.DataFrame, params: dict,
                    theme: "Theme") -> Figure:  # noqa: F821
    """热力图"""
    fig = Figure(figsize=params.get("figsize", (10, 8)))
    ax = fig.add_subplot(111)

    im = ax.imshow(data.values, aspect="auto", cmap="RdYlBu_r",
                   vmin=-1, vmax=1)
    fig.colorbar(im, ax=ax, shrink=0.8)

    ax.set_xticks(range(len(data.columns)))
    ax.set_xticklabels([str(c) for c in data.columns], rotation=45,
                       ha="right", fontsize=8)
    ax.set_yticks(range(len(data.index)))
    ax.set_yticklabels([str(i) for i in data.index], fontsize=8)
    ax.set_title(params.get("title", "相关性热力图"))
    fig.tight_layout()
    return fig


def _render_bar_chart(data: pd.DataFrame, params: dict,
                      theme: "Theme") -> Figure:  # noqa: F821
    """通用柱状图"""
    fig = Figure(figsize=params.get("figsize", (14, 6)))
    ax = fig.add_subplot(111)

    colors = theme.chart_colors
    orientation = params.get("orientation", "vertical")

    if orientation == "horizontal":
        values = data.iloc[:, 0].values if len(data.columns) > 0 else []
        labels = [str(i) for i in data.index]
        ax.barh(range(len(labels)), values,
                color=colors[0], alpha=0.8)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels)
    else:
        n_cols = len(data.columns)
        width = 0.8 / max(n_cols, 1)
        x = np.arange(len(data.index))
        for i, col in enumerate(data.columns):
            ax.bar(x + i * width, data[col].values, width,
                   color=colors[i % len(colors)],
                   alpha=0.8, label=str(col))
        ax.set_xticks(x + width * (n_cols - 1) / 2)
        ax.set_xticklabels([str(i) for i in data.index], rotation=45,
                           ha="right")
        ax.legend(loc="upper right", fontsize=9)

    ax.set_title(params.get("title", ""))
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
    fig.tight_layout()
    return fig


def _render_line_chart(data: pd.DataFrame, params: dict,
                       theme: "Theme") -> Figure:  # noqa: F821
    """通用折线图"""
    fig = Figure(figsize=params.get("figsize", (14, 6)))
    ax = fig.add_subplot(111)

    colors = theme.chart_colors

    for i, col in enumerate(data.columns):
        series = data[col].dropna()
        if series.empty:
            continue
        ax.plot(series.index if hasattr(series, "index") else range(len(series)),
                series.values,
                color=colors[i % len(colors)],
                linewidth=2, label=str(col), alpha=0.85)

    ax.set_title(params.get("title", ""))
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
    if len(data.columns) > 1:
        ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    return fig


# ============================================================
# Chart 组件
# ============================================================

class Chart(Component):
    """图表组件。

    YAML 中使用:
        component: chart
        params:
          type: ic_bar        # 图表类型
          title: "标题"        # 图表标题
          figsize: [16, 6]    # 可选，画布大小
    """

    name = "chart"

    CHART_FUNCTIONS: Dict[str, Callable] = {}

    @classmethod
    def register_chart_type(cls, name: str, func: Callable):
        """注册新的图表类型生成函数"""
        cls.CHART_FUNCTIONS[name] = func

    def render(self, data: pd.DataFrame, params: dict, theme: "Theme",  # noqa: F821
               renderer: "ReportRenderer") -> str:  # noqa: F821
        chart_type = params.get("type", "bar_chart")
        chart_func = self.CHART_FUNCTIONS.get(chart_type)
        if chart_func is None:
            raise ValueError(
                f"未知的图表类型: '{chart_type}'，"
                f"可用类型: {list(self.CHART_FUNCTIONS.keys())}"
            )

        if data is None or (isinstance(data, pd.DataFrame) and data.empty):
            return renderer.render_text(
                f"> ⚠ 图表数据为空（类型: {chart_type}）"
            )

        fig = chart_func(data, params, theme)
        result = renderer.render_chart(
            fig, title=params.get("title")
        )
        # 显式关闭 Figure 防止 matplotlib 内存泄漏
        import matplotlib.pyplot as plt
        plt.close(fig)
        return result


# ---- 注册内置图表类型 ----
Chart.register_chart_type("ic_bar", _render_ic_bar)
Chart.register_chart_type("ic_decay_bar", _render_ic_decay_bar)
Chart.register_chart_type("nav_curve", _render_nav_curve)
Chart.register_chart_type("long_excess_nav", _render_long_excess_nav)
Chart.register_chart_type("long_short_nav", _render_long_short_nav)
Chart.register_chart_type("turnover_area", _render_turnover_area)
Chart.register_chart_type("heatmap", _render_heatmap)
Chart.register_chart_type("bar_chart", _render_bar_chart)
Chart.register_chart_type("line_chart", _render_line_chart)
