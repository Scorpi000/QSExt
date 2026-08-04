# -*- coding: utf-8 -*-
"""实时监控页面。

显示挖掘进程的实时日志和进度信息。
"""
import os
from pathlib import Path

import streamlit as st

from QSExt.LLMFactor.web.components.log_viewer import render_log_viewer
from QSExt.LLMFactor.web.utils.workspace import load_loop_summary, scan_workspace

st.set_page_config(page_title="监控", page_icon="📊", layout="wide")
st.title("📊 实时监控")
st.markdown("---")

# ============================================================
# 工作目录选择
# ============================================================

workspace_dir = st.session_state.get("workspace_dir", "")

# 也允许手动输入工作目录
col1, col2 = st.columns([3, 1])
with col1:
    manual_dir = st.text_input(
        "工作目录路径",
        value=workspace_dir,
        placeholder="如：workspace/loop_xxx",
        help="挖掘进程的工作目录，启动挖掘后自动填充",
    )
with col2:
    if st.button("🔄 刷新", use_container_width=True):
        st.rerun()

if manual_dir:
    workspace_dir = manual_dir

if not workspace_dir:
    st.info("📭 请先启动挖掘进程，或手动输入工作目录路径")
    st.stop()

# ============================================================
# 进度概览
# ============================================================

st.subheader("📈 进度概览")

# 优先从 loop_xxx.json 读取循环级汇总
loop_summary = load_loop_summary(workspace_dir)
if loop_summary:
    col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)
    col_s1.metric("循环 ID", loop_summary.get("loop_id", "-"))
    col_s2.metric("✅ 入库", loop_summary.get("accepted", 0))
    col_s3.metric("❌ 拒绝", loop_summary.get("rejected", 0))
    col_s4.metric("🔄 精炼", loop_summary.get("refining", 0))
    col_s5.metric("⚠️ 错误", loop_summary.get("errors", 0))

rounds = scan_workspace(workspace_dir)
if rounds:
    # 统计
    total = len(rounds)
    accepted = sum(1 for r in rounds if r.decision == "accepted")
    rejected = sum(1 for r in rounds if r.decision == "rejected")
    refining = sum(1 for r in rounds if r.decision == "refining")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("总轮次", total)
    m2.metric("✅ 入库", accepted)
    m3.metric("❌ 拒绝", rejected)
    m4.metric("🔄 精炼", refining)

    # 最近轮次
    st.markdown("---")
    st.subheader("🕐 最近轮次")
    for r in rounds[:5]:
        from QSExt.LLMFactor.web.components.status_card import render_round_card
        render_round_card(r)
else:
    st.info("暂无轮次数据")

# ============================================================
# 日志查看
# ============================================================

st.markdown("---")
st.subheader("📝 运行日志")

# 查找日志文件
log_files = []
workspace_path = Path(workspace_dir)
if workspace_path.exists():
    # 主日志
    for log_name in ["mining_loop.log", "pipeline.log"]:
        log_file = workspace_path / log_name
        if log_file.exists():
            log_files.append(str(log_file))

    # 如果是 loop_ 目录，也查找父目录的日志
    if workspace_path.name.startswith("loop_"):
        parent_log = workspace_path.parent / "mining_loop.log"
        if parent_log.exists() and str(parent_log) not in log_files:
            log_files.append(str(parent_log))

    # 子目录日志
    for fm_dir in workspace_path.glob("FM_*/"):
        for log_name in ["pipeline.log"]:
            log_file = fm_dir / log_name
            if log_file.exists():
                log_files.append(str(log_file))

if log_files:
    selected_log = st.selectbox("选择日志文件", log_files, index=0)
    max_lines = st.slider("显示行数", 50, 500, 200, step=50)
    render_log_viewer(selected_log, max_lines=max_lines, auto_refresh=True)
else:
    st.info("未找到日志文件")
