# -*- coding: utf-8 -*-
"""挖掘日志数据库 CRUD 操作。

基于 KDB PostgreSQL 文档表统一字段结构，对 mining_log 和 mining_experience
两张表进行增删改查。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor, Json

from QSExt.LLMFactor.mining_log.models import (
    MiningRun,
    Experience,
    RunStatus,
    Decision,
    ExperienceTrack,
    ExperienceType,
    FailureType,
    VerificationStatus,
)
from QSExt.LLMFactor.mining_log.db import MiningLogDB
from QSExt.LLMFactor.mining_log.embedding import EmbeddingService

logger = logging.getLogger(__name__)


class MiningLogRepository:
    """挖掘日志数据库仓库。

    提供对 mining_log 和 mining_experience 两张表的 CRUD 操作。
    metadata 中的业务字段通过 JSONB 操作符在 SQL 中直接访问。
    """

    def __init__(self, db: MiningLogDB, embedding_service: Optional[EmbeddingService] = None):
        self._db = db
        self._embedding_service = embedding_service

    @property
    def conn(self) -> psycopg2.extensions.connection:
        return self._db.connect()

    # ============================================================
    # MiningRun CRUD
    # ============================================================

    def _ensure_embedding(self, content: str) -> str:
        """调用 embedding 服务生成向量字符串。"""
        if self._embedding_service is None:
            return ""
        vec = self._embedding_service.encode(content)
        return self._embedding_service.to_db_format(vec)

    def insert_run(self, run: MiningRun) -> str:
        """插入一条挖掘运行记录，返回 run_id。"""
        if not run.embedding_str and run.content and self._embedding_service:
            run.embedding_str = self._ensure_embedding(run.content)
        row = run.to_db_row()
        with self.conn.cursor() as cur:
            fields = list(row.keys())
            values: list[str] = []
            for f in fields:
                if f == "metadata":
                    values.append(f"%(metadata)s::jsonb")
                elif f == "embedding" and row.get("embedding"):
                    values.append(f"%(embedding)s::vector")
                else:
                    values.append(f"%({f})s")

            cur.execute(f"""
                INSERT INTO mining_log ({', '.join(fields)})
                VALUES ({', '.join(values)})
                ON CONFLICT (id) DO UPDATE SET
                    source = EXCLUDED.source,
                    source_path = EXCLUDED.source_path,
                    content = EXCLUDED.content,
                    tags = EXCLUDED.tags,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    created_at = EXCLUDED.created_at
                RETURNING id
            """, row)
            result = cur.fetchone()
            return result[0] if result else run.id

    def get_run(self, run_id: str) -> Optional[MiningRun]:
        """按 run_id 查询单条记录。"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM mining_log WHERE id = %s AND doc_type = 'mining_log'",
                (run_id,),
            )
            row = cur.fetchone()
            return MiningRun.from_db_row(row) if row else None

    def get_children(self, run_id: str) -> list[MiningRun]:
        """获取某次运行的所有子运行（基于 parent_run_id）。"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM mining_log
                WHERE doc_type = 'mining_log'
                  AND metadata->>'parent_run_id' = %(run_id)s
                ORDER BY created_at ASC
            """, {"run_id": run_id})
            return [MiningRun.from_db_row(row) for row in cur.fetchall()]

    def update_status(self, run_id: str, status: RunStatus) -> None:
        """更新运行状态。"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE mining_log
                SET metadata = jsonb_set(metadata, '{status}', %s::jsonb)
                WHERE id = %s
            """, (json.dumps(status.value), run_id))

    def update_eval_results(self, run_id: str, **kwargs: Any) -> None:
        """更新评测结果字段。支持 rankic_mean, rankicir, oos_rankic,
        incremental_ic, incremental_ic_t, max_correlation, composite_score,
        decision, decision_reason, factor_type 等。
        """
        with self.conn.cursor() as cur:
            for key, value in kwargs.items():
                cur.execute("""
                    UPDATE mining_log
                    SET metadata = jsonb_set(metadata, ARRAY[%s]::text[], %s::jsonb)
                    WHERE id = %s
                """, (key, json.dumps(value), run_id))

    def set_decision(self, run_id: str, decision: Decision, reason: str = "") -> None:
        """设置入库决策。"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE mining_log
                SET metadata = jsonb_set(
                    jsonb_set(metadata, '{decision}', %s::jsonb),
                    '{decision_reason}', %s::jsonb
                )
                WHERE id = %s
            """, (json.dumps(decision.value), json.dumps(reason), run_id))

    def list_runs(
        self,
        status: Optional[RunStatus] = None,
        decision: Optional[Decision] = None,
        category: Optional[str] = None,
        direction_tag: Optional[str] = None,
        min_rankic: Optional[float] = None,
        min_composite_score: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MiningRun]:
        """按条件列出运行记录。"""
        conditions = ["doc_type = 'mining_log'"]
        params: dict[str, Any] = {}

        if status:
            conditions.append("metadata->>'status' = %(status)s")
            params["status"] = status.value
        if decision:
            conditions.append("metadata->>'decision' = %(decision)s")
            params["decision"] = decision.value
        if category:
            conditions.append("metadata->>'category' = %(category)s")
            params["category"] = category
        if direction_tag:
            conditions.append("metadata->>'direction_tag' = %(direction_tag)s")
            params["direction_tag"] = direction_tag
        if min_rankic is not None:
            conditions.append("(metadata->>'rankic_mean')::float >= %(min_rankic)s")
            params["min_rankic"] = min_rankic
        if min_composite_score is not None:
            conditions.append("(metadata->>'composite_score')::float >= %(min_composite_score)s")
            params["min_composite_score"] = min_composite_score

        params["limit"] = limit
        params["offset"] = offset

        query = f"""
            SELECT * FROM mining_log
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
        """

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [MiningRun.from_db_row(row) for row in cur.fetchall()]

    def get_accepted_runs(self, limit: int = 100) -> list[MiningRun]:
        """获取已入库的运行记录。"""
        return self.list_runs(decision=Decision.ACCEPTED, limit=limit)

    def get_runs_by_direction(
        self, direction_tag: str, limit: int = 20
    ) -> list[MiningRun]:
        """按方向标签查询运行记录。"""
        return self.list_runs(direction_tag=direction_tag, limit=limit)

    def search_by_content(self, query: str, limit: int = 20) -> list[MiningRun]:
        """全文检索：基于 tsv_content 搜索内容。

        用 OR 语义连接多个词（空格替换为 |），避免 AND 语义过严。
        """
        ts_query = query.strip().replace(" ", "|").replace("，", "|").replace("、", "|")
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM mining_log
                WHERE doc_type = 'mining_log'
                  AND tsv_content @@ to_tsquery('public.jiebacfg', %(ts_query)s)
                ORDER BY ts_rank(tsv_content, to_tsquery('public.jiebacfg', %(ts_query)s)) DESC
                LIMIT %(limit)s
            """, {"ts_query": ts_query, "limit": limit})
            return [MiningRun.from_db_row(row) for row in cur.fetchall()]

    def search_by_tags(self, tags: list[str], limit: int = 20) -> list[MiningRun]:
        """按标签搜索（交集匹配）。"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM mining_log
                WHERE doc_type = 'mining_log'
                  AND tags @> %(tags)s
                ORDER BY created_at DESC
                LIMIT %(limit)s
            """, {"tags": tags, "limit": limit})
            return [MiningRun.from_db_row(row) for row in cur.fetchall()]

    def count_by_direction(self) -> dict[str, dict[str, int]]:
        """统计各方向的尝试次数和成功次数。"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    metadata->>'direction_tag' AS direction,
                    COUNT(*) AS attempts,
                    SUM(CASE WHEN metadata->>'decision' = 'accepted' THEN 1 ELSE 0 END) AS successes
                FROM mining_log
                WHERE doc_type = 'mining_log'
                  AND metadata->>'direction_tag' IS NOT NULL
                  AND metadata->>'direction_tag' != ''
                GROUP BY metadata->>'direction_tag'
                ORDER BY attempts DESC
            """)
            return {
                r["direction"]: {"attempts": r["attempts"], "successes": r["successes"]}
                for r in cur.fetchall()
            }

    def get_max_rankic_in_category(self, category: str) -> Optional[float]:
        """获取某类别下的历史最高 RankIC。"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT MAX((metadata->>'rankic_mean')::float) AS max_rankic
                FROM mining_log
                WHERE doc_type = 'mining_log'
                  AND metadata->>'category' = %(category)s
                  AND metadata->>'rankic_mean' IS NOT NULL
            """, {"category": category})
            row = cur.fetchone()
            return row["max_rankic"] if row and row["max_rankic"] else None

    # ============================================================
    # Experience CRUD
    # ============================================================

    def insert_experience(self, exp: Experience) -> str:
        """插入一条经验记录，返回 experience_id。"""
        if not exp.embedding_str and exp.content and self._embedding_service:
            exp.embedding_str = self._ensure_embedding(exp.content)
        row = exp.to_db_row()
        with self.conn.cursor() as cur:
            fields = list(row.keys())
            values: list[str] = []
            for f in fields:
                if f == "metadata":
                    values.append("%(metadata)s::jsonb")
                elif f == "embedding" and row.get("embedding"):
                    values.append("%(embedding)s::vector")
                else:
                    values.append(f"%({f})s")

            cur.execute(f"""
                INSERT INTO mining_experience ({', '.join(fields)})
                VALUES ({', '.join(values)})
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    tags = EXCLUDED.tags,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    created_at = EXCLUDED.created_at
                RETURNING id
            """, row)
            result = cur.fetchone()
            return result[0] if result else exp.id

    def get_experience(self, experience_id: str) -> Optional[Experience]:
        """按 experience_id 查询单条经验。"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM mining_experience WHERE id = %s AND doc_type = 'mining_experience'",
                (experience_id,),
            )
            row = cur.fetchone()
            return Experience.from_db_row(row) if row else None

    def get_success_experiences(
        self,
        exp_type: Optional[ExperienceType] = None,
        min_quality: float = 0.7,
        limit: int = 50,
    ) -> list[Experience]:
        """获取成功经验（已验证，质量达标）。"""
        conditions = [
            "doc_type = 'mining_experience'",
            "metadata->>'track' = 'success'",
            "(metadata->>'quality_score')::float >= %(min_quality)s",
        ]
        params: dict[str, Any] = {"min_quality": min_quality, "limit": limit}

        if exp_type:
            conditions.append("metadata->>'type' = %(exp_type)s")
            params["exp_type"] = exp_type.value

        query = f"""
            SELECT * FROM mining_experience
            WHERE {' AND '.join(conditions)}
            ORDER BY (metadata->>'quality_score')::float DESC
            LIMIT %(limit)s
        """

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [Experience.from_db_row(row) for row in cur.fetchall()]

    def get_failure_experiences(
        self,
        direction_tag: Optional[str] = None,
        failure_type: Optional[FailureType] = None,
        limit: int = 50,
    ) -> list[Experience]:
        """获取失败轨迹记录。"""
        conditions = [
            "doc_type = 'mining_experience'",
            "metadata->>'track' = 'failure'",
        ]
        params: dict[str, Any] = {"limit": limit}

        if direction_tag:
            conditions.append("metadata->>'direction_tag' = %(direction_tag)s")
            params["direction_tag"] = direction_tag
        if failure_type:
            conditions.append("metadata->>'failure_type' = %(failure_type)s")
            params["failure_type"] = failure_type.value

        query = f"""
            SELECT * FROM mining_experience
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [Experience.from_db_row(row) for row in cur.fetchall()]

    def get_experiences_by_direction(
        self, direction_tag: str, limit: int = 30
    ) -> list[Experience]:
        """按方向标签获取经验（含成功和失败）。"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM mining_experience
                WHERE doc_type = 'mining_experience'
                  AND metadata->>'direction_tag' = %(direction_tag)s
                ORDER BY created_at DESC
                LIMIT %(limit)s
            """, {"direction_tag": direction_tag, "limit": limit})
            return [Experience.from_db_row(row) for row in cur.fetchall()]

    def increment_usage(self, experience_id: str) -> None:
        """增加经验使用次数，更新 last_used_at。"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE mining_experience
                SET metadata = jsonb_set(
                    jsonb_set(metadata, '{usage_count}',
                        to_jsonb(COALESCE((metadata->>'usage_count')::int, 0) + 1)),
                    '{last_used_at}', to_jsonb(%(now)s::text)
                )
                WHERE id = %(id)s
            """, {"id": experience_id, "now": datetime.now().isoformat()})

    def deprecate_experience(self, experience_id: str, deprecated_by: str) -> None:
        """标记经验为已废弃。"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE mining_experience
                SET metadata = jsonb_set(
                    jsonb_set(metadata, '{verification_status}', '"deprecated"'::jsonb),
                    '{deprecated_by}', %(deprecated_by)s::jsonb
                )
                WHERE id = %(id)s
            """, {"id": experience_id, "deprecated_by": json.dumps(deprecated_by)})

    def search_experiences_by_content(
        self, query: str, track: Optional[ExperienceTrack] = None, limit: int = 20
    ) -> list[Experience]:
        """全文检索经验库。

        用 OR 语义连接多个词（空格替换为 |），避免 AND 语义过严。
        """
        ts_query = query.strip().replace(" ", "|").replace("，", "|").replace("、", "|")
        conditions = [
            "doc_type = 'mining_experience'",
            "tsv_content @@ to_tsquery('public.jiebacfg', %(ts_query)s)",
        ]
        if track:
            conditions.append("metadata->>'track' = %(track)s")
            params = {"ts_query": ts_query, "limit": limit, "track": track.value}
        else:
            params = {"ts_query": ts_query, "limit": limit}

        query_sql = f"""
            SELECT * FROM mining_experience
            WHERE {' AND '.join(conditions)}
            ORDER BY ts_rank(tsv_content, to_tsquery('public.jiebacfg', %(ts_query)s)) DESC
            LIMIT %(limit)s
        """

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query_sql, params)
            return [Experience.from_db_row(row) for row in cur.fetchall()]

    # ============================================================
    # 向量语义检索
    # ============================================================

    def backfill_embeddings(self, table: str = "mining_log", batch_size: int = 100) -> int:
        """为缺少 embedding 的记录补写向量。

        Args:
            table: "mining_log" 或 "mining_experience"
            batch_size: 每批处理数量

        Returns:
            已补写数量
        """
        if self._embedding_service is None:
            logger.warning("EmbeddingService 未配置，无法执行 backfill")
            return 0

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"""
                SELECT id, content FROM {table}
                WHERE embedding IS NULL AND content IS NOT NULL AND content != ''
                LIMIT %(limit)s
            """, {"limit": batch_size})
            rows = cur.fetchall()

        count = 0
        for row in rows:
            vec = self._embedding_service.encode(row["content"])
            vec_str = self._embedding_service.to_db_format(vec)
            with self.conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {table} SET embedding = %s::vector WHERE id = %s",
                    (vec_str, row["id"]),
                )
            count += 1

        logger.info("backfill %s: %d 条记录写入 embedding", table, count)
        return count

    def search_mining_log_by_embedding(
        self,
        embedding_str: str,
        top_k: int = 10,
        score_threshold: float = 0.3,
    ) -> list[tuple[MiningRun, float]]:
        """在 mining_log 表中按向量余弦相似度检索。

        Returns:
            list of (MiningRun, score) 元组，按相似度降序。
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT *, 1 - (embedding <=> %(vec)s::vector) AS score
                FROM mining_log
                WHERE doc_type = 'mining_log'
                  AND embedding IS NOT NULL
                  AND 1 - (embedding <=> %(vec)s::vector) >= %(threshold)s
                ORDER BY embedding <=> %(vec)s::vector
                LIMIT %(limit)s
            """, {"vec": embedding_str, "threshold": score_threshold, "limit": top_k})
            results = []
            for row in cur.fetchall():
                score = row.pop("score", 0.0)
                run = MiningRun.from_db_row(row)
                results.append((run, score))
            return results

    def search_experience_by_embedding(
        self,
        embedding_str: str,
        top_k: int = 10,
        score_threshold: float = 0.3,
        track: Optional[str] = None,
    ) -> list[tuple[Experience, float]]:
        """在 mining_experience 表中按向量余弦相似度检索。

        Args:
            embedding_str: pgvector 格式的查询向量
            top_k: 返回数量上限
            score_threshold: 余弦相似度阈值
            track: 可选过滤，"success" 或 "failure"

        Returns:
            list of (Experience, score) 元组，按相似度降序。
        """
        conditions = [
            "doc_type = 'mining_experience'",
            "embedding IS NOT NULL",
            "1 - (embedding <=> %(vec)s::vector) >= %(threshold)s",
        ]
        params: dict[str, Any] = {
            "vec": embedding_str,
            "threshold": score_threshold,
            "limit": top_k,
        }
        if track:
            conditions.append("metadata->>'track' = %(track)s")
            params["track"] = track

        query = f"""
            SELECT *, 1 - (embedding <=> %(vec)s::vector) AS score
            FROM mining_experience
            WHERE {' AND '.join(conditions)}
            ORDER BY embedding <=> %(vec)s::vector
            LIMIT %(limit)s
        """

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            results = []
            for row in cur.fetchall():
                score = row.pop("score", 0.0)
                exp = Experience.from_db_row(row)
                results.append((exp, score))
            return results

    # ============================================================
    # 关联查询
    # ============================================================

    def get_run_with_experiences(self, run_id: str) -> dict[str, Any]:
        """获取一次运行记录及其关联的经验。"""
        run = self.get_run(run_id)
        if run is None:
            return {}

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM mining_experience
                WHERE metadata->'source_mining_ids' ? %(run_id)s
            """, {"run_id": run_id})
            experiences = [Experience.from_db_row(row) for row in cur.fetchall()]

        return {"run": run, "experiences": experiences}
