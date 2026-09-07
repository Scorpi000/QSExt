# -*- coding: utf-8 -*-
"""单策略回测报告场景

``SingleStrategyReport`` 是 ``ReportGenerator`` 的子类，定义单策略回测报告所需的
上游节点（AccountStats）和数据到报告的映射。

使用方式::

    from QSExt.ReportGenerator.scenarios.single_strategy import SingleStrategyReport

    # 创建节点
    nodes = SingleStrategyReport.create_nodes(
        strategy=strategy_factor,
        bmk_nv=benchmark_nv_factor,
    )

    # 嵌入计算图
    report_node = SingleStrategyReport(
        nodes,
        args={"OutputFormat": "html"},
        strategy_name="动量策略",
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
    inject_strategy_info,
    build_performance_stats,
    build_nav_data,
    build_drawdown_data,
    build_period_returns,
    build_trade_stats,
)
from QuantStudio.Core.Node import Node


class SingleStrategyReport(ReportGenerator):
    """单策略回测报告生成节点。

    依赖节点（create_nodes 返回顺序）：
    0. AccountStats（账户统计）
    """

    class __QS_ArgClass__(ReportGenerator.__QS_ArgClass__):
        Name: str = Field(default="策略回测报告", frozen=True, title="名称")
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
    def create_nodes(cls, strategy, /, bmk_nv=None,
                     config: Optional[str] = None,
                     **kwargs) -> List[Node]:
        """创建单策略回测场景所需的上游节点。

        Args:
            strategy: 策略因子（MakeStrategy/MakeAccount 的输出）
            bmk_nv: 基准净值因子（可选）
            config: YAML 配置文件路径，空字符串或 None 使用内置默认配置

        Returns:
            上游节点列表：[AccountStats]
        """
        from QuantStudio.BackTest.Strategy.Strategy import AccountStats

        full_config = cls._load_config(config)
        cfg = full_config.get("modules", {}).get("account_stats", {})

        risk_free_rate = cfg.get("risk_free_rate", 0) if isinstance(cfg, dict) else 0
        bmk_id = cfg.get("bmk_id", None) if isinstance(cfg, dict) else None

        account_stats = AccountStats(
            account=strategy,
            bmk_nv=bmk_nv,
            args={
                "Name": "账户统计",
                "RiskFreeRate": risk_free_rate,
                "BmkID": bmk_id,
            },
        )

        return [account_stats]

    def __init__(self, deps: list = [], args: dict = {}, config_file: Optional[str] = None, **kwargs):
        strategy_name = kwargs.pop("strategy_name", "")
        self._strategy_name = strategy_name

        super().__init__(deps=deps, args=args, config_file=config_file, **kwargs)

        full_config = self._load_config(self._QSArgs.ReportConfig)
        self._report_config = full_config.get("report", {})
        self._modules_config = full_config.get("modules", {})

        if "OutputFormat" not in (args or {}):
            output_config = full_config.get("output", {})
            fmts = output_config.get("formats", ["html"])
            self._QSArgs.OutputFormat = fmts[0] if fmts else "html"

    def generate_report(self, output_list: List[Any]) -> dict:
        """将 AccountStats 产出组织为 DataContext 并渲染报告。

        Args:
            output_list: [AccountStats.output]

        Returns:
            dict: {ReportKey: 报告内容}
        """
        account_output = output_list[0] if output_list else {}
        if not account_output:
            return {self._QSArgs.ReportKey: "<p>无策略回测数据</p>"}

        # 构建 DataContext
        ctx = DataContext({}, [self._strategy_name], self._report_config)

        # 注入策略元信息
        inject_strategy_info(ctx, self._strategy_name, account_output)

        # 0-绩效统计
        build_performance_stats(ctx, account_output)

        # 1-净值走势
        build_nav_data(ctx, account_output)

        # 2-回撤分析
        build_drawdown_data(ctx, account_output)

        # 3-分时段收益
        build_period_returns(ctx, account_output)

        # 4-交易统计
        trade_freq = self._modules_config.get("trade_freq", "M")
        build_trade_stats(ctx, account_output, trade_freq=trade_freq)

        # 渲染
        report_config = self._report_config
        fmt = self._QSArgs.OutputFormat
        theme = Theme()
        layout_renderer = LayoutRenderer()
        global_params = {"engine": self._QSArgs.ChartEngine}

        content = layout_renderer.render(
            report_config, ctx, theme, fmt, global_params=global_params
        )
        return {self._QSArgs.ReportKey: content}
