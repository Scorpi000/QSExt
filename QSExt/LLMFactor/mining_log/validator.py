# -*- coding: utf-8 -*-
"""挖掘日志完整性校验。

检查 mining_log 表中已有记录的字段完整性，输出缺失字段报告。

用法：
    from QSExt.LLMFactor.mining_log.validator import validate_all_runs

    report = validate_all_runs()
    for item in report["issues"]:
        print(f"{item['run_id']}: {item['missing']}")
"""
from __future__ import annotations

import logging
from typing import Any

from QSExt.LLMFactor.mining_log.models import RunStatus
from QSExt.LLMFactor.mining_log.repository import MiningLogRepository

__QS_Logger__ = logging.getLogger("QSR.mining_log_validator")

# 各状态下的推荐字段
RECOMMENDED_FIELDS = {
    "any": [
        "factor_name", "category", "direction_tag", "status",
    ],
    RunStatus.IN_DEVELOPMENT.value: [
        "hypothesis", "timing",
    ],
    RunStatus.EVALUATING.value: [
        "hypothesis", "development", "timing",
    ],
    RunStatus.COMPLETED.value: [
        "hypothesis", "development", "evaluation", "decision",
        "decision_reason", "rankic_mean", "timing",
    ],
    RunStatus.FAILED.value: [
        "failure_reason",
    ],
}

# 评测相关字段（status=completed 时推荐有）
EVAL_FIELDS = [
    "rankic_mean", "rankicir", "composite_score",
]


def validate_run(metadata: dict[str, Any]) -> dict[str, Any]:
    """校验单条运行记录的字段完整性。

    Parameters
    ----------
    metadata : dict
        MiningRun.metadata

    Returns
    -------
    dict
        {
            "status": str,          # 运行状态
            "missing_required": [], # 缺失的必填字段
            "missing_recommended": [],  # 缺失的推荐字段
            "is_complete": bool,    # 是否完整
        }
    """
    status = metadata.get("status", "")
    missing_required = []
    missing_recommended = []

    # 检查通用字段
    for field in RECOMMENDED_FIELDS["any"]:
        if field not in metadata or metadata[field] is None:
            missing_required.append(field)

    # 检查状态相关字段
    status_fields = RECOMMENDED_FIELDS.get(status, [])
    for field in status_fields:
        if field not in metadata or metadata[field] is None:
            missing_recommended.append(field)

    # completed 状态下检查评测字段
    if status == RunStatus.COMPLETED.value:
        for field in EVAL_FIELDS:
            if field not in metadata or metadata[field] is None:
                missing_recommended.append(field)

    return {
        "status": status,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "is_complete": len(missing_required) == 0 and len(missing_recommended) == 0,
    }


def validate_all_runs(repo: MiningLogRepository) -> dict[str, Any]:
    """校验所有运行记录的完整性。

    Parameters
    ----------
    repo : MiningLogRepository
        日志数据库仓库

    Returns
    -------
    dict
        {
            "total": int,           # 总记录数
            "complete": int,        # 完整记录数
            "incomplete": int,      # 不完整记录数
            "issues": [             # 问题详情
                {"run_id": str, "status": str, "missing": [...], "recommended_missing": [...]},
            ],
        }
    """
    runs = repo.list_runs()
    issues = []
    complete_count = 0

    for run in runs:
        result = validate_run(run.metadata)
        if result["is_complete"]:
            complete_count += 1
        else:
            issues.append({
                "run_id": run.id,
                "status": result["status"],
                "missing": result["missing_required"],
                "recommended_missing": result["missing_recommended"],
            })

    return {
        "total": len(runs),
        "complete": complete_count,
        "incomplete": len(runs) - complete_count,
        "issues": issues,
    }


def print_validation_report(report: dict[str, Any]) -> None:
    """打印校验报告。"""
    print(f"\n{'='*60}")
    print(f"挖掘日志完整性校验报告")
    print(f"{'='*60}")
    print(f"总记录数: {report['total']}")
    print(f"完整记录: {report['complete']}")
    print(f"不完整记录: {report['incomplete']}")

    if report["issues"]:
        print(f"\n{'─'*60}")
        print("问题详情:")
        for item in report["issues"]:
            print(f"\n  Run: {item['run_id']} (status={item['status']})")
            if item["missing"]:
                print(f"    缺失必填: {', '.join(item['missing'])}")
            if item["recommended_missing"]:
                print(f"    缺失推荐: {', '.join(item['recommended_missing'])}")
    else:
        print("\n✅ 所有记录完整。")
    print()
