# -*- coding: utf-8 -*-
"""日志查看器组件。

提供实时日志流显示功能。
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st


def render_log_viewer(log_path: str, max_lines: int = 200, auto_refresh: bool = True):
    """渲染实时日志查看器。

    Args:
        log_path: 日志文件路径
        max_lines: 最大显示行数
        auto_refresh: 是否自动刷新
    """
    if not log_path or not os.path.exists(log_path):
        st.info("📭 暂无日志文件")
        return

    # 自动刷新
    if auto_refresh:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=3000, key="log_refresh")
        except ImportError:
            st.caption("💡 安装 streamlit-autorefresh 可实现自动刷新: pip install streamlit-autorefresh")

    # 读取日志
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        st.error(f"读取日志失败: {e}")
        return

    # 只显示最近的行
    if len(lines) > max_lines:
        lines = lines[-max_lines:]

    # 渲染日志（带语法高亮）
    log_text = "".join(lines)
    st.code(log_text, language="log")

    # 显示日志统计
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总行数", len(lines))
    with col2:
        error_count = sum(1 for l in lines if "ERROR" in l or "CRITICAL" in l)
        st.metric("错误数", error_count)
    with col3:
        warning_count = sum(1 for l in lines if "WARNING" in l)
        st.metric("警告数", warning_count)


def render_log_tail(log_path: str, tail_lines: int = 50):
    """渲染日志尾部（不自动刷新）。

    Args:
        log_path: 日志文件路径
        tail_lines: 显示的尾部行数
    """
    if not log_path or not os.path.exists(log_path):
        return

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return

    if len(lines) > tail_lines:
        lines = lines[-tail_lines:]

    st.code("".join(lines), language="log")
