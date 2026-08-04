# -*- coding: utf-8 -*-
"""搜索预算分配器。

基于方案 3.4 节的简化版乘法模型，为候选方向分配搜索预算：
  budget = wiki_potential * (0.3 + 0.7 * success_rate) * (0.2 + 0.8 * unexplored_ratio)

预算得分用于决定在该方向上投入多少调研资源。
"""
from __future__ import annotations

from QSExt.LLMFactor.hypothesis.models import (
    DirectionCandidate,
    DirectionStats,
)


class BudgetAllocator:
    """搜索预算分配器。

    使用乘法模型综合考虑三个因素：
      1. wiki_potential: 知识库中的潜在信息量（基于关联页面数）
      2. success_rate: 该方向的历史成功率
      3. unexplored_ratio: 该方向的未探索程度
    """

    def __init__(
        self,
        max_wiki_pages: int = 5,
        max_factor_codes: int = 3,
    ):
        """初始化预算分配器。

        Args:
            max_wiki_pages: 每方向最大 wiki 页面数
            max_factor_codes: 每方向最大因子代码数
        """
        self._max_wiki_pages = max_wiki_pages
        self._max_factor_codes = max_factor_codes

    def score(
        self,
        direction: DirectionCandidate,
        coverage: dict[str, DirectionStats],
    ) -> float:
        """计算方向的搜索预算得分。

        Args:
            direction: 候选方向
            coverage: 方向覆盖率统计

        Returns:
            预算得分（0~1）
        """
        # 1. wiki 潜力：关联页面数 / 最大页面数，上限 1.0
        wiki_potential = min(
            len(direction.wiki_pages) / max(self._max_wiki_pages, 1),
            1.0,
        )

        # 2. 历史成功率
        stats = coverage.get(direction.direction_tag)
        success_rate = stats.success_rate if stats else 0.0

        # 3. 未探索比例：该方向尝试次数越少，未探索比例越高
        if stats and stats.attempts > 0:
            # 使用反向归一化：尝试次数越多，未探索比例越低
            unexplored_ratio = 1.0 / (1.0 + stats.attempts)
        else:
            unexplored_ratio = 1.0  # 完全未探索

        # 乘法模型
        budget = wiki_potential * (0.3 + 0.7 * success_rate) * (0.2 + 0.8 * unexplored_ratio)
        return round(budget, 4)

    def allocate(
        self,
        directions: list[DirectionCandidate],
        coverage: dict[str, DirectionStats],
    ) -> list[DirectionCandidate]:
        """为所有候选方向分配预算得分并排序。

        Args:
            directions: 候选方向列表
            coverage: 方向覆盖率统计

        Returns:
            按预算得分降序排列的方向列表（budget_score 已更新）
        """
        for d in directions:
            d.budget_score = self.score(d, coverage)
        return sorted(directions, key=lambda d: d.budget_score, reverse=True)

    def get_wiki_budget(self, direction: DirectionCandidate) -> int:
        """获取该方向应调研的 wiki 页面数。

        Args:
            direction: 候选方向（budget_score 已设置）

        Returns:
            应调研的 wiki 页面数
        """
        # 按预算得分线性缩放，至少 1 页
        pages = max(1, int(self._max_wiki_pages * direction.budget_score))
        return min(pages, self._max_wiki_pages)

    def get_factor_code_budget(self, direction: DirectionCandidate) -> int:
        """获取该方向应获取的因子代码数。

        Args:
            direction: 候选方向（budget_score 已设置）

        Returns:
            应获取的因子代码数
        """
        codes = max(1, int(self._max_factor_codes * direction.budget_score))
        return min(codes, self._max_factor_codes)
