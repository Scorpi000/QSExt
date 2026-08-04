# -*- coding: utf-8 -*-
"""挖掘日志库数据模型定义。

复用 KDB 文档数据库统一字段结构：
  id: TEXT PRIMARY KEY
  source: TEXT
  source_path: TEXT
  doc_type: VARCHAR(200)
  content: TEXT
  tags: TEXT[]
  tsv_content: TSVECTOR
  embedding: VECTOR / BIT(64)
  metadata: JSONB
  created_at: TIMESTAMP

业务字段全部存放在 metadata JSONB 中，直接通过 dict 访问。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================
# 枚举类型
# ============================================================

class RunStatus(str, Enum):
    PENDING = "pending"
    IN_DEVELOPMENT = "in_development"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class Decision(str, Enum):
    ACCEPTED = "accepted"
    REFINING = "refining"
    REJECTED = "rejected"


class FactorType(str, Enum):
    STANDARD = "standard"
    SYNERGISTIC = "synergistic"


class ExperienceTrack(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class ExperienceType(str, Enum):
    # 成功经验
    LOGIC_COMPONENT = "logic_component"
    TOOL_FUNCTION = "tool_function"
    FORMULA_PATTERN = "formula_pattern"
    # 失败轨迹
    DEAD_END = "dead_end"
    SIMILAR_CANDIDATE = "similar_candidate"
    RECOVERY_PATTERN = "recovery_pattern"


class FailureType(str, Enum):
    LOW_IC = "low_ic"
    NO_INCREMENTAL_IC = "no_incremental_ic"
    OVERFITTING = "overfitting"
    DATA_LEAKAGE = "data_leakage"
    LOGIC_FLAW = "logic_flaw"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    DEPRECATED = "deprecated"


# ============================================================
# 核心数据模型
# ============================================================

class MiningRun(BaseModel):
    """一次完整的因子挖掘运行记录。

    doc_type = 'mining_log'。
    metadata 中常用的业务字段（均为可选，按需写入）：
      hypothesis_id: str       关联假设文档 ID
      parent_run_id: str       父运行 ID，null 表示全新方向探索
      status: str              pending / in_development / evaluating / completed / failed
      decision: str            accepted / refining / rejected
      decision_reason: str
      factor_name: str
      category: str
      direction_tag: str
      factor_type: str         standard / synergistic
      rankic_mean: float
      rankicir: float
      oos_rankic: float
      incremental_ic: float    组合增量 IC（多样性主判据）
      incremental_ic_t: float  增量 IC 的 t 统计量
      max_correlation: float   与已有因子最大相关性（仅参考）
      composite_score: float   五维综合评分
      hypothesis: dict         完整假设文档
      development: dict        开发阶段产物
      evaluation: dict         评测阶段完整数据
      exploration_trail: list  检索溯源记录
      code_versions: list      代码版本链
      timing: dict             各阶段耗时
      llm_usage: dict          LLM 使用统计
    """

    # ---- 表级统一字段 ----
    id: str = ""  # run_id, 如 "FM_20260701_143052"
    source: str = "factor_mining_system"
    source_path: str = ""
    doc_type: str = "mining_log"
    content: str = ""  # 摘要文本（供全文检索和 embedding）
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    embedding_str: str = ""  # pgvector 格式的向量字符串，由 EmbeddingService.to_db_format() 生成

    @property
    def meta(self) -> dict[str, Any]:
        return self.metadata

    def to_db_row(self) -> dict[str, Any]:
        """转为数据库插入行，metadata 字段序列化为 JSON 兼容对象。"""
        import json

        row = {
            "id": self.id,
            "source": self.source,
            "source_path": self.source_path,
            "doc_type": self.doc_type,
            "content": self.content,
            "tags": self.tags,
            "metadata": json.dumps(self.metadata, ensure_ascii=False, default=str),
            "created_at": self.created_at or datetime.now(),
        }
        if self.embedding_str:
            row["embedding"] = self.embedding_str
        return row

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "MiningRun":
        """从数据库查询结果行构造 MiningRun。"""
        import json

        metadata = row.get("metadata", {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return cls(
            id=row.get("id", ""),
            source=row.get("source", "factor_mining_system"),
            source_path=row.get("source_path", ""),
            doc_type=row.get("doc_type", "mining_log"),
            content=row.get("content", ""),
            tags=row.get("tags", []),
            metadata=metadata,
            created_at=row.get("created_at"),
        )


class Experience(BaseModel):
    """经验库记录（成功经验或失败轨迹）。

    doc_type = 'mining_experience'。
    metadata 中常用的业务字段（均为可选，按需写入）：
      track: str                 success / failure
      type: str                  成功: logic_component/tool_function/formula_pattern
                                 失败: dead_end/similar_candidate/recovery_pattern
      name: str
      description: str
      direction_tag: str
      quality_score: float
      usage_count: int
      last_used_at: str
      verification_status: str  pending / verified / deprecated
      source_mining_ids: list   来源运行 ID 列表
      deprecated_by: str
      code_snippet: str         成功经验：可复用代码
      financial_rationale: str  成功经验：金融逻辑
      failure_type: str         失败经验：low_ic / no_incremental_ic / ...
      lesson_learned: str       失败经验：教训
      recovery_strategy: str    失败经验：恢复策略
    """

    # ---- 表级统一字段 ----
    id: str = ""  # experience_id, 如 "EXP_20260701_001"
    source: str = "factor_mining_system"
    source_path: str = ""
    doc_type: str = "mining_experience"
    content: str = ""  # 经验描述文本（供全文检索）
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    embedding_str: str = ""  # pgvector 格式的向量字符串

    @property
    def meta(self) -> dict[str, Any]:
        return self.metadata

    def to_db_row(self) -> dict[str, Any]:
        """转为数据库插入行。"""
        import json

        row = {
            "id": self.id,
            "source": self.source,
            "source_path": self.source_path,
            "doc_type": self.doc_type,
            "content": self.content,
            "tags": self.tags,
            "metadata": json.dumps(self.metadata, ensure_ascii=False, default=str),
            "created_at": self.created_at or datetime.now(),
        }
        if self.embedding_str:
            row["embedding"] = self.embedding_str
        return row

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "Experience":
        """从数据库查询结果行构造 Experience。"""
        import json

        metadata = row.get("metadata", {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return cls(
            id=row.get("id", ""),
            source=row.get("source", "factor_mining_system"),
            source_path=row.get("source_path", ""),
            doc_type=row.get("doc_type", "mining_experience"),
            content=row.get("content", ""),
            tags=row.get("tags", []),
            metadata=metadata,
            created_at=row.get("created_at"),
        )
