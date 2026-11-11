"""股票单因子报告：具名依赖、统计口径、样本质量和原始分析结果。"""
from copy import deepcopy
from html import escape
from pydantic import Field
from QuantStudio.Core.Input import DependencyModel
from QuantStudio.BackTest.SectionFactor.IC import IC, ICDecay
from QuantStudio.BackTest.SectionFactor.Correlation import FactorTurnover
from QuantStudio.BackTest.SectionFactor.QuantilePortfolio import MultiPortfolio
from QSExt.BackTest.StockFactor import StockQuality
from QSExt.ReportGenerator.components.chart import Chart
from QSExt.ReportGenerator.renderers.html_renderer import HtmlRenderer
from QSExt.ReportGenerator.themes.base import Theme
from .scenario import SingleFactorReport


def format_sampling_dates(dates):
    """五个以内完整显示，超过五个仅显示首尾、省略号和总数。"""
    values = list(dates)
    if len(values) <= 5:
        return ", ".join(values)
    return f"{values[0]}, ..., {values[-1]}（共 {len(values)} 个时点）"


class StockSingleFactorReport(SingleFactorReport):
    """在单因子布局渲染器上补充股票场景说明与可核查数据。"""
    class __QS_DepClass__(DependencyModel):
        quality: StockQuality
        ic: IC
        ic_decay: ICDecay
        quantile_portfolio: MultiPortfolio
        factor_stability: FactorTurnover

    class __QS_ArgClass__(SingleFactorReport.__QS_ArgClass__):
        Summary: dict = Field(default_factory=dict)

    @property
    def _report_config(self):
        """旧图保存的时序表格布局也使用图像，保留统计指标表格。"""
        config = deepcopy(super()._report_config)
        time_series = {"IC", "IC衰减", "换手率", "因子换手率", "净值", "超额净值"}

        def visit(node):
            if isinstance(node, list):
                for child in node:
                    visit(child)
            elif isinstance(node, dict):
                children = node.get("children") or node.get("params", {}).get("children", [])
                if len(children) == 2 and all(child.get("data", {}).get("source") == "3-因子换手率" for child in children):
                    keys = {child["data"].get("key") for child in children}
                    if "统计数据" in keys and keys.intersection({"换手率", "因子换手率"}):
                        node.setdefault("params", {})["layout"] = "two_column"
                        for child in children:
                            chart = child["data"].get("key") != "统计数据"
                            child["span"] = "left" if chart else "right"
                            if chart:
                                child.setdefault("params", {})["figsize"] = (16, 6)
                key = node.get("data", {}).get("key")
                if node.get("component") == "data_table" and key in time_series:
                    node["component"] = "chart"
                    previous = node.get("params", {})
                    node["params"] = {**previous, "type": "line_chart", "engine": "matplotlib",
                        "title": previous.get("title") or ("因子值稳定性（Spearman 自相关）" if key in ("换手率", "因子换手率") else key)}
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        visit(value)

        visit(config)
        return config

    def backward_compute(self, path, bwd_data_list, context, local_context=None):
        quality, ic, decay, portfolio, stability = bwd_data_list
        if not ic["IC"].notna().any().any():
            raise ValueError("没有有效 Rank IC 观测，请检查因子变化、价格收益及样本数量")
        rendered = self.generate_report([ic, decay, portfolio, stability])
        coverage = quality["采样覆盖"]
        chart = Chart()
        renderer, theme = HtmlRenderer(), Theme()
        coverage_charts = theme.apply_layout([chart.render(coverage[columns], {
            "engine": "matplotlib", "type": "line_chart", "title": title, "figsize": (16, 6),
        }, theme, renderer) for title, columns in (
            ("采样股票数与不同因子值数量", ["候选股票数", "有效股票数", "不同因子值数量"]),
            ("有效覆盖率与因子缺失比例（0–1）", ["有效覆盖率", "因子缺失或非有限值比例"]),
        )], "two_column")
        summary = dict(self.Args.Summary)
        sampling = summary.get("IC 采样时点")
        if isinstance(sampling, str) and "..." not in sampling:
            summary["IC 采样时点"] = format_sampling_dates(part.strip() for part in sampling.split(",") if part.strip())
        rows = "".join(f"<tr><th>{escape(str(k))}</th><td>{escape(str(v))}</td></tr>" for k, v in summary.items())
        notes = (
            "Rank IC = corr(f[t-1], P[t]/P[t-1]-1)，时点按收益结束日标记。"
            "滞后 k 期衰减 = corr(f[t-k], 单期收益[t])。"
            "因子值稳定性为相邻采样截面的 Spearman 自相关。"
            "组合在采样日收盘后更新理论权重，下一交易区间产生收益；忽略交易成本、停牌和涨跌停成交约束。"
            "无效价格沿用组合净值引擎的前值估值规则；动态筛选仅在调仓时影响建仓。"
            "股票 ID 为候选范围；未配置历史成分筛选时，不代表历史指数成分。"
            "未执行行业、市值中性化或风险归因。"
        )
        prefix = (f"<section><h1>{escape(self.Args.FactorNames[0])} — 股票单因子测试报告</h1>"
            f"<h2>测试配置与口径</h2><table>{rows}</table><p>{notes}</p>"
            f"<h2>样本质量</h2><p>无效采样期数：{quality['无效采样期数']}；空值指标不记为零。</p>"
            f"{coverage_charts}</section>")
        html = rendered[self.Args.ReportKey]
        body = html.find(">", html.find("<body")) if "<body" in html else -1
        rendered[self.Args.ReportKey] = html[:body + 1] + prefix + html[body + 1:] if body >= 0 else prefix + html
        return {**rendered, "Rank IC": ic, "因子滞后衰减": decay, "分位数组合": portfolio,
            "因子值稳定性": {"Spearman 自相关": stability["因子换手率"], "统计数据": stability["统计数据"]},
            "样本质量": quality, "测试配置": summary}
