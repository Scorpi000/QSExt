# -*- coding: utf-8 -*-
"""假设生成模块数据模型定义。

定义假设生成流程中的核心数据结构：
  - DirectionCandidate: Step 1 产出的候选研究方向
  - ResearchContext: Steps 1-2 累积的调研上下文
  - HypothesisDoc: 假设生成阶段最终输出的结构化假设文档
  - 以及各类辅助数据类

Schema 严格对齐方案文档 3.5 节和数据契约 7.1 节。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import yaml


# ============================================================
# 辅助数据类
# ============================================================

@dataclass
class DirectionStats:
    """方向覆盖率统计。"""
    direction_tag: str
    attempts: int = 0
    successes: int = 0
    success_rate: float = 0.0

    def __post_init__(self):
        if self.attempts > 0:
            self.success_rate = self.successes / self.attempts


@dataclass
class WikiResearchResult:
    """Wiki 页面深度阅读结果。"""
    page_name: str
    page_type: str                              # concept / entity / comparison
    tldr: str
    key_insights: str
    related_pages: list[str] = field(default_factory=list)


@dataclass
class FactorCodeSnippet:
    """已有因子代码摘录。"""
    qsid: str
    name: str
    code: str
    description: str


@dataclass
class DataFieldSpec:
    """数据字段需求。"""
    name: str
    dtype: str
    frequency: str
    description: str
    table_source: Optional[str] = None
    available: Optional[bool] = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "name": self.name,
            "dtype": self.dtype,
            "frequency": self.frequency,
            "description": self.description,
        }
        if self.table_source:
            d["table_source"] = self.table_source
        if self.available is not None:
            d["available"] = self.available
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DataFieldSpec":
        return cls(
            name=d.get("name", ""),
            dtype=d.get("dtype", ""),
            frequency=d.get("frequency", ""),
            description=d.get("description", ""),
            table_source=d.get("table_source"),
            available=d.get("available"),
        )


@dataclass
class ReflectionRecord:
    """反思记录。"""
    critique_notes: str
    revisions_from_draft: list[str] = field(default_factory=list)


@dataclass
class InspiredBy:
    """假设灵感来源。"""
    wiki_pages: list[dict] = field(default_factory=list)        # [{page, relevance}]
    existing_factors: list[dict] = field(default_factory=list)  # [{qsid, name, relevance}]
    prior_attempts: list[dict] = field(default_factory=list)    # [{run_id, outcome, reason, lesson_applied}]


@dataclass
class ExpectedCharacteristics:
    """预期因子特征。"""
    ic_sign: str                            # positive / negative
    ic_magnitude: str                       # 如 "0.03-0.06"
    icir: str                               # 如 "> 0.5"
    turnover: str
    market_cap_bias: str
    expected_incremental_ic: str
    susceptible_to: str


@dataclass
class NoveltyCheckResult:
    """新颖性校验结果。"""
    passed: bool
    warnings: list[str] = field(default_factory=list)
    block_reason: Optional[str] = None
    similarity_scores: dict[str, float] = field(default_factory=dict)
    direction_overlap: list[str] = field(default_factory=list)


# ============================================================
# 核心数据模型
# ============================================================

@dataclass
class DirectionCandidate:
    """Step 1 产出：一个候选研究方向。"""
    direction_tag: str                          # "动量/日内方向预测"
    category: str                               # "动量"
    description: str                            # 方向摘要
    rationale: str                              # 为什么有潜力
    wiki_pages: list[str] = field(default_factory=list)
    existing_factor_qsids: list[str] = field(default_factory=list)
    prior_attempt_run_ids: list[str] = field(default_factory=list)
    coverage: Optional[DirectionStats] = None
    budget_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = {
            "direction_tag": self.direction_tag,
            "category": self.category,
            "description": self.description,
            "rationale": self.rationale,
            "wiki_pages": self.wiki_pages,
            "existing_factor_qsids": self.existing_factor_qsids,
            "prior_attempt_run_ids": self.prior_attempt_run_ids,
            "budget_score": self.budget_score,
        }
        if self.coverage:
            d["coverage"] = {
                "direction_tag": self.coverage.direction_tag,
                "attempts": self.coverage.attempts,
                "successes": self.coverage.successes,
                "success_rate": self.coverage.success_rate,
            }
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DirectionCandidate":
        coverage = None
        if "coverage" in d and d["coverage"]:
            c = d["coverage"]
            coverage = DirectionStats(
                direction_tag=c.get("direction_tag", ""),
                attempts=c.get("attempts", 0),
                successes=c.get("successes", 0),
            )
        return cls(
            direction_tag=d.get("direction_tag", ""),
            category=d.get("category", ""),
            description=d.get("description", ""),
            rationale=d.get("rationale", ""),
            wiki_pages=d.get("wiki_pages", []),
            existing_factor_qsids=d.get("existing_factor_qsids", []),
            prior_attempt_run_ids=d.get("prior_attempt_run_ids", []),
            coverage=coverage,
            budget_score=d.get("budget_score", 0.0),
        )


@dataclass
class ResearchContext:
    """Steps 1-2 累积的全部调研结果，作为 Step 3 的输入上下文。"""
    direction: DirectionCandidate
    wiki_results: list[WikiResearchResult] = field(default_factory=list)
    factor_code_snippets: list[FactorCodeSnippet] = field(default_factory=list)
    data_field_availability: list[DataFieldSpec] = field(default_factory=list)
    successful_patterns: list[dict] = field(default_factory=list)
    failure_lessons: list[dict] = field(default_factory=list)
    frequent_patterns: list[dict] = field(default_factory=list)
    direction_coverage: dict[str, DirectionStats] = field(default_factory=dict)
    exploration_trail: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction.to_dict(),
            "wiki_results": [
                {
                    "page_name": r.page_name,
                    "page_type": r.page_type,
                    "tldr": r.tldr,
                    "key_insights": r.key_insights,
                    "related_pages": r.related_pages,
                }
                for r in self.wiki_results
            ],
            "factor_code_snippets": [
                {
                    "qsid": s.qsid,
                    "name": s.name,
                    "code": s.code,
                    "description": s.description,
                }
                for s in self.factor_code_snippets
            ],
            "data_field_availability": [f.to_dict() for f in self.data_field_availability],
            "successful_patterns": self.successful_patterns,
            "failure_lessons": self.failure_lessons,
            "frequent_patterns": self.frequent_patterns,
            "direction_coverage": {
                k: {
                    "direction_tag": v.direction_tag,
                    "attempts": v.attempts,
                    "successes": v.successes,
                    "success_rate": v.success_rate,
                }
                for k, v in self.direction_coverage.items()
            },
            "exploration_trail": self.exploration_trail,
        }


@dataclass
class HypothesisDoc:
    """假设生成阶段最终输出：结构化假设文档。

    Schema 严格对齐方案文档 3.5 节和数据契约 7.1 节。
    """
    hypothesis_id: str
    created: str
    status: str                                 # "pending"
    inspired_by: InspiredBy
    exploration_trail: list[dict]
    reflection: ReflectionRecord
    factor_name: str
    category: str
    market: str
    frequency: str
    economic_rationale: str
    calculation_pseudo: str
    data_requirements_fields: list[DataFieldSpec]
    data_requirements_universe: str
    data_requirements_lookback: list[int]
    operator_suggestions: list[str]
    expected_characteristics: ExpectedCharacteristics
    novelty_rationale: str
    references: list[str]
    forbidden_patterns: list[str]

    def to_yaml(self) -> str:
        """序列化为 YAML 字符串。"""
        data = {
            "hypothesis_id": self.hypothesis_id,
            "created": self.created,
            "status": self.status,
            "inspired_by": {
                "wiki_pages": self.inspired_by.wiki_pages,
                "existing_factors": self.inspired_by.existing_factors,
                "prior_attempts": self.inspired_by.prior_attempts,
            },
            "exploration_trail": self.exploration_trail,
            "reflection": {
                "critique_notes": self.reflection.critique_notes,
                "revisions_from_draft": self.reflection.revisions_from_draft,
            },
            "factor_name": self.factor_name,
            "category": self.category,
            "market": self.market,
            "frequency": self.frequency,
            "economic_rationale": self.economic_rationale,
            "calculation_pseudo": self.calculation_pseudo,
            "data_requirements": {
                "fields": [f.to_dict() for f in self.data_requirements_fields],
                "universe": self.data_requirements_universe,
                "lookback_range": self.data_requirements_lookback,
            },
            "operator_suggestions": self.operator_suggestions,
            "expected_characteristics": {
                "ic_sign": self.expected_characteristics.ic_sign,
                "ic_magnitude": self.expected_characteristics.ic_magnitude,
                "icir": self.expected_characteristics.icir,
                "turnover": self.expected_characteristics.turnover,
                "market_cap_bias": self.expected_characteristics.market_cap_bias,
                "expected_incremental_ic": self.expected_characteristics.expected_incremental_ic,
                "susceptible_to": self.expected_characteristics.susceptible_to,
            },
            "novelty_rationale": self.novelty_rationale,
            "references": self.references,
            "forbidden_patterns": self.forbidden_patterns,
        }
        return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def to_development_input(self) -> dict[str, Any]:
        """转为因子开发阶段输入格式，严格对齐方案 7.1 节数据契约。"""
        return {
            "factor_name": self.factor_name,
            "factor_description": self.economic_rationale,
            "formula": self.calculation_pseudo,
            "market": self.market,
            "frequency": self.frequency,
            "forbidden_patterns": self.forbidden_patterns,
            "expected_characteristics": {
                "ic_sign": self.expected_characteristics.ic_sign,
                "ic_magnitude": self.expected_characteristics.ic_magnitude,
                "icir": self.expected_characteristics.icir,
                "turnover": self.expected_characteristics.turnover,
                "market_cap_bias": self.expected_characteristics.market_cap_bias,
                "expected_incremental_ic": self.expected_characteristics.expected_incremental_ic,
                "susceptible_to": self.expected_characteristics.susceptible_to,
            },
            "data_requirements": {
                "fields": [f.to_dict() for f in self.data_requirements_fields],
                "universe": self.data_requirements_universe,
                "lookback_range": self.data_requirements_lookback,
            },
            "operator_suggestions": self.operator_suggestions,
            "references": self.references,
            "hypothesis_id": self.hypothesis_id,
            "inspired_by": {
                "wiki_pages": self.inspired_by.wiki_pages,
                "existing_factors": self.inspired_by.existing_factors,
                "prior_attempts": self.inspired_by.prior_attempts,
            },
        }

    @classmethod
    def from_llm_yaml(cls, raw_yaml: str, context: ResearchContext) -> "HypothesisDoc":
        """从 LLM 输出的 YAML 解析为 HypothesisDoc。

        Args:
            raw_yaml: LLM 输出的原始 YAML 字符串
            context: 调研上下文（用于填充 inspired_by 等字段）

        Returns:
            解析后的 HypothesisDoc 实例
        """
        # 清理可能的 markdown 代码块标记
        cleaned = raw_yaml.strip()
        if cleaned.startswith("```yaml"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        data = yaml.safe_load(cleaned)

        # 解析 data_requirements
        dr = data.get("data_requirements", {})
        fields = [DataFieldSpec.from_dict(f) for f in dr.get("fields", [])]

        # 解析 expected_characteristics
        ec = data.get("expected_characteristics", {})
        expected = ExpectedCharacteristics(
            ic_sign=ec.get("ic_sign", ""),
            ic_magnitude=ec.get("ic_magnitude", ""),
            icir=ec.get("icir", ""),
            turnover=ec.get("turnover", ""),
            market_cap_bias=ec.get("market_cap_bias", ""),
            expected_incremental_ic=ec.get("expected_incremental_ic", ""),
            susceptible_to=ec.get("susceptible_to", ""),
        )

        # 构建 inspired_by（从 context 推导）
        inspired = InspiredBy(
            wiki_pages=[
                {"page": r.page_name, "relevance": "direct"}
                for r in context.wiki_results
            ],
            existing_factors=[
                {"qsid": s.qsid, "name": s.name, "relevance": "reference"}
                for s in context.factor_code_snippets
            ],
            prior_attempts=[
                {
                    "run_id": fp.get("run_id", ""),
                    "outcome": fp.get("outcome", ""),
                    "reason": fp.get("reason", ""),
                    "lesson_applied": fp.get("lesson_learned", ""),
                }
                for fp in context.failure_lessons
            ],
        )

        # 解析 reflection
        ref_data = data.get("reflection", {})
        reflection = ReflectionRecord(
            critique_notes=ref_data.get("critique_notes", ""),
            revisions_from_draft=ref_data.get("revisions_from_draft", []),
        )

        return cls(
            hypothesis_id=data.get("hypothesis_id", f"hyp_{datetime.now().strftime('%Y%m%d')}_{datetime.now().strftime('%H%M%S')}"),
            created=data.get("created", datetime.now().isoformat()),
            status=data.get("status", "pending"),
            inspired_by=inspired,
            exploration_trail=context.exploration_trail,
            reflection=reflection,
            factor_name=data.get("factor_name", ""),
            category=data.get("category", ""),
            market=data.get("market", "A股"),
            frequency=data.get("frequency", "日频"),
            economic_rationale=data.get("economic_rationale", ""),
            calculation_pseudo=data.get("calculation_pseudo", ""),
            data_requirements_fields=fields,
            data_requirements_universe=dr.get("universe", ""),
            data_requirements_lookback=dr.get("lookback_range", []),
            operator_suggestions=data.get("operator_suggestions", []),
            expected_characteristics=expected,
            novelty_rationale=data.get("novelty_rationale", ""),
            references=data.get("references", []),
            forbidden_patterns=data.get("forbidden_patterns", []),
        )
