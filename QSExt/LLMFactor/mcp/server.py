# -*- coding: utf-8 -*-
"""挖掘日志库 MCP Server — 基于 fastmcp 将 MiningLogRetriever 暴露为 MCP 工具。

提供给 LLM / Agent 在假设生成阶段调用，检索历史挖掘记录和经验库。

启动方式:
    python -m QSExt.LLMFactor.mcp.server

或在 .mcp.json 中配置:
    "mining-log": {
        "command": "python",
        "args": ["-m", "QSExt.LLMFactor.mcp.server"],
        "cwd": "项目根目录",
        "env": {"PYTHONPATH": "..."}
    }
"""
from __future__ import annotations

import os
import sys

# 确保项目根路径在 sys.path 中
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastmcp import FastMCP

from QSExt.LLMFactor.mining_log.db import MiningLogDB
from QSExt.LLMFactor.mining_log.repository import MiningLogRepository
from QSExt.LLMFactor.mining_log.retriever import MiningLogRetriever

# ============================================================
# 初始化
# ============================================================

mcp = FastMCP("mining-log")

_db = MiningLogDB()
_db.init_tables()
_repo = MiningLogRepository(_db)
_retriever = MiningLogRetriever(_repo)


# ============================================================
# 工具：运行记录检索
# ============================================================

@mcp.tool
def search_history(query: str, top_k: int = 10) -> list[dict]:
    """按研究方向搜索历史挖掘记录。

    通过全文检索和标签匹配找到与查询相关、的历史运行记录（含已入库、已放弃和精炼中）。
    返回每条记录的因子名称、类别、RankIC、入库决策等摘要信息。

    Args:
        query: 搜索关键词或自然语言描述，如 "动量因子 日内"、"估值类因子 PE"
        top_k: 返回结果数量上限，默认 10
    """
    results = _retriever.search_by_direction(query, top_k=top_k)
    return {"items": [_summary_to_dict(r) for r in results]}


@mcp.tool
def get_accepted_factors(
    direction: str = "",
    min_rankic: float = 0.0,
    metric: str = "rankic_mean",
    limit: int = 20,
) -> dict:
    """获取已入库的成功因子列表（用于 few-shot 范例）。

    Args:
        direction: 按方向标签过滤，如 "动量"、"估值"。空字符串表示不过滤
        min_rankic: 最低 RankIC 阈值，默认 0（不限制）
        metric: 排序指标: rankic_mean / composite_score / incremental_ic_t，默认 rankic_mean
        limit: 返回数量上限，默认 20
    """
    if direction:
        results = _retriever.search_accepted_in_direction(direction, limit=limit)
    else:
        results = _retriever.get_top_factors(metric=metric, limit=limit)

    if min_rankic > 0:
        results = [r for r in results if (r.rankic_mean or 0) >= min_rankic]
    return {"items": [_summary_to_dict(r) for r in results]}


# ============================================================
# 工具：经验检索
# ============================================================

@mcp.tool
def get_successful_components(
    domain: str = "",
    direction: str = "",
    min_quality: float = 0.7,
    limit: int = 20,
) -> dict:
    """获取成功经验库中的可复用逻辑组件。

    这些组件来自已验证有效的因子代码，按三层过滤（解析→审查→复评）后入库。

    Args:
        domain: 组件类型: logic_component / tool_function / formula_pattern。空字符串表示不限
        direction: 按方向标签过滤。空字符串表示不限制
        min_quality: 最低质量评分 0~1，默认 0.7
        limit: 返回数量上限，默认 20
    """
    domain = domain or None
    direction = direction or None
    components = _retriever.get_successful_patterns(
        domain=domain, direction_tag=direction, min_quality=min_quality, limit=limit,
    )
    return {"items": [_component_to_dict(c) for c in components]}


@mcp.tool
def get_failure_lessons(query: str = "", direction: str = "", limit: int = 10) -> dict:
    """检索历史失败记录和教训。

    查询某个方向下之前失败的原因和恢复策略，避免重复无效探索。

    Args:
        query: 搜索关键词，如 "日内动量"
        direction: 按方向标签精确过滤。空字符串表示全文检索
        limit: 返回数量上限，默认 10
    """
    if direction:
        results = _retriever.get_failure_by_direction(direction, limit=limit)
    else:
        results = _retriever.get_failed_directions(query, limit=limit)
    return {"items": [_failure_to_dict(r) for r in results]}


# ============================================================
# 工具：方向覆盖率
# ============================================================

@mcp.tool
def get_direction_coverage() -> dict:
    """统计各研究方向的探索次数和成功率。

    返回每个方向标签的 attempts（总尝试次数）、successes（成功入库次数）、
    success_rate（成功率）。用于识别高潜力未充分探索区域。

    Returns:
        以方向标签为 key 的字典，value 包含 attempts, successes, success_rate 等
    """
    coverage = _retriever.get_direction_coverage()
    result = []
    for tag, stats in coverage.items():
        result.append({
            "direction_tag": tag,
            "attempts": stats.attempts,
            "successes": stats.successes,
            "success_rate": round(stats.success_rate, 3),
        })
    result.sort(key=lambda x: x["attempts"], reverse=True)
    return {"items": result}


# ============================================================
# 工具：演化追溯
# ============================================================

@mcp.tool
def get_evolution_trail(factor_name: str) -> dict:
    """追溯一个因子的完整演化历史。

    查询同名因子的所有运行版本（从初始假设到多次精炼），
    按时间排序展示 RankIC 的变化趋势和改进过程。

    Args:
        factor_name: 因子名称，如 "enhanced_intraday_momentum_v2"
    """
    trail = _retriever.get_factor_evolution_trail(factor_name)
    return {"items": [_summary_to_dict(r) for r in trail]}


@mcp.tool
def get_evolution_tree(run_id: str) -> dict:
    """以给定运行 ID 为根，递归构建完整演化树。

    向上追溯到最原始的假设，向下展示所有后继精炼/改进。
    用于理解一个因子从创生到入库的全过程。

    Args:
        run_id: 挖掘运行 ID，如 "FM_20260704_143052"
    """
    tree = _retriever.get_evolution_tree(run_id)
    return _simplify_tree(tree)


# ============================================================
# 格式化辅助
# ============================================================

def _summary_to_dict(r) -> dict:
    return {
        "run_id": r.run_id,
        "factor_name": r.factor_name,
        "category": r.category,
        "direction_tag": r.direction_tag,
        "status": r.status,
        "decision": r.decision,
        "decision_reason": r.decision_reason,
        "rankic_mean": r.rankic_mean,
        "rankicir": r.rankicir,
        "incremental_ic_t": r.incremental_ic_t,
        "composite_score": r.composite_score,
        "parent_run_id": r.parent_run_id,
        "tags": r.tags,
        "created_at": r.created_at,
    }


def _component_to_dict(c) -> dict:
    return {
        "experience_id": c.experience_id,
        "name": c.name,
        "type": c.exp_type,
        "description": c.description,
        "code_snippet": c.code_snippet,
        "financial_rationale": c.financial_rationale,
        "quality_score": c.quality_score,
        "usage_count": c.usage_count,
        "tags": c.tags,
    }


def _failure_to_dict(f) -> dict:
    return {
        "experience_id": f.experience_id,
        "direction_tag": f.direction_tag,
        "failure_type": f.failure_type,
        "description": f.description,
        "lesson_learned": f.lesson_learned,
        "recovery_strategy": f.recovery_strategy,
        "source_run_ids": f.source_run_ids,
    }


def _simplify_tree(node: dict) -> dict:
    if not node:
        return {}
    return {
        "run": _summary_to_dict(node["run"]),
        "children": [_simplify_tree(child) for child in node.get("children", [])],
    }


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    mcp.run()
