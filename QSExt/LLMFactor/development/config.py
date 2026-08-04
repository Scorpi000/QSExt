# -*- coding: utf-8 -*-
"""因子开发配置。

提供 DevelopmentConfig 数据类，控制因子开发流程的各个环节：
  - 代码生成：LLM 模型和温度
  - 验证：自动修复次数、各验证器开关
  - 参数搜索：Optuna 配置、优化目标

使用示例::

    from QSExt.LLMFactor.development.config import DevelopmentConfig

    # 默认配置
    config = DevelopmentConfig()

    # 自定义配置
    config = DevelopmentConfig(
        max_auto_fixes=5,
        enable_leak_test=False,
        optimization_objective="custom",
        custom_objective_fn=lambda m, p: m.icir * 0.7 - m.turnover * 0.3,
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import yaml


@dataclass
class DevelopmentConfig:
    """因子开发配置。

    Attributes:
        llm_model: 代码生成和语义审查使用的 LLM 模型
        llm_temperature: LLM 温度（低温度确保一致性）

        max_auto_fixes: 最大自动修复次数
        enable_leak_test: 是否启用未来信息泄漏检测（时序截断测试）
        enable_unit_check: 是否启用单位检查
        enable_semantic_review: 是否启用语义审查 (LLM)

        enable_param_search: 是否启用参数搜索（关闭则跳过 Step 3）
        max_trials: Optuna 最大评估次数
        cv_folds: 交叉验证折数
        early_stop_rounds: 早停轮数（连续无改进则停止）
        timeout: 搜索超时（秒），None 表示不限时
        optimization_objective: 优化目标模式
            - "rankic": 单目标，最大化 RankIC（默认）
            - "icir": 单目标，最大化 ICIR
            - "multi": 多目标，按 multi_objective_weights 加权
            - "custom": 用户自定义，通过 custom_objective_fn 注入
        multi_objective_weights: 多目标权重，如 {"rankic": 0.6, "icir": 0.4}
        custom_objective_fn: 自定义目标函数
            签名: (metrics: EvalMetrics, params: dict) -> float
            ParamSearcher 将最大化该函数的返回值
        custom_metric_calculators: 自定义指标计算器列表
            每个计算器需实现 calculator(factor, price, fdi, params) -> dict
            返回的指标会合并到 EvalMetrics.extra 中
    """
    # ---- 代码生成 ----
    llm_model: str = "claude-sonnet-5"
    llm_temperature: float = 0.1

    # ---- 验证 ----
    max_auto_fixes: int = 3
    enable_leak_test: bool = True
    enable_unit_check: bool = True
    enable_semantic_review: bool = True

    # ---- 参数搜索 ----
    enable_param_search: bool = True   # 是否启用参数搜索（关闭则跳过 Step 3）
    max_trials: int = 200
    cv_folds: int = 3
    early_stop_rounds: int = 30
    timeout: Optional[int] = None
    optimization_objective: str = "rankic"
    multi_objective_weights: Optional[dict[str, float]] = None
    custom_objective_fn: Optional[Callable[[Any, dict], float]] = None
    custom_metric_calculators: Optional[list[Any]] = None

    # Claude Agent 权限模式
    permission_mode: str = "bypassPermissions"

    def __post_init__(self):
        self._validate()

    def _validate(self):
        """校验配置合法性。"""
        valid_objectives = {"rankic", "icir", "multi", "custom"}
        if self.optimization_objective not in valid_objectives:
            raise ValueError(
                f"optimization_objective 必须是 {valid_objectives} 之一，"
                f"当前值: '{self.optimization_objective}'"
            )

        if self.optimization_objective == "multi" and not self.multi_objective_weights:
            raise ValueError(
                "optimization_objective='multi' 时必须提供 multi_objective_weights"
            )

        if self.optimization_objective == "custom" and not self.custom_objective_fn:
            raise ValueError(
                "optimization_objective='custom' 时必须提供 custom_objective_fn"
            )

        if self.max_auto_fixes < 0:
            raise ValueError(f"max_auto_fixes 不能为负数: {self.max_auto_fixes}")

        if self.max_trials < 1:
            raise ValueError(f"max_trials 必须大于 0: {self.max_trials}")

        if self.cv_folds < 1:
            raise ValueError(f"cv_folds 必须大于 0: {self.cv_folds}")

    def to_dict(self) -> dict:
        """序列化为字典（不含不可序列化的字段）。"""
        return {
            "llm_model": self.llm_model,
            "llm_temperature": self.llm_temperature,
            "max_auto_fixes": self.max_auto_fixes,
            "enable_leak_test": self.enable_leak_test,
            "enable_unit_check": self.enable_unit_check,
            "enable_semantic_review": self.enable_semantic_review,
            "enable_param_search": self.enable_param_search,
            "max_trials": self.max_trials,
            "cv_folds": self.cv_folds,
            "early_stop_rounds": self.early_stop_rounds,
            "timeout": self.timeout,
            "optimization_objective": self.optimization_objective,
            "multi_objective_weights": self.multi_objective_weights,
            "permission_mode": self.permission_mode,
        }

    @classmethod
    def from_yaml(cls, path: str) -> "DevelopmentConfig":
        """从 YAML 文件加载配置。

        Args:
            path: YAML 文件路径

        Returns:
            DevelopmentConfig 实例
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(
            llm_model=data.get("llm_model", "claude-sonnet-5"),
            llm_temperature=data.get("llm_temperature", 0.1),
            max_auto_fixes=data.get("max_auto_fixes", 3),
            enable_leak_test=data.get("enable_leak_test", True),
            enable_unit_check=data.get("enable_unit_check", True),
            enable_semantic_review=data.get("enable_semantic_review", True),
            enable_param_search=data.get("enable_param_search", True),
            max_trials=data.get("max_trials", 200),
            cv_folds=data.get("cv_folds", 3),
            early_stop_rounds=data.get("early_stop_rounds", 30),
            timeout=data.get("timeout"),
            optimization_objective=data.get("optimization_objective", "rankic"),
            multi_objective_weights=data.get("multi_objective_weights"),
            permission_mode=data.get("permission_mode", "bypassPermissions"),
        )
