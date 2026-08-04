# -*- coding: utf-8 -*-
"""数据库连接管理与表创建 (DDL)。

连接到 KDB PostgreSQL 数据库，管理 mining_runs 和 experiences 两张核心表。
表结构复用 KDB 文档数据库的统一字段结构。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor, Json
from dotenv import load_dotenv

from QSExt import __QS_MainPath__

logger = logging.getLogger(__name__)

# 加载时读取环境变量，确保 KDB DSN 可用
_ENV_FILE = os.path.join(__QS_MainPath__, "config", ".env")
if os.path.isfile(_ENV_FILE):
    load_dotenv(_ENV_FILE)

DEFAULT_KDB_DSN = os.getenv("POSTGRESQL_KDB_DSN_DEV", "")

# ============================================================
# DDL — 复用 KDB 文档数据库统一字段结构
# ============================================================

DDL_CREATE_TABLES = """
-- 挖掘运行记录表 (doc_type = 'mining_log')
-- 每条记录对应一次完整的 hypothesis → development → evaluation 闭环

CREATE TABLE IF NOT EXISTS mining_log (
    id              TEXT PRIMARY KEY,               -- run_id，如 "FM_20260701_143052"
    source          TEXT NOT NULL DEFAULT 'factor_mining_system',
    source_path     TEXT NOT NULL DEFAULT '',
    doc_type        VARCHAR(200) NOT NULL DEFAULT 'mining_log',
    content         TEXT NOT NULL DEFAULT '',       -- 摘要文本（全文检索 + embedding）
    tags            TEXT[] DEFAULT '{}',
    tsv_content     TSVECTOR,                       -- 全文检索索引字段
    embedding       VECTOR(1024),                   -- bge-m3 embedding 向量
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 经验库记录 (doc_type = 'mining_experience')
-- track 区分 success / failure
-- type 区分 成功: logic_component/tool_function/formula_pattern
--                失败: dead_end/similar_candidate/recovery_pattern

CREATE TABLE IF NOT EXISTS mining_experience (
    id              TEXT PRIMARY KEY,               -- experience_id，如 "EXP_20260701_001"
    source          TEXT NOT NULL DEFAULT 'factor_mining_system',
    source_path     TEXT NOT NULL DEFAULT '',
    doc_type        VARCHAR(200) NOT NULL DEFAULT 'mining_experience',
    content         TEXT NOT NULL DEFAULT '',       -- 经验描述文本（全文检索）
    tags            TEXT[] DEFAULT '{}',
    tsv_content     TSVECTOR,
    embedding       VECTOR(1024),
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 索引
-- ============================================================

-- mining_log 索引
CREATE INDEX IF NOT EXISTS idx_mining_log_doc_type ON mining_log(doc_type);
CREATE INDEX IF NOT EXISTS idx_mining_log_tags ON mining_log USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_mining_log_created ON mining_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mining_log_metadata_status
    ON mining_log ((metadata->>'status'));
CREATE INDEX IF NOT EXISTS idx_mining_log_metadata_decision
    ON mining_log ((metadata->>'decision'));
CREATE INDEX IF NOT EXISTS idx_mining_log_metadata_category
    ON mining_log ((metadata->>'category'));
CREATE INDEX IF NOT EXISTS idx_mining_log_metadata_direction
    ON mining_log ((metadata->>'direction_tag'));
CREATE INDEX IF NOT EXISTS idx_mining_log_metadata_rankic
    ON mining_log (((metadata->>'rankic_mean')::float));
CREATE INDEX IF NOT EXISTS idx_mining_log_metadata_inc_ic
    ON mining_log (((metadata->>'incremental_ic_t')::float));
CREATE INDEX IF NOT EXISTS idx_mining_log_metadata_composite
    ON mining_log (((metadata->>'composite_score')::float));
CREATE INDEX IF NOT EXISTS idx_mining_log_metadata_parent
    ON mining_log ((metadata->>'parent_run_id'));
CREATE INDEX IF NOT EXISTS idx_mining_log_tsv
    ON mining_log USING GIN(tsv_content);

-- mining_experience 索引
CREATE INDEX IF NOT EXISTS idx_mining_experience_doc_type ON mining_experience(doc_type);
CREATE INDEX IF NOT EXISTS idx_mining_experience_tags ON mining_experience USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_mining_experience_created ON mining_experience(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mining_experience_metadata_track
    ON mining_experience ((metadata->>'track'));
CREATE INDEX IF NOT EXISTS idx_mining_experience_metadata_type
    ON mining_experience ((metadata->>'type'));
CREATE INDEX IF NOT EXISTS idx_mining_experience_metadata_quality
    ON mining_experience (((metadata->>'quality_score')::float));
CREATE INDEX IF NOT EXISTS idx_mining_experience_metadata_direction
    ON mining_experience ((metadata->>'direction_tag'));
CREATE INDEX IF NOT EXISTS idx_mining_experience_tsv
    ON mining_experience USING GIN(tsv_content);

-- 向量检索索引（pgvector HNSW，余弦距离）
CREATE INDEX IF NOT EXISTS idx_mining_log_embedding
    ON mining_log USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_mining_experience_embedding
    ON mining_experience USING hnsw (embedding vector_cosine_ops);

-- 全文检索触发器：自动更新 tsv_content
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_mining_log_tsv'
    ) THEN
        CREATE TRIGGER trg_mining_log_tsv
            BEFORE INSERT OR UPDATE ON mining_log
            FOR EACH ROW EXECUTE FUNCTION
                tsvector_update_trigger(tsv_content, 'public.jiebacfg', content);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_mining_experience_tsv'
    ) THEN
        CREATE TRIGGER trg_mining_experience_tsv
            BEFORE INSERT OR UPDATE ON mining_experience
            FOR EACH ROW EXECUTE FUNCTION
                tsvector_update_trigger(tsv_content, 'public.jiebacfg', content);
    END IF;
END $$;
"""


# ============================================================
# 连接管理
# ============================================================

class MiningLogDB:
    """挖掘日志数据库连接管理器。"""

    def __init__(self, dsn: Optional[str] = None):
        self._dsn = dsn or DEFAULT_KDB_DSN
        self._conn: Optional[psycopg2.extensions.connection] = None

    @property
    def dsn(self) -> str:
        return self._dsn

    def connect(self) -> psycopg2.extensions.connection:
        """获取数据库连接，惰性创建。"""
        if self._conn is None or self._conn.closed:
            logger.info("连接 KDB 数据库: %s", self._dsn.split("@")[-1] if "@" in self._dsn else "***")
            self._conn = psycopg2.connect(self._dsn)
            self._conn.autocommit = True
        return self._conn

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("已断开 KDB 数据库连接")

    def init_tables(self) -> None:
        """创建 mining_log 和 mining_experience 表及索引（幂等）。"""
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(DDL_CREATE_TABLES)
        conn.commit()
        logger.info("mining_log / mining_experience 表初始化完成")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit() if self._conn else None
        self.close()
        return False
