# -*- coding: utf-8 -*-
"""单因子测试报告场景

``SingleFactorReport`` 是 ``ReportGenerator`` 的子类，定义单因子回测报告所需的
上游节点（IC、IC 衰减、分位数组合、换手率）和数据到报告的映射。

使用方式::

    from QSExt.ReportGenerator.scenarios.single_factor import SingleFactorReport

    # 创建节点
    nodes = SingleFactorReport.create_nodes(
        factors=[momentum_factor],
        price=price_factor,
        mask=mask_factor,
        cat_data=industry_factor,
    )

    # 嵌入计算图
    report_node = SingleFactorReport(
        nodes,
        args={"OutputFormats": ["html"], "ReportConfig": "config.yaml"},
    )

    result = Engine().run([report_node], context)[0]
"""

import os
import datetime as dt
from typing import Any, List, Optional

import pandas as pd

from pydantic import Field

from QSExt.ReportGenerator import ReportGenerator
from QSExt.ReportGenerator.core import DataContext, split_output_for_factor
from QSExt.ReportGenerator.layout import LayoutRenderer
from QSExt.ReportGenerator.themes.base import Theme
from QuantStudio.Core.Node import Node
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Tools.DateTimeFun import transformDateTime


class SingleFactorReport(ReportGenerator):
    """单因子测试报告生成节点。

    依赖节点（按 create_nodes 返回顺序）：
    0. IC 分析
    1. IC 衰减分析
    2. 分位数组合（每个因子一个）
    3. 因子换手率
    """

    class __QS_ArgClass__(ReportGenerator.__QS_ArgClass__):
        Name: str = Field(default="单因子测试报告", frozen=True, title="名称")
        ReportConfig: str = Field(default="", title="报告配置文件", description="YAML 报告配置文件路径，空字符串使用内置默认配置")

    @classmethod
    def _load_config(cls, config_path: Optional[str] = None) -> dict:
        """加载 YAML 配置文件。

        Args:
            config_path: 配置文件路径，空字符串或 None 使用内置默认配置

        Returns:
            完整配置 dict
        """
        if not config_path:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "config.yaml"
            )
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @classmethod
    def create_nodes(cls, factors, /, price=None, mask=None,
                     cat_data=None, weight=None,
                     descriptor_ids=None,
                     dtruler: Optional[List[dt.datetime]] = None,
                     config: Optional[str] = None,
                     **kwargs) -> List[Node]:
        """创建单因子测试场景所需的上游节点。

        Args:
            factors: 被测因子列表
            price: 价格因子（可选）
            mask: 掩码因子（可选）
            cat_data: 分类因子/行业（可选）
            weight: 权重因子（可选）
            descriptor_ids: 描述子 ID 列表
            dtruler: 时点标尺列表（可选，用于 calc_freq 变换）
            config: YAML 配置文件路径，空字符串或 None 使用内置默认配置

        Returns:
            上游节点列表，顺序：IC → IC 衰减 → 分位数组合(×N) → 换手率
        """
        full_config = cls._load_config(config)
        cfg = full_config.get("modules", {})
        nodes = []

        # 处理 calc_freq：变换 DTRuler 生成 CalcDTRuler
        def get_calc_dtruler(module_cfg):
            """根据模块配置的 calc_freq 变换 DTRuler"""
            if not dtruler:
                return None
            calc_freq = module_cfg.get("calc_freq", "") if isinstance(module_cfg, dict) else ""
            if calc_freq:
                return transformDateTime(dtruler, freq=calc_freq)
            return None

        # 1. IC 分析
        if cfg.get("ic", True):
            from QuantStudio.BackTest.SectionFactor.IC import CalcIC, IC
            ic_cfg = cfg["ic"] if isinstance(cfg.get("ic"), dict) else {}
            # 使用 rename 创建带 CalcDTRuler 的因子
            calc_dtruler = get_calc_dtruler(ic_cfg)
            ic_factors = factors
            if calc_dtruler:
                ic_factors = [rename(f, f.Name, {"CalcDTRuler": calc_dtruler}) for f in factors]
            factor_ic = CalcIC(
                descriptor_ids=descriptor_ids,
                lookback=ic_cfg.get("lookback", 31),
                period_lookback=ic_cfg.get("period_lookback", 1),
                corr_method=ic_cfg.get("corr_method", "spearman"),
            )(*ic_factors, price=price, mask=mask,
              cat_data=cat_data, weight=weight)
            nodes.append(IC(factor_ic, args={
                "RollingAvgPeriod": ic_cfg.get("rolling_avg_period", 12),

                "Name": "Rank IC 分析"
            }))

        # 2. IC 衰减
        if cfg.get("ic_decay", True):
            from QuantStudio.BackTest.SectionFactor.IC import CalcIC, ICDecay
            decay_cfg = cfg["ic_decay"] if isinstance(cfg.get("ic_decay"), dict) else {}
            # 使用 rename 创建带 CalcDTRuler 的因子
            calc_dtruler = get_calc_dtruler(decay_cfg)
            decay_factors = factors
            if calc_dtruler:
                decay_factors = [rename(f, f.Name, {"CalcDTRuler": calc_dtruler}) for f in factors]
            periods = decay_cfg.get("periods", [1, 2, 3, 6, 12])
            ic_list = [
                CalcIC(
                    descriptor_ids=descriptor_ids,
                    lookback=31 * p,
                    period_lookback=p,
                )(*decay_factors, price=price, mask=mask, cat_data=cat_data)
                for p in periods
            ]
            nodes.append(ICDecay(ic_list, args={

                "Name": "IC 衰减分析"
            }))

        # 3. 分位数组合（每个因子各自建分组）
        if cfg.get("quantile_portfolio", True):
            from QuantStudio.BackTest.SectionFactor.QuantilePortfolio import (
                makeQuantilePortfolio, MultiPortfolio
            )
            from QuantStudio.BackTest.Strategy.AllocationStrategy import (
                CalcPortfolioNV
            )
            pf_cfg = cfg["quantile_portfolio"] if isinstance(cfg.get("quantile_portfolio"), dict) else {}
            # calc_freq 配置的 calc_dtruler 作为 rebalance_dts
            rebalance_dts = get_calc_dtruler(pf_cfg)
            for f in factors:
                portfolios = makeQuantilePortfolio(
                    f, mask=mask, cat_data=cat_data, weight=weight,
                    descriptor_ids=descriptor_ids,
                    rebalance_dts=rebalance_dts,
                    ascending=False,  # 升降序已在外部处理（_load_factors 中取负值）
                    group_num=pf_cfg.get("group_num", 5)
                )
                calc_nv = CalcPortfolioNV(descriptor_ids=descriptor_ids)
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

                        "Name": f"分位数组合({f.Name})"
                    }
                ))

        # 4. 因子换手率
        if cfg.get("factor_turnover", True):
            from QuantStudio.BackTest.SectionFactor.Correlation import (
                CalcFactorTurnover, FactorTurnover
            )
            to_cfg = cfg["factor_turnover"] if isinstance(cfg.get("factor_turnover"), dict) else {}
            # 使用 rename 创建带 CalcDTRuler 的因子
            calc_dtruler = get_calc_dtruler(to_cfg)
            turnover_factors = factors
            if calc_dtruler:
                turnover_factors = [rename(f, f.Name, {"CalcDTRuler": calc_dtruler}) for f in factors]
            turnover_factor = CalcFactorTurnover(
                descriptor_ids=descriptor_ids,
                lookback=to_cfg.get("lookback", 31),
                period_lookback=to_cfg.get("period_lookback", 1),
            )(*turnover_factors, mask=mask)
            nodes.append(FactorTurnover(turnover_factor, args={

                "Name": "因子换手率"
            }))

        return nodes

    # ---- 依赖节点的索引常量（与 create_nodes 返回顺序一致） ----

    _IDX_IC = 0
    _IDX_IC_DECAY = 1
    _IDX_QUANTILE_START = 2  # 分位数组合从索引 2 开始

    def __init__(self, deps: list = [], args: dict = {}, config_file: Optional[str] = None, **kwargs):
        # 在 super().__init__ 之前提取，避免传给父类
        factor_names = kwargs.pop("factor_names", [])
        self._factor_names = list(factor_names) if factor_names else []

        super().__init__(deps=deps, args=args, config_file=config_file, **kwargs)

        # 加载 YAML 报告配置
        full_config = self._load_config(self._QSArgs.ReportConfig)
        self._report_config = full_config.get("report", {})
        self._modules_config = full_config.get("modules", {})

        # 从配置中提取 OutputFormats（仅当用户未显式指定时）
        if "OutputFormats" not in (args or {}):
            output_config = full_config.get("output", {})
            self._QSArgs.OutputFormats = output_config.get("formats", ["html"])

    def generate_report(self, output_list: List[Any]) -> dict:
        """将上游节点产出组织为 output dict 并渲染报告。

        output_list 与 create_nodes 返回的节点一一对应：
        [IC输出, IC衰减输出, 分位数组合(f1), 分位数组合(f2), ..., 换手率输出]

        Returns:
            dict: 包含 ``ReportKey``（合并 HTML）和 ``"reports"``（按因子拆分的报告）
        """
        # 按约定 key 组织 output dict（与 config.yaml 中 source 引用一致）
        output = {}

        # IC 分析
        if len(output_list) > self._IDX_IC:
            output["0-Rank IC 分析"] = output_list[self._IDX_IC]

        # IC 衰减：展平 {factor: {sub: df}} → {sub: df}
        if len(output_list) > self._IDX_IC_DECAY:
            decay_raw = output_list[self._IDX_IC_DECAY]
            decay_flat = {}
            if isinstance(decay_raw, dict):
                for fname, inner in decay_raw.items():
                    if isinstance(inner, dict):
                        inner_copy = dict(inner)
                        if "IC" in inner_copy:
                            inner_copy["IC衰减"] = inner_copy.pop("IC")
                        decay_flat.update(inner_copy)
                    else:
                        decay_flat[fname] = inner
            output["1-IC 衰减分析"] = decay_flat

        # 分位数组合：合并多因子到一个 key
        n_factors = len(self._factor_names) if self._factor_names else 1
        if len(output_list) > self._IDX_QUANTILE_START:
            pf_outputs = output_list[self._IDX_QUANTILE_START:self._IDX_QUANTILE_START + n_factors]
            if n_factors == 1:
                raw = pf_outputs[0] if pf_outputs else {}
                output["2-分位数组合"] = self._normalize_quantile_keys(raw)
            else:
                merged = {}
                for i, pf_out in enumerate(pf_outputs):
                    fname = self._factor_names[i] if i < len(self._factor_names) else f"factor_{i}"
                    if isinstance(pf_out, dict):
                        for k, v in pf_out.items():
                            if isinstance(v, pd.DataFrame) and k not in merged:
                                merged[k] = v.rename(
                                    columns=lambda c, prefix=f"{fname}::": (
                                        f"{prefix}{c}" if not str(c).startswith(prefix) else c
                                    )
                                )
                            elif isinstance(v, pd.DataFrame):
                                merged[k] = pd.concat([merged[k], v.rename(
                                    columns=lambda c, prefix=f"{fname}::": (
                                        f"{prefix}{c}" if not str(c).startswith(prefix) else c
                                    )
                                )], axis=1)
                            elif isinstance(v, dict):
                                merged.setdefault(k, {}).update(v)
                output["2-分位数组合"] = self._normalize_quantile_keys(merged)

        # 换手率
        turnover_idx = self._IDX_QUANTILE_START + n_factors
        if len(output_list) > turnover_idx:
            raw = output_list[turnover_idx]
            normalized = {}
            if isinstance(raw, dict):
                for k, v in raw.items():
                    normalized["换手率" if "换手率" in k else k] = v
            output["3-因子换手率"] = normalized

        # 渲染
        report_config = self._report_config
        output_formats = self._QSArgs.OutputFormats
        theme = Theme()
        layout_renderer = LayoutRenderer()

        reports = {}
        factor_names = self._factor_names or self._infer_factor_names(output_list)

        for fname in factor_names:
            single = split_output_for_factor(output, fname)
            ctx = DataContext(single, [fname], report_config)
            self._inject_factor_info(ctx, [fname])
            reports[fname] = {}
            for fmt in output_formats:
                reports[fname][fmt] = layout_renderer.render(
                    report_config, ctx, theme, fmt
                )

        # 合并所有因子报告为单个 HTML，写入 ReportKey 供 BTReport 聚合
        report_key = self._QSArgs.ReportKey
        sep = '<hr style="border:1px solid #e0e0e0;margin:2em 0">'
        html_parts = []
        for fname, fmt_dict in reports.items():
            for fmt, content in fmt_dict.items():
                html_parts.append(content)
        combined_html = sep.join(html_parts)

        return {report_key: combined_html, "reports": reports}

    # ---- 内部工具方法 ----

    @staticmethod
    def _infer_factor_names(output_list: list) -> list:
        """从 output_list 中推断因子名列表（兜底）。"""
        for item in output_list:
            if isinstance(item, dict):
                for v in item.values():
                    if isinstance(v, pd.DataFrame) and not v.empty:
                        return list(v.columns[:1])
        return ["未知因子"]

    @staticmethod
    def _inject_factor_info(ctx: DataContext, factor_names: list) -> None:
        """注入因子元信息到 DataContext 的 meta 通道。"""
        dt_start = ctx.get("meta", "dt_start") or "未指定"
        dt_end = ctx.get("meta", "dt_end") or "未指定"
        ctx.set("meta", "factor_info", {
            "name": factor_names[0] if len(factor_names) == 1 else ", ".join(factor_names),
            "count": len(factor_names),
            "dt_start": dt_start,
            "dt_end": dt_end,
        })

    @staticmethod
    def _normalize_quantile_keys(module_dict: dict) -> dict:
        """规范化分位数组合模块的子 key 名。"""
        result = {}
        for k, v in module_dict.items():
            if "超额净值" in k:
                result["超额净值"] = v
            elif "净值" in k and "超额" not in k:
                result["净值"] = v
            else:
                result[k] = v
        return result
