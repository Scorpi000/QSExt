# -*- coding: utf-8 -*-
"""图表组件模块。

提供 IC 曲线、分组收益、五维雷达图等可视化组件。
"""
from __future__ import annotations

from typing import Any, Optional

import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_ic_curve(ic_data: dict, title: str = "RankIC 时间序列") -> go.Figure:
    """绘制 IC 曲线图。

    Args:
        ic_data: IC 数据，包含 dates 和 ic_series
        title: 图表标题

    Returns:
        plotly Figure 对象
    """
    fig = go.Figure()

    dates = ic_data.get("dates", [])
    ic_series = ic_data.get("ic_series", [])

    if dates and ic_series:
        # IC 序列
        fig.add_trace(go.Scatter(
            x=dates, y=ic_series,
            mode="lines",
            name="RankIC",
            line=dict(color="steelblue", width=1),
        ))

        # 累计 IC
        cumsum = []
        s = 0
        for v in ic_series:
            s += v
            cumsum.append(s)
        fig.add_trace(go.Scatter(
            x=dates, y=cumsum,
            mode="lines",
            name="累计 RankIC",
            line=dict(color="coral", width=2),
            yaxis="y2",
        ))

        # 零线
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        title=title,
        xaxis_title="日期",
        yaxis=dict(title="RankIC", side="left"),
        yaxis2=dict(title="累计 RankIC", side="right", overlaying="y"),
        height=400,
        margin=dict(l=60, r=60, t=50, b=50),
        legend=dict(x=0.01, y=0.99),
    )

    return fig


def plot_group_return(group_data: dict, title: str = "分组收益") -> go.Figure:
    """绘制分组收益柱状图。

    Args:
        group_data: 分组数据，包含 groups 和 returns
        title: 图表标题

    Returns:
        plotly Figure 对象
    """
    fig = go.Figure()

    groups = group_data.get("groups", [])
    returns = group_data.get("returns", [])

    if groups and returns:
        colors = ["green" if r > 0 else "red" for r in returns]
        fig.add_trace(go.Bar(
            x=groups, y=returns,
            marker_color=colors,
            name="年化收益",
        ))

    fig.update_layout(
        title=title,
        xaxis_title="分组",
        yaxis_title="年化收益率",
        height=350,
        margin=dict(l=60, r=30, t=50, b=50),
    )

    return fig


def plot_radar(scores: dict, title: str = "五维评分") -> go.Figure:
    """绘制五维雷达图。

    Args:
        scores: 五维评分字典，键为维度名，值为 0-1 分数
        title: 图表标题

    Returns:
        plotly Figure 对象
    """
    dimensions = ["有效性", "稳定性", "换手率", "多样性", "过拟合风险"]
    values = [
        scores.get("effectiveness", 0),
        scores.get("stability", 0),
        scores.get("turnover", 0),
        scores.get("diversity", 0),
        scores.get("overfitting_risk", 0),
    ]

    # 闭合雷达图
    values_closed = values + [values[0]]
    dims_closed = dimensions + [dimensions[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=dims_closed,
        fill="toself",
        name="评分",
        line=dict(color="steelblue"),
        fillcolor="rgba(70, 130, 180, 0.3)",
    ))

    fig.update_layout(
        title=title,
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1]),
        ),
        height=400,
        margin=dict(l=80, r=80, t=60, b=40),
    )

    return fig


def plot_evaluation_summary(stats: dict) -> go.Figure:
    """绘制评测摘要图（IC + 分组 + 累计收益）。

    Args:
        stats: 评测统计数据

    Returns:
        plotly Figure 对象
    """
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=["RankIC 分布", "分组年化收益", "多空净值"],
        specs=[[{"type": "histogram"}, {"type": "bar"}, {"type": "scatter"}]],
    )

    # IC 分布
    ic_values = stats.get("ic_series", [])
    if ic_values:
        fig.add_trace(go.Histogram(x=ic_values, name="IC 分布", marker_color="steelblue"), row=1, col=1)

    # 分组收益
    group_returns = stats.get("group_returns", {})
    if group_returns:
        fig.add_trace(go.Bar(
            x=list(group_returns.keys()),
            y=list(group_returns.values()),
            name="分组收益",
            marker_color=["green" if v > 0 else "red" for v in group_returns.values()],
        ), row=1, col=2)

    # 多空净值
    ls_nav = stats.get("long_short_nav", [])
    if ls_nav:
        fig.add_trace(go.Scatter(y=ls_nav, mode="lines", name="多空净值", line=dict(color="coral")), row=1, col=3)

    fig.update_layout(height=350, showlegend=False, margin=dict(l=40, r=40, t=50, b=40))
    return fig
