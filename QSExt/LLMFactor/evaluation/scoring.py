# -*- coding: utf-8 -*-
"""五维度评分算法。

基于方案文档 5.4 节的五维度评分体系：
1. 有效性（effectiveness）— RankIC 均值 + ICIR
2. 稳定性（stability）— IC 时序特征
3. 换手率（turnover）— 交易成本代理
4. 多样性（diversity）— 增量 IC 显著性
5. 过拟合风险（overfitting_risk）— IS/OOS 衰减比
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class FiveDimScore:
    """五维度综合评分（每个维度 0-1）。

    Attributes:
        effectiveness: 有效性评分
        stability: 稳定性评分
        turnover: 换手率评分
        diversity: 多样性评分
        overfitting_risk: 过拟合风险评分（低风险 → 高分）
        composite: 综合得分（加权平均）
    """
    effectiveness: float = 0.0
    stability: float = 0.0
    turnover: float = 0.0
    diversity: float = 0.0
    overfitting_risk: float = 0.0
    composite: float = 0.0

    def __post_init__(self):
        if self.composite == 0:
            self.composite = (
                0.25 * self.effectiveness +
                0.20 * self.stability +
                0.15 * self.turnover +
                0.20 * self.diversity +
                0.20 * self.overfitting_risk
            )

    def to_dict(self) -> dict:
        return {
            "有效性": self.effectiveness,
            "稳定性": self.stability,
            "换手率": self.turnover,
            "多样性": self.diversity,
            "过拟合风险": self.overfitting_risk,
            "综合评分": self.composite,
        }

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([self.to_dict()])


def calc_effectiveness(rankic_mean: float, icir: float) -> float:
    """有效性评分：RankIC 均值和 ICIR 的归一化。

    - RankIC: 0.02 → 0.5, 0.06 → 1.0
    - ICIR: 0.3 → 0.5, 0.8 → 1.0
    """
    ic_score = np.clip((abs(rankic_mean) - 0.01) / 0.05, 0, 1)
    ir_score = np.clip((abs(icir) - 0.1) / 0.7, 0, 1)
    return 0.6 * ic_score + 0.4 * ir_score


def calc_stability(ic_series: pd.Series) -> float:
    """稳定性评分：IC 时序特征。

    - 胜率（IC > 0 的比例）
    - IC 的自相关性（高自相关 → 更稳定）
    """
    if len(ic_series) < 3:
        return 0.5

    win_rate = (ic_series > 0).mean()
    autocorr = ic_series.autocorr(lag=1) if len(ic_series) > 2 else 0

    win_score = np.clip((win_rate - 0.4) / 0.3, 0, 1)
    stab_score = np.clip((autocorr + 0.5) / 1.0, 0, 1) if pd.notnull(autocorr) else 0.5

    return 0.6 * win_score + 0.4 * stab_score


def calc_turnover(avg_turnover: float) -> float:
    """换手率评分：低换手更好。

    - 换手率 0.3 → 1.0, 0.8 → 0.2
    """
    return np.clip(1.0 - (avg_turnover - 0.2) / 0.8, 0, 1)


def calc_diversity(incremental_ic_t: float, max_correlation: float = 0.0) -> float:
    """多样性评分：增量 IC 显著性 + 相关性惩罚。

    - 增量 IC t 统计量归一化
    - 相关性连续折价：(1 - MaxCorr * 0.3)
    """
    ic_score = np.clip((abs(incremental_ic_t) - 1.0) / 3.0, 0, 1)
    corr_penalty = 1.0 - max_correlation * 0.3
    return ic_score * corr_penalty


def calc_overfitting_risk(
    is_rankic: float,
    oos_rankic: float,
    is_icir: float,
    oos_icir: float,
) -> float:
    """过拟合风险评分（低风险 → 高分）。

    - 量化：IS/OOS 衰减比（> 0.7 → 低风险, < 0.3 → 高风险）
    """
    if abs(is_rankic) < 1e-6:
        return 0.5

    ic_decay = abs(oos_rankic / is_rankic) if abs(is_rankic) > 0 else 0.5
    ir_decay = abs(oos_icir / is_icir) if abs(is_icir) > 0 else 0.5

    decay_score = (
        np.clip((ic_decay - 0.3) / 0.5, 0, 1) * 0.5 +
        np.clip((ir_decay - 0.3) / 0.5, 0, 1) * 0.5
    )

    return decay_score


def calc_scores(
    ic_stats: dict,
    oos_ic_stats: dict = None,
    portfolio_stats: dict = None,
    incremental_ic_stats: dict = None,
    turnover_stats: dict = None,
    ic_series: pd.Series = None,
) -> FiveDimScore:
    """计算五维度评分。

    Parameters
    ----------
    ic_stats : dict
        样本内 IC 统计，包含 rankic_mean, icir 等
    oos_ic_stats : dict
        样本外 IC 统计（可选）
    portfolio_stats : dict
        分组回测统计（可选）
    incremental_ic_stats : dict
        增量 IC 统计，包含 t_stat, max_correlation 等
    turnover_stats : dict
        换手率统计，包含 avg_turnover
    ic_series : pd.Series
        IC 时间序列（可选，用于计算稳定性）

    Returns
    -------
    FiveDimScore
        五维度评分
    """
    # 有效性
    effectiveness = calc_effectiveness(
        ic_stats.get("rankic_mean", 0),
        ic_stats.get("icir", 0),
    )

    # 稳定性
    if ic_series is not None and len(ic_series) > 0:
        stability = calc_stability(ic_series)
    else:
        # 使用胜率近似
        win_rate = ic_stats.get("win_rate", 0.5)
        stability = np.clip((win_rate - 0.4) / 0.3, 0, 1)

    # 换手率
    avg_turnover = turnover_stats.get("avg_turnover", 0.5) if turnover_stats else 0.5
    turnover = calc_turnover(avg_turnover)

    # 多样性
    if incremental_ic_stats:
        diversity = calc_diversity(
            incremental_ic_stats.get("t_stat", 0),
            incremental_ic_stats.get("max_correlation", 0),
        )
    else:
        diversity = 0.5  # 默认中性

    # 过拟合风险
    if oos_ic_stats:
        overfitting = calc_overfitting_risk(
            ic_stats.get("rankic_mean", 0),
            oos_ic_stats.get("rankic_mean", 0),
            ic_stats.get("icir", 0),
            oos_ic_stats.get("icir", 0),
        )
    else:
        overfitting = 0.5  # 默认中性

    return FiveDimScore(
        effectiveness=effectiveness,
        stability=stability,
        turnover=turnover,
        diversity=diversity,
        overfitting_risk=overfitting,
    )
