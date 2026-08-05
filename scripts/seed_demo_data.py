# -*- coding: utf-8 -*-
"""将 demo_stock_cn_factor_def 示例挖掘产物写入数据库。"""
import json
import os
from datetime import datetime

from QSExt import __QS_MainPath__
from QSExt.LLMFactor.mining_log.db import MiningLogDB
from QSExt.LLMFactor.mining_log.models import (
    MiningRun, Experience, RunStatus, Decision,
    ExperienceTrack, ExperienceType, VerificationStatus,
)
from QSExt.LLMFactor.mining_log.repository import MiningLogRepository
from QSExt.LLMFactor.mining_log.embedding import EmbeddingService

_DEMO_DIR = os.path.join(__QS_MainPath__, "LLMFactor", "llm", "demo_stock_cn_factor_def")

# 读取 demo 产物
with open(os.path.join(_DEMO_DIR, "metadata.json"), encoding="utf-8") as f:
    metadata = json.load(f)
with open(os.path.join(_DEMO_DIR, "factor_def.py"), encoding="utf-8") as f:
    factor_code = f.read()
with open(os.path.join(_DEMO_DIR, "validation", "syntax_report.json"), encoding="utf-8") as f:
    validation = json.load(f)
with open(os.path.join(_DEMO_DIR, "validation", "leak_test_report.json"), encoding="utf-8") as f:
    leak_report = json.load(f)
with open(os.path.join(_DEMO_DIR, "validation", "semantic_review.md"), encoding="utf-8") as f:
    semantic_review = f.read()

db = MiningLogDB()
db.init_tables()
repo = MiningLogRepository(db)
emb = EmbeddingService()

# ============================================================
# MiningRun
# ============================================================

content = (
    "PE_TTM A股滚动市盈率因子：总市值除以归母净利润TTM。"
    "主板使用公司衍生报表数据和股票行情表现，"
    "科创板使用科创板衍生报表数据和科创板行情表现，"
    "合并时科创板总市值由元统一为万元。"
    "财务数据使用CalcType=最新基于公告时点取数防止未来信息泄漏。"
)

run = MiningRun(id="FM_demo_pe_ttm")
run.content = content
run.tags = metadata["tags"]
m = run.metadata

m["hypothesis_id"] = "hyp_demo_pe_ttm"
m["parent_run_id"] = None
m["status"] = RunStatus.COMPLETED.value
m["decision"] = Decision.ACCEPTED.value
m["decision_reason"] = "PE_TTM 是核心估值指标，代码通过语法/执行/泄漏/单位四重验证"
m["factor_name"] = metadata["factor_name"]
m["category"] = metadata["category"]
m["direction_tag"] = "估值/PE"
m["factor_type"] = "standard"
m["rankic_mean"] = 0.042
m["rankicir"] = 0.68
m["oos_rankic"] = 0.039
m["incremental_ic"] = 0.015
m["incremental_ic_t"] = 2.3
m["max_correlation"] = 0.35
m["composite_score"] = 0.72

m["hypothesis"] = {
    "factor_name": metadata["factor_name"],
    "category": metadata["category"],
    "market": metadata["market"],
    "frequency": metadata["frequency"],
    "description": metadata["description"],
    "formula": metadata["formula"],
    "economic_rationale": (
        "PE_TTM 是衡量股票估值水平的核心指标，"
        "等于总市值除以最近四个季度归属于母公司股东的净利润之和。"
        "低 PE 股票通常被认为被低估，长期来看具有更高的预期收益。"
    ),
    "data_requirements": metadata["data_sources"],
    "unit_conversions": metadata["unit_conversions"],
}

m["development"] = {
    "code_path": "QSExt/LLMFactor/llm/demo_stock_cn_factor_def/factor_def.py",
    "code": factor_code,
    "auto_fix_count": 0,
    "param_search": {
        "method": "TPE",
        "n_trials": 200,
        "best_params": {},
        "note": "PE_TTM 无需超参数搜索",
    },
}

m["evaluation"] = {
    "sample_period": {
        "in_sample": ["2015-01", "2022-12"],
        "out_of_sample": ["2023-01", "2025-12"],
    },
    "rankic_mean": 0.042,
    "rankicir": 0.68,
    "oos_rankic": 0.039,
    "incremental_ic": 0.015,
    "incremental_ic_t": 2.3,
    "max_correlation": 0.35,
    "composite_score": 0.72,
    "dim_effectiveness": 0.65,
    "dim_stability": 0.70,
    "dim_turnover": 0.80,
    "dim_diversity": 0.75,
    "dim_overfitting": 0.73,
    "diagnostics": {
        "coverage_metrics": {
            "valid_security_ratio": 0.92,
            "cap_coverage_ratio": 0.85,
        },
        "spread_portfolio_stats": {
            "long_short_annual_return": 0.12,
            "long_short_sharpe": 1.1,
        },
        "alpha_tests": {
            "capm": {"alpha": 0.08, "t_stat": 3.2},
            "ff3": {"alpha": 0.06, "t_stat": 2.8},
        },
        "size_stratified_alpha": {
            "q1_micro": {"alpha": 0.10},
            "q5_mega": {"alpha": 0.03},
        },
    },
}

m["validation"] = {
    "syntax": validation["syntax"],
    "execution": validation["execution"],
    "leak_test": validation["leak_test"],
    "unit_consistency": validation["unit_consistency"],
    "semantic_review": validation["semantic_review"],
    "details": validation["details"],
    "issues": validation["issues"],
    "auto_fix_count": validation["auto_fix_count"],
    "validated_at": validation["validated_at"],
}

m["exploration_trail"] = [
    {
        "source": "factor_registry",
        "type": "search_factors",
        "query": "PE TTM 估值",
        "note": "参考已有 PE 因子定义，确保代码规范和双板合并一致性",
    },
]

now = datetime.now().isoformat()
m["timing"] = {
    "started_at": "2025-07-01T10:00:00",
    "hypothesis_end": "2025-07-01T10:15:00",
    "development_end": "2025-07-01T10:30:00",
    "evaluation_end": "2025-07-01T10:45:00",
}
m["llm_usage"] = {
    "model": "deepseek-v4-pro",
    "total_tokens": 8000,
    "interactions": 3,
}

# embedding
run.embedding_str = emb.to_db_format(emb.encode(run.content))

repo.insert_run(run)
print(f"[OK] 已写入 MiningRun: {run.id}")

# ============================================================
# 成功经验 1：双板单位换算
# ============================================================
exp1 = Experience(id="EXP_demo_unit_conversion")
exp1.content = (
    "科创板总市值单位统一：元 / 10000 → 万元。"
    "合并主板和科创板数据前必须检查并统一单位。"
    "类似场景：成交量（万股 vs 股）、成交金额（万元 vs 元）也需统一。"
)
exp1.tags = ["估值", "单位换算", "可复用组件"]
e1 = exp1.metadata
e1["track"] = ExperienceTrack.SUCCESS.value
e1["type"] = ExperienceType.TOOL_FUNCTION.value
e1["name"] = "unit_conversion_stib"
e1["description"] = "科创板总市值单位统一：元 / 10000 → 万元"
e1["code_snippet"] = (
    "# 总市值 —— 科创板（元）\n"
    'TotalMV_STIB = FT_STIB.getFactor("总市值(元)") / 10000  # 元→万元'
)
e1["financial_rationale"] = (
    "主板市值单位为万元，科创板为元，合并前必须统一单位。"
    "常见需要统一单位的指标：总市值、流通市值、成交量、成交金额。"
)
e1["quality_score"] = 0.92
e1["source_mining_ids"] = ["FM_demo_pe_ttm"]
e1["direction_tag"] = "估值/PE"
e1["verification_status"] = VerificationStatus.VERIFIED.value
repo.insert_experience(exp1)
print(f"[OK] 已写入 Experience: {exp1.id}")

# ============================================================
# 成功经验 2：财务数据防泄漏
# ============================================================
exp2 = Experience(id="EXP_demo_calc_type_latest")
exp2.content = (
    "财务数据使用 CalcType=最新 防止未来信息泄漏。"
    "基于公告时点而非报告期取数，确保不在回测中引入前瞻偏差。"
)
exp2.tags = ["防泄漏", "财务", "最佳实践"]
e2 = exp2.metadata
e2["track"] = ExperienceTrack.SUCCESS.value
e2["type"] = ExperienceType.LOGIC_COMPONENT.value
e2["name"] = "calc_type_latest"
e2["description"] = "财务数据使用 CalcType=最新 取最新已公告财报数据，防止未来信息泄漏"
e2["code_snippet"] = (
    '# 主板\n'
    'FT = SDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "最新"})\n'
    'NP_TTM = FT.getFactor("归属母公司股东的净利润(TTM)")\n'
    '\n'
    '# 科创板\n'
    'FT_STIB = SDB.getTable("科创板衍生报表数据", args={"CalcType": "最新"})\n'
    'NP_TTM_STIB = FT_STIB.getFactor("归属母公司股东的净利润(TTM)")'
)
e2["financial_rationale"] = (
    "财务数据在财报公告日才进入市场，在公告日之前属于未来信息。"
    "CalcType=最新 基于公告时点取数，确保不会引入前瞻偏差。"
)
e2["quality_score"] = 0.95
e2["source_mining_ids"] = ["FM_demo_pe_ttm"]
e2["direction_tag"] = "估值/PE"
e2["verification_status"] = VerificationStatus.VERIFIED.value
repo.insert_experience(exp2)
print(f"[OK] 已写入 Experience: {exp2.id}")

# ============================================================
# 成功经验 3：双板合并模式
# ============================================================
exp3 = Experience(id="EXP_demo_dual_board_merge")
exp3.content = (
    "A股因子须同时覆盖主板和科创板，使用 fo.Where + fo.NotNull 合并策略："
    "主板优先，缺失时以科创板填充。"
)
exp3.tags = ["双板合并", "A股", "可复用组件"]
e3 = exp3.metadata
e3["track"] = ExperienceTrack.SUCCESS.value
e3["type"] = ExperienceType.FORMULA_PATTERN.value
e3["name"] = "dual_board_merge"
e3["description"] = "主板+科创板双数据源合并：Where(主板, NotNull(主板), 科创板)"
e3["code_snippet"] = (
    "# 合并主板与科创板（主板优先，缺失时以科创板填充）\n"
    'where = fo.Where(dtype="double")\n'
    "notnull = fo.NotNull()\n"
    "Factor = where(Factor_Main, notnull(Factor_Main), Factor_STIB)"
)
e3["financial_rationale"] = (
    "科创板与主板数据源分开，A股因子必须同时覆盖。"
    "主板数据优先保证了数据连续性（科创板早期历史数据为空），"
    "科创板填补了新上市股票的覆盖。"
)
e3["quality_score"] = 0.90
e3["source_mining_ids"] = ["FM_demo_pe_ttm"]
e3["direction_tag"] = "估值/PE"
e3["verification_status"] = VerificationStatus.VERIFIED.value
repo.insert_experience(exp3)
print(f"[OK] 已写入 Experience: {exp3.id}")

db.close()
print()
print("=== demo 写入全部完成! ===")
