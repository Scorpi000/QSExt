# -*- coding: utf-8 -*-
"""方向调度器 — 自动选择下一个最有潜力的研究方向。

基于 MiningLogDB 的历史数据，使用 BudgetAllocator 的评分公式
对候选方向进行排序，选择得分最高的方向。

评分公式：
    score = wiki_potential * (0.3 + 0.7 * success_rate) * (0.2 + 0.8 * unexplored_ratio)

使用示例::

    from QSExt.LLMFactor.loop.scheduler import DirectionScheduler

    scheduler = DirectionScheduler()
    next_direction = scheduler.select_next(candidates)
"""
from __future__ import annotations

import logging
from typing import Optional

__QS_Logger__ = logging.getLogger("QSR.loop.scheduler")


class DirectionScheduler:
    """方向调度器。

    根据历史成功率和探索程度自动选择下一个研究方向。

    Attributes:
        retriever: MiningLogRetriever 实例
        allocator: BudgetAllocator 实例
        coverage: 各方向的历史覆盖数据
    """

    def __init__(self, retriever=None, allocator=None):
        """初始化调度器。

        Args:
            retriever: MiningLogRetriever 实例（可选，懒加载）
            allocator: BudgetAllocator 实例（可选，懒加载）
        """
        self._retriever = retriever
        self._allocator = allocator
        self._coverage = None

    @property
    def retriever(self):
        """懒加载 MiningLogRetriever。"""
        if self._retriever is None:
            try:
                from QSExt.LLMFactor.mining_log.retriever import MiningLogRetriever
                from QSExt.LLMFactor.mining_log.db import MiningLogDB
                db = MiningLogDB()
                db.init_tables()
                from QSExt.LLMFactor.mining_log.repository import MiningLogRepository
                repo = MiningLogRepository(db)
                self._retriever = MiningLogRetriever(repo)
            except Exception as e:
                __QS_Logger__.warning("无法初始化 MiningLogRetriever: %s", e)
        return self._retriever

    @property
    def allocator(self):
        """懒加载 BudgetAllocator。"""
        if self._allocator is None:
            from QSExt.LLMFactor.hypothesis.budget import BudgetAllocator
            self._allocator = BudgetAllocator()
        return self._allocator

    def get_coverage(self) -> dict:
        """获取各方向的历史覆盖数据。

        Returns:
            {direction_tag: DirectionStats} 字典
        """
        if self._coverage is None:
            try:
                if self.retriever:
                    self._coverage = self.retriever.get_direction_coverage()
                else:
                    self._coverage = {}
            except Exception as e:
                __QS_Logger__.warning("获取方向覆盖数据失败: %s", e)
                self._coverage = {}
        return self._coverage

    def select_next(self, candidates: list) -> Optional[object]:
        """从候选方向中选择下一个最有潜力的方向。

        Args:
            candidates: DirectionCandidate 列表

        Returns:
            得分最高的 DirectionCandidate，或 None（无候选）
        """
        if not candidates:
            __QS_Logger__.info("无候选方向可选")
            return None

        coverage = self.get_coverage()

        # 使用 BudgetAllocator 评分排序
        ranked = self.allocator.allocate(candidates, coverage)

        if not ranked:
            return None

        # 选择得分最高的方向
        best = ranked[0]
        __QS_Logger__.info(
            "选择方向: %s (score=%.3f, attempts=%d, success_rate=%.2f)",
            best.direction_tag,
            best.budget_score,
            best.coverage.attempts if best.coverage else 0,
            best.coverage.success_rate if best.coverage else 0.0,
        )

        return best

    def get_coverage_summary(self) -> dict:
        """获取当前各方向的探索状态摘要。

        Returns:
            {
                "total_directions": int,
                "total_attempts": int,
                "total_successes": int,
                "directions": [{direction_tag, attempts, successes, success_rate}, ...]
            }
        """
        coverage = self.get_coverage()
        total_attempts = sum(s.attempts for s in coverage.values())
        total_successes = sum(s.successes for s in coverage.values())

        return {
            "total_directions": len(coverage),
            "total_attempts": total_attempts,
            "total_successes": total_successes,
            "overall_success_rate": total_successes / total_attempts if total_attempts > 0 else 0.0,
            "directions": [
                {
                    "direction_tag": s.direction_tag,
                    "attempts": s.attempts,
                    "successes": s.successes,
                    "success_rate": s.success_rate,
                }
                for s in sorted(coverage.values(), key=lambda x: x.success_rate, reverse=True)
            ],
        }
