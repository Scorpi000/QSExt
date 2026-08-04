# -*- coding: utf-8 -*-
"""MiningLogRetriever — 假设生成阶段的核心检索接口。

提供对挖掘日志库的结构化查询能力：
  - 语义/关键词搜索历史运行记录
  - 获取成功经验库中的可复用组件
  - 检索相似方向上的历史失败记录
  - 统计各方向的覆盖率和成功率
  - 获取频繁代码结构（供生成去同质化）
  - 查询因子演化历史
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from psycopg2.extras import RealDictCursor

from QSExt.LLMFactor.mining_log.models import (
    MiningRun,
    Experience,
    Decision,
    ExperienceTrack,
    ExperienceType,
)
from QSExt.LLMFactor.mining_log.repository import MiningLogRepository
from QSExt.LLMFactor.mining_log.embedding import EmbeddingService

logger = logging.getLogger(__name__)


# ============================================================
# 检索结果类型
# ============================================================

def _get_meta(d: dict[str, Any], key: str, default: Any = "") -> Any:
    """从 metadata dict 安全取值。"""
    return d.get(key, default) if isinstance(d, dict) else default


@dataclass
class RunSummary:
    """运行记录摘要（轻量，不包含完整 metadata）。"""
    run_id: str
    hypothesis_id: str
    factor_name: str
    category: str
    direction_tag: str
    status: str
    decision: Optional[str]
    decision_reason: str
    rankic_mean: Optional[float]
    rankicir: Optional[float]
    incremental_ic_t: Optional[float]
    composite_score: Optional[float]
    parent_run_id: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    created_at: Optional[str] = None

    @classmethod
    def from_run(cls, run: MiningRun) -> "RunSummary":
        m = run.metadata
        return cls(
            run_id=run.id,
            hypothesis_id=_get_meta(m, "hypothesis_id", ""),
            factor_name=_get_meta(m, "factor_name", ""),
            category=_get_meta(m, "category", ""),
            direction_tag=_get_meta(m, "direction_tag", ""),
            status=_get_meta(m, "status", "pending"),
            decision=_get_meta(m, "decision"),
            decision_reason=_get_meta(m, "decision_reason", ""),
            rankic_mean=_get_meta(m, "rankic_mean"),
            rankicir=_get_meta(m, "rankicir"),
            incremental_ic_t=_get_meta(m, "incremental_ic_t"),
            composite_score=_get_meta(m, "composite_score"),
            parent_run_id=_get_meta(m, "parent_run_id"),
            tags=run.tags,
            created_at=run.created_at.isoformat() if run.created_at else None,
        )


@dataclass
class DirectionStats:
    """方向统计数据。"""
    direction_tag: str
    attempts: int
    successes: int
    success_rate: float = 0.0

    def __post_init__(self):
        if self.attempts > 0:
            self.success_rate = self.successes / self.attempts


@dataclass
class FailureTrajectory:
    """失败轨迹摘要。"""
    experience_id: str
    direction_tag: str
    failure_type: Optional[str]
    description: str
    lesson_learned: str
    recovery_strategy: str
    source_run_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_experience(cls, exp: Experience) -> "FailureTrajectory":
        m = exp.metadata
        return cls(
            experience_id=exp.id,
            direction_tag=_get_meta(m, "direction_tag", ""),
            failure_type=_get_meta(m, "failure_type"),
            description=_get_meta(m, "description", ""),
            lesson_learned=_get_meta(m, "lesson_learned", ""),
            recovery_strategy=_get_meta(m, "recovery_strategy", ""),
            source_run_ids=_get_meta(m, "source_mining_ids", []),
        )


@dataclass
class ExperienceComponent:
    """成功经验组件。"""
    experience_id: str
    name: str
    exp_type: str
    description: str
    code_snippet: str
    financial_rationale: str
    quality_score: float
    usage_count: int
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_experience(cls, exp: Experience) -> "ExperienceComponent":
        m = exp.metadata
        return cls(
            experience_id=exp.id,
            name=_get_meta(m, "name", ""),
            exp_type=_get_meta(m, "type", ""),
            description=_get_meta(m, "description", ""),
            code_snippet=_get_meta(m, "code_snippet", ""),
            financial_rationale=_get_meta(m, "financial_rationale", ""),
            quality_score=float(_get_meta(m, "quality_score", 0)),
            usage_count=int(_get_meta(m, "usage_count", 0)),
            tags=exp.tags,
        )


# ============================================================
# MiningLogRetriever
# ============================================================

class MiningLogRetriever:
    """挖掘日志检索器 — 假设生成阶段的核心依赖。

    整合全文检索、标签匹配和结构化过滤，为假设生成提供
    历史经验（成功+失败）、方向覆盖率和频繁结构等信息。
    """

    def __init__(self, repo: MiningLogRepository, embedding_service: Optional[EmbeddingService] = None):
        self._repo = repo
        self._embedding_service = embedding_service or repo._embedding_service

    # ---- 运行记录检索 ----

    def search_by_direction(
        self, query: str, top_k: int = 10
    ) -> list[RunSummary]:
        """按研究方向搜索相关历史记录。

        使用组合策略：
        1. 标签精确匹配 (tags @>)
        2. 全文检索 (tsv_content)
        结果去重合并后返回 top_k 条。
        """
        text_results = self._repo.search_by_content(query, limit=top_k * 2)
        seen_ids = {r.id for r in text_results}
        all_runs = list(text_results)

        tag_candidates = [t for t in query.replace("，", ",").replace(" ", ",").split(",") if t.strip()]
        if tag_candidates:
            tag_results = self._repo.search_by_tags(tag_candidates, limit=top_k)
            for r in tag_results:
                if r.id not in seen_ids:
                    all_runs.append(r)
                    seen_ids.add(r.id)

        return [RunSummary.from_run(r) for r in all_runs[:top_k]]

    # ---- 语义检索 ----

    def search_by_embedding(
        self,
        query: str,
        table: str = "mining_log",
        top_k: int = 10,
        score_threshold: float = 0.3,
        track: Optional[str] = None,
    ) -> list[tuple[RunSummary | ExperienceComponent, float]]:
        """语义搜索：将 query 向量化后执行余弦相似度检索。

        Args:
            query: 自然语言查询文本
            table: 检索目标表，"mining_log" 或 "mining_experience"
            top_k: 返回数量上限
            score_threshold: 余弦相似度阈值（0~1）
            track: experience 表过滤: "success" / "failure"

        Returns:
            list of (result, score) 元组，按相似度降序
        """
        if self._embedding_service is None:
            logger.warning("EmbeddingService 未配置，无法执行语义检索")
            return []

        vec = self._embedding_service.encode(query)
        vec_str = self._embedding_service.to_db_format(vec)

        if table == "mining_experience":
            raw = self._repo.search_experience_by_embedding(
                vec_str, top_k=top_k, score_threshold=score_threshold, track=track,
            )
            return [(ExperienceComponent.from_experience(exp), score) for exp, score in raw]
        else:
            raw = self._repo.search_mining_log_by_embedding(
                vec_str, top_k=top_k, score_threshold=score_threshold,
            )
            return [(RunSummary.from_run(run), score) for run, score in raw]

    def search_similar_accepted(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.3,
    ) -> list[tuple[RunSummary, float]]:
        """语义搜索 accepted 运行记录，供 few-shot 范例。

        Returns:
            list of (RunSummary, score) 元组，按相似度降序
        """
        if self._embedding_service is None:
            logger.warning("EmbeddingService 未配置，无法执行语义检索")
            return []

        vec = self._embedding_service.encode(query)
        vec_str = self._embedding_service.to_db_format(vec)
        raw = self._repo.search_mining_log_by_embedding(
            vec_str, top_k=top_k * 3, score_threshold=score_threshold,
        )
        # 过滤仅保留 accepted
        results = []
        for run, score in raw:
            if run.metadata.get("decision") == Decision.ACCEPTED.value:
                results.append((RunSummary.from_run(run), score))
                if len(results) >= top_k:
                    break
        return results

    def get_similar_failures(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.3,
    ) -> list[tuple[FailureTrajectory, float]]:
        """语义搜索失败经验，供规避参考。

        Returns:
            list of (FailureTrajectory, score) 元组，按相似度降序
        """
        if self._embedding_service is None:
            logger.warning("EmbeddingService 未配置，无法执行语义检索")
            return []

        vec = self._embedding_service.encode(query)
        vec_str = self._embedding_service.to_db_format(vec)
        raw = self._repo.search_experience_by_embedding(
            vec_str, top_k=top_k, score_threshold=score_threshold, track="failure",
        )
        return [(FailureTrajectory.from_experience(exp), score) for exp, score in raw]

    def search_accepted_in_direction(
        self, direction_tag: str, limit: int = 10
    ) -> list[RunSummary]:
        """获取特定方向的成功入库记录（作为 few-shot 范例）。"""
        runs = self._repo.get_runs_by_direction(direction_tag, limit=limit * 2)
        accepted = [r for r in runs if r.metadata.get("decision") == Decision.ACCEPTED.value]
        return [RunSummary.from_run(r) for r in accepted[:limit]]

    # ---- 经验检索 ----

    def get_successful_patterns(
        self,
        domain: Optional[str] = None,
        direction_tag: Optional[str] = None,
        min_quality: float = 0.7,
        limit: int = 20,
    ) -> list[ExperienceComponent]:
        """获取成功经验库中的可复用组件。

        domain: 经验类型过滤 (logic_component / tool_function / formula_pattern)
        direction_tag: 方向过滤
        min_quality: 最低质量分
        """
        exp_type = ExperienceType(domain) if domain else None
        exps = self._repo.get_success_experiences(
            exp_type=exp_type, min_quality=min_quality, limit=limit,
        )
        if direction_tag:
            exps = [e for e in exps if e.metadata.get("direction_tag") == direction_tag]
        return [ExperienceComponent.from_experience(e) for e in exps]

    def get_failed_directions(
        self, query: str, limit: int = 10
    ) -> list[FailureTrajectory]:
        """检索相似方向的历史失败记录。"""
        exps = self._repo.get_failure_experiences(limit=limit * 2)
        if not exps:
            text_exps = self._repo.search_experiences_by_content(
                query, track=ExperienceTrack.FAILURE, limit=limit,
            )
            return [FailureTrajectory.from_experience(e) for e in text_exps[:limit]]
        return [FailureTrajectory.from_experience(e) for e in exps[:limit]]

    def get_failure_by_direction(
        self, direction_tag: str, limit: int = 10
    ) -> list[FailureTrajectory]:
        """按方向标签获取失败记录。"""
        exps = self._repo.get_failure_experiences(
            direction_tag=direction_tag, limit=limit,
        )
        return [FailureTrajectory.from_experience(e) for e in exps]

    # ---- 方向覆盖率 ----

    def get_direction_coverage(self) -> dict[str, DirectionStats]:
        """统计各方向的探索次数和成功率，识别未充分探索的区域。"""
        raw = self._repo.count_by_direction()
        return {
            tag: DirectionStats(
                direction_tag=tag,
                attempts=info["attempts"],
                successes=info["successes"],
            )
            for tag, info in raw.items()
        }

    def get_unexplored_directions(self, all_directions: set[str]) -> list[str]:
        """返回尚未探索过的方向列表。"""
        covered = set(self._repo.count_by_direction().keys())
        return sorted(all_directions - covered)

    # ---- 频繁结构 (简化版) ----

    def get_frequent_patterns(self, top_k: int = 3) -> list[dict[str, Any]]:
        """获取最频繁的方向/类别组合（启发式频繁结构近似）。"""
        coverage = self._repo.count_by_direction()
        sorted_dirs = sorted(coverage.items(), key=lambda x: x[1]["attempts"], reverse=True)
        patterns = []
        for tag, stats in sorted_dirs[:top_k]:
            runs = self._repo.get_runs_by_direction(tag, limit=3)
            accepted = [r for r in runs if r.metadata.get("decision") == Decision.ACCEPTED.value]
            patterns.append({
                "pattern_name": tag,
                "attempts": stats["attempts"],
                "successes": stats["successes"],
                "examples": [
                    {
                        "factor_name": r.metadata.get("factor_name", ""),
                        "rankic_mean": r.metadata.get("rankic_mean"),
                    }
                    for r in accepted
                ],
            })
        return patterns

    # ---- 排行榜 ----

    def get_top_factors(
        self, metric: str = "rankic_mean", limit: int = 10
    ) -> list[RunSummary]:
        """获取排行前列的入库因子。"""
        runs = self._repo.get_accepted_runs(limit=limit * 3)
        if metric == "composite_score":
            runs.sort(key=lambda r: r.metadata.get("composite_score") or 0, reverse=True)
        elif metric == "incremental_ic_t":
            runs.sort(key=lambda r: r.metadata.get("incremental_ic_t") or 0, reverse=True)
        else:
            runs.sort(key=lambda r: r.metadata.get("rankic_mean") or 0, reverse=True)
        return [RunSummary.from_run(r) for r in runs[:limit]]

    # ---- 演化追溯 ----

    def get_factor_evolution_trail(
        self, factor_name: str
    ) -> list[RunSummary]:
        """追溯一个因子名称的完整演化历史（同名因子多次运行）。"""
        with self._repo.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM mining_log
                WHERE doc_type = 'mining_log'
                  AND metadata->>'factor_name' = %(name)s
                ORDER BY created_at ASC
            """, {"name": factor_name})
            from QSExt.LLMFactor.mining_log.models import MiningRun
            rows = cur.fetchall()
            runs = [MiningRun.from_db_row(row) for row in rows]
            return [RunSummary.from_run(r) for r in runs]

    def get_evolution_tree(self, run_id: str) -> dict[str, Any]:
        """以给定运行 ID 为根，递归构建完整演化树。

        向下追溯所有后继精炼/改进（通过 parent_run_id 关联），
        向上追溯到最顶层的原始假设。
        """
        root = self._repo.get_run(run_id)
        if root is None:
            return {}

        # 向上追溯到根（最原始的假设）
        current = root
        while current.metadata.get("parent_run_id"):
            parent = self._repo.get_run(current.metadata["parent_run_id"])
            if parent is None:
                break
            current = parent
        root_run = current

        def build_node(run: MiningRun) -> dict[str, Any]:
            children = self._repo.get_children(run.id)
            return {
                "run": RunSummary.from_run(run),
                "children": [build_node(child) for child in children],
            }

        return build_node(root_run)
