# -*- coding: utf-8 -*-
"""挖掘控制页面。

启动/停止挖掘进程，查看运行状态和实时日志。
"""
import time
from datetime import datetime

import streamlit as st

from QSExt.LLMFactor.web.components.log_viewer import render_log_tail
from QSExt.LLMFactor.web.components.status_card import render_status_card
from QSExt.LLMFactor.web.utils.process import MiningConfig, MiningProcessManager

st.set_page_config(page_title="控制", page_icon="🎮", layout="wide")
st.title("🎮 挖掘控制")
st.markdown("---")

# ============================================================
# 进程管理器初始化
# ============================================================

if "process_manager" not in st.session_state:
    st.session_state.process_manager = MiningProcessManager()
else:
    # 兼容旧实例：缺少新增属性时重建
    _mgr = st.session_state.process_manager
    if not hasattr(_mgr, "_start_error"):
        st.session_state.process_manager = MiningProcessManager()

if "start_time" not in st.session_state:
    st.session_state.start_time = None

manager: MiningProcessManager = st.session_state.process_manager

# ============================================================
# 状态展示
# ============================================================

config = st.session_state.get("mining_config", {})
is_running = manager.is_running

elapsed = ""
if is_running and st.session_state.start_time:
    delta = datetime.now() - st.session_state.start_time
    elapsed = f"{int(delta.total_seconds() // 60)} 分 {int(delta.total_seconds() % 60)} 秒"

render_status_card(
    is_running=is_running,
    pid=manager.pid,
    direction=config.get("direction", ""),
    mode=config.get("mode", ""),
    current_round=0,  # TODO: 从日志解析当前轮次
    max_rounds=config.get("max_rounds", 0),
    elapsed_time=elapsed,
    workspace_dir=manager.workspace_dir or "",
)

# 显示启动错误
if manager.start_error and not is_running:
    st.error(f"❌ {manager.start_error}")

st.markdown("---")

# ============================================================
# 控制按钮
# ============================================================

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    if not config:
        st.warning("⚠️ 请先在 **配置** 页面设置挖掘参数")
    elif is_running:
        st.success("🟢 挖掘进程运行中...")
    else:
        st.info("⚪ 就绪，可以启动挖掘")

with col2:
    start_disabled = is_running or not config
    if st.button(
        "🚀 启动挖掘",
        disabled=start_disabled,
        use_container_width=True,
        type="primary",
    ):
        try:
            mining_config = MiningConfig(
                direction=config.get("direction", "全部"),
                mode=config.get("mode", "skill"),
                max_rounds=config.get("max_rounds", 5),
                max_hours=config.get("max_hours", 4.0),
                workspace_dir=config.get("workspace_dir", ""),
                max_turns_hypothesis=config.get("max_turns_hypothesis", 50),
                max_turns_development=config.get("max_turns_development", 80),
                config_path=config.get("config_path", ""),
                clear_cache=config.get("clear_cache", True),
            )
            workspace_dir = manager.start(mining_config)
            st.session_state.start_time = datetime.now()
            st.session_state.workspace_dir = workspace_dir
            st.rerun()
        except Exception as e:
            st.error(f"启动失败: {e}")

with col3:
    stop_disabled = not is_running
    if st.button(
        "⏹️ 停止挖掘",
        disabled=stop_disabled,
        use_container_width=True,
    ):
        try:
            manager.stop()
            st.session_state.start_time = None
            st.warning("挖掘进程已停止")
            st.rerun()
        except Exception as e:
            st.error(f"停止失败: {e}")

# ============================================================
# 运行日志（从日志文件实时读取）
# ============================================================

st.markdown("---")
st.subheader("📝 运行日志")

log_path = manager.log_path
if log_path and is_running:
    # 进程运行中，从日志文件实时读取
    from QSExt.LLMFactor.web.components.log_viewer import render_log_viewer
    render_log_viewer(log_path, max_lines=200, auto_refresh=True)
elif log_path:
    # 进程已结束，显示最终日志
    st.caption(f"日志文件: `{log_path}`")
    render_log_tail(log_path, tail_lines=50)
else:
    st.info("启动挖掘后，日志将在此显示")
