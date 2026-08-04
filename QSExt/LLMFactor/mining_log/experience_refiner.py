# -*- coding: utf-8 -*-
"""经验提炼 — 评测完成后从因子代码中拆解可复用经验。

遵循设计文档 6.5 节的三层过滤流程：
  Step 1: 解析 (Parse) — 从因子代码中识别可独立存在的逻辑组件
  Step 2: 审查 (Review) — LLM 审查组件的金融逻辑和代码正确性
  Step 3: 复评 (Re-evaluate) — 独立评测组件的有效性
  Step 4: 更新 — 写入经验库 + 更新方向索引

当前版本提供框架和确定性逻辑；LLM 审查部分（Step 2）通过回调注入，
以便后续集成不同 LLM 后端。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional, Protocol

from QSExt.LLMFactor.mining_log.models import (
    MiningRun,
    Experience,
    Decision,
    ExperienceTrack,
    ExperienceType,
    FailureType,
    VerificationStatus,
)
from QSExt.LLMFactor.mining_log.repository import MiningLogRepository

logger = logging.getLogger(__name__)

# ============================================================
# LLM 审查回调协议
# ============================================================


class ComponentReviewer(Protocol):
    """LLM 组件审查接口。

    实现此协议以接入具体的 LLM 后端进行代码审查。
    """

    def review_component(
        self, code_snippet: str, name: str, description: str
    ) -> dict[str, Any]:
        """审查单个逻辑组件。

        Returns:
            {
                "approved": bool,
                "financial_rationale": str,
                "issues": list[str],
                "suggestions": str,
                "quality_score": float,
            }
        """
        ...

    def classify_failure(self, run: MiningRun) -> dict[str, Any]:
        """分析失败原因，生成教训和恢复策略。

        Returns:
            {
                "failure_type": str,
                "lesson_learned": str,
                "recovery_strategy": str,
            }
        """
        ...


class NoOpReviewer:
    """空操作审查器，用于尚未接入 LLM 的阶段。"""

    def review_component(
        self, code_snippet: str, name: str, description: str
    ) -> dict[str, Any]:
        return {
            "approved": True,
            "financial_rationale": f"组件 {name} 的金融逻辑待 LLM 审查确认",
            "issues": [],
            "suggestions": "",
            "quality_score": 0.5,
        }

    def classify_failure(self, run: MiningRun) -> dict[str, Any]:
        rankic = run.metadata.get("rankic_mean") or 0
        inc_ic_t = run.metadata.get("incremental_ic_t") or 0

        if abs(rankic) < 0.01:
            failure_type = "low_ic"
        elif inc_ic_t < 1.0:
            failure_type = "no_incremental_ic"
        else:
            failure_type = "logic_flaw"

        return {
            "failure_type": failure_type,
            "lesson_learned": f"RankIC={rankic:.4f}, 增量IC_t={inc_ic_t:.2f}",
            "recovery_strategy": "",
        }


# ============================================================
# 代码解析工具
# ============================================================

def extract_code_components(code: str) -> list[dict[str, str]]:
    """从因子代码中识别可独立存在的逻辑组件。

    当前使用启发式规则：按注释分隔和连续操作块拆分。
    后续可接入 AST 解析做更精准的拆分。
    """
    components: list[dict[str, str]] = []
    if not code:
        return components

    lines = code.split("\n")

    current_block: list[str] = []
    current_label = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ----") or stripped.startswith("# ===="):
            if current_block and current_label:
                components.append({
                    "name": _derive_component_name(current_label),
                    "description": current_label,
                    "code": "\n".join(current_block),
                })
            current_label = stripped.lstrip("# -=").strip()
            current_block = []
        elif current_label:
            current_block.append(line)

    if current_block and current_label:
        components.append({
            "name": _derive_component_name(current_label),
            "description": current_label,
            "code": "\n".join(current_block),
        })

    return components


def _derive_component_name(description: str) -> str:
    """从中文描述推导英文组件名。"""
    mapping = {
        "归母净利润": "net_profit_ttm",
        "净利润": "net_profit_ttm",
        "总市值": "total_market_value",
        "市值": "market_value",
        "成交": "volume",
        "行情": "price_data",
        "财务": "financial_data",
        "PE": "pe_calculation", "PB": "pb_calculation", "ROE": "roe_calculation",
        "收益": "return_calculation",
        "波动": "volatility",
        "动量": "momentum", "反转": "reversal",
        "估值": "valuation", "成长": "growth", "质量": "quality",
        "杠杆": "leverage", "流动性": "liquidity", "换手": "turnover",
        "行业": "industry",
    }
    for cn_key, en_name in mapping.items():
        if cn_key in description:
            return en_name
    return "component_" + description[:20].replace(" ", "_")


# ============================================================
# 经验提炼器
# ============================================================


class ExperienceRefiner:
    """经验提炼器 — 评测完成后执行三层过滤，更新经验库。"""

    def __init__(
        self,
        repo: MiningLogRepository,
        reviewer: Optional[ComponentReviewer] = None,
    ):
        self._repo = repo
        self._reviewer = reviewer or NoOpReviewer()
        self._experience_counter = 0

    def _next_experience_id(self) -> str:
        self._experience_counter += 1
        date_str = datetime.now().strftime("%Y%m%d")
        return f"EXP_{date_str}_{self._experience_counter:03d}"

    def refine(self, run: MiningRun) -> list[Experience]:
        """对一次挖掘运行执行经验提炼。

        - accepted → 成功经验提炼 (三层过滤)
        - rejected → 失败轨迹记录
        - refining → 恢复模式记录
        """
        decision = run.metadata.get("decision")
        if decision == Decision.ACCEPTED.value:
            return self._refine_success(run)
        elif decision == Decision.REJECTED.value:
            return self._refine_failure(run)
        elif decision == Decision.REFINING.value:
            return self._refine_recovery(run)
        return []

    def _refine_success(self, run: MiningRun) -> list[Experience]:
        """成功经验三层过滤。"""
        results: list[Experience] = []

        code = run.metadata.get("development", {}).get("code", "")
        if not code:
            code = run.metadata.get("hypothesis", {}).get("calculation_pseudo", "")

        components = extract_code_components(code)
        logger.info(
            "Step 1 解析: 从 %s 中提取 %d 个逻辑组件",
            run.metadata.get("factor_name", ""), len(components),
        )

        approved_components = []
        for comp in components:
            review = self._reviewer.review_component(
                code_snippet=comp["code"],
                name=comp["name"],
                description=comp["description"],
            )
            if review.get("approved"):
                approved_components.append({**comp, **review})
                logger.info("  组件 '%s' 通过审查 (quality=%.2f)", comp["name"], review.get("quality_score", 0))

        logger.info("Step 2 审查: %d/%d 个组件通过", len(approved_components), len(components))

        direction_tag = run.metadata.get("direction_tag", "")

        for comp in approved_components:
            qs = comp.get("quality_score", 0.5)
            if qs < 0.3:
                logger.info("  组件 '%s' 质量不达标 (%.2f < 0.3)，不入库", comp["name"], qs)
                continue

            exp = Experience(
                id=self._next_experience_id(),
                source="factor_mining_system",
                doc_type="mining_experience",
                content=f"{comp['name']}: {comp['description']}",
                tags=run.tags,
            )
            exp.metadata["track"] = ExperienceTrack.SUCCESS.value
            exp.metadata["type"] = ExperienceType.LOGIC_COMPONENT.value
            exp.metadata["name"] = comp["name"]
            exp.metadata["description"] = comp["description"]
            exp.metadata["code_snippet"] = comp["code"]
            exp.metadata["financial_rationale"] = comp.get("financial_rationale", "")
            exp.metadata["quality_score"] = qs
            exp.metadata["source_mining_ids"] = [run.id]
            exp.metadata["direction_tag"] = direction_tag
            exp.metadata["verification_status"] = (
                VerificationStatus.VERIFIED.value if qs >= 0.7
                else VerificationStatus.PENDING.value
            )

            self._repo.insert_experience(exp)
            results.append(exp)
            logger.info("Step 3 复评: 组件 '%s' 入库 (quality=%.2f)", comp["name"], qs)

        return results

    def _refine_failure(self, run: MiningRun) -> list[Experience]:
        """记录失败经验。"""
        analysis = self._reviewer.classify_failure(run)
        factor_name = run.metadata.get("factor_name", "")
        decision_reason = run.metadata.get("decision_reason", "")

        exp = Experience(
            id=self._next_experience_id(),
            source="factor_mining_system",
            doc_type="mining_experience",
            content=f"失败: {factor_name} - {analysis.get('lesson_learned', '')}",
            tags=run.tags,
        )
        exp.metadata["track"] = ExperienceTrack.FAILURE.value
        exp.metadata["type"] = ExperienceType.DEAD_END.value
        exp.metadata["name"] = f"failed_{factor_name}"
        exp.metadata["description"] = f"{factor_name}: {decision_reason}"
        exp.metadata["lesson_learned"] = analysis.get("lesson_learned", decision_reason)
        exp.metadata["recovery_strategy"] = analysis.get("recovery_strategy", "")
        exp.metadata["failure_type"] = analysis.get("failure_type", "logic_flaw")
        exp.metadata["source_mining_ids"] = [run.id]
        exp.metadata["direction_tag"] = run.metadata.get("direction_tag", "")

        self._repo.insert_experience(exp)
        logger.info("失败经验入库: %s (failure_type=%s)", exp.id, exp.metadata["failure_type"])
        return [exp]

    def _refine_recovery(self, run: MiningRun) -> list[Experience]:
        """记录恢复模式（精炼态）。"""
        factor_name = run.metadata.get("factor_name", "")
        decision_reason = run.metadata.get("decision_reason", "")

        exp = Experience(
            id=self._next_experience_id(),
            source="factor_mining_system",
            doc_type="mining_experience",
            content=f"精炼: {factor_name} - {decision_reason}",
            tags=run.tags,
        )
        exp.metadata["track"] = ExperienceTrack.FAILURE.value
        exp.metadata["type"] = ExperienceType.RECOVERY_PATTERN.value
        exp.metadata["name"] = f"refining_{factor_name}"
        exp.metadata["description"] = f"需精炼: {decision_reason}"
        exp.metadata["lesson_learned"] = decision_reason
        exp.metadata["recovery_strategy"] = run.metadata.get("refine_suggestions", "")
        exp.metadata["source_mining_ids"] = [run.id]
        exp.metadata["direction_tag"] = run.metadata.get("direction_tag", "")

        self._repo.insert_experience(exp)
        logger.info("恢复模式入库: %s", exp.id)
        return [exp]


def _parse_failure_type(raw: str) -> Optional[FailureType]:
    mapping = {
        "low_ic": FailureType.LOW_IC,
        "no_incremental_ic": FailureType.NO_INCREMENTAL_IC,
        "overfitting": FailureType.OVERFITTING,
        "data_leakage": FailureType.DATA_LEAKAGE,
        "logic_flaw": FailureType.LOGIC_FLAW,
    }
    return mapping.get(raw)
