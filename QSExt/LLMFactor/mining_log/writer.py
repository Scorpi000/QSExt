# -*- coding: utf-8 -*-
"""挖掘日志写入器。

在因子挖掘流程的各个阶段自动写入日志，封装 MiningLogRepository 的调用，
提供阶段化的写入接口和格式校验。

用法：
    from QSExt.LLMFactor.mining_log import MiningLogWriter

    writer = MiningLogWriter(repo)

    # 假设生成阶段完成
    writer.start_run(run_id, hypothesis={...}, tags=[...])

    # 因子开发阶段完成
    writer.record_development(run_id, code_path="...", best_params={...})

    # 因子评测阶段完成
    writer.record_evaluation(run_id, eval_results={...})

    # 决策
    writer.set_decision(run_id, decision="accepted", reason="...")
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from QSExt.LLMFactor.mining_log.models import (
    MiningRun,
    RunStatus,
)
from QSExt.LLMFactor.mining_log.repository import MiningLogRepository

__QS_Logger__ = logging.getLogger("QSR.mining_log_writer")


# ============================================================
# 字段规范
# ============================================================

# 各阶段必填字段
REQUIRED_FIELDS = {
    "start": ["factor_name", "category", "direction_tag", "hypothesis"],
    "development": ["code_path"],
    "evaluation": ["rankic_mean"],
    "decision": ["decision", "decision_reason"],
}

# 各阶段可选字段（用于日志完整性检查）
OPTIONAL_FIELDS = {
    "start": [
        "hypothesis_id", "parent_run_id", "inspired_by",
        "exploration_trail", "reflection",
    ],
    "development": [
        "code_versions", "auto_fix_count", "param_search",
        "validation_results",
    ],
    "evaluation": [
        "rankicir", "oos_rankic", "incremental_ic", "incremental_ic_t",
        "max_correlation", "composite_score", "overfitting_risk_score",
        "diagnostics", "factor_type",
    ],
    "decision": ["decision"],
}


class MiningLogWriter:
    """挖掘日志写入器。

    在挖掘流程各阶段自动写入日志，提供格式校验和 timing 记录。

    Parameters
    ----------
    repo : MiningLogRepository
        日志数据库仓库
    """

    def __init__(self, repo: MiningLogRepository):
        self._repo = repo

    # ============================================================
    # 假设生成阶段
    # ============================================================

    def start_run(
        self,
        run_id: str,
        factor_name: str,
        category: str,
        direction_tag: str,
        hypothesis: dict,
        tags: Optional[list[str]] = None,
        parent_run_id: Optional[str] = None,
        hypothesis_id: Optional[str] = None,
        inspired_by: Optional[dict] = None,
        exploration_trail: Optional[list] = None,
        reflection: Optional[dict] = None,
        **kwargs,
    ) -> MiningRun:
        """记录假设生成阶段完成，创建新的挖掘运行记录。

        Parameters
        ----------
        run_id : str
            运行唯一 ID，如 "FM_20260701_143052"
        factor_name : str
            因子名称
        category : str
            因子类别（动量、估值、质量...）
        direction_tag : str
            方向标签（如 "动量/日内方向预测"）
        hypothesis : dict
            完整假设文档
        tags : list[str], optional
            标签列表
        parent_run_id : str, optional
            父运行 ID（精炼时指向原运行）
        hypothesis_id : str, optional
            假设文档 ID
        inspired_by : dict, optional
            灵感来源
        exploration_trail : list, optional
            检索溯源记录
        reflection : dict, optional
            反思式规划记录

        Returns
        -------
        MiningRun
            创建的运行记录
        """
        run = MiningRun(id=run_id)
        run.metadata.update({
            "factor_name": factor_name,
            "category": category,
            "direction_tag": direction_tag,
            "hypothesis": hypothesis,
            "status": RunStatus.IN_DEVELOPMENT.value,
        })

        if parent_run_id:
            run.metadata["parent_run_id"] = parent_run_id
        if hypothesis_id:
            run.metadata["hypothesis_id"] = hypothesis_id
        if inspired_by:
            run.metadata["inspired_by"] = inspired_by
        if exploration_trail:
            run.metadata["exploration_trail"] = exploration_trail
        if reflection:
            run.metadata["reflection"] = reflection

        # 记录 timing
        run.metadata["timing"] = {
            "hypothesis_end": datetime.now().isoformat(),
        }

        # 额外字段
        run.metadata.update(kwargs)

        # 构建 content（供全文检索和 embedding）
        run.content = self._build_content(run)
        run.tags = tags or [category, direction_tag]

        # 校验
        self._validate("start", run.metadata)

        self._repo.insert_run(run)
        __QS_Logger__.info(f"假设生成完成: {run_id} ({factor_name})")
        return run

    # ============================================================
    # 因子开发阶段
    # ============================================================

    def record_development(
        self,
        run_id: str,
        code_path: str,
        best_params: Optional[dict] = None,
        code_versions: Optional[list] = None,
        auto_fix_count: int = 0,
        param_search: Optional[dict] = None,
        validation_results: Optional[dict] = None,
        **kwargs,
    ) -> None:
        """记录因子开发阶段完成。

        Parameters
        ----------
        run_id : str
            运行 ID
        code_path : str
            因子代码文件路径
        best_params : dict, optional
            贝叶斯搜索最优参数
        code_versions : list, optional
            代码版本链
        auto_fix_count : int
            自动修复次数
        param_search : dict, optional
            参数搜索详情（method, n_trials, best_is_rankic 等）
        validation_results : dict, optional
            验证结果（syntax, leak_test, semantic_review）
        """
        run = self._repo.get_run(run_id)
        if run is None:
            raise ValueError(f"运行记录不存在: {run_id}")

        run.metadata["status"] = RunStatus.EVALUATING.value
        run.metadata["development"] = {
            "code_path": code_path,
            "auto_fix_count": auto_fix_count,
        }

        if best_params:
            run.metadata["development"]["best_params"] = best_params
        if code_versions:
            run.metadata["code_versions"] = code_versions
            run.metadata["development"]["code_versions"] = code_versions
        if param_search:
            run.metadata["development"]["param_search"] = param_search
        if validation_results:
            run.metadata["development"]["validation"] = validation_results

        # 额外字段
        for k, v in kwargs.items():
            run.metadata["development"][k] = v

        # 更新 timing
        if "timing" not in run.metadata:
            run.metadata["timing"] = {}
        run.metadata["timing"]["development_end"] = datetime.now().isoformat()

        # 更新 content
        run.content = self._build_content(run)

        self._repo.insert_run(run)
        __QS_Logger__.info(f"因子开发完成: {run_id}")

    # ============================================================
    # 因子评测阶段
    # ============================================================

    def record_evaluation(
        self,
        run_id: str,
        rankic_mean: float,
        rankicir: Optional[float] = None,
        oos_rankic: Optional[float] = None,
        incremental_ic: Optional[float] = None,
        incremental_ic_t: Optional[float] = None,
        max_correlation: Optional[float] = None,
        composite_score: Optional[float] = None,
        overfitting_risk_score: Optional[float] = None,
        factor_type: str = "standard",
        diagnostics: Optional[dict] = None,
        **kwargs,
    ) -> None:
        """记录因子评测阶段完成。

        Parameters
        ----------
        run_id : str
            运行 ID
        rankic_mean : float
            样本内 RankIC 均值（必填）
        rankicir : float, optional
            ICIR
        oos_rankic : float, optional
            样本外 RankIC
        incremental_ic : float, optional
            组合增量 IC
        incremental_ic_t : float, optional
            增量 IC 的 t 统计量
        max_correlation : float, optional
            与已有因子最大相关性
        composite_score : float, optional
            五维综合评分
        overfitting_risk_score : float, optional
            过拟合风险评分
        factor_type : str
            因子类型：standard / synergistic
        diagnostics : dict, optional
            四部分诊断详细数据
        """
        run = self._repo.get_run(run_id)
        if run is None:
            raise ValueError(f"运行记录不存在: {run_id}")

        # 更新顶层字段（用于索引和查询）
        eval_fields = {
            "rankic_mean": rankic_mean,
            "rankicir": rankicir,
            "oos_rankic": oos_rankic,
            "incremental_ic": incremental_ic,
            "incremental_ic_t": incremental_ic_t,
            "max_correlation": max_correlation,
            "composite_score": composite_score,
            "factor_type": factor_type,
        }
        for k, v in eval_fields.items():
            if v is not None:
                run.metadata[k] = v

        # 详细评测数据
        run.metadata["evaluation"] = {
            k: v for k, v in {
                "rankic_mean": rankic_mean,
                "rankicir": rankicir,
                "oos_rankic": oos_rankic,
                "incremental_ic": incremental_ic,
                "incremental_ic_t": incremental_ic_t,
                "max_correlation": max_correlation,
                "composite_score": composite_score,
                "overfitting_risk_score": overfitting_risk_score,
                "factor_type": factor_type,
                "diagnostics": diagnostics,
            }.items() if v is not None
        }

        # 额外字段
        for k, v in kwargs.items():
            run.metadata["evaluation"][k] = v

        # 更新 timing
        if "timing" not in run.metadata:
            run.metadata["timing"] = {}
        run.metadata["timing"]["evaluation_end"] = datetime.now().isoformat()

        # 更新 content
        run.content = self._build_content(run)

        self._validate("evaluation", run.metadata)
        self._repo.insert_run(run)
        __QS_Logger__.info(f"因子评测完成: {run_id} (RankIC={rankic_mean:.4f})")

    # ============================================================
    # 决策
    # ============================================================

    def set_decision(
        self,
        run_id: str,
        decision: str,
        reason: str,
        status: Optional[str] = None,
    ) -> None:
        """设置入库决策。

        Parameters
        ----------
        run_id : str
            运行 ID
        decision : str
            决策：accepted / refining / rejected
        reason : str
            决策原因
        status : str, optional
            运行状态，默认根据 decision 自动设置
        """
        run = self._repo.get_run(run_id)
        if run is None:
            raise ValueError(f"运行记录不存在: {run_id}")

        run.metadata["decision"] = decision
        run.metadata["decision_reason"] = reason
        run.metadata["status"] = status or RunStatus.COMPLETED.value

        # 更新 timing
        if "timing" not in run.metadata:
            run.metadata["timing"] = {}
        run.metadata["timing"]["completed_at"] = datetime.now().isoformat()

        # 更新 content
        run.content = self._build_content(run)

        self._validate("decision", run.metadata)
        self._repo.insert_run(run)
        __QS_Logger__.info(f"决策设置: {run_id} → {decision}")

    # ============================================================
    # 辅助方法
    # ============================================================

    def update_field(self, run_id: str, key: str, value: Any) -> None:
        """更新单个 metadata 字段。"""
        run = self._repo.get_run(run_id)
        if run is None:
            raise ValueError(f"运行记录不存在: {run_id}")
        run.metadata[key] = value
        self._repo.insert_run(run)

    def update_tags(self, run_id: str, tags: list[str]) -> None:
        """更新标签列表。"""
        run = self._repo.get_run(run_id)
        if run is None:
            raise ValueError(f"运行记录不存在: {run_id}")
        run.tags = tags
        self._repo.insert_run(run)

    def mark_failed(self, run_id: str, reason: str) -> None:
        """标记运行失败。"""
        run = self._repo.get_run(run_id)
        if run is None:
            raise ValueError(f"运行记录不存在: {run_id}")
        run.metadata["status"] = RunStatus.FAILED.value
        run.metadata["failure_reason"] = reason
        if "timing" not in run.metadata:
            run.metadata["timing"] = {}
        run.metadata["timing"]["failed_at"] = datetime.now().isoformat()
        run.content = self._build_content(run)
        self._repo.insert_run(run)
        __QS_Logger__.info(f"运行失败: {run_id} ({reason})")

    @staticmethod
    def _build_content(run: MiningRun) -> str:
        """从 metadata 构建 content 文本（供全文检索和 embedding）。"""
        parts = []
        meta = run.metadata
        if meta.get("factor_name"):
            parts.append(f"因子: {meta['factor_name']}")
        if meta.get("category"):
            parts.append(f"类别: {meta['category']}")
        if meta.get("direction_tag"):
            parts.append(f"方向: {meta['direction_tag']}")
        if meta.get("hypothesis", {}).get("economic_rationale"):
            # 取假设的前 500 字符
            rationale = meta["hypothesis"]["economic_rationale"]
            parts.append(f"逻辑: {rationale[:500]}")
        if meta.get("decision"):
            parts.append(f"决策: {meta['decision']}")
        if meta.get("decision_reason"):
            parts.append(f"原因: {meta['decision_reason']}")
        if meta.get("rankic_mean") is not None:
            parts.append(f"RankIC: {meta['rankic_mean']:.4f}")
        return " | ".join(parts)

    @staticmethod
    def _validate(stage: str, metadata: dict) -> list[str]:
        """校验必填字段，返回缺失字段列表。"""
        required = REQUIRED_FIELDS.get(stage, [])
        missing = []
        for field in required:
            if field not in metadata or metadata[field] is None:
                missing.append(field)
        if missing:
            __QS_Logger__.warning(
                f"阶段 '{stage}' 缺少字段: {missing}"
            )
        return missing
