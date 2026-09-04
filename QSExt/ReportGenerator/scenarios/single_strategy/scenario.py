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

import numpy as np
import pandas as pd

from pydantic import Field

from QSExt.ReportGenerator import ReportGenerator
from QSExt.ReportGenerator.core import DataContext
from QSExt.ReportGenerator.layout import LayoutRenderer
from QSExt.ReportGenerator.themes.base import Theme
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
        self._inject_strategy_info(ctx, account_output)

        # 0-绩效统计
        self._build_performance_stats(ctx, account_output)

        # 1-净值走势
        self._build_nav_data(ctx, account_output)

        # 2-回撤分析
        self._build_drawdown_data(ctx, account_output)

        # 3-分时段收益
        self._build_period_returns(ctx, account_output)

        # 4-交易统计
        self._build_trade_stats(ctx, account_output)

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

    # ---- 数据构建方法 ----

    def _inject_strategy_info(self, ctx: DataContext, output: dict) -> None:
        """注入策略元信息到 meta 通道。"""
        time_series = output.get("时间序列", pd.DataFrame())
        dt_start = time_series.index[0] if len(time_series) > 0 else "未指定"
        dt_end = time_series.index[-1] if len(time_series) > 0 else "未指定"
        ctx.set("meta", "strategy_info", {
            "name": self._strategy_name or "策略",
            "count": 1,
            "dt_start": dt_start,
            "dt_end": dt_end,
        })

    @staticmethod
    def _build_performance_stats(ctx: DataContext, output: dict) -> None:
        """构建绩效统计数据。"""
        stats = output.get("统计数据", pd.DataFrame())
        if stats.empty:
            return
        # 绝对表现列
        if "绝对表现" in stats.columns:
            ctx.set("0-绩效统计", "绝对表现", stats[["绝对表现"]])
        ctx.set("0-绩效统计", "统计全表", stats)

    @staticmethod
    def _build_nav_data(ctx: DataContext, output: dict) -> None:
        """构建净值走势数据。"""
        ts = output.get("时间序列", pd.DataFrame())
        if ts.empty:
            return

        # 净值列
        nav_cols = ["净值"]
        if "基准净值" in ts.columns:
            nav_cols.append("基准净值")
        if "相对净值" in ts.columns:
            nav_cols.append("相对净值")
        ctx.set("1-净值走势", "净值", ts[nav_cols])

        # 收益率列
        ret_cols = ["收益率"]
        if "基准收益率" in ts.columns:
            ret_cols.append("基准收益率")
        ctx.set("1-净值走势", "收益率", ts[ret_cols])

    @staticmethod
    def _build_drawdown_data(ctx: DataContext, output: dict) -> None:
        """构建回撤分析数据。"""
        ts = output.get("时间序列", pd.DataFrame())
        if ts.empty or "净值" not in ts.columns:
            return

        nav = ts["净值"].dropna()
        if nav.empty:
            return

        # 回撤序列：净值 / 历史最高净值 - 1
        cummax = nav.cummax()
        drawdown = nav / cummax - 1
        drawdown_df = drawdown.to_frame("回撤")
        ctx.set("2-回撤分析", "回撤序列", drawdown_df)

        # 回撤事件表：识别主要回撤（> 5% 或 Top 5）
        events = _identify_drawdown_events(nav, min_pct=0.05, top_n=5)
        if not events.empty:
            ctx.set("2-回撤分析", "回撤事件", events)

    @staticmethod
    def _build_period_returns(ctx: DataContext, output: dict) -> None:
        """构建分时段收益数据。"""
        ts = output.get("时间序列", pd.DataFrame())
        if ts.empty or "净值" not in ts.columns:
            return

        nav = ts["净值"].dropna()
        if len(nav) < 2:
            return

        # 年度收益
        annual = _calc_annual_returns(nav)
        if not annual.empty:
            ctx.set("3-分时段收益", "年度收益", annual)

        # 月度收益
        monthly = _calc_monthly_returns(nav)
        if not monthly.empty:
            ctx.set("3-分时段收益", "月度收益", monthly)

    @staticmethod
    def _build_trade_stats(ctx: DataContext, output: dict) -> None:
        """构建交易统计数据。"""
        trade_record = output.get("交易记录", pd.DataFrame())
        position_num = output.get("持仓数量", pd.DataFrame())

        if trade_record.empty:
            return

        # 交易概要指标
        n_trades = len(trade_record)
        buy_count = len(trade_record[trade_record["交易量"] > 0]) if "交易量" in trade_record.columns else 0
        sell_count = len(trade_record[trade_record["交易量"] < 0]) if "交易量" in trade_record.columns else 0
        avg_holdings = (position_num > 0).sum(axis=1).mean() if not position_num.empty else 0

        summary = pd.DataFrame({
            "绝对表现": {
                "总交易次数": n_trades,
                "买入次数": buy_count,
                "卖出次数": sell_count,
                "平均持仓数": avg_holdings,
            }
        })
        ctx.set("4-交易统计", "交易概要", summary)

        # 交易记录（限制行数避免报告过大）
        display_cols = [c for c in trade_record.columns if c in ["交易时点", "ID", "交易量", "成交价", "交易费"]]
        if display_cols:
            ctx.set("4-交易统计", "交易记录", trade_record[display_cols])


# ---- 辅助函数 ----

def _identify_drawdown_events(nav: pd.Series, min_pct: float = 0.05,
                               top_n: int = 5) -> pd.DataFrame:
    """识别主要回撤事件。

    Args:
        nav: 净值序列
        min_pct: 最小回撤幅度阈值
        top_n: 最多返回的事件数

    Returns:
        DataFrame，columns=[开始时点, 结束时点, 最大回撤, 持续天数]
    """
    cummax = nav.cummax()
    drawdown = nav / cummax - 1
    is_in_dd = drawdown < 0

    events = []
    in_event = False
    start_dt = None
    trough_dt = None
    trough_val = 0.0

    for dt, val in drawdown.items():
        if val < 0 and not in_event:
            in_event = True
            start_dt = dt
            trough_dt = dt
            trough_val = val
        elif val < 0 and in_event:
            if val < trough_val:
                trough_dt = dt
                trough_val = val
        elif val >= 0 and in_event:
            in_event = False
            if trough_val <= -min_pct:
                duration = (dt - start_dt).days if hasattr((dt - start_dt), "days") else 0
                events.append({
                    "开始时点": start_dt,
                    "最低点时点": trough_dt,
                    "最大回撤": trough_val,
                    "持续天数": duration,
                })
            start_dt = None
            trough_dt = None
            trough_val = 0.0

    # 处理未结束的回撤
    if in_event and trough_val <= -min_pct:
        duration = (nav.index[-1] - start_dt).days if hasattr((nav.index[-1] - start_dt), "days") else 0
        events.append({
            "开始时点": start_dt,
            "最低点时点": trough_dt,
            "最大回撤": trough_val,
            "持续天数": duration,
        })

    if not events:
        return pd.DataFrame()

    df = pd.DataFrame(events).sort_values("最大回撤").head(top_n).reset_index(drop=True)
    return df


def _calc_annual_returns(nav: pd.Series) -> pd.DataFrame:
    """计算年度收益率。"""
    if not isinstance(nav.index, pd.DatetimeIndex):
        return pd.DataFrame()

    yearly = nav.resample("YE").last()
    if len(yearly) < 1:
        return pd.DataFrame()

    returns = yearly.pct_change()
    returns.iloc[0] = yearly.iloc[0] / 1.0 - 1  # 首年以 1 为基准

    result = pd.DataFrame({
        "年末净值": yearly.values,
        "年度收益率": returns.values,
    }, index=[dt.year for dt in yearly.index])
    result.index.name = "年度"
    return result


def _calc_monthly_returns(nav: pd.Series) -> pd.DataFrame:
    """计算月度收益矩阵（行=年份，列=月份）。"""
    if not isinstance(nav.index, pd.DatetimeIndex):
        return pd.DataFrame()

    monthly = nav.resample("ME").last()
    if len(monthly) < 2:
        return pd.DataFrame()

    returns = monthly.pct_change().dropna()
    if returns.empty:
        return pd.DataFrame()

    # 构建年×月矩阵
    matrix = {}
    for dt, ret in returns.items():
        year = dt.year
        month = dt.month
        matrix.setdefault(year, {})[month] = ret

    df = pd.DataFrame(matrix).T
    df.index.name = "年度"
    df.columns = [f"{m}月" for m in sorted(df.columns)]
    return df
