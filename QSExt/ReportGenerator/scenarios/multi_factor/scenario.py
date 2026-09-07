# -*- coding: utf-8 -*-
"""多因子对比报告场景

``MultiFactorReport`` 是 ``ReportGenerator`` 的子类，接收多个因子，
通过共用的 IC/分位数组合/换手率回测节点进行横向对比。

使用方式::

    from QSExt.ReportGenerator.scenarios.multi_factor import MultiFactorReport

    # 创建节点
    nodes = MultiFactorReport.create_nodes(
        factors=[factor1, factor2],
        price=price_factor,
        mask=mask_factor,
    )

    # 嵌入计算图
    report_node = MultiFactorReport(
        nodes,
        args={"OutputFormat": "html"},
        factor_names=["动量因子", "反转因子"],
    )

    result = Engine().run([report_node], context)[0]
"""

import datetime as dt
import os
from typing import Any, List, Optional

import pandas as pd

from pydantic import Field

from QSExt.ReportGenerator import ReportGenerator
from QSExt.ReportGenerator.core import DataContext
from QSExt.ReportGenerator.layout import LayoutRenderer
from QSExt.ReportGenerator.themes.base import Theme
from QuantStudio.Core.Node import Node


class MultiFactorReport(ReportGenerator):
    """多因子对比报告生成节点。

    依赖节点（与 SingleFactorReport 相同的顺序）：
    0. IC 分析（多因子共用，输出已是多列 DataFrame）
    1. IC 衰减分析（多因子共用）
    2. 分位数组合（每个因子一个）
    3. 因子换手率（多因子共用，输出已是多列 DataFrame）
    """

    class __QS_ArgClass__(ReportGenerator.__QS_ArgClass__):
        Name: str = Field(default="多因子对比报告", frozen=True, title="名称")
        ReportConfig: str = Field(default="", title="报告配置文件", description="YAML 报告配置文件路径，空字符串使用内置默认配置")

    @classmethod
    def _load_config(cls, config_path: Optional[str] = None) -> dict:
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
        """创建多因子对比场景所需的上游节点。

        委托给 SingleFactorReport.create_nodes，复用完整的节点构建逻辑。

        Args:
            factors: 因子列表
            price: 价格因子
            mask: 掩码因子
            cat_data: 分类因子/行业
            weight: 权重因子
            descriptor_ids: 描述子 ID 列表
            dtruler: 时点标尺列表
            config: YAML 配置文件路径

        Returns:
            上游节点列表：[IC, IC衰减, 分位数组合(×N), 换手率]
        """
        from QSExt.ReportGenerator.scenarios.single_factor.scenario import (
            SingleFactorReport,
        )
        return SingleFactorReport.create_nodes(
            factors, price=price, mask=mask, cat_data=cat_data,
            weight=weight, descriptor_ids=descriptor_ids,
            dtruler=dtruler, config=config, **kwargs,
        )

    # ---- 依赖节点索引（与 SingleFactorReport 一致） ----

    _IDX_IC = 0
    _IDX_IC_DECAY = 1
    _IDX_QUANTILE_START = 2

    def __init__(self, deps: list = [], args: dict = {},
                 config_file: Optional[str] = None, **kwargs):
        factor_names = kwargs.pop("factor_names", [])
        self._factor_names = list(factor_names)

        super().__init__(deps=deps, args=args, config_file=config_file, **kwargs)

        full_config = self._load_config(self._QSArgs.ReportConfig)
        self._report_config = full_config.get("report", {})
        self._modules_config = full_config.get("modules", {})

        if "OutputFormat" not in (args or {}):
            output_config = full_config.get("output", {})
            fmts = output_config.get("formats", ["html"])
            self._QSArgs.OutputFormat = fmts[0] if fmts else "html"

    def generate_report(self, output_list: List[Any]) -> dict:
        """将多个因子的回测产出组织为对比数据并渲染报告。

        output_list 结构与 SingleFactorReport 一致：
        [IC输出, IC衰减输出, 分位数组合(f1), ..., 分位数组合(fN), 换手率输出]

        Returns:
            dict: {ReportKey: 报告内容}
        """
        if not output_list:
            return {self._QSArgs.ReportKey: "<p>无因子回测数据</p>"}

        n_factors = len(self._factor_names) if self._factor_names else 1
        factor_names = self._factor_names or self._infer_factor_names(output_list)

        ctx = DataContext({}, factor_names, self._report_config)

        # 0-IC 对比
        self._build_ic_comparison(ctx, factor_names, output_list)

        # 1-IC 衰减对比
        self._build_ic_decay_comparison(ctx, factor_names, output_list)

        # 2-分位数组合对比
        self._build_portfolio_comparison(ctx, factor_names, output_list)

        # 3-换手率对比
        self._build_turnover_comparison(ctx, factor_names, output_list)

        # 注入元信息
        self._inject_factor_info(ctx, factor_names)

        # 渲染
        fmt = self._QSArgs.OutputFormat
        theme = Theme()
        layout_renderer = LayoutRenderer()
        global_params = {"engine": self._QSArgs.ChartEngine}

        content = layout_renderer.render(
            self._report_config, ctx, theme, fmt, global_params=global_params
        )
        return {self._QSArgs.ReportKey: content}

    # ---- 对比数据构建 ----

    @staticmethod
    def _build_ic_comparison(ctx: DataContext, factor_names: list,
                             output_list: list) -> None:
        """IC 对比：IC 序列（已是多列）+ 各因子统计合并。"""
        if len(output_list) <= 0:
            return
        ic_output = output_list[0]
        if not isinstance(ic_output, dict):
            return

        # IC 序列（CalcIC 输出已是多列 DataFrame，columns = 因子名）
        for k, v in ic_output.items():
            if isinstance(v, pd.DataFrame) and not v.empty:
                ctx.set("0-IC 对比", k, v)

        # IC 统计数据合并（每个因子一行，合并为多列对比表）
        stats_frames = []
        for k, v in ic_output.items():
            if isinstance(v, pd.DataFrame) and "平均值" in v.index:
                stats_frames.append(v)
        if len(stats_frames) > 1:
            # 如果是单因子统计（1×N DataFrame），合并
            ctx.set("0-IC 对比", "IC 统计对比", pd.concat(stats_frames))

    @staticmethod
    def _build_ic_decay_comparison(ctx: DataContext, factor_names: list,
                                   output_list: list) -> None:
        """IC 衰减对比：从各因子衰减统计中提取 IC 均值合并。"""
        if len(output_list) <= 1:
            return
        decay_raw = output_list[1]
        if not isinstance(decay_raw, dict):
            return

        # ICDecay 输出: {factor_name: {统计数据: DataFrame}} 或展平形式
        ic_means = {}
        for fname_or_key, inner in decay_raw.items():
            if isinstance(inner, dict):
                stats = inner.get("统计数据") or inner.get("IC衰减")
                if isinstance(stats, pd.DataFrame) and not stats.empty:
                    # 取 IC 均值列
                    value_col = None
                    for c in stats.columns:
                        if "IC平均值" in str(c) or "IC" in str(c):
                            value_col = c
                            break
                    if value_col is None and len(stats.columns) > 0:
                        value_col = stats.columns[0]
                    if value_col is not None:
                        ic_means[fname_or_key] = stats[value_col]

        if ic_means:
            decay_df = pd.DataFrame(ic_means)
            if not decay_df.empty:
                ctx.set("1-IC 衰减对比", "IC 衰减对比", decay_df)

    @staticmethod
    def _build_portfolio_comparison(ctx: DataContext, factor_names: list,
                                    output_list: list) -> None:
        """分位数组合对比：合并各因子的净值/超额净值为多列。"""
        start = 2
        if len(output_list) <= start:
            return

        pf_outputs = output_list[start:start + len(factor_names)]
        excess_navs = []
        ls_navs = []
        stats_list = []

        for fname, pf_out in zip(factor_names, pf_outputs):
            if not isinstance(pf_out, dict):
                continue
            # 超额净值
            for k, v in pf_out.items():
                if isinstance(v, pd.DataFrame):
                    if "超额净值" in k:
                        # 取多头超额列（通常第一列或含 P0 的列）
                        col = v.iloc[:, 0] if len(v.columns) > 0 else None
                        if col is not None:
                            excess_navs.append(col.rename(fname))
                    elif "净值" in k and "超额" not in k:
                        # 多空净值：取含 "-" 的列（如 P0-P4）
                        ls_cols = [c for c in v.columns if "-" in str(c)]
                        if ls_cols:
                            ls_navs.append(v[ls_cols[0]].rename(fname))
                        elif len(v.columns) > 0:
                            ls_navs.append(v.iloc[:, -1].rename(fname))
                elif isinstance(v, pd.DataFrame) and "统计数据" in k:
                    pass

            # 统计数据
            for k, v in pf_out.items():
                if isinstance(v, pd.DataFrame) and "统计" in k:
                    if not v.empty:
                        stats_list.append(v)

        if excess_navs:
            df = pd.concat(excess_navs, axis=1).dropna(how="all")
            if not df.empty:
                ctx.set("2-分位数组合对比", "多头超额净值", df)

        if ls_navs:
            df = pd.concat(ls_navs, axis=1).dropna(how="all")
            if not df.empty:
                ctx.set("2-分位数组合对比", "多空净值", df)

        if stats_list:
            ctx.set("2-分位数组合对比", "统计数据对比",
                    pd.concat(stats_list))

    @staticmethod
    def _build_turnover_comparison(ctx: DataContext, factor_names: list,
                                   output_list: list) -> None:
        """换手率对比：直接取换手率输出（已是多列）。"""
        turnover_idx = 2 + len(factor_names)
        if len(output_list) <= turnover_idx:
            return

        raw = output_list[turnover_idx]
        if not isinstance(raw, dict):
            return

        for k, v in raw.items():
            if isinstance(v, pd.DataFrame) and not v.empty:
                ctx.set("3-换手率对比", k, v)

    # ---- 辅助方法 ----

    @staticmethod
    def _infer_factor_names(output_list: list) -> list:
        """从 IC 输出推断因子名列表。"""
        if output_list and isinstance(output_list[0], dict):
            for v in output_list[0].values():
                if isinstance(v, pd.DataFrame) and not v.empty:
                    return list(v.columns)
        return ["未知因子"]

    @staticmethod
    def _inject_factor_info(ctx: DataContext, factor_names: list) -> None:
        """注入因子元信息。"""
        dt_start = ctx.get("meta", "dt_start") or "未指定"
        dt_end = ctx.get("meta", "dt_end") or "未指定"
        ctx.set("meta", "factor_info", {
            "name": " vs ".join(factor_names),
            "count": len(factor_names),
            "dt_start": dt_start,
            "dt_end": dt_end,
        })
