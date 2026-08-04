# -*- coding: utf-8 -*-
"""状态卡片组件。

展示挖掘进程的运行状态信息。
"""
from __future__ import annotations

from typing import Optional

import streamlit as st


def render_status_card(
    is_running: bool,
    pid: Optional[int] = None,
    direction: str = "",
    mode: str = "",
    current_round: int = 0,
    max_rounds: int = 0,
    elapsed_time: str = "",
    workspace_dir: str = "",
):
    """渲染运行状态卡片。

    Args:
        is_running: 是否正在运行
        pid: 进程 PID
        direction: 当前研究方向
        mode: 运行模式
        current_round: 当前轮次
        max_rounds: 最大轮次
        elapsed_time: 已运行时间
        workspace_dir: 工作目录
    """
    if is_running:
        st.success("🟢 **挖掘进程运行中**")
    else:
        st.info("⚪ **挖掘进程未运行**")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("进程 PID", pid if pid else "-")
    with col2:
        st.metric("研究方向", direction if direction else "-")
    with col3:
        st.metric("运行模式", mode if mode else "-")
    with col4:
        st.metric("进度", f"{current_round}/{max_rounds}" if max_rounds else "-")

    if elapsed_time:
        st.caption(f"⏱️ 已运行: {elapsed_time}")
    if workspace_dir:
        st.caption(f"📁 工作目录: `{workspace_dir}`")


def render_round_card(round_info):
    """渲染单轮挖掘结果卡片。

    Args:
        round_info: RoundInfo 对象
    """
    decision = round_info.decision_emoji
    status = round_info.status_emoji

    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{decision} {round_info.factor_name}** `{round_info.run_id}`")
            st.caption(f"类别: {round_info.category or '-'} | 状态: {status}")
        with col2:
            score = round_info.composite_score
            color = "green" if score > 0.6 else "orange" if score > 0.4 else "red"
            st.markdown(f"<h3 style='text-align:right;color:{color}'>{score:.3f}</h3>", unsafe_allow_html=True)

        # 指标行
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("RankIC", f"{round_info.rankic_mean:.4f}")
        m2.metric("ICIR", f"{round_info.rankicir:.2f}")
        m3.metric("OOS IC", f"{round_info.oos_rankic:.4f}")
        m4.metric("增量 IC t", f"{round_info.incremental_ic_t:.2f}")
