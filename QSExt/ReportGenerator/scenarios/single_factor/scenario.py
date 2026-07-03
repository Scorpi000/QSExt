# -*- coding: utf-8 -*-
"""单因子全面测试场景 — 回测模块构建

create_modules() 构建回测 DAG（BTNode 列表），负责 QuantStudio 回测编排。
报告渲染由 ReportGeneratorNode 在 DAG 内部完成。
"""

from typing import List, Optional


# ============================================================
# 回测模块构建
# ============================================================

def create_modules(factors, /, price=None, mask=None,
                   cat_data=None, weight=None,
                   descriptor_ids=None, rebalance_dts=None,
                   config: Optional[dict] = None,
                   **kwargs) -> list:
    """构建单因子测试场景的所有 BTNode。

    这是原 Scenario.assemble_modules() 的逻辑，已提取为独立函数，
    方便在不依赖 Scenario 的上下文中复用（如配合 ReportGeneratorNode 使用）。

    Args:
        factors: 被测因子列表
        price: 价格因子（可选）
        mask: 掩码因子（可选）
        cat_data: 分类因子/行业（可选）
        weight: 权重因子（可选）
        descriptor_ids: 描述子 ID 列表
        rebalance_dts: 调仓时点列表
        config: 模块配置 dict（对应 config.yaml 中 modules 段）。None 时所有模块启用

    Returns:
        BTNode 实例列表（GenReport=False）
    """
    if config is None:
        cfg = {}
    else:
        cfg = config

    nodes = []

    # ---- 1. IC 分析 ----
    if cfg.get("ic", True):
        from QuantStudio.BackTest.SectionFactor.IC import CalcIC, IC

        ic_cfg = cfg["ic"] if isinstance(cfg.get("ic"), dict) else {}
        factor_ic = CalcIC(
            descriptor_ids=descriptor_ids,
            lookback=ic_cfg.get("lookback", 31),
            period_lookback=ic_cfg.get("period_lookback", 1),
            corr_method=ic_cfg.get("corr_method", "spearman"),
        )(*factors, price=price, mask=mask,
          cat_data=cat_data, weight=weight)
        nodes.append(IC(factor_ic, args={
            "RollingAvgPeriod": ic_cfg.get("rolling_avg_period", 12),
            "GenReport": False,
            "Name": "Rank IC 分析"
        }))

    # ---- 2. IC 衰减 ----
    if cfg.get("ic_decay", True):
        from QuantStudio.BackTest.SectionFactor.IC import CalcIC, ICDecay

        decay_cfg = cfg["ic_decay"] if isinstance(cfg.get("ic_decay"), dict) else {}
        periods = decay_cfg.get("periods", [1, 2, 3, 6, 12])
        ic_list = [
            CalcIC(
                descriptor_ids=descriptor_ids,
                lookback=31 * p,
                period_lookback=p,
            )(*factors, price=price, mask=mask,
              cat_data=cat_data)
            for p in periods
        ]
        nodes.append(ICDecay(ic_list, args={
            "GenReport": False,
            "Name": "IC 衰减分析"
        }))

    # ---- 3. 分位数组合（每个因子各自建分组）----
    if cfg.get("quantile_portfolio", True):
        from QuantStudio.BackTest.SectionFactor.QuantilePortfolio import (
            makeQuantilePortfolio, MultiPortfolio
        )
        from QuantStudio.BackTest.Strategy.AllocationStrategy import (
            CalcPortfolioNV
        )

        pf_cfg = cfg["quantile_portfolio"] if isinstance(cfg.get("quantile_portfolio"), dict) else {}

        for f in factors:
            portfolios = makeQuantilePortfolio(
                f, mask=mask, cat_data=cat_data, weight=weight,
                descriptor_ids=descriptor_ids,
                rebalance_dts=rebalance_dts,
                ascending=pf_cfg.get("ascending", False),
                group_num=pf_cfg.get("group_num", 5)
            )
            calc_nv = CalcPortfolioNV(
                descriptor_ids=descriptor_ids
            )
            nv_combined = calc_nv(*portfolios, price=price, init_nv=1)
            group_num = pf_cfg.get("group_num", 5)
            raw_pairs = pf_cfg.get("long_short_pairs", [[0, -1]])
            LSPairs = [
                [f"P{i if i >= 0 else group_num + i}" for i in pair]
                for pair in raw_pairs
            ]
            nodes.append(MultiPortfolio(
                nv_combined, portfolio_list=portfolios, args={
                    "RebalanceDTs": rebalance_dts,
                    "LSPairs": LSPairs,
                    "GenReport": False,
                    "Name": f"分位数组合({f.Name})"
                }
            ))

    # ---- 4. 因子换手率 ----
    if cfg.get("factor_turnover", True):
        from QuantStudio.BackTest.SectionFactor.Correlation import (
            CalcFactorTurnover, FactorTurnover
        )

        to_cfg = cfg["factor_turnover"] if isinstance(cfg.get("factor_turnover"), dict) else {}
        turnover_factor = CalcFactorTurnover(
            descriptor_ids=descriptor_ids,
            lookback=to_cfg.get("lookback", 31),
            period_lookback=to_cfg.get("period_lookback", 1),
        )(*factors, mask=mask)
        nodes.append(FactorTurnover(turnover_factor, args={
            "GenReport": False,
            "Name": "因子换手率"
        }))

    return nodes
