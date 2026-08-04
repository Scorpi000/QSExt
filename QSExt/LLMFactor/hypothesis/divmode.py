# -*- coding: utf-8 -*-
"""多样化模式选择器。

提供五种多样化模式，用于 Step 3 假设生成阶段注入多样性：
  - light: 轻度变异（温度 0.3）
  - moderate: 中度变异（温度 0.5）
  - creative: 创意变异（温度 0.7）
  - divergent: 发散变异（温度 0.9）
  - concrete: 具象变异（温度 0.4）
"""
from __future__ import annotations

import random
from enum import Enum
from typing import Optional


class DiversityMode(str, Enum):
    """多样化模式枚举。"""
    LIGHT = "light"             # 轻度变异
    MODERATE = "moderate"       # 中度变异
    CREATIVE = "creative"       # 创意变异
    DIVERGENT = "divergent"     # 发散变异
    CONCRETE = "concrete"       # 具象变异


# 模式 → 温度映射
_MODE_TEMPERATURES: dict[DiversityMode, float] = {
    DiversityMode.LIGHT: 0.3,
    DiversityMode.MODERATE: 0.5,
    DiversityMode.CREATIVE: 0.7,
    DiversityMode.DIVERGENT: 0.9,
    DiversityMode.CONCRETE: 0.4,
}

# 模式 → 多样化指令
_MODE_INSTRUCTIONS: dict[DiversityMode, str] = {
    DiversityMode.LIGHT: (
        "在保持主流因子构造逻辑的基础上，对参数或计算窗口做适度调整，"
        "探索是否存在更优的参数组合。"
    ),
    DiversityMode.MODERATE: (
        "在已有因子逻辑的基础上，尝试替换部分计算步骤或组合方式，"
        "产生与现有因子相关性适中的新因子。"
    ),
    DiversityMode.CREATIVE: (
        "跳出常规因子构造范式，从不同学科（如物理学、心理学）或"
        "非传统数据源中寻找灵感，创造全新的因子逻辑。"
    ),
    DiversityMode.DIVERGENT: (
        "最大化探索范围，尝试与现有因子完全不同的计算路径，"
        "即使风险较高也要追求最大的差异化。"
    ),
    DiversityMode.CONCRETE: (
        "从具体的市场现象或交易场景出发，构建与实际交易行为"
        "直接对应的因子，强调可解释性和实际应用价值。"
    ),
}


class DiversityModeSelector:
    """多样化模式选择器。

    支持随机选择、指定模式、按权重选择等方式。
    """

    def __init__(self, weights: Optional[dict[DiversityMode, float]] = None):
        """初始化选择器。

        Args:
            weights: 各模式的选择权重，默认均匀分布
        """
        self._weights = weights or {mode: 1.0 for mode in DiversityMode}

    def select(self, mode: Optional[DiversityMode] = None) -> DiversityMode:
        """选择一个多样化模式。

        Args:
            mode: 指定模式，为 None 时按权重随机选择

        Returns:
            选中的多样化模式
        """
        if mode is not None:
            return mode

        modes = list(self._weights.keys())
        weights = [self._weights[m] for m in modes]
        return random.choices(modes, weights=weights, k=1)[0]

    def get_temperature(self, mode: DiversityMode) -> float:
        """获取指定模式的温度参数。

        Args:
            mode: 多样化模式

        Returns:
            对应的温度值
        """
        return _MODE_TEMPERATURES.get(mode, 0.5)

    def get_instruction(self, mode: DiversityMode) -> str:
        """获取指定模式的多样化指令。

        Args:
            mode: 多样化模式

        Returns:
            对应的多样化指令文本
        """
        return _MODE_INSTRUCTIONS.get(mode, "")

    def get_all_modes(self) -> list[DiversityMode]:
        """获取所有可用模式列表。"""
        return list(DiversityMode)
