# -*- coding: utf-8 -*-
"""统一评测入口。

构建 QuantStudio 评测 DAG，执行 IS/OOS 两段评测，
调用 scoring 和 decision 模块完成五维度评分与入库决策。

支持 FeatherFactorCache 缓存，通过 EvalConfig 或外部传入的 cache 实例控制。
多轮评测可共享同一 Cache，避免重复计算。

用法：
    from QSExt.LLMFactor.evaluation import FactorEvaluator, EvalConfig
    from QSExt.LLMFactor.evaluation.cache_manager import EvalCacheManager

    config = EvalConfig.from_yaml("evaluation.yaml")
    evaluator = FactorEvaluator(config)

    # 方式 1: 外部管理 Cache（推荐用于多轮评测）
    cache_manager = EvalCacheManager(cache_dir=config.cache_dir)
    cache = cache_manager.get_or_create(dt_ruler)
    report = evaluator.evaluate(..., cache=cache)
    cache_manager.close()

    # 方式 2: 内部自动管理 Cache
    report = evaluator.evaluate(...)
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from QSExt.LLMFactor.evaluation.config import EvalConfig
from QSExt.LLMFactor.evaluation.decision import DecisionResult, make_decision
from QSExt.LLMFactor.evaluation.scoring import FiveDimScore, calc_scores

__QS_Logger__ = logging.getLogger("QSR.evaluator")


# ============================================================
# 评测报告数据类
# ============================================================

@dataclass
class EvalReport:
    """评测报告结果。

    Attributes:
        factor_name: 因子名称
        qsid: 因子 QSID
        category: 因子类别
        scores: 五维度评分
        decision: 入库决策
        report_html: 合并后的 HTML 报告
        is_output: 样本内原始 output
        oos_output: 样本外原始 output
        is_stats: 样本内提取的标准化统计
        oos_stats: 样本外提取的标准化统计
    """
    factor_name: str
    qsid: str
    category: str
    scores: FiveDimScore
    decision: DecisionResult
    report_html: str
    is_output: Dict[str, Any]
    oos_output: Dict[str, Any]
    is_stats: Dict[str, Any]
    oos_stats: Dict[str, Any]

    @property
    def summary(self) -> dict:
        return {
            "factor_name": self.factor_name,
            "decision": self.decision.decision,
            "factor_type": self.decision.factor_type,
            "composite_score": self.scores.composite,
            "rankic_mean": self.is_stats.get("ic", {}).get("rankic_mean"),
            "oos_rankic": self.oos_stats.get("ic", {}).get("rankic_mean"),
            "incremental_ic_t": self.is_stats.get("incremental_ic", {}).get("t_stat"),
        }


# ============================================================
# 统计提取辅助函数
# ============================================================

def _safe_float(val, default: float = 0.0) -> float:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """在 DataFrame 列名中找到第一个匹配的列。"""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _extract_ic_stats(output: dict, node_key: str) -> dict:
    """从 IC 节点 output 提取标准化统计。"""
    node = output.get(node_key, {})
    stats_df = node.get("统计数据")
    if stats_df is None or stats_df.empty:
        return {}
    row = stats_df.iloc[0]
    ic_mean_col = _find_col(stats_df, ["平均值", "IC均值", "IC_mean", "Mean"])
    icir_col = _find_col(stats_df, ["IC_IR", "ICIR", "ir"])
    t_col = _find_col(stats_df, ["t统计量", "t_stat", "t"])
    wr_col = _find_col(stats_df, ["胜率", "win_rate", "WinRate"])

    ic_df = node.get("IC")
    # 取第一列作为 IC 时间序列（单因子评测时只有一列）
    ic_series = ic_df.iloc[:, 0] if ic_df is not None and not ic_df.empty else None

    return {
        "rankic_mean": _safe_float(row.get(ic_mean_col, 0) if ic_mean_col else 0),
        "icir": _safe_float(row.get(icir_col, 0) if icir_col else 0),
        "t_stat": _safe_float(row.get(t_col, 0) if t_col else 0),
        "win_rate": _safe_float(row.get(wr_col, 0.5) if wr_col else 0.5),
        "ic_series": ic_series,
    }


def _extract_portfolio_stats(output: dict, node_key: str) -> dict:
    """从 MultiPortfolio 节点 output 提取标准化统计。"""
    node = output.get(node_key, {})
    stats_df = node.get("统计数据")
    if stats_df is None or stats_df.empty:
        return {}

    ret_col = _find_col(stats_df, ["年化收益率", "年化收益", "AnnualReturn"])
    sharpe_col = _find_col(stats_df, ["Sharpe比率", "Sharpe", "sharpe"])
    mdd_col = _find_col(stats_df, ["最大回撤率", "最大回撤", "MaxDrawdown", "mdd"])
    vol_col = _find_col(stats_df, ["波动率", "Volatility", "vol"])
    alpha_col = _find_col(stats_df, ["CAPM Alpha", "Alpha", "alpha"])

    # 取第一组（P0）的统计数据作为代表
    first_idx = stats_df.index[0]
    row = stats_df.loc[first_idx]

    result = {
        "annual_return": _safe_float(row.get(ret_col, 0) if ret_col else 0),
        "sharpe": _safe_float(row.get(sharpe_col, 0) if sharpe_col else 0),
        "max_drawdown": _safe_float(row.get(mdd_col, 0) if mdd_col else 0),
        "volatility": _safe_float(row.get(vol_col, 0) if vol_col else 0),
        "stats_df": stats_df,
        "nv": node.get("净值"),
        "excess_nv": node.get("超额净值"),
    }

    # 提取 L/S 组合收益（index 中查找 "P0-P4" 或类似命名）
    ls_candidates = [idx for idx in stats_df.index if "-" in str(idx) and "P" in str(idx)]
    if not ls_candidates:
        # 兜底：取最后一行
        ls_candidates = [stats_df.index[-1]]
    ls_idx = ls_candidates[0]
    ls_row = stats_df.loc[ls_idx]
    result["long_short_return"] = _safe_float(ls_row.get(ret_col, 0) if ret_col else 0)
    result["long_short_sharpe"] = _safe_float(ls_row.get(sharpe_col, 0) if sharpe_col else 0)

    # 提取 alpha_stats（用于决策中的 Alpha t 检验）
    if alpha_col:
        # 各组的 Alpha 值
        alphas = stats_df[alpha_col].dropna().abs()
        if not alphas.empty:
            result["max_alpha"] = float(alphas.max())

    return result


def _extract_turnover_stats(output: dict, node_key: str) -> dict:
    """从 FactorTurnover 节点 output 提取标准化统计。"""
    node = output.get(node_key, {})
    stats_df = node.get("统计数据")
    if stats_df is None or stats_df.empty:
        return {}

    row = stats_df.iloc[0]
    mean_col = _find_col(stats_df, ["平均值", "Mean", "mean"])
    return {
        "avg_turnover": 1.0 - _safe_float(row.get(mean_col, 0.5) if mean_col else 0.5),
        "stats_df": stats_df,
    }


def _extract_incremental_ic_stats(output: dict, node_key: str) -> dict:
    """从 IncrementalICNode output 提取标准化统计。"""
    node = output.get(node_key, {})
    stats_df = node.get("统计数据")
    if stats_df is None or stats_df.empty:
        return {}

    row = stats_df.iloc[0]
    mean_col = _find_col(stats_df, ["增量IC均值", "IC均值", "Mean"])
    t_col = _find_col(stats_df, ["增量IC t统计量", "t统计量", "t_stat"])
    corr_col = _find_col(stats_df, ["最大相关性均值", "最大相关性", "MaxCorrelation"])
    ir_col = _find_col(stats_df, ["IC_IR", "ICIR"])

    return {
        "mean_ic": _safe_float(row.get(mean_col, 0) if mean_col else 0),
        "t_stat": _safe_float(row.get(t_col, 0) if t_col else 0),
        "max_correlation": _safe_float(row.get(corr_col, 0) if corr_col else 0),
        "icir": _safe_float(row.get(ir_col, 0) if ir_col else 0),
    }


# ============================================================
# FactorEvaluator
# ============================================================

class FactorEvaluator:
    """因子评测器 — 构建并执行 QuantStudio 评测 DAG。

    职责：
    1. 构建 QuantStudio 计算图（IC + IC衰减 + 分位数组合 + 换手率 + 增量IC + ...）
    2. 驱动 Engine 执行（IS + OOS 两段）
    3. 收集结果，调用 scoring 和 decision
    4. 生成报告
    5. 写入 MiningLogDB
    """

    def __init__(self, config: EvalConfig = None):
        self.config = config or EvalConfig()

    def _create_cache(self, dt_ruler, cache_dir: str | None = None):
        """创建 FeatherFactorCache 实例。

        Args:
            dt_ruler: 交易日序列
            cache_dir: 缓存目录，None 表示使用系统临时目录

        Returns:
            FeatherFactorCache 实例
        """
        from QuantStudio.Factor.FactorCache import FeatherFactorCache
        import tempfile

        if cache_dir is None:
            cache_dir = str(Path(tempfile.mkdtemp(prefix="qs_eval_cache_")))

        cache = FeatherFactorCache(args={
            "DTRuler": dt_ruler,
            "PIDs": ["0"],
            "CacheDir": cache_dir,
            "StartMode": self.config.cache_start_mode,
        })
        # 启动 cache（不使用 with 语句，由调用方管理生命周期）
        cache.start()
        __QS_Logger__.info("Cache 已创建: dir=%s, mode=%s", cache_dir, self.config.cache_start_mode)
        return cache

    # ── 公开接口 ──────────────────────────────────────────

    def evaluate(
        self,
        factor: Any,
        price: Any,
        descriptor_ids: List[str],
        dt_ruler: List[dt.datetime],
        balance_dts: List[dt.datetime],
        mask: Any = None,
        industry: Any = None,
        market_cap: Any = None,
        base_factors: Optional[List[Any]] = None,
        factor_name: str = "",
        category: str = "",
        qsid: str = "",
        cache_dir: Optional[str] = None,
        cache: Any = None,
    ) -> EvalReport:
        """执行完整评测流程。

        Parameters
        ----------
        factor : Factor
            候选因子对象
        price : Factor
            价格/净值因子
        descriptor_ids : List[str]
            截面 ID 序列（股票列表），必传
        dt_ruler : List[datetime]
            全量日期序列，用于 Cache 初始化，必传
        balance_dts : List[datetime]
            再平衡时点序列，用于分位数组合，必传
        mask : Factor, optional
            筛选条件因子（值为 1 表示纳入）
        industry : Factor, optional
            行业因子（用于 IC 行业调整和分组内分组）
        market_cap : Factor, optional
            市值因子（用于规模分层 Alpha 检验）
        base_factors : List[Factor], optional
            基准因子池（用于组合增量 IC 检验）
        factor_name : str
            因子名称
        category : str
            因子类别
        qsid : str
            因子 QSID
        cache_dir : str, optional
            Cache 目录，默认使用系统临时目录（仅在 cache 为 None 时使用）
        cache : FeatherFactorCache, optional
            外部传入的 Cache 实例（由调用方管理生命周期）。
            若为 None 且 config.cache_enabled=True，内部创建临时 Cache。

        Returns
        -------
        EvalReport
            完整评测报告
        """
        config = self.config

        # 解析时间区间
        is_start, is_end = _parse_dt_range(config.in_sample_start, config.in_sample_end)
        oos_start, oos_end = _parse_dt_range(config.oos_start, config.oos_end)

        __QS_Logger__.info(f"开始评测因子: {factor_name or 'unnamed'}")
        __QS_Logger__.info(f"  样本内: {is_start.date()} ~ {is_end.date()}")
        __QS_Logger__.info(f"  样本外: {oos_start.date()} ~ {oos_end.date()}")

        # 准备 Cache
        own_cache = None
        if cache is None and config.cache_enabled:
            own_cache = self._create_cache(dt_ruler, cache_dir or config.cache_dir)
            cache = own_cache

        try:
            # 样本内评测
            __QS_Logger__.info("  执行样本内评测...")
            is_output = self._run_single_period(
                factor, price, descriptor_ids, dt_ruler, balance_dts,
                mask, industry, market_cap, base_factors,
                dt_range=(is_start, is_end),
                cache=cache,
            )
            is_stats = self._extract_all_stats(is_output)

            # 样本外评测
            __QS_Logger__.info("  执行样本外评测...")
            oos_output = self._run_single_period(
                factor, price, descriptor_ids, dt_ruler, balance_dts,
                mask, industry, market_cap, base_factors,
                dt_range=(oos_start, oos_end),
                cache=cache,
            )
            oos_stats = self._extract_all_stats(oos_output)
        finally:
            # 仅关闭内部创建的 Cache，外部传入的不关闭
            if own_cache is not None:
                try:
                    own_cache.end()
                except Exception:
                    pass

        # 五维度评分
        __QS_Logger__.info("  计算五维度评分...")
        scores = calc_scores(
            ic_stats=is_stats.get("ic", {}),
            oos_ic_stats=oos_stats.get("ic", {}),
            portfolio_stats=is_stats.get("portfolio", {}),
            incremental_ic_stats=is_stats.get("incremental_ic", {}),
            turnover_stats=is_stats.get("turnover", {}),
            ic_series=is_stats.get("ic", {}).get("ic_series"),
        )

        # 入库决策
        __QS_Logger__.info("  执行入库决策...")
        # alpha_stats: 从 portfolio 统计中提取 CAPM Alpha t 统计量
        portfolio_stats = is_stats.get("portfolio", {})
        alpha_stats = {}
        if "max_alpha" in portfolio_stats:
            # 使用 CAPM Alpha 的 t 统计量近似（如果有）
            alpha_stats["capm_t"] = portfolio_stats.get("max_alpha", 0)

        decision = make_decision(
            ic_stats=is_stats.get("ic", {}),
            oos_ic_stats=oos_stats.get("ic", {}),
            incremental_ic_stats=is_stats.get("incremental_ic", {}),
            scores=scores,
            alpha_stats=alpha_stats,
            config=config,
        )

        __QS_Logger__.info(f"  决策结果: {decision.decision} ({decision.reason})")

        # 生成报告
        report_html = self._generate_report(is_output, oos_output, scores, decision, factor_name)

        report = EvalReport(
            factor_name=factor_name,
            qsid=qsid,
            category=category,
            scores=scores,
            decision=decision,
            report_html=report_html,
            is_output=is_output,
            oos_output=oos_output,
            is_stats=is_stats,
            oos_stats=oos_stats,
        )

        # 写入挖掘日志库
        if config.save_to_mining_log:
            self._save_to_mining_log(report)

        return report

    # ── DAG 构建 ──────────────────────────────────────────

    def _build_eval_nodes(
        self,
        factor: Any,
        price: Any,
        descriptor_ids: List[str],
        balance_dts: List[dt.datetime],
        mask: Any,
        industry: Any,
        market_cap: Any,
        base_factors: Optional[List[Any]],
    ) -> List[Any]:
        """构建评测节点列表。"""
        from QuantStudio.BackTest.SectionFactor.IC import CalcIC, IC, ICDecay
        from QuantStudio.BackTest.SectionFactor.QuantilePortfolio import makeQuantilePortfolio, MultiPortfolio
        from QuantStudio.BackTest.Strategy.AllocationStrategy import CalcPortfolioNV
        from QuantStudio.BackTest.SectionFactor.Correlation import CalcFactorTurnover, FactorTurnover

        from QSExt.LLMFactor.evaluation.operators.incremental_ic import CalcIncrementalIC
        from QSExt.LLMFactor.evaluation.nodes.incremental_ic_node import IncrementalICNode
        from QSExt.LLMFactor.evaluation.operators.size_stratified import CalcSizeStratifiedAlpha
        from QSExt.LLMFactor.evaluation.nodes.size_stratified_node import SizeStratifiedAlphaNode

        config = self.config
        node_list = []
        factor_args = {"CalcDTRuler": balance_dts}

        # 1. Rank IC
        ic_factor = CalcIC(
            descriptor_ids=descriptor_ids,
            lookback=config.ic_lookback,
            period_lookback=config.period_lookback,
            corr_method=config.corr_method,
        )(factor, price=price, mask=mask, cat_data=industry, factor_args=factor_args)
        node_list.append(IC(ic_factor, args={"GenReport": True}))

        # 2. IC 衰减
        ic_decay_factors = [
            CalcIC(
                descriptor_ids=descriptor_ids,
                lookback=config.ic_lookback * p,
                period_lookback=p,
                corr_method=config.corr_method,
            )(factor, price=price, mask=mask, cat_data=industry, factor_args=factor_args)
            for p in config.ic_decay_periods
        ]
        node_list.append(ICDecay(ic_list=ic_decay_factors, args={"GenReport": True}))

        # 3. 分位数组合
        quantile_portfolios = makeQuantilePortfolio(
            factor, mask=mask, cat_data=industry, weight=None,
            descriptor_ids=descriptor_ids, rebalance_dts=balance_dts,
            group_num=config.group_num,
        )
        calc_nv = CalcPortfolioNV(descriptor_ids=descriptor_ids, start_dt=None)
        nv_factor = calc_nv(*quantile_portfolios, price=price, init_nv=1)
        node_list.append(MultiPortfolio(
            nv=nv_factor,
            portfolio_list=quantile_portfolios,
            args={
                "RebalanceDTs": balance_dts,
                "GenReport": True,
                "LSPairs": [("P0", f"P{config.group_num - 1}")],
            },
        ))

        # 4. 因子换手率
        turnover_factor = CalcFactorTurnover(
            descriptor_ids=descriptor_ids,
            lookback=config.ic_lookback,
            period_lookback=config.period_lookback,
        )(factor, mask=mask)
        node_list.append(FactorTurnover(turnover_factor, args={"GenReport": True}))

        # 5. 组合增量 IC（可选）
        if base_factors:
            inc_ic_factor = CalcIncrementalIC(
                descriptor_ids=descriptor_ids,
                lookback=config.ic_lookback,
                period_lookback=config.period_lookback,
                corr_method=config.corr_method,
            )(factor, price=price, base_factors=base_factors, mask=mask, cat_data=industry)
            node_list.append(IncrementalICNode(ic=inc_ic_factor, args={"GenReport": True}))

        # 6. 规模分层 Alpha（可选）
        if market_cap is not None:
            size_alpha_factor = CalcSizeStratifiedAlpha(
                descriptor_ids=descriptor_ids,
                group_num=config.group_num,
            )(factor, market_cap=market_cap, price=price, mask=mask)
            node_list.append(SizeStratifiedAlphaNode(alpha=size_alpha_factor, args={"GenReport": True}))

        return node_list

    # ── 单段执行 ──────────────────────────────────────────

    def _run_single_period(
        self,
        factor, price, descriptor_ids, dt_ruler, balance_dts,
        mask, industry, market_cap, base_factors,
        dt_range: tuple[dt.datetime, dt.datetime],
        cache: Any = None,
    ) -> dict:
        """执行单段时间区间的评测 DAG。

        Args:
            cache: 外部传入的 FeatherFactorCache 实例。
                   若为 None，内部创建临时 Cache（StartMode="new"）。
        """
        from QuantStudio.Core.CalcEngine import Engine
        from QuantStudio.Core.Node import DTLocalContext, DTInitData
        from QuantStudio.Factor.Factor import FactorContext
        from QuantStudio.BackTest.BackTestModel import BTReport

        start_dt, end_dt = dt_range

        # 筛选测试时点
        test_dts = [d for d in dt_ruler if start_dt <= d <= end_dt]
        if not test_dts:
            raise ValueError(f"时间区间 {start_dt.date()}~{end_dt.date()} 内无有效交易日")

        # 构建节点
        node_list = self._build_eval_nodes(
            factor, price, descriptor_ids, balance_dts,
            mask, industry, market_cap, base_factors,
        )
        report_node = BTReport(bt_node_list=node_list)

        # 使用外部 cache 或创建临时 cache
        if cache is not None:
            # 直接使用外部 cache，不管理其生命周期
            with FactorContext(
                PID="0", PIDList=["0"],
                DTRuler=dt_ruler,
                SectionIDs=descriptor_ids,
                DataCache=cache,
            ) as context:
                with Engine() as engine:
                    output_tuple = engine.run(
                        [report_node], context,
                        fwd_data_list=[DTLocalContext(DTs=test_dts)],
                        init_data_list=[DTInitData(DTRange=(start_dt, end_dt))],
                    )
            return output_tuple[0]
        else:
            # 内部创建临时 cache
            from QuantStudio.Factor.FactorCache import FeatherFactorCache
            import tempfile
            cache_dir = str(Path(tempfile.mkdtemp(prefix="qs_eval_")))

            with FeatherFactorCache(args={
                "DTRuler": dt_ruler,
                "PIDs": ["0"],
                "CacheDir": cache_dir,
                "StartMode": "new",
            }) as tmp_cache:
                with FactorContext(
                    PID="0", PIDList=["0"],
                    DTRuler=dt_ruler,
                    SectionIDs=descriptor_ids,
                    DataCache=tmp_cache,
                ) as context:
                    with Engine() as engine:
                        output_tuple = engine.run(
                            [report_node], context,
                            fwd_data_list=[DTLocalContext(DTs=test_dts)],
                            init_data_list=[DTInitData(DTRange=(start_dt, end_dt))],
                        )
                return output_tuple[0]

    # ── 统计提取 ──────────────────────────────────────────

    def _extract_all_stats(self, output: dict) -> dict:
        """从 DAG output 中提取所有模块的标准化统计。"""
        stats = {}

        # IC 统计（节点 key 格式: "0-IC"）
        ic_key = _find_output_key(output, "IC")
        if ic_key:
            stats["ic"] = _extract_ic_stats(output, ic_key)

        # 分位数组合统计（key 格式: "1-多组合对比" 或 "2-xxx-分位数组合"）
        portfolio_key = _find_output_key(output, "多组合对比")
        if not portfolio_key:
            portfolio_key = _find_output_key(output, "分位数组合")
        if portfolio_key:
            stats["portfolio"] = _extract_portfolio_stats(output, portfolio_key)

        # 换手率统计
        turnover_key = _find_output_key(output, "因子换手率")
        if turnover_key:
            stats["turnover"] = _extract_turnover_stats(output, turnover_key)

        # 增量 IC 统计
        inc_key = _find_output_key(output, "增量 IC 检验")
        if inc_key:
            stats["incremental_ic"] = _extract_incremental_ic_stats(output, inc_key)

        # 规模分层 Alpha 统计
        size_key = _find_output_key(output, "规模分层 Alpha")
        if size_key:
            stats["size_stratified"] = _extract_size_stratified_stats(output, size_key)

        return stats

    # ── 报告生成 ──────────────────────────────────────────

    def _generate_report(
        self, is_output, oos_output, scores, decision, factor_name,
    ) -> str:
        """生成评测报告（调用 QSExt ReportGenerator）。"""
        from QSExt.LLMFactor.evaluation.report import generate_eval_report
        return generate_eval_report(
            is_output=is_output,
            oos_output=oos_output,
            scores=scores,
            decision=decision,
            factor_name=factor_name,
            config=self.config,
            fmt="html",
        )

    # ── 挖掘日志 ──────────────────────────────────────────

    def _save_to_mining_log(self, report: EvalReport):
        """将评测结果写入 MiningLogDB。"""
        try:
            from QSExt.LLMFactor.mining_log.db import MiningLogDB
            from QSExt.LLMFactor.mining_log.repository import MiningLogRepository
            from QSExt.LLMFactor.mining_log.models import MiningRun

            import datetime as _dt

            db = MiningLogDB()
            db.init_tables()
            repo = MiningLogRepository(db)

            run = MiningRun(id=f"EVAL_{report.factor_name}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}")
            run.metadata["factor_name"] = report.factor_name
            run.metadata["category"] = report.category
            run.metadata["qsid"] = report.qsid
            run.metadata["status"] = "completed"

            ic = report.is_stats.get("ic", {})
            run.metadata["rankic_mean"] = ic.get("rankic_mean", 0)
            run.metadata["rankicir"] = ic.get("icir", 0)
            run.metadata["oos_rankic"] = report.oos_stats.get("ic", {}).get("rankic_mean", 0)

            inc = report.is_stats.get("incremental_ic", {})
            run.metadata["incremental_ic"] = inc.get("mean_ic", 0)
            run.metadata["incremental_ic_t"] = inc.get("t_stat", 0)
            run.metadata["max_correlation"] = inc.get("max_correlation", 0)

            run.metadata["composite_score"] = report.scores.composite
            run.metadata["decision"] = report.decision.decision
            run.metadata["decision_reason"] = report.decision.reason
            run.metadata["factor_type"] = report.decision.factor_type

            run.content = f"因子评测: {report.factor_name}, 决策: {report.decision.decision}"
            run.tags = [report.category, report.decision.decision]

            repo.insert_run(run)
            __QS_Logger__.info(f"  评测结果已写入 MiningLogDB: {run.id}")
        except Exception as e:
            __QS_Logger__.warning(f"  写入 MiningLogDB 失败: {e}")


# ============================================================
# 辅助函数
# ============================================================

def _parse_dt_range(start_str: str, end_str: str) -> tuple[dt.datetime, dt.datetime]:
    """解析 'YYYY-MM' 格式的日期范围。"""
    parts_start = start_str.split("-")
    parts_end = end_str.split("-")
    start = dt.datetime(int(parts_start[0]), int(parts_start[1]), 1)
    end = dt.datetime(int(parts_end[0]), int(parts_end[1]), 28)  # 月末近似
    return start, end


def _find_output_key(output: dict, name_fragment: str) -> Optional[str]:
    """在 output dict 中找到包含指定名称片段的 key。"""
    for key in output:
        if isinstance(key, str) and name_fragment in key:
            return key
    return None



def _extract_size_stratified_stats(output: dict, node_key: str) -> dict:
    """从 SizeStratifiedAlphaNode output 提取标准化统计。"""
    node = output.get(node_key, {})
    stats_df = node.get("统计数据")
    if stats_df is None or stats_df.empty:
        return {}

    # 提取各组的 Alpha 和 t 统计量
    result = {"groups": []}
    for idx in stats_df.index:
        row = stats_df.loc[idx]
        alpha_cols = [c for c in stats_df.columns if "Alpha" in c]
        t_cols = [c for c in stats_df.columns if "t统计量" in c or "t_stat" in c]

        group_info = {"name": str(idx)}
        for ac in alpha_cols:
            group_info[ac] = _safe_float(row.get(ac, 0))
        for tc in t_cols:
            group_info[tc] = _safe_float(row.get(tc, 0))
        result["groups"].append(group_info)

    # 最大 t 统计量（用于 alpha_stats）
    all_t = []
    for c in stats_df.columns:
        if "t统计量" in c or "t_stat" in c:
            all_t.extend(stats_df[c].dropna().abs().tolist())
    if all_t:
        result["max_t"] = max(all_t)

    return result
