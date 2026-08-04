# -*- coding: utf-8 -*-
"""评测结果页面。

查看因子评测结果：IC 曲线、分组收益、五维雷达图、汇总表格。
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from QSExt.LLMFactor.web.components.charts import (
    plot_group_return,
    plot_ic_curve,
    plot_radar,
)
from QSExt.LLMFactor.web.utils.workspace import get_round_detail, scan_workspace

st.set_page_config(page_title="结果", page_icon="📈", layout="wide")
st.title("📈 评测结果")
st.markdown("---")

# ============================================================
# 工作目录选择
# ============================================================

workspace_dir = st.session_state.get("workspace_dir", "")
manual_dir = st.text_input(
    "工作目录路径",
    value=workspace_dir,
    placeholder="如：workspace/loop_xxx",
)

if not manual_dir:
    st.info("请先启动挖掘进程，或手动输入工作目录路径")
    st.stop()

# ============================================================
# 汇总表格
# ============================================================

st.subheader("📋 因子汇总")

rounds = scan_workspace(manual_dir)
if not rounds:
    st.info("暂无评测结果")
    st.stop()

# 构建 DataFrame
df_data = []
for r in rounds:
    df_data.append({
        "因子名称": r.factor_name,
        "类别": r.category,
        "决策": f"{r.decision_emoji} {r.decision}",
        "综合评分": r.composite_score,
        "RankIC": r.rankic_mean,
        "ICIR": r.rankicir,
        "OOS IC": r.oos_rankic,
        "增量 IC t": r.incremental_ic_t,
        "运行ID": r.run_id,
    })

df = pd.DataFrame(df_data)

# 筛选
col1, col2 = st.columns(2)
with col1:
    decision_filter = st.multiselect(
        "按决策筛选",
        options=["accepted", "refining", "rejected"],
        default=["accepted", "refining", "rejected"],
    )
with col2:
    category_filter = st.multiselect(
        "按类别筛选",
        options=df["类别"].unique().tolist() if not df.empty else [],
        default=df["类别"].unique().tolist() if not df.empty else [],
    )

# 应用筛选
if not df.empty:
    mask = df["决策"].apply(lambda x: any(d in x for d in decision_filter))
    if category_filter:
        mask = mask & df["类别"].isin(category_filter)
    filtered_df = df[mask]
else:
    filtered_df = df

# 显示表格
st.dataframe(
    filtered_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "综合评分": st.column_config.ProgressColumn("综合评分", min_value=0, max_value=1, format="%.3f"),
        "RankIC": st.column_config.NumberColumn("RankIC", format="%.4f"),
        "ICIR": st.column_config.NumberColumn("ICIR", format="%.2f"),
        "OOS IC": st.column_config.NumberColumn("OOS IC", format="%.4f"),
        "增量 IC t": st.column_config.NumberColumn("增量 IC t", format="%.2f"),
    },
)

# ============================================================
# 单因子详情
# ============================================================

st.markdown("---")
st.subheader("🔍 因子详情")

if not rounds:
    st.stop()

# 选择因子
factor_names = [f"{r.factor_name} ({r.run_id})" for r in rounds]
selected_idx = st.selectbox("选择因子", range(len(factor_names)), format_func=lambda i: factor_names[i])

if selected_idx is not None:
    selected_round = rounds[selected_idx]
    detail = get_round_detail(selected_round.workspace_path)

    # 基本信息
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("综合评分", f"{selected_round.composite_score:.3f}")
    with col2:
        st.metric("RankIC", f"{selected_round.rankic_mean:.4f}")
    with col3:
        st.metric("ICIR", f"{selected_round.rankicir:.2f}")

    # 五维雷达图
    metadata = detail.get("metadata", {})
    eval_data = metadata.get("evaluation", {})
    scores = eval_data.get("scores", {})

    if scores:
        st.plotly_chart(plot_radar(scores, title=f"{selected_round.factor_name} 五维评分"), use_container_width=True)
    else:
        st.info("暂无五维评分数据")

    # IC 曲线
    ic_data = eval_data.get("ic_curve", {})
    if ic_data:
        st.plotly_chart(plot_ic_curve(ic_data, title=f"{selected_round.factor_name} RankIC 曲线"), use_container_width=True)

    # 分组收益
    group_data = eval_data.get("group_returns", {})
    if group_data:
        st.plotly_chart(plot_group_return(group_data, title=f"{selected_round.factor_name} 分组收益"), use_container_width=True)

    # 详细数据
    with st.expander("📄 元数据详情"):
        st.json(metadata)

    # 因子代码
    factor_code = detail.get("factor_code", "")
    if factor_code:
        with st.expander("💻 因子代码"):
            st.code(factor_code, language="python")

    # README
    readme = detail.get("readme", "")
    if readme:
        with st.expander("📖 README"):
            st.markdown(readme)
