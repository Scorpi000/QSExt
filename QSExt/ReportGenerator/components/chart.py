# -*- coding: utf-8 -*-
"""图表组件

将 DataFrame 渲染为 matplotlib 或 plotly 图表，嵌入报告。

扩展新图表类型：
    1. 写生成函数 _render_xxx(data, params, theme) → matplotlib.Figure 或 plotly.Figure
    2. Chart.register_chart_type("engine", "xxx", _render_xxx)
    3. YAML 中使用 type: xxx
"""

from typing import Callable, Dict, Tuple

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
# 工具函数
# ============================================================

def _pick_date_format(index: pd.DatetimeIndex) -> str:
    """根据数据频率自动选择日期格式：月度→YYYY-MM，日度→YYYY-MM-DD"""
    if len(index) < 2:
        return "%Y-%m-%d"
    gaps = pd.Series((index[1:] - index[:-1]).days)
    median_gap_days = gaps.median()
    return "%Y-%m" if median_gap_days >= 25 else "%Y-%m-%d"


def _set_datetime_xticks(ax, index: pd.DatetimeIndex, max_labels: int = 20):
    """在数据实际位置上设置日期刻度，标签过多时等距抽稀，避免堆叠。"""
    n = len(index)
    step = max(1, n // max_labels)
    tick_locs = list(range(0, n, step))
    if tick_locs[-1] != n - 1:
        tick_locs.append(n - 1)
    fmt = _pick_date_format(index)
    ax.set_xticks(tick_locs)
    ax.set_xticklabels(
        [index[i].strftime(fmt) for i in tick_locs],
        rotation=45, ha="right", fontsize=8,
    )


def _clean_data(data: pd.DataFrame) -> pd.DataFrame:
    """去除缺失行，保证绘图数据连续紧凑。"""
    return data.dropna(how="all").dropna(subset=[data.columns[0]])


def _to_plotly_x(index) -> list:
    """将 index 转为 plotly x 轴数据（datetime 保持原样，其他转 str）。"""
    if isinstance(index, pd.DatetimeIndex):
        return index
    return [str(i) for i in index]


# ============================================================
# matplotlib 图表生成函数
# ============================================================

def _render_ic_bar(data: pd.DataFrame, params: dict,
                   theme: "Theme") -> Figure:  # noqa: F821
    """IC 柱状图 + 移动平均线（matplotlib）"""
    fig = Figure(figsize=params.get("figsize", (16, 6)))
    ax = fig.add_subplot(111)

    data = _clean_data(data)
    colors = theme.chart_colors
    n_cols = len(data.columns)
    n_bars = len(data)
    width = 0.8 / max(n_cols, 1)

    for i, col in enumerate(data.columns):
        vals = data[col].values
        ax.bar(np.arange(n_bars) + i * width, vals, width,
               color=colors[i % len(colors)],
               alpha=0.7, label=str(col))

    if isinstance(data.index, pd.DatetimeIndex):
        _set_datetime_xticks(ax, data.index)
    else:
        ax.set_xticks(np.arange(n_bars))
        ax.set_xticklabels([str(i) for i in data.index], rotation=45, ha="right", fontsize=8)

    ax.set_title(params.get("title", "IC 分析"))
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_xlabel("时点")
    ax.set_ylabel("IC")
    fig.tight_layout()
    return fig


def _render_ic_decay_bar(data: pd.DataFrame, params: dict,
                         theme: "Theme") -> Figure:  # noqa: F821
    """IC 衰减柱状图（matplotlib）"""
    fig = Figure(figsize=params.get("figsize", (14, 6)))
    ax = fig.add_subplot(111)

    value_col = None
    for c in data.columns:
        if "IC平均值" in str(c) or "IC" in str(c):
            value_col = c
            break
    if value_col is None:
        value_col = data.columns[0]

    values = data[value_col].dropna()
    x = np.arange(len(values))
    ax.bar(x, values, 0.6, color=theme.chart_colors[0], alpha=0.8)
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
    """净值曲线（matplotlib）"""
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
    """多头超额净值曲线（matplotlib）"""
    fig = Figure(figsize=params.get("figsize", (10, 6)))
    ax = fig.add_subplot(111)

    colors = theme.chart_colors
    cols = [c for c in data.columns
            if str(c).startswith("P") and "-" not in str(c) and str(c) != "基准"]

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
    """多空净值曲线（matplotlib）"""
    fig = Figure(figsize=params.get("figsize", (10, 6)))
    ax = fig.add_subplot(111)

    ls_cols = [c for c in data.columns if "-" in str(c)]
    col = ls_cols[0] if ls_cols else data.columns[-1]
    series = data[col].dropna()
    color = theme.chart_colors[1]

    ax.plot(series.index, series.values, color=color, linewidth=1.8, label=str(col))
    ax.axhline(y=1, color="gray", linestyle="--", linewidth=0.8)
    ax.fill_between(series.index, 1, series.values,
                    where=(series.values >= 1), alpha=0.15, color=theme.chart_colors[2])
    ax.fill_between(series.index, 1, series.values,
                    where=(series.values < 1), alpha=0.15, color=theme.chart_colors[3])
    ax.set_title(params.get("title", "多空净值"))
    ax.legend(loc="upper left", fontsize=9)
    ax.set_ylabel("净值")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.2f}"))
    fig.tight_layout()
    return fig


def _render_turnover_area(data: pd.DataFrame, params: dict,
                          theme: "Theme") -> Figure:  # noqa: F821
    """换手率面积图（matplotlib）"""
    fig = Figure(figsize=params.get("figsize", (16, 5)))
    ax = fig.add_subplot(111)

    data = _clean_data(data)
    colors = theme.chart_colors
    is_datetime = isinstance(data.index, pd.DatetimeIndex)
    n = len(data)
    x = np.arange(n)

    for i, col in enumerate(data.columns):
        vals = data[col].values
        ax.fill_between(x, vals, alpha=0.3, color=colors[i % len(colors)], label=str(col))
        ax.plot(x, vals, color=colors[i % len(colors)], linewidth=1.5, alpha=0.8)

    if is_datetime:
        _set_datetime_xticks(ax, data.index)
    else:
        ax.set_xticks(x)
        ax.set_xticklabels([str(i) for i in data.index], rotation=45, ha="right", fontsize=8)

    ax.set_title(params.get("title", "因子换手率"))
    ax.legend(loc="upper right", fontsize=9)
    ax.set_ylabel("换手率")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.2f}"))
    fig.tight_layout()
    return fig


def _render_heatmap(data: pd.DataFrame, params: dict,
                    theme: "Theme") -> Figure:  # noqa: F821
    """热力图（matplotlib）"""
    fig = Figure(figsize=params.get("figsize", (10, 8)))
    ax = fig.add_subplot(111)

    im = ax.imshow(data.values, aspect="auto", cmap="RdYlBu_r", vmin=-1, vmax=1)
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_xticks(range(len(data.columns)))
    ax.set_xticklabels([str(c) for c in data.columns], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(data.index)))
    ax.set_yticklabels([str(i) for i in data.index], fontsize=8)
    ax.set_title(params.get("title", "相关性热力图"))
    fig.tight_layout()
    return fig


def _render_bar_chart(data: pd.DataFrame, params: dict,
                      theme: "Theme") -> Figure:  # noqa: F821
    """通用柱状图（matplotlib）"""
    fig = Figure(figsize=params.get("figsize", (14, 6)))
    ax = fig.add_subplot(111)

    colors = theme.chart_colors
    orientation = params.get("orientation", "vertical")

    if orientation == "horizontal":
        values = data.iloc[:, 0].values if len(data.columns) > 0 else []
        labels = [str(i) for i in data.index]
        ax.barh(range(len(labels)), values, color=colors[0], alpha=0.8)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels)
    else:
        n_cols = len(data.columns)
        width = 0.8 / max(n_cols, 1)
        x = np.arange(len(data.index))
        for i, col in enumerate(data.columns):
            ax.bar(x + i * width, data[col].values, width,
                   color=colors[i % len(colors)], alpha=0.8, label=str(col))
        ax.set_xticks(x + width * (n_cols - 1) / 2)
        ax.set_xticklabels([str(i) for i in data.index], rotation=45, ha="right")
        ax.legend(loc="upper right", fontsize=9)

    ax.set_title(params.get("title", ""))
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
    fig.tight_layout()
    return fig


def _render_drawdown_line(data: pd.DataFrame, params: dict,
                          theme: "Theme") -> Figure:  # noqa: F821
    """回撤曲线（水下曲线，matplotlib）

    data: 单列 DataFrame，值为回撤比例（负数或 0），index 为 DatetimeIndex。
    """
    fig = Figure(figsize=params.get("figsize", (16, 5)))
    ax = fig.add_subplot(111)

    series = data.iloc[:, 0].dropna()
    color = theme.chart_colors[3 % len(theme.chart_colors)]

    ax.fill_between(series.index, series.values, 0, color=color, alpha=0.35)
    ax.plot(series.index, series.values, color=color, linewidth=1.2, alpha=0.9)
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)

    if isinstance(series.index, pd.DatetimeIndex):
        _set_datetime_xticks(ax, series.index)

    ax.set_title(params.get("title", "回撤分析"))
    ax.set_ylabel("回撤幅度")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.1%}"))
    fig.tight_layout()
    return fig


def _render_line_chart(data: pd.DataFrame, params: dict,
                       theme: "Theme") -> Figure:  # noqa: F821
    """通用折线图（matplotlib）"""
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
# Plotly 图表生成函数
# ============================================================

import plotly.graph_objects as go


def _plotly_layout(fig: go.Figure, params: dict, theme: "Theme") -> None:
    """统一设置 plotly 布局：标题、字体、hovermode。"""
    fig.update_layout(
        title=params.get("title", ""),
        hovermode="x unified",
        font=dict(family="Microsoft YaHei, sans-serif", size=12),
        template="plotly_white",
        margin=dict(l=60, r=30, t=50, b=60),
    )


def _render_ic_bar_plotly(data: pd.DataFrame, params: dict,
                          theme: "Theme") -> go.Figure:
    """IC 柱状图（plotly）"""
    data = _clean_data(data)
    fig = go.Figure()
    x = _to_plotly_x(data.index)

    for i, col in enumerate(data.columns):
        vals = data[col]
        fig.add_trace(go.Bar(
            x=x, y=vals, name=str(col),
            marker_color=theme.chart_colors[i % len(theme.chart_colors)],
            opacity=0.75,
            hovertemplate="%{x}<br>IC: %{y:.4f}<extra></extra>",
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=0.8)
    fig.update_layout(barmode="group")
    _plotly_layout(fig, params, theme)
    fig.update_xaxes(title="时点")
    fig.update_yaxes(title="IC")
    return fig


def _render_ic_decay_bar_plotly(data: pd.DataFrame, params: dict,
                                theme: "Theme") -> go.Figure:
    """IC 衰减柱状图（plotly）"""
    value_col = None
    for c in data.columns:
        if "IC平均值" in str(c) or "IC" in str(c):
            value_col = c
            break
    if value_col is None:
        value_col = data.columns[0]

    values = data[value_col].dropna()
    x_labels = [str(i) for i in values.index]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x_labels, y=values, name=str(value_col),
        marker_color=theme.chart_colors[0], opacity=0.8,
        hovertemplate="%{x}<br>IC 均值: %{y:.4f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=0.8)
    _plotly_layout(fig, params, theme)
    fig.update_xaxes(title="调仓周期（月）")
    fig.update_yaxes(title="IC 均值")
    return fig


def _render_nav_curve_plotly(data: pd.DataFrame, params: dict,
                             theme: "Theme") -> go.Figure:
    """净值曲线（plotly）"""
    fig = go.Figure()
    for i, col in enumerate(data.columns):
        series = data[col].dropna()
        if series.empty:
            continue
        fig.add_trace(go.Scatter(
            x=_to_plotly_x(series.index), y=series.values,
            mode="lines", name=str(col),
            line=dict(color=theme.chart_colors[i % len(theme.chart_colors)], width=1.5),
            opacity=0.85,
            hovertemplate="%{x}<br>净值: %{y:.4f}<extra></extra>",
        ))
    fig.add_hline(y=1, line_dash="dash", line_color="gray", line_width=0.8)
    _plotly_layout(fig, params, theme)
    fig.update_yaxes(title="净值")
    return fig


def _render_long_excess_nav_plotly(data: pd.DataFrame, params: dict,
                                   theme: "Theme") -> go.Figure:
    """多头超额净值曲线（plotly）"""
    fig = go.Figure()
    cols = [c for c in data.columns
            if str(c).startswith("P") and "-" not in str(c) and str(c) != "基准"]

    for i, col in enumerate(cols):
        series = data[col].dropna()
        if series.empty:
            continue
        fig.add_trace(go.Scatter(
            x=_to_plotly_x(series.index), y=series.values,
            mode="lines", name=str(col),
            line=dict(color=theme.chart_colors[i % len(theme.chart_colors)], width=1.5),
            opacity=0.85,
            hovertemplate="%{x}<br>超额净值: %{y:.4f}<extra></extra>",
        ))
    fig.add_hline(y=1, line_dash="dash", line_color="gray", line_width=0.8)
    _plotly_layout(fig, params, theme)
    fig.update_yaxes(title="超额净值")
    return fig


def _render_long_short_nav_plotly(data: pd.DataFrame, params: dict,
                                  theme: "Theme") -> go.Figure:
    """多空净值曲线（plotly）"""
    ls_cols = [c for c in data.columns if "-" in str(c)]
    col = ls_cols[0] if ls_cols else data.columns[-1]
    series = data[col].dropna()
    x = _to_plotly_x(series.index)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=series.values, mode="lines", name=str(col),
        line=dict(color=theme.chart_colors[1], width=1.8),
        hovertemplate="%{x}<br>净值: %{y:.4f}<extra></extra>",
    ))
    # 填充区域
    fig.add_trace(go.Scatter(
        x=x, y=[1] * len(series), mode="lines", showlegend=False,
        line=dict(color="rgba(0,0,0,0)"),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=series.values, fill="tonexty", mode="none",
        fillcolor="rgba(0,100,200,0.1)", showlegend=False,
    ))
    fig.add_hline(y=1, line_dash="dash", line_color="gray", line_width=0.8)
    _plotly_layout(fig, params, theme)
    fig.update_yaxes(title="净值")
    return fig


def _render_turnover_area_plotly(data: pd.DataFrame, params: dict,
                                 theme: "Theme") -> go.Figure:
    """换手率面积图（plotly）"""
    data = _clean_data(data)
    fig = go.Figure()

    for i, col in enumerate(data.columns):
        vals = data[col].values
        fig.add_trace(go.Scatter(
            x=_to_plotly_x(data.index), y=vals,
            mode="lines", name=str(col),
            line=dict(color=theme.chart_colors[i % len(theme.chart_colors)], width=1.5),
            fill="tozeroy", opacity=0.5,
            hovertemplate="%{x}<br>换手率: %{y:.4f}<extra></extra>",
        ))

    _plotly_layout(fig, params, theme)
    fig.update_yaxes(title="换手率")
    return fig


def _render_heatmap_plotly(data: pd.DataFrame, params: dict,
                           theme: "Theme") -> go.Figure:
    """热力图（plotly）"""
    fig = go.Figure(data=go.Heatmap(
        z=data.values,
        x=[str(c) for c in data.columns],
        y=[str(i) for i in data.index],
        colorscale="RdYlBu_r", zmin=-1, zmax=1,
        hovertemplate="X: %{x}<br>Y: %{y}<br>值: %{z:.4f}<extra></extra>",
    ))
    _plotly_layout(fig, params, theme)
    return fig


def _render_bar_chart_plotly(data: pd.DataFrame, params: dict,
                             theme: "Theme") -> go.Figure:
    """通用柱状图（plotly）"""
    fig = go.Figure()
    orientation = params.get("orientation", "vertical")

    if orientation == "horizontal":
        values = data.iloc[:, 0] if len(data.columns) > 0 else []
        labels = [str(i) for i in data.index]
        fig.add_trace(go.Bar(
            y=labels, x=values, orientation="h",
            marker_color=theme.chart_colors[0], opacity=0.8,
            hovertemplate="%{y}: %{x:.4f}<extra></extra>",
        ))
    else:
        for i, col in enumerate(data.columns):
            fig.add_trace(go.Bar(
                x=[str(i) for i in data.index], y=data[col].values,
                name=str(col),
                marker_color=theme.chart_colors[i % len(theme.chart_colors)],
                opacity=0.8,
                hovertemplate="%{x}<br>" + str(col) + ": %{y:.4f}<extra></extra>",
            ))
        fig.update_layout(barmode="group")

    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=0.8)
    _plotly_layout(fig, params, theme)
    return fig


def _render_line_chart_plotly(data: pd.DataFrame, params: dict,
                              theme: "Theme") -> go.Figure:
    """通用折线图（plotly）"""
    fig = go.Figure()

    for i, col in enumerate(data.columns):
        series = data[col].dropna()
        if series.empty:
            continue
        fig.add_trace(go.Scatter(
            x=_to_plotly_x(series.index), y=series.values,
            mode="lines", name=str(col),
            line=dict(color=theme.chart_colors[i % len(theme.chart_colors)], width=2),
            opacity=0.85,
            hovertemplate="%{x}<br>" + str(col) + ": %{y:.4f}<extra></extra>",
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=0.8)
    _plotly_layout(fig, params, theme)
    return fig


def _render_drawdown_line_plotly(data: pd.DataFrame, params: dict,
                                 theme: "Theme") -> go.Figure:  # noqa: F821
    """回撤曲线（plotly）"""
    series = data.iloc[:, 0].dropna()
    x = _to_plotly_x(series.index)
    color = theme.chart_colors[3 % len(theme.chart_colors)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=series.values, mode="lines", name="回撤",
        line=dict(color=color, width=1.2),
        fill="tozeroy", fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.25)",
        hovertemplate="%{x}<br>回撤: %{y:.2%}<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=0.8)
    _plotly_layout(fig, params, theme)
    fig.update_yaxes(title="回撤幅度", tickformat=".1%")
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
          engine: plotly       # 可选，图表引擎（plotly / matplotlib）
          figsize: [16, 6]    # 可选，画布大小（仅 matplotlib）
    """

    name = "chart"

    # 注册表：(engine, chart_type) → 生成函数
    CHART_FUNCTIONS: Dict[Tuple[str, str], Callable] = {}

    @classmethod
    def register_chart_type(cls, engine: str, chart_type: str, func: Callable):
        """注册图表类型生成函数。

        Args:
            engine: "plotly" 或 "matplotlib"
            chart_type: 图表类型名（如 "ic_bar"）
            func: 生成函数 (data, params, theme) → Figure
        """
        cls.CHART_FUNCTIONS[(engine, chart_type)] = func

    def render(self, data: pd.DataFrame, params: dict, theme: "Theme",  # noqa: F821
               renderer: "ReportRenderer") -> str:  # noqa: F821
        engine = params.get("engine", "plotly")
        chart_type = params.get("type", "bar_chart")
        key = (engine, chart_type)
        chart_func = self.CHART_FUNCTIONS.get(key)

        if chart_func is None:
            available = [t for e, t in self.CHART_FUNCTIONS if e == engine]
            raise ValueError(
                f"未知的图表类型: '{chart_type}'（引擎: {engine}），"
                f"可用类型: {available}"
            )

        if data is None or (isinstance(data, pd.DataFrame) and data.empty):
            return renderer.render_text(
                f"> ⚠ 图表数据为空（类型: {chart_type}）"
            )

        fig = chart_func(data, params, theme)

        # 根据引擎选择渲染方法
        if engine == "plotly":
            result = renderer.render_plotly_chart(fig, title=params.get("title"))
        else:
            result = renderer.render_chart(fig, title=params.get("title"))
            import matplotlib.pyplot as plt
            plt.close(fig)
        return result


# ---- 注册内置图表类型（matplotlib） ----
Chart.register_chart_type("matplotlib", "ic_bar", _render_ic_bar)
Chart.register_chart_type("matplotlib", "ic_decay_bar", _render_ic_decay_bar)
Chart.register_chart_type("matplotlib", "nav_curve", _render_nav_curve)
Chart.register_chart_type("matplotlib", "long_excess_nav", _render_long_excess_nav)
Chart.register_chart_type("matplotlib", "long_short_nav", _render_long_short_nav)
Chart.register_chart_type("matplotlib", "turnover_area", _render_turnover_area)
Chart.register_chart_type("matplotlib", "heatmap", _render_heatmap)
Chart.register_chart_type("matplotlib", "bar_chart", _render_bar_chart)
Chart.register_chart_type("matplotlib", "line_chart", _render_line_chart)
Chart.register_chart_type("matplotlib", "drawdown_line", _render_drawdown_line)

# ---- 注册内置图表类型（plotly） ----
Chart.register_chart_type("plotly", "ic_bar", _render_ic_bar_plotly)
Chart.register_chart_type("plotly", "ic_decay_bar", _render_ic_decay_bar_plotly)
Chart.register_chart_type("plotly", "nav_curve", _render_nav_curve_plotly)
Chart.register_chart_type("plotly", "long_excess_nav", _render_long_excess_nav_plotly)
Chart.register_chart_type("plotly", "long_short_nav", _render_long_short_nav_plotly)
Chart.register_chart_type("plotly", "turnover_area", _render_turnover_area_plotly)
Chart.register_chart_type("plotly", "heatmap", _render_heatmap_plotly)
Chart.register_chart_type("plotly", "bar_chart", _render_bar_chart_plotly)
Chart.register_chart_type("plotly", "line_chart", _render_line_chart_plotly)
Chart.register_chart_type("plotly", "drawdown_line", _render_drawdown_line_plotly)
