# -*- coding: utf-8 -*-
"""多策略对比报告场景

``MultiStrategyReport`` 是 ``ReportGenerator`` 的子类，接收多个策略因子，
每个策略独立通过 AccountStats 回测后进行横向对比。

使用方式::

    from QSExt.ReportGenerator.scenarios.multi_strategy import MultiStrategyReport

    # 创建节点
    nodes = MultiStrategyReport.create_nodes(
        strategies=[strategy1, strategy2],
        bmk_nv=benchmark_nv_factor,
    )

    # 嵌入计算图
    report_node = MultiStrategyReport(
        nodes,
        args={"OutputFormat": "html"},
        strategy_names=["策略A", "策略B"],
    )

    result = Engine().run([report_node], context)[0]
"""

import os
from typing import Any, List, Optional

import pandas as pd

from pydantic import Field

from QSExt.ReportGenerator import ReportGenerator
from QSExt.ReportGenerator.core import DataContext
from QSExt.ReportGenerator.layout import LayoutRenderer
from QSExt.ReportGenerator.themes.base import Theme
from QSExt.ReportGenerator.scenarios._strategy_utils import (
    calc_annual_returns,
)
from QuantStudio.Core.Node import Node


class MultiStrategyReport(ReportGenerator):
    """多策略对比报告生成节点。

    依赖节点（create_nodes 返回顺序）：
    0..N-1. AccountStats（每个策略一个）
    """

    class __QS_ArgClass__(ReportGenerator.__QS_ArgClass__):
        Name: str = Field(default="多策略对比报告", frozen=True, title="名称")
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
    def create_nodes(cls, strategies, /, bmk_nv=None,
                     config: Optional[str] = None,
                     **kwargs) -> List[Node]:
        """创建多策略对比场景所需的上游节点。

        Args:
            strategies: 策略因子列表（MakeStrategy/MakeAccount 的输出）
            bmk_nv: 基准净值因子（可选，共享给所有策略）
            config: YAML 配置文件路径

        Returns:
            上游节点列表：[AccountStats_1, AccountStats_2, ...]
        """
        from QuantStudio.BackTest.Strategy.Strategy import AccountStats

        full_config = cls._load_config(config)
        cfg = full_config.get("modules", {}).get("account_stats", {})

        risk_free_rate = cfg.get("risk_free_rate", 0) if isinstance(cfg, dict) else 0
        bmk_id = cfg.get("bmk_id", None) if isinstance(cfg, dict) else None

        nodes = []
        for i, strategy in enumerate(strategies):
            account_stats = AccountStats(
                account=strategy,
                bmk_nv=bmk_nv,
                args={
                    "Name": f"账户统计_{i}",
                    "RiskFreeRate": risk_free_rate,
                    "BmkID": bmk_id,
                },
            )
            nodes.append(account_stats)

        return nodes

    def __init__(self, deps: list = [], args: dict = {},
                 config_file: Optional[str] = None, **kwargs):
        strategy_names = kwargs.pop("strategy_names", [])
        self._strategy_names = list(strategy_names)

        super().__init__(deps=deps, args=args, config_file=config_file, **kwargs)

        full_config = self._load_config(self._QSArgs.ReportConfig)
        self._report_config = full_config.get("report", {})
        self._modules_config = full_config.get("modules", {})

        if "OutputFormat" not in (args or {}):
            output_config = full_config.get("output", {})
            fmts = output_config.get("formats", ["html"])
            self._QSArgs.OutputFormat = fmts[0] if fmts else "html"

    def generate_report(self, output_list: List[Any]) -> dict:
        """将多个 AccountStats 产出组织为对比数据并渲染报告。

        Args:
            output_list: [AccountStats_1.output, AccountStats_2.output, ...]

        Returns:
            dict: {ReportKey: 报告内容}
        """
        if not output_list or all(not o for o in output_list):
            return {self._QSArgs.ReportKey: "<p>无策略回测数据</p>"}

        n = len(output_list)
        names = self._strategy_names[:n]
        while len(names) < n:
            names.append(f"策略{len(names) + 1}")

        ctx = DataContext({}, names, self._report_config)

        # 注入元信息
        self._inject_multi_info(ctx, names, output_list)

        # 0-绩效对比
        self._build_comparison_performance(ctx, names, output_list)

        # 1-净值对比
        self._build_comparison_nav(ctx, names, output_list)

        # 2-回撤对比
        self._build_comparison_drawdown(ctx, names, output_list)

        # 3-分时段收益对比
        self._build_comparison_period_returns(ctx, names, output_list)

        # 4-交易统计对比
        trade_freq = self._modules_config.get("trade_freq", "M")
        self._build_comparison_trade_stats(ctx, names, output_list, trade_freq)

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
    def _inject_multi_info(ctx: DataContext, names: List[str],
                           output_list: List[dict]) -> None:
        """注入多策略元信息到 meta 通道。"""
        first_ts = output_list[0].get("时间序列", pd.DataFrame())
        dt_start = first_ts.index[0] if len(first_ts) > 0 else "未指定"
        dt_end = first_ts.index[-1] if len(first_ts) > 0 else "未指定"
        ctx.set("meta", "strategy_info", {
            "name": " vs ".join(names),
            "count": len(names),
            "dt_start": dt_start,
            "dt_end": dt_end,
        })

    @staticmethod
    def _build_comparison_performance(ctx: DataContext, names: List[str],
                                      output_list: List[dict]) -> None:
        """构建多策略绩效对比表。"""
        cols = []
        for name, output in zip(names, output_list):
            stats = output.get("统计数据", pd.DataFrame())
            if not stats.empty and "绝对表现" in stats.columns:
                cols.append(stats["绝对表现"].rename(name))
        if cols:
            ctx.set("0-绩效对比", "核心指标对比", pd.concat(cols, axis=1))

    @staticmethod
    def _build_comparison_nav(ctx: DataContext, names: List[str],
                              output_list: List[dict]) -> None:
        """构建多策略净值对比。"""
        nav_series = []
        for name, output in zip(names, output_list):
            ts = output.get("时间序列", pd.DataFrame())
            if not ts.empty and "净值" in ts.columns:
                nav_series.append(ts["净值"].rename(name))

        if not nav_series:
            return

        nav_df = pd.concat(nav_series, axis=1)

        # 加入基准净值（从第一个策略的输出中取，避免重复）
        first_ts = output_list[0].get("时间序列", pd.DataFrame())
        if "基准净值" in first_ts.columns:
            nav_df["基准净值"] = first_ts["基准净值"]

        ctx.set("1-净值对比", "净值", nav_df)

    @staticmethod
    def _build_comparison_drawdown(ctx: DataContext, names: List[str],
                                   output_list: List[dict]) -> None:
        """构建多策略回撤对比。"""
        dd_series = []
        for name, output in zip(names, output_list):
            ts = output.get("时间序列", pd.DataFrame())
            if not ts.empty and "净值" in ts.columns:
                nav = ts["净值"].dropna()
                if not nav.empty:
                    dd = nav / nav.cummax() - 1
                    dd_series.append(dd.rename(name))

        if dd_series:
            ctx.set("2-回撤对比", "回撤序列", pd.concat(dd_series, axis=1))

    @staticmethod
    def _build_comparison_period_returns(ctx: DataContext, names: List[str],
                                         output_list: List[dict]) -> None:
        """构建多策略分时段收益对比。"""
        annual_list = []
        for name, output in zip(names, output_list):
            ts = output.get("时间序列", pd.DataFrame())
            if ts.empty or "净值" not in ts.columns:
                continue
            nav = ts["净值"].dropna()
            if len(nav) < 2:
                continue
            annual = calc_annual_returns(nav)
            if not annual.empty:
                annual_list.append(annual["年度收益率"].rename(name))

        if annual_list:
            annual_compare = pd.concat(annual_list, axis=1)
            annual_compare.index.name = "年度"
            ctx.set("3-分时段收益对比", "年度收益对比", annual_compare)

    @staticmethod
    def _build_comparison_trade_stats(ctx: DataContext, names: List[str],
                                      output_list: List[dict],
                                      trade_freq: str = "M") -> None:
        """构建多策略交易统计对比。"""
        summaries = []
        for name, output in zip(names, output_list):
            trade_record = output.get("交易记录", pd.DataFrame())
            position_num = output.get("持仓数量", pd.DataFrame())
            if trade_record.empty:
                continue

            n_trades = len(trade_record)
            buy_count = len(trade_record[trade_record["交易量"] > 0]) if "交易量" in trade_record.columns else 0
            sell_count = len(trade_record[trade_record["交易量"] < 0]) if "交易量" in trade_record.columns else 0
            avg_holdings = (position_num > 0).sum(axis=1).mean() if not position_num.empty else 0

            summaries.append(pd.Series({
                "总交易次数": n_trades,
                "买入次数": buy_count,
                "卖出次数": sell_count,
                "平均持仓数": avg_holdings,
            }, name=name))

        if summaries:
            ctx.set("4-交易统计对比", "交易概要对比", pd.concat(summaries, axis=1))
