# -*- coding: utf-8 -*-
"""因子挖掘 Web 管理界面主入口。

启动方式：
    streamlit run QSExt/LLMFactor/web/app.py --server.port 8501

功能：
    - 配置挖掘参数（方向/市场/频率/模式）
    - 启动/停止挖掘进程
    - 实时监控日志
    - 查看评测结果
"""
import streamlit as st

st.set_page_config(
    page_title="因子挖掘管理平台",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⛏️ 因子挖掘管理平台")
st.markdown("---")

st.markdown("""
欢迎使用因子挖掘管理平台。请从左侧导航栏选择功能：

- **配置** — 设置挖掘参数（研究方向、市场、频率等）
- **控制** — 启动/停止挖掘进程
- **监控** — 实时查看挖掘日志
- **结果** — 查看评测结果和因子表现
""")

# 初始化 session_state
if "mining_config" not in st.session_state:
    st.session_state.mining_config = {}
if "mining_process" not in st.session_state:
    st.session_state.mining_process = None
if "workspace_dir" not in st.session_state:
    st.session_state.workspace_dir = None
