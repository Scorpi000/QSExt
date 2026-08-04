# -*- coding: utf-8 -*-
"""因子评测配置。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class EvalConfig:
    """因子评测配置。

    Attributes:
        in_sample_start/is_end: 样本内区间
        oos_start/oos_end: 样本外区间
        exclude_st: 是否剔除 ST
        min_listing_days: 最小上市天数
        corr_method: 相关性方法 (spearman/pearson/kendall)
        ic_lookback: IC 回溯期数
        period_lookback: 因子回溯期数
        group_num: 分组数
        rebalance_freq: 再平衡频率 (daily/weekly/monthly)
        min_alpha_t: Alpha t 统计量阈值
        min_composite_score: 综合评分阈值
        min_incremental_ic_t: 增量 IC t 阈值（多样性主关卡）
        min_oos_rankic: OOS RankIC 阈值
        corr_warning_threshold: 相关性预警阈值（非硬门槛）
        score_weights: 五维度评分权重
        save_to_mining_log: 是否写入挖掘日志库
        cache_enabled: 是否启用因子数据缓存（FeatherFactorCache）
        cache_dir: 缓存目录路径，None 表示使用系统临时目录
        cache_start_mode: 缓存启动模式，"new" 清空缓存，"continue" 复用已有缓存
    """
    # 时间区间
    in_sample_start: str = "2015-01"
    in_sample_end: str = "2022-12"
    oos_start: str = "2023-01"
    oos_end: str = "2025-12"

    # 股票池筛选
    exclude_st: bool = True
    min_listing_days: int = 60

    # IC 计算
    corr_method: str = "spearman"
    ic_lookback: int = 31
    period_lookback: int = 1
    ic_decay_periods: list = field(default_factory=lambda: [1, 2, 3, 6, 12])

    # 分组回测
    group_num: int = 5
    rebalance_freq: str = "monthly"

    # 入库决策阈值（v1）
    min_alpha_t: float = 3.0
    min_composite_score: float = 0.60
    min_incremental_ic_t: float = 2.0
    min_oos_rankic: float = 0.02
    corr_warning_threshold: float = 0.7

    # 评分权重
    score_weights: dict = field(default_factory=lambda: {
        "effectiveness": 0.25,
        "stability": 0.20,
        "turnover": 0.15,
        "diversity": 0.20,
        "overfitting_risk": 0.20,
    })

    # 输出
    save_to_mining_log: bool = True

    # 缓存配置
    cache_enabled: bool = True          # 是否启用因子数据缓存
    cache_dir: str | None = None        # 缓存目录，None 表示使用系统临时目录
    cache_start_mode: str = "continue"  # "new" 每次清空，"continue" 复用已有缓存

    @classmethod
    def from_yaml(cls, path: str) -> "EvalConfig":
        """从 YAML 文件加载配置。

        Args:
            path: YAML 文件路径

        Returns:
            EvalConfig 实例
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        weights = data.get("score_weights")
        if weights is None:
            weights = {
                "effectiveness": 0.25,
                "stability": 0.20,
                "turnover": 0.15,
                "diversity": 0.20,
                "overfitting_risk": 0.20,
            }

        return cls(
            in_sample_start=data.get("in_sample_start", "2015-01"),
            in_sample_end=data.get("in_sample_end", "2022-12"),
            oos_start=data.get("oos_start", "2023-01"),
            oos_end=data.get("oos_end", "2025-12"),
            exclude_st=data.get("exclude_st", True),
            min_listing_days=data.get("min_listing_days", 60),
            corr_method=data.get("corr_method", "spearman"),
            ic_lookback=data.get("ic_lookback", 31),
            period_lookback=data.get("period_lookback", 1),
            ic_decay_periods=data.get("ic_decay_periods", [1, 2, 3, 6, 12]),
            group_num=data.get("group_num", 5),
            rebalance_freq=data.get("rebalance_freq", "monthly"),
            min_alpha_t=data.get("min_alpha_t", 3.0),
            min_composite_score=data.get("min_composite_score", 0.60),
            min_incremental_ic_t=data.get("min_incremental_ic_t", 2.0),
            min_oos_rankic=data.get("min_oos_rankic", 0.02),
            corr_warning_threshold=data.get("corr_warning_threshold", 0.7),
            score_weights=weights,
            save_to_mining_log=data.get("save_to_mining_log", True),
            cache_enabled=data.get("cache_enabled", True),
            cache_dir=data.get("cache_dir", None),
            cache_start_mode=data.get("cache_start_mode", "continue"),
        )
