# -*- coding: utf-8 -*-
"""假设生成模块配置。

提供 ResearchConfig 数据类，支持从 YAML 文件或 dict 加载。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import yaml


@dataclass
class ResearchConfig:
    """研究方向配置，可从 YAML 加载。

    Attributes:
        target: 研究目标，如 "动量因子"
        market: 目标市场，如 "A股"
        frequency: 数据频率，如 "日频"
        data_domains: 允许的数据域列表
        avoid_domains: 需要规避的数据域列表
        reference_factors: 参考因子 QSID 列表
        correlation_warning_threshold: 相关性预警阈值（软约束）
        min_incremental_ic_t: 增量 IC t 统计量阈值
        min_turnover_days: 最小换手天数
        llm_provider: LLM 提供商（仅第二阶段使用）
        llm_model: LLM 模型名称（仅第二阶段使用）
        max_directions: 最大方向数
        max_wiki_pages_per_direction: 每方向最大 wiki 页面数
        max_factor_codes_per_direction: 每方向最大因子代码数
        freeze_after_n_failures: 连续失败 N 次后冻结方向
    """
    # 研究方向
    target: str = ""
    market: str = "A股"
    frequency: str = "日频"
    data_domains: list[str] = field(default_factory=list)
    avoid_domains: list[str] = field(default_factory=list)
    reference_factors: list[str] = field(default_factory=list)

    # 约束（软）
    correlation_warning_threshold: float = 0.7
    min_incremental_ic_t: float = 2.0
    min_turnover_days: int = 5

    # LLM 配置（仅第二阶段使用）
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

    # 搜索预算
    max_directions: int = 5
    max_wiki_pages_per_direction: int = 5
    max_factor_codes_per_direction: int = 3

    # 动态调整
    freeze_after_n_failures: int = 3

    # Claude Agent 权限模式
    permission_mode: str = "bypassPermissions"

    @classmethod
    def from_yaml(cls, path: str) -> "ResearchConfig":
        """从 YAML 文件加载配置。

        Args:
            path: YAML 文件路径

        Returns:
            ResearchConfig 实例
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ResearchConfig":
        """从 dict 加载配置。

        Args:
            d: 配置字典，支持嵌套的 research_direction 结构

        Returns:
            ResearchConfig 实例
        """
        # 支持嵌套的 research_direction 结构
        if "research_direction" in d:
            d = d["research_direction"]

        constraints = d.get("constraints", {})

        return cls(
            target=d.get("target", ""),
            market=d.get("market", "A股"),
            frequency=d.get("frequency", "日频"),
            data_domains=d.get("data_domains", []),
            avoid_domains=d.get("avoid_domains", []),
            reference_factors=d.get("reference_factors", []),
            correlation_warning_threshold=constraints.get(
                "correlation_warning_threshold", 0.7
            ),
            min_incremental_ic_t=constraints.get("min_incremental_ic_t", 2.0),
            min_turnover_days=constraints.get("min_turnover_days", 5),
            llm_provider=d.get("llm_provider"),
            llm_model=d.get("llm_model"),
            max_directions=d.get("max_directions", 5),
            max_wiki_pages_per_direction=d.get("max_wiki_pages_per_direction", 5),
            max_factor_codes_per_direction=d.get("max_factor_codes_per_direction", 3),
            freeze_after_n_failures=d.get("freeze_after_n_failures", 3),
            permission_mode=d.get("permission_mode", "bypassPermissions"),
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict。"""
        return {
            "target": self.target,
            "market": self.market,
            "frequency": self.frequency,
            "data_domains": self.data_domains,
            "avoid_domains": self.avoid_domains,
            "reference_factors": self.reference_factors,
            "constraints": {
                "correlation_warning_threshold": self.correlation_warning_threshold,
                "min_incremental_ic_t": self.min_incremental_ic_t,
                "min_turnover_days": self.min_turnover_days,
            },
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "max_directions": self.max_directions,
            "max_wiki_pages_per_direction": self.max_wiki_pages_per_direction,
            "max_factor_codes_per_direction": self.max_factor_codes_per_direction,
            "freeze_after_n_failures": self.freeze_after_n_failures,
            "permission_mode": self.permission_mode,
        }
