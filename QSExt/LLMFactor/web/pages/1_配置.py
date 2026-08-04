# -*- coding: utf-8 -*-
"""挖掘参数配置页面。

从 LLMFactor/config/ 目录加载 4 个 YAML 配置文件，提供可视化编辑界面。
修改后点击"保存"按钮会写回对应的 YAML 文件。
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from QSExt.LLMFactor.web.utils.config_io import (
    find_config_dir,
    load_all_configs,
    load_default_config_dir,
    save_config,
    save_default_config_dir,
)

st.set_page_config(page_title="配置", page_icon="⚙️", layout="wide")
st.title("⚙️ 挖掘参数配置")
st.markdown("---")


# ============================================================
# 辅助函数
# ============================================================

def _get(cfg_key: str, *keys, default=None):
    """从 session_state 中的配置字典取值，支持嵌套 key。"""
    d = st.session_state[cfg_key]
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d if d is not None else default


def _set(cfg_key: str, *keys_and_value):
    """设置 session_state 中的配置字典值。

    用法: _set("config_pipeline", "data", "max_stocks", 1000)
    """
    keys = keys_and_value[:-1]
    value = keys_and_value[-1]
    d = st.session_state[cfg_key]
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _ensure_widget_key(key: str, fallback):
    """确保 widget key 存在于 session_state 中。

    只在 key 不存在时写入（首次加载或重新加载后），
    已存在时不覆盖（保留用户编辑或重新加载写入的值）。
    """
    if key not in st.session_state:
        st.session_state[key] = fallback


# ============================================================
# 配置目录选择
# ============================================================

# 优先使用用户设为默认的目录，其次自动查找
if "config_dir" not in st.session_state:
    saved_default = load_default_config_dir()
    auto_found = find_config_dir()
    st.session_state["config_dir"] = saved_default or (str(auto_found) if auto_found else "")

col_dir1, col_dir2, col_dir3 = st.columns([4, 1, 1])
with col_dir1:
    config_dir_input = st.text_input(
        "📁 配置目录",
        value=st.session_state["config_dir"],
        key="config_dir_input",
        help="YAML 配置文件所在目录，修改后点击「重新加载」读取新配置",
    )
with col_dir2:
    st.write("")  # 垂直对齐
    if st.button("🔄 重新加载", use_container_width=True):
        st.session_state["config_dir"] = config_dir_input
        # 清除加载标记和所有 widget key，让它们在下方用新配置值重新初始化
        for k in list(st.session_state):
            if k in ("config_dir", "config_dir_input"):
                continue
            if k.startswith(("pipeline_", "hypo_", "dev_", "eval_")):
                del st.session_state[k]
        st.session_state.pop("config_loaded", None)
        st.rerun()
with col_dir3:
    st.write("")  # 垂直对齐
    if st.button("⭐ 设为默认", use_container_width=True):
        if config_dir_input.strip():
            save_default_config_dir(config_dir_input)
            st.success(f"✅ 已将 `{config_dir_input.strip()}` 设为默认配置目录")
        else:
            st.warning("⚠️ 请先填写配置目录路径")

config_dir = Path(config_dir_input) if config_dir_input else None

# ============================================================
# 加载配置（仅首次 或 重新加载后）
# ============================================================

if config_dir is None or not config_dir.exists():
    if config_dir_input:
        st.warning(f"⚠️ 目录不存在: `{config_dir_input}`，保存时将自动创建。")
    else:
        st.error("❌ 请填写配置目录路径。")
        st.stop()

if "config_loaded" not in st.session_state:
    if config_dir and config_dir.exists():
        all_configs = load_all_configs(config_dir)
        st.session_state["config_pipeline"] = all_configs.get("pipeline.yaml", {})
        st.session_state["config_hypothesis"] = all_configs.get("hypothesis_research.yaml", {})
        st.session_state["config_development"] = all_configs.get("development.yaml", {})
        st.session_state["config_evaluation"] = all_configs.get("evaluation.yaml", {})
    else:
        st.session_state["config_pipeline"] = {}
        st.session_state["config_hypothesis"] = {}
        st.session_state["config_development"] = {}
        st.session_state["config_evaluation"] = {}

    st.session_state["config_loaded"] = True
    st.session_state["config_dir"] = config_dir_input

# ============================================================
# 预设 widget key（从配置字典初始化，已存在则不覆盖）
# ============================================================

_WIDGET_DEFAULTS = {
    "pipeline_project_root": ("config_pipeline", "project_root", "auto"),
    "pipeline_claude_cli": ("config_pipeline", "claude_cli", "auto"),
    "pipeline_workspace_dir": ("config_pipeline", "workspace_dir", "workspace"),
    "pipeline_max_turns_hypothesis": ("config_pipeline", "max_turns_hypothesis", 50),
    "pipeline_max_turns_development": ("config_pipeline", "max_turns_development", 80),
    "pipeline_data__trade_day_start": ("config_pipeline", "data", "trade_day_start", "2013-01-01"),
    "pipeline_data__trade_day_end": ("config_pipeline", "data", "trade_day_end", "2025-12-31"),
    "pipeline_data__stock_date": ("config_pipeline", "data", "stock_date", "2025-06-30"),
    "pipeline_data__max_stocks": ("config_pipeline", "data", "max_stocks", 1000),
    "hypo_market": ("config_hypothesis", "market", "A股"),
    "hypo_frequency": ("config_hypothesis", "frequency", "日频"),
    "hypo_max_directions": ("config_hypothesis", "max_directions", 5),
    "hypo_max_wiki_pages_per_direction": ("config_hypothesis", "max_wiki_pages_per_direction", 5),
    "hypo_max_factor_codes_per_direction": ("config_hypothesis", "max_factor_codes_per_direction", 3),
    "hypo_freeze_after_n_failures": ("config_hypothesis", "freeze_after_n_failures", 3),
    "hypo_permission_mode": ("config_hypothesis", "permission_mode", "bypassPermissions"),
    "dev_llm_model": ("config_development", "llm_model", "claude-sonnet-5"),
    "dev_llm_temperature": ("config_development", "llm_temperature", 0.1),
    "dev_max_auto_fixes": ("config_development", "max_auto_fixes", 3),
    "dev_enable_leak_test": ("config_development", "enable_leak_test", True),
    "dev_enable_unit_check": ("config_development", "enable_unit_check", True),
    "dev_enable_semantic_review": ("config_development", "enable_semantic_review", True),
    "dev_enable_param_search": ("config_development", "enable_param_search", True),
    "dev_max_trials": ("config_development", "max_trials", 200),
    "dev_cv_folds": ("config_development", "cv_folds", 3),
    "dev_early_stop_rounds": ("config_development", "early_stop_rounds", 30),
    "dev_optimization_objective": ("config_development", "optimization_objective", "rankic"),
    "dev_permission_mode": ("config_development", "permission_mode", "bypassPermissions"),
    "eval_in_sample_start": ("config_evaluation", "in_sample_start", "2015-01"),
    "eval_in_sample_end": ("config_evaluation", "in_sample_end", "2022-12"),
    "eval_oos_start": ("config_evaluation", "oos_start", "2023-01"),
    "eval_oos_end": ("config_evaluation", "oos_end", "2025-12"),
    "eval_exclude_st": ("config_evaluation", "exclude_st", True),
    "eval_min_listing_days": ("config_evaluation", "min_listing_days", 60),
    "eval_corr_method": ("config_evaluation", "corr_method", "spearman"),
    "eval_ic_lookback": ("config_evaluation", "ic_lookback", 31),
    "eval_period_lookback": ("config_evaluation", "period_lookback", 1),
    "eval_group_num": ("config_evaluation", "group_num", 5),
    "eval_rebalance_freq": ("config_evaluation", "rebalance_freq", "monthly"),
    "eval_min_alpha_t": ("config_evaluation", "min_alpha_t", 3.0),
    "eval_min_composite_score": ("config_evaluation", "min_composite_score", 0.60),
    "eval_min_incremental_ic_t": ("config_evaluation", "min_incremental_ic_t", 2.0),
    "eval_min_oos_rankic": ("config_evaluation", "min_oos_rankic", 0.02),
    "eval_corr_warning_threshold": ("config_evaluation", "corr_warning_threshold", 0.7),
    "eval_save_to_mining_log": ("config_evaluation", "save_to_mining_log", True),
    "eval_cache_enabled": ("config_evaluation", "cache_enabled", True),
    "eval_cache_start_mode": ("config_evaluation", "cache_start_mode", "continue"),
    "eval_cache_dir": ("config_evaluation", "cache_dir", ""),
}
for widget_key, spec in _WIDGET_DEFAULTS.items():
    cfg_key = spec[0]
    *nested_keys, default = spec[1:]
    _ensure_widget_key(widget_key, _get(cfg_key, *nested_keys, default=default))

# ic_decay_periods — 特殊处理为逗号分隔字符串
decay_val = _get("config_evaluation", "ic_decay_periods", default=[1, 2, 3, 6, 12])
_ensure_widget_key("eval_ic_decay_periods", ", ".join(str(x) for x in decay_val) if isinstance(decay_val, list) else str(decay_val))

# score_weights
default_weights = {
    "effectiveness": 0.25, "stability": 0.20, "turnover": 0.15,
    "diversity": 0.20, "overfitting_risk": 0.20,
}
weights = _get("config_evaluation", "score_weights", default=default_weights)
for key in default_weights:
    _ensure_widget_key(f"eval_weight_{key}", float(weights.get(key, default_weights[key])))

# ============================================================
# Tab 布局
# ============================================================

tab_pipe, tab_hypo, tab_dev, tab_eval = st.tabs([
    "🌐 全局流水线",
    "🔬 假设生成",
    "🛠️ 因子开发",
    "📊 因子评测",
])


# ============================================================
# Tab 1: 全局流水线 (pipeline.yaml)
# ============================================================

with tab_pipe:
    st.subheader("项目路径")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input(
            "项目根目录",
            key="pipeline_project_root",
            help='"auto" 自动查找，或填写绝对路径',
        )
    with col2:
        st.text_input(
            "Claude CLI 路径",
            key="pipeline_claude_cli",
            help='"auto" 自动查找，或填写绝对路径',
        )

    st.text_input(
        "产出物输出目录",
        key="pipeline_workspace_dir",
        help="支持绝对路径或相对于项目根目录的路径",
    )

    st.subheader("Agent 轮次限制")
    col3, col4 = st.columns(2)
    with col3:
        st.number_input(
            "假设生成阶段最大轮次",
            min_value=1, max_value=500, step=5,
            key="pipeline_max_turns_hypothesis",
        )
    with col4:
        st.number_input(
            "因子开发阶段最大轮次",
            min_value=1, max_value=500, step=10,
            key="pipeline_max_turns_development",
        )

    st.subheader("数据上下文")
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.text_input(
            "交易日起始",
            key="pipeline_data__trade_day_start",
            help="格式: YYYY-MM-DD",
        )
    with col6:
        st.text_input(
            "交易日截止",
            key="pipeline_data__trade_day_end",
            help="格式: YYYY-MM-DD",
        )
    with col7:
        st.text_input(
            "股票截面日期",
            key="pipeline_data__stock_date",
            help="格式: YYYY-MM-DD",
        )
    with col8:
        st.number_input(
            "最大股票数量",
            min_value=10, max_value=10000, step=100,
            key="pipeline_data__max_stocks",
        )

    if st.button("💾 保存全局配置", key="save_pipeline", type="primary", use_container_width=True):
        cfg = {
            "project_root": st.session_state.pipeline_project_root,
            "claude_cli": st.session_state.pipeline_claude_cli,
            "workspace_dir": st.session_state.pipeline_workspace_dir,
            "max_turns_hypothesis": st.session_state.pipeline_max_turns_hypothesis,
            "max_turns_development": st.session_state.pipeline_max_turns_development,
            "data": {
                "trade_day_start": st.session_state.pipeline_data__trade_day_start,
                "trade_day_end": st.session_state.pipeline_data__trade_day_end,
                "stock_date": st.session_state.pipeline_data__stock_date,
                "max_stocks": st.session_state.pipeline_data__max_stocks,
            },
        }
        save_config(config_dir, "pipeline.yaml", cfg)
        st.session_state["config_pipeline"] = cfg
        st.success("✅ 全局配置已保存到 pipeline.yaml")


# ============================================================
# Tab 2: 假设生成 (hypothesis_research.yaml)
# ============================================================

with tab_hypo:
    st.subheader("研究方向")
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox(
            "目标市场",
            options=["A股", "港股", "美股"],
            key="hypo_market",
        )
    with col2:
        st.selectbox(
            "数据频率",
            options=["日频", "周频", "月频"],
            key="hypo_frequency",
        )

    st.subheader("搜索预算")
    col3, col4, col5 = st.columns(3)
    with col3:
        st.number_input(
            "最大方向数",
            min_value=1, max_value=50, step=1,
            key="hypo_max_directions",
        )
    with col4:
        st.number_input(
            "每方向最大 Wiki 页面数",
            min_value=1, max_value=50, step=1,
            key="hypo_max_wiki_pages_per_direction",
        )
    with col5:
        st.number_input(
            "每方向最大因子代码数",
            min_value=1, max_value=20, step=1,
            key="hypo_max_factor_codes_per_direction",
        )

    st.subheader("动态调整")
    st.number_input(
        "连续失败冻结阈值",
        min_value=1, max_value=20, step=1,
        key="hypo_freeze_after_n_failures",
        help="连续失败 N 次后冻结该方向",
    )

    st.subheader("Claude Agent")
    st.selectbox(
        "权限模式",
        options=["bypassPermissions", "auto", "default"],
        key="hypo_permission_mode",
        help="bypassPermissions: 跳过授权, auto: 自动确认, default: 手动授权",
    )

    if st.button("💾 保存假设生成配置", key="save_hypothesis", type="primary", use_container_width=True):
        cfg = {
            "market": st.session_state.hypo_market,
            "frequency": st.session_state.hypo_frequency,
            "max_directions": st.session_state.hypo_max_directions,
            "max_wiki_pages_per_direction": st.session_state.hypo_max_wiki_pages_per_direction,
            "max_factor_codes_per_direction": st.session_state.hypo_max_factor_codes_per_direction,
            "freeze_after_n_failures": st.session_state.hypo_freeze_after_n_failures,
            "permission_mode": st.session_state.hypo_permission_mode,
        }
        save_config(config_dir, "hypothesis_research.yaml", cfg)
        st.session_state["config_hypothesis"] = cfg
        st.success("✅ 假设生成配置已保存到 hypothesis_research.yaml")


# ============================================================
# Tab 3: 因子开发 (development.yaml)
# ============================================================

with tab_dev:
    st.subheader("代码生成")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input(
            "LLM 模型",
            key="dev_llm_model",
        )
    with col2:
        st.number_input(
            "LLM 温度",
            min_value=0.0, max_value=2.0, step=0.05, format="%.2f",
            key="dev_llm_temperature",
        )

    st.subheader("验证")
    col3, col4, col5, col6 = st.columns(4)
    with col3:
        st.number_input(
            "最大自动修复次数",
            min_value=0, max_value=20, step=1,
            key="dev_max_auto_fixes",
        )
    with col4:
        st.checkbox(
            "未来信息泄漏检测",
            key="dev_enable_leak_test",
        )
    with col5:
        st.checkbox(
            "单位检查",
            key="dev_enable_unit_check",
        )
    with col6:
        st.checkbox(
            "语义审查 (LLM)",
            key="dev_enable_semantic_review",
        )

    st.subheader("参数搜索")
    st.checkbox(
        "启用参数搜索",
        key="dev_enable_param_search",
        help="关闭则跳过参数搜索步骤",
    )
    col7, col8, col9, col10 = st.columns(4)
    with col7:
        st.number_input(
            "最大评估次数",
            min_value=1, max_value=5000, step=50,
            key="dev_max_trials",
        )
    with col8:
        st.number_input(
            "交叉验证折数",
            min_value=2, max_value=20, step=1,
            key="dev_cv_folds",
        )
    with col9:
        st.number_input(
            "早停轮数",
            min_value=1, max_value=500, step=5,
            key="dev_early_stop_rounds",
        )
    with col10:
        st.selectbox(
            "优化目标",
            options=["rankic", "icir", "multi", "custom"],
            key="dev_optimization_objective",
        )

    st.subheader("Claude Agent")
    st.selectbox(
        "权限模式 ",
        options=["bypassPermissions", "auto", "default"],
        key="dev_permission_mode",
        help="bypassPermissions: 跳过授权, auto: 自动确认, default: 手动授权",
    )

    if st.button("💾 保存因子开发配置", key="save_development", type="primary", use_container_width=True):
        cfg = {
            "llm_model": st.session_state.dev_llm_model,
            "llm_temperature": st.session_state.dev_llm_temperature,
            "max_auto_fixes": st.session_state.dev_max_auto_fixes,
            "enable_leak_test": st.session_state.dev_enable_leak_test,
            "enable_unit_check": st.session_state.dev_enable_unit_check,
            "enable_semantic_review": st.session_state.dev_enable_semantic_review,
            "enable_param_search": st.session_state.dev_enable_param_search,
            "max_trials": st.session_state.dev_max_trials,
            "cv_folds": st.session_state.dev_cv_folds,
            "early_stop_rounds": st.session_state.dev_early_stop_rounds,
            "optimization_objective": st.session_state.dev_optimization_objective,
            "permission_mode": st.session_state.dev_permission_mode,
        }
        save_config(config_dir, "development.yaml", cfg)
        st.session_state["config_development"] = cfg
        st.success("✅ 因子开发配置已保存到 development.yaml")


# ============================================================
# Tab 4: 因子评测 (evaluation.yaml)
# ============================================================

with tab_eval:
    st.subheader("时间区间")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.text_input(
            "样本内起始",
            key="eval_in_sample_start",
            help="格式: YYYY-MM",
        )
    with col2:
        st.text_input(
            "样本内截止",
            key="eval_in_sample_end",
            help="格式: YYYY-MM",
        )
    with col3:
        st.text_input(
            "样本外起始",
            key="eval_oos_start",
            help="格式: YYYY-MM",
        )
    with col4:
        st.text_input(
            "样本外截止",
            key="eval_oos_end",
            help="格式: YYYY-MM",
        )

    st.subheader("股票池筛选")
    col5, col6 = st.columns(2)
    with col5:
        st.checkbox(
            "剔除 ST 股票",
            key="eval_exclude_st",
        )
    with col6:
        st.number_input(
            "最小上市天数",
            min_value=0, max_value=365, step=10,
            key="eval_min_listing_days",
        )

    st.subheader("IC 计算")
    col7, col8, col9 = st.columns(3)
    with col7:
        st.selectbox(
            "相关性方法",
            options=["spearman", "pearson", "kendall"],
            key="eval_corr_method",
        )
    with col8:
        st.number_input(
            "IC 回溯期数",
            min_value=1, max_value=252, step=1,
            key="eval_ic_lookback",
        )
    with col9:
        st.number_input(
            "因子回溯期数",
            min_value=1, max_value=60, step=1,
            key="eval_period_lookback",
        )

    st.text_input(
        "IC 衰减周期",
        key="eval_ic_decay_periods",
        help="逗号分隔的整数列表，如: 1, 2, 3, 6, 12",
    )

    st.subheader("分组回测")
    col10, col11 = st.columns(2)
    with col10:
        st.number_input(
            "分组数",
            min_value=2, max_value=20, step=1,
            key="eval_group_num",
        )
    with col11:
        st.selectbox(
            "再平衡频率",
            options=["daily", "weekly", "monthly"],
            key="eval_rebalance_freq",
        )

    st.subheader("入库决策阈值")
    col12, col13, col14, col15 = st.columns(4)
    with col12:
        st.number_input(
            "Alpha t 统计量",
            min_value=0.0, max_value=10.0, step=0.1, format="%.2f",
            key="eval_min_alpha_t",
        )
    with col13:
        st.number_input(
            "综合评分",
            min_value=0.0, max_value=1.0, step=0.05, format="%.2f",
            key="eval_min_composite_score",
        )
    with col14:
        st.number_input(
            "增量 IC t",
            min_value=0.0, max_value=10.0, step=0.1, format="%.2f",
            key="eval_min_incremental_ic_t",
        )
    with col15:
        st.number_input(
            "OOS RankIC",
            min_value=0.0, max_value=1.0, step=0.01, format="%.3f",
            key="eval_min_oos_rankic",
        )

    st.number_input(
        "相关性预警阈值",
        min_value=0.0, max_value=1.0, step=0.05, format="%.2f",
        key="eval_corr_warning_threshold",
    )

    st.subheader("评分权重")
    weight_labels = {
        "effectiveness": "有效性",
        "stability": "稳定性",
        "turnover": "换手率",
        "diversity": "多样性",
        "overfitting_risk": "过拟合风险",
    }
    w_cols = st.columns(5)
    for i, (key, label) in enumerate(weight_labels.items()):
        with w_cols[i]:
            st.number_input(
                label,
                min_value=0.0, max_value=1.0, step=0.05, format="%.2f",
                key=f"eval_weight_{key}",
            )

    st.subheader("输出与缓存")
    col16, col17, col18 = st.columns(3)
    with col16:
        st.checkbox(
            "写入挖掘日志库",
            key="eval_save_to_mining_log",
        )
    with col17:
        st.checkbox(
            "启用缓存",
            key="eval_cache_enabled",
        )
    with col18:
        st.selectbox(
            "缓存启动模式",
            options=["continue", "new"],
            key="eval_cache_start_mode",
            help='"new" 每次清空缓存，"continue" 复用已有缓存',
        )

    st.text_input(
        "缓存目录",
        key="eval_cache_dir",
        help="留空表示使用系统临时目录",
    )

    if st.button("💾 保存因子评测配置", key="save_evaluation", type="primary", use_container_width=True):
        # 解析 ic_decay_periods
        raw_decay = st.session_state.eval_ic_decay_periods
        try:
            ic_decay = [int(x.strip()) for x in raw_decay.split(",") if x.strip()]
        except ValueError:
            ic_decay = [1, 2, 3, 6, 12]
            st.warning(f"⚠️ IC 衰减周期格式有误，已恢复默认值: {ic_decay}")

        cache_dir = st.session_state.eval_cache_dir.strip() or None

        cfg = {
            "in_sample_start": st.session_state.eval_in_sample_start,
            "in_sample_end": st.session_state.eval_in_sample_end,
            "oos_start": st.session_state.eval_oos_start,
            "oos_end": st.session_state.eval_oos_end,
            "exclude_st": st.session_state.eval_exclude_st,
            "min_listing_days": st.session_state.eval_min_listing_days,
            "corr_method": st.session_state.eval_corr_method,
            "ic_lookback": st.session_state.eval_ic_lookback,
            "period_lookback": st.session_state.eval_period_lookback,
            "ic_decay_periods": ic_decay,
            "group_num": st.session_state.eval_group_num,
            "rebalance_freq": st.session_state.eval_rebalance_freq,
            "min_alpha_t": st.session_state.eval_min_alpha_t,
            "min_composite_score": st.session_state.eval_min_composite_score,
            "min_incremental_ic_t": st.session_state.eval_min_incremental_ic_t,
            "min_oos_rankic": st.session_state.eval_min_oos_rankic,
            "corr_warning_threshold": st.session_state.eval_corr_warning_threshold,
            "score_weights": {
                "effectiveness": st.session_state.eval_weight_effectiveness,
                "stability": st.session_state.eval_weight_stability,
                "turnover": st.session_state.eval_weight_turnover,
                "diversity": st.session_state.eval_weight_diversity,
                "overfitting_risk": st.session_state.eval_weight_overfitting_risk,
            },
            "save_to_mining_log": st.session_state.eval_save_to_mining_log,
            "cache_enabled": st.session_state.eval_cache_enabled,
            "cache_dir": cache_dir,
            "cache_start_mode": st.session_state.eval_cache_start_mode,
        }
        save_config(config_dir, "evaluation.yaml", cfg)
        st.session_state["config_evaluation"] = cfg
        st.success("✅ 因子评测配置已保存到 evaluation.yaml")


# ============================================================
# 运行参数（控制页面使用）
# ============================================================

st.markdown("---")
st.subheader("🎯 运行参数")
st.caption("以下参数用于控制页面启动挖掘时传递给子进程，不写入 YAML 文件。")

# 预定义研究方向目录
DIRECTION_CATALOG = [
    "全部",
    "动量/短期反转", "动量/中期动量", "动量/动量因子",
    "估值/EP_TTM", "估值/BP_MRQ", "估值/SP_TTM",
    "波动率/低波动率", "波动率/特质波动率",
    "流动性/换手率", "流动性/非流动性",
    "质量/ROE", "质量/毛利率",
    "技术/量价背离", "技术/成交额分布",
]

# 初始化默认值
if "mining_config" not in st.session_state:
    st.session_state.mining_config = {}

_mining_cfg = st.session_state.mining_config

col_r1, col_r2, col_r3 = st.columns(3)
with col_r1:
    direction = st.selectbox(
        "研究方向",
        options=DIRECTION_CATALOG,
        index=DIRECTION_CATALOG.index(_mining_cfg.get("direction", "全部"))
        if _mining_cfg.get("direction", "全部") in DIRECTION_CATALOG else 0,
        key="run_direction",
        help="选择要探索的因子类别方向",
    )
with col_r2:
    mode = st.selectbox(
        "运行模式",
        options=["skill", "graph"],
        index=["skill", "graph"].index(_mining_cfg.get("mode", "skill")),
        key="run_mode",
        help="Skill 模式使用 Claude Agent SDK，Graph 模式使用 LangGraph",
    )
with col_r3:
    max_rounds = st.number_input(
        "最大轮次",
        value=_mining_cfg.get("max_rounds", 5),
        min_value=1, max_value=100, step=1,
        key="run_max_rounds",
    )

col_r4, col_r5, col_r6 = st.columns(3)
with col_r4:
    max_hours = st.number_input(
        "最大运行时间（小时）",
        value=float(_mining_cfg.get("max_hours", 4.0)),
        min_value=0.5, max_value=48.0, step=0.5,
        key="run_max_hours",
    )
with col_r5:
    # 默认使用 pipeline.yaml 中的 workspace_dir
    default_ws = _get("config_pipeline", "workspace_dir", default="")
    workspace_dir = st.text_input(
        "工作目录",
        value=_mining_cfg.get("workspace_dir", default_ws),
        key="run_workspace_dir",
        help="产出物输出目录，留空使用 pipeline.yaml 中的配置",
    )
with col_r6:
    # 默认使用 pipeline.yaml 中的配置路径
    default_config_path = str(config_dir / "pipeline.yaml") if config_dir else ""
    config_path = st.text_input(
        "配置文件路径",
        value=_mining_cfg.get("config_path", default_config_path),
        key="run_config_path",
        help="pipeline.yaml 的路径，留空使用默认",
    )

col_r7, _, _ = st.columns(3)
with col_r7:
    clear_cache = st.checkbox(
        "挖掘前清空评测缓存",
        value=_mining_cfg.get("clear_cache", True),
        key="run_clear_cache",
        help="取消勾选可复用已有缓存，加速重复运行",
    )

if st.button("💾 保存运行参数", key="save_run_params", use_container_width=True, type="primary"):
    st.session_state.mining_config = {
        "direction": st.session_state.run_direction,
        "mode": st.session_state.run_mode,
        "max_rounds": st.session_state.run_max_rounds,
        "max_hours": st.session_state.run_max_hours,
        "workspace_dir": st.session_state.run_workspace_dir,
        "config_path": st.session_state.run_config_path,
        "clear_cache": st.session_state.run_clear_cache,
        # 同步 pipeline.yaml 中的轮次限制
        "max_turns_hypothesis": _get("config_pipeline", "max_turns_hypothesis", default=50),
        "max_turns_development": _get("config_pipeline", "max_turns_development", default=80),
    }
    st.success("✅ 运行参数已保存！请前往 **控制** 页面启动挖掘。")


# ============================================================
# 底部：配置预览
# ============================================================

st.markdown("---")
with st.expander("📋 当前配置预览（YAML 原始内容）", expanded=False):
    preview_tab1, preview_tab2, preview_tab3, preview_tab4 = st.tabs([
        "pipeline", "hypothesis", "development", "evaluation",
    ])
    with preview_tab1:
        st.json(st.session_state.get("config_pipeline", {}))
    with preview_tab2:
        st.json(st.session_state.get("config_hypothesis", {}))
    with preview_tab3:
        st.json(st.session_state.get("config_development", {}))
    with preview_tab4:
        st.json(st.session_state.get("config_evaluation", {}))
