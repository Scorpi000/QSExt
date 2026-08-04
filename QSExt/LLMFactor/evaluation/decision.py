# -*- coding: utf-8 -*-
"""入库决策规则引擎。

基于方案文档 5.5 节的三态决策规则：
1. accepted — 入库
2. refining — 精炼
3. rejected — 放弃
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from QSExt.LLMFactor.evaluation.config import EvalConfig
from QSExt.LLMFactor.evaluation.scoring import FiveDimScore


@dataclass
class DecisionResult:
    """入库决策结果。

    Attributes:
        decision: 决策 ("accepted" / "refining" / "rejected")
        reason: 决策原因摘要
        checks: 各项检查详情
    """
    decision: str = "rejected"
    reason: str = ""
    checks: dict = field(default_factory=dict)

    @property
    def factor_type(self) -> str:
        """因子类型：standard / synergistic。"""
        if self.checks.get("oos_rankic", {}).get("synergistic", False):
            return "synergistic"
        return "standard"

    def to_dict(self) -> dict:
        return {
            "决策": self.decision,
            "决策原因": self.reason,
            "因子类型": self.factor_type,
            "检查详情": self.checks,
        }

    def to_dataframe(self) -> pd.DataFrame:
        """转为 DataFrame（用于报告展示）。"""
        rows = []
        for check_name, check_info in self.checks.items():
            rows.append({
                "检查项": check_name,
                "通过": "✅" if check_info.get("passed", False) else "❌",
                "实际值": f"{check_info.get('value', 'N/A'):.4f}" if isinstance(check_info.get('value'), (int, float)) else str(check_info.get('value', 'N/A')),
                "阈值": f"{check_info.get('threshold', 'N/A'):.4f}" if isinstance(check_info.get('threshold'), (int, float)) else str(check_info.get('threshold', 'N/A')),
            })
        return pd.DataFrame(rows)


def make_decision(
    ic_stats: dict,
    oos_ic_stats: dict = None,
    incremental_ic_stats: dict = None,
    scores: FiveDimScore = None,
    alpha_stats: dict = None,
    config: EvalConfig = None,
) -> DecisionResult:
    """入库决策（三态）。

    必要条件（全部满足 → accepted）：
    1. 至少一个 Alpha 检验 t > 3.0
    2. 五维度综合评分 > 0.60
    3. 组合增量 IC 显著（t > 2.0）← 多样性主关卡
    4. OOS RankIC > 0.02 或增量 IC 显著（协同型例外）

    Parameters
    ----------
    ic_stats : dict
        样本内 IC 统计
    oos_ic_stats : dict
        样本外 IC 统计
    incremental_ic_stats : dict
        增量 IC 统计
    scores : FiveDimScore
        五维度评分
    alpha_stats : dict
        Alpha 检验统计
    config : EvalConfig
        评测配置

    Returns
    -------
    DecisionResult
        决策结果
    """
    if config is None:
        config = EvalConfig()

    checks = {}

    # 检查 1: Alpha t > 3.0
    if alpha_stats:
        max_t = max(
            abs(alpha_stats.get("capm_t", 0)),
            abs(alpha_stats.get("ff3_t", 0)),
            abs(alpha_stats.get("ff5_t", 0)),
            abs(alpha_stats.get("carhart_t", 0)),
        )
    else:
        # 如果没有 Alpha 统计，使用 IC t 统计量近似
        max_t = abs(ic_stats.get("t_stat", 0))

    alpha_ok = max_t > config.min_alpha_t
    checks["alpha_t"] = {
        "passed": alpha_ok,
        "value": max_t,
        "threshold": config.min_alpha_t,
    }

    # 检查 2: 综合评分 > 0.60
    composite_score = scores.composite if scores else 0.5
    score_ok = composite_score >= config.min_composite_score
    checks["composite_score"] = {
        "passed": score_ok,
        "value": composite_score,
        "threshold": config.min_composite_score,
    }

    # 检查 3: 增量 IC t > 2.0（多样性主关卡）
    if incremental_ic_stats:
        inc_t = abs(incremental_ic_stats.get("t_stat", 0))
        inc_ok = inc_t >= config.min_incremental_ic_t
        checks["incremental_ic_t"] = {
            "passed": inc_ok,
            "value": inc_t,
            "threshold": config.min_incremental_ic_t,
        }
    else:
        inc_t = 0
        inc_ok = False
        checks["incremental_ic_t"] = {
            "passed": False,
            "value": 0,
            "threshold": config.min_incremental_ic_t,
            "note": "未提供增量 IC 统计",
        }

    # 检查 4: OOS RankIC > 0.02 或增量 IC 显著（协同型例外）
    if oos_ic_stats:
        oos_rankic = abs(oos_ic_stats.get("rankic_mean", 0))
    else:
        # 如果没有 OOS 统计，使用 IS 统计近似
        oos_rankic = abs(ic_stats.get("rankic_mean", 0))

    oos_ok = oos_rankic >= config.min_oos_rankic
    synergistic = not oos_ok and inc_ok  # 协同型因子
    checks["oos_rankic"] = {
        "passed": oos_ok or synergistic,
        "value": oos_rankic,
        "threshold": config.min_oos_rankic,
        "synergistic": synergistic,
    }

    # 决策
    all_passed = all(c["passed"] for c in checks.values())
    if all_passed:
        return DecisionResult(
            decision="accepted",
            reason=_build_accept_reason(checks),
            checks=checks,
        )
    elif any([alpha_ok, score_ok]):
        return DecisionResult(
            decision="refining",
            reason=_build_refine_reason(checks),
            checks=checks,
        )
    else:
        return DecisionResult(
            decision="rejected",
            reason=_build_reject_reason(checks),
            checks=checks,
        )


def _build_accept_reason(checks: dict) -> str:
    """构建入库决策原因。"""
    reasons = []
    if checks.get("alpha_t", {}).get("passed"):
        reasons.append(f"Alpha t={checks['alpha_t']['value']:.2f} > {checks['alpha_t']['threshold']}")
    if checks.get("composite_score", {}).get("passed"):
        reasons.append(f"综合评分={checks['composite_score']['value']:.2f} > {checks['composite_score']['threshold']}")
    if checks.get("incremental_ic_t", {}).get("passed"):
        reasons.append(f"增量IC t={checks['incremental_ic_t']['value']:.2f} > {checks['incremental_ic_t']['threshold']}")
    if checks.get("oos_rankic", {}).get("synergistic"):
        reasons.append("协同型因子（单独不达标但增量IC显著）")
    return "入库通过：" + "；".join(reasons)


def _build_refine_reason(checks: dict) -> str:
    """构建精炼决策原因。"""
    failed = [name for name, info in checks.items() if not info.get("passed")]
    return f"建议精炼：以下检查未通过：{', '.join(failed)}"


def _build_reject_reason(checks: dict) -> str:
    """构建放弃决策原因。"""
    failed = [name for name, info in checks.items() if not info.get("passed")]
    return f"建议放弃：多项检查未通过：{', '.join(failed)}"


def check_correlation_warning(
    max_correlation: float,
    config: EvalConfig = None,
) -> dict:
    """相关性预警检查。

    超过阈值 → 触发增量 IC 复核，而非直接拒绝。

    Parameters
    ----------
    max_correlation : float
        与已有因子的最大相关性
    config : EvalConfig
        评测配置

    Returns
    -------
    dict
        预警信息
    """
    if config is None:
        config = EvalConfig()

    if max_correlation > config.corr_warning_threshold:
        return {
            "warning": True,
            "message": (
                f"与已有因子最大相关性 {max_correlation:.2f} 超过预警阈值 "
                f"{config.corr_warning_threshold}，需复核增量 IC"
            ),
        }
    return {"warning": False}
