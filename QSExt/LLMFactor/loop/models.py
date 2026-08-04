# -*- coding: utf-8 -*-
"""持续挖掘循环的数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RoundResult:
    """单轮挖掘的结果。

    Attributes:
        round_num: 轮次编号（从 1 开始）
        direction: 研究方向标签
        factor_name: 因子名称
        decision: 入库决策（accepted / refining / rejected / error）
        composite_score: 五维度综合评分
        elapsed_seconds: 本轮耗时
        workspace_dir: 本轮工作区目录
        error: 错误信息（如果有）
    """
    round_num: int
    direction: str
    factor_name: str = ""
    decision: str = "pending"
    composite_score: float = 0.0
    elapsed_seconds: float = 0.0
    workspace_dir: str = ""
    error: str | None = None


@dataclass
class LoopResult:
    """持续挖掘循环的总结果。

    Attributes:
        loop_id: 循环 ID（如 loop_20260709_140000）
        started_at: 开始时间
        finished_at: 结束时间
        total_rounds: 总轮次数
        accepted: 入库因子数
        rejected: 拒绝因子数
        refining: 待精炼因子数
        errors: 错误轮次数
        rounds: 各轮结果
    """
    loop_id: str
    started_at: str
    finished_at: str = ""
    total_rounds: int = 0
    accepted: int = 0
    rejected: int = 0
    refining: int = 0
    errors: int = 0
    rounds: list[RoundResult] = field(default_factory=list)

    def add_round(self, result: RoundResult):
        """添加一轮结果并更新统计。"""
        self.rounds.append(result)
        self.total_rounds = len(self.rounds)
        if result.decision == "accepted":
            self.accepted += 1
        elif result.decision == "rejected":
            self.rejected += 1
        elif result.decision == "refining":
            self.refining += 1
        elif result.decision == "error":
            self.errors += 1

    def to_dict(self) -> dict:
        """转为可序列化的字典。"""
        return {
            "loop_id": self.loop_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_rounds": self.total_rounds,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "refining": self.refining,
            "errors": self.errors,
            "rounds": [
                {
                    "round_num": r.round_num,
                    "direction": r.direction,
                    "factor_name": r.factor_name,
                    "decision": r.decision,
                    "composite_score": r.composite_score,
                    "elapsed_seconds": r.elapsed_seconds,
                    "workspace_dir": r.workspace_dir,
                    "error": r.error,
                }
                for r in self.rounds
            ],
        }
