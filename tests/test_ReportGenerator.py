# -*- coding: utf-8 -*-
"""ReportGenerator 模块测试

测试覆盖：
- DataContext 数据存取
- split_output_for_factor 结果拆分
- Theme CSS 生成
- HtmlRenderer / MarkdownRenderer 各渲染方法
- 所有组件 (Chart, DataTable, StatGrid, FactorSummary, Section)
- LayoutRenderer 端到端渲染
- config.yaml 加载和解析
- 组件注册表
"""

import os
import sys
import datetime as dt
import unittest

import numpy as np
import pandas as pd

# 确保 QSExt 在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from QSExt.ReportGenerator.core import DataContext, split_output_for_factor
from QSExt.ReportGenerator.themes.base import Theme
from QSExt.ReportGenerator.themes.base import Theme
from QSExt.ReportGenerator.renderers.html_renderer import HtmlRenderer
from QSExt.ReportGenerator.renderers.md_renderer import MarkdownRenderer
from QSExt.ReportGenerator.components.registry import ComponentRegistry
from QSExt.ReportGenerator.components.chart import Chart
from QSExt.ReportGenerator.components.data_table import DataTable
from QSExt.ReportGenerator.components.stat_grid import StatGrid
from QSExt.ReportGenerator.components.factor_summary import FactorSummary
from QSExt.ReportGenerator.components.section import Section
from QSExt.ReportGenerator.layout import LayoutRenderer
from QSExt.ReportGenerator import ReportGenerator
from QSExt.ReportGenerator.scenarios.single_factor import SingleFactorReport
from QuantStudio.Core.Node import Context


# ============================================================
# Mock 数据工具
# ============================================================

def _make_mock_output(factor_names=None):
    """构造模拟 BTReport output dict。

    模拟 IC、ICDecay、分位数组合、换手率四个模块的输出。
    数据结构对齐 QuantStudio 实际 BTNode.backward_compute() 产出。
    """
    if factor_names is None:
        factor_names = ["test_factor"]

    dates = pd.date_range("2020-01-01", "2025-12-31", freq="ME")

    # IC: DataFrame(index=dates, columns=factor_names)
    np.random.seed(42)
    ic_data = np.random.randn(len(dates), len(factor_names)) * 0.05 + 0.02
    ic_df = pd.DataFrame(ic_data, index=dates, columns=factor_names)

    # IC 移动平均
    ic_ma = ic_df.rolling(12).mean()

    # IC 统计数据：index=因子名, columns=统计量名（对齐 QuantStudio IC.backward_compute）
    n_factors = len(factor_names)
    stat_df = pd.DataFrame(index=factor_names)
    stat_df["平均值"] = [0.018 + i * 0.002 for i in range(n_factors)]
    stat_df["标准差"] = [0.06 - i * 0.003 for i in range(n_factors)]
    stat_df["最小值"] = [0.005 - i * 0.001 for i in range(n_factors)]
    stat_df["最大值"] = [0.035 + i * 0.003 for i in range(n_factors)]
    stat_df["IC_IR"] = stat_df["平均值"] / stat_df["标准差"]
    stat_df["t统计量"] = [3.2 + i * 0.3 for i in range(n_factors)]
    stat_df["平均截面宽度"] = [350 + i * 10 for i in range(n_factors)]
    stat_df["IC×Sqrt(N)"] = stat_df["平均值"] * np.sqrt(stat_df["平均截面宽度"])
    stat_df["有效期数"] = len(dates)

    output = {
        "0-Rank IC 分析": {
            "IC": ic_df,
            "IC的移动平均": ic_ma,
            "统计数据": stat_df,
            "截面宽度": pd.DataFrame(
                np.random.randint(200, 500, (len(dates), 1)),
                index=dates, columns=["宽度"]
            ),
        },
        "1-IC 衰减分析": {
            "IC衰减": pd.DataFrame(
                np.random.randn(5, len(factor_names)) * 0.02 + 0.015,
                index=[1, 2, 3, 6, 12], columns=factor_names
            ),
            "统计数据": pd.DataFrame(
                index=[1, 2, 3, 6, 12],
                data={
                    "IC平均值": [0.025, 0.022, 0.020, 0.018, 0.015],
                    "标准差": [0.06, 0.058, 0.057, 0.055, 0.053],
                    "IC_IR": [0.42, 0.38, 0.35, 0.33, 0.28],
                    "t统计量": [3.5, 3.2, 2.9, 2.7, 2.3],
                    "胜率": [0.62, 0.60, 0.58, 0.57, 0.55],
                },
            ),
        },
    }

    # 分位数组合（每个因子一个，key 格式对齐 create_modules 产生的节点名）
    # 单因子：key="2-分位数组合"，列名无前缀
    # 多因子：key="2-分位数组合"，列名含 "因子名::" 前缀（模拟合并逻辑）
    if len(factor_names) == 1:
        fn = factor_names[0]
        nav_df = pd.DataFrame(
            np.cumprod(1 + np.random.randn(len(dates), 5) * 0.02, axis=0),
            index=dates,
            columns=[f"Q{j+1}" for j in range(5)]
        )
        pf_stat = pd.DataFrame(
            {
                "年化收益率": [0.15 - j * 0.04 for j in range(5)],
                "Sharpe比率": [1.2 - j * 0.2 for j in range(5)],
                "最大回撤率": [-0.1 - j * 0.03 for j in range(5)],
                "胜率": [0.6 - j * 0.03 for j in range(5)],
            },
            index=[f"Q{j+1}" for j in range(5)]
        ).T
        output["2-分位数组合"] = {
            "净值": nav_df,
            "统计数据": pf_stat,
        }
    else:
        # 多因子：合并为一个 key，列名加因子名前缀
        nav_dfs = []
        stat_dfs = []
        for fn in factor_names:
            _nav = pd.DataFrame(
                np.cumprod(1 + np.random.randn(len(dates), 5) * 0.02, axis=0),
                index=dates,
                columns=[f"Q{j+1}" for j in range(5)]
            ).rename(columns=lambda c: f"{fn}::{c}")
            nav_dfs.append(_nav)
            _stat = pd.DataFrame(
                {
                    "年化收益率": [0.15 - j * 0.04 for j in range(5)],
                    "Sharpe比率": [1.2 - j * 0.2 for j in range(5)],
                    "最大回撤率": [-0.1 - j * 0.03 for j in range(5)],
                    "胜率": [0.6 - j * 0.03 for j in range(5)],
                },
                index=[f"Q{j+1}" for j in range(5)]
            ).T.rename(columns=lambda c: f"{fn}::{c}")
            stat_dfs.append(_stat)
        output["2-分位数组合"] = {
            "净值": pd.concat(nav_dfs, axis=1),
            "统计数据": pd.concat(stat_dfs, axis=1),
        }

    # 换手率
    output["3-因子换手率"] = {
        "换手率": pd.DataFrame(
            np.random.rand(len(dates), len(factor_names)) * 0.4,
            index=dates, columns=factor_names
        ),
    }

    return output


# ============================================================
# 测试用例
# ============================================================

class TestDataContext(unittest.TestCase):
    """DataContext 数据存取测试"""

    def setUp(self):
        self.output = _make_mock_output(["factor_A", "factor_B"])
        self.ctx = DataContext(self.output, ["factor_A", "factor_B"], {})

    def test_get_module_data(self):
        df = self.ctx.get("0-Rank IC 分析", "IC")
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(list(df.columns), ["factor_A", "factor_B"])

    def test_get_meta(self):
        self.assertEqual(self.ctx.get("meta", "factor_count"), 2)
        self.assertEqual(self.ctx.get("meta", "factor_names"), ["factor_A", "factor_B"])

    def test_get_nonexistent(self):
        self.assertIsNone(self.ctx.get("nonexistent_source", "nonexistent_key"))

    def test_set_custom_data(self):
        self.ctx.set("meta", "custom_key", "custom_value")
        self.assertEqual(self.ctx.get("meta", "custom_key"), "custom_value")

    def test_infer_date_range(self):
        self.assertIsNotNone(self.ctx.get("meta", "dt_start"))
        self.assertIsNotNone(self.ctx.get("meta", "dt_end"))


class TestSplitOutput(unittest.TestCase):
    """结果拆分测试"""

    def setUp(self):
        self.output = _make_mock_output(["factor_A", "factor_B"])

    def test_split_single_factor(self):
        result = split_output_for_factor(self.output, "factor_A")
        self.assertIn("0-Rank IC 分析", result)
        ic_df = result["0-Rank IC 分析"]["IC"]
        self.assertEqual(list(ic_df.columns), ["factor_A"])

    def test_split_preserves_shared_data(self):
        """拆分后共享数据（截面宽度等）直接保留"""
        result = split_output_for_factor(self.output, "factor_A")
        width_df = result["0-Rank IC 分析"].get("截面宽度")
        self.assertIsNotNone(width_df)

    def test_split_removes_report_key(self):
        output_with_report = {**self.output, "Report": "<html>...</html>"}
        result = split_output_for_factor(output_with_report, "factor_A")
        self.assertNotIn("Report", result)


class TestTheme(unittest.TestCase):
    """主题测试"""

    def test_base_css_generation(self):
        theme = Theme()
        css = theme.get_base_css()
        self.assertIn("<style>", css)
        self.assertIn("font-family", css)
        self.assertIn(".page-title", css)

    def test_apply_layout_single(self):
        theme = Theme()
        html = theme.apply_layout(["content"], "single")
        self.assertIn("layout-single", html)
        self.assertIn("content", html)

    def test_apply_layout_two_column(self):
        theme = Theme()
        html = theme.apply_layout(["left", "right"], "two_column")
        self.assertIn("layout-two-col", html)
        self.assertIn("left", html)
        self.assertIn("right", html)

    def test_apply_layout_grid(self):
        theme = Theme()
        html = theme.apply_layout(["a", "b", "c"], "grid", columns=3)
        self.assertIn("layout-grid", html)
        self.assertIn("repeat(3, 1fr)", html)


class TestHtmlRenderer(unittest.TestCase):
    """HTML 渲染器测试"""

    def setUp(self):
        self.renderer = HtmlRenderer()
        self.df = pd.DataFrame(
            {"A": [1.0, 2.0], "B": [3.5, 4.5]},
            index=["r1", "r2"]
        )

    def test_render_table(self):
        html = self.renderer.render_table(self.df, title="测试表")
        self.assertIn("<table", html)
        self.assertIn("测试表", html)

    def test_render_chart(self):
        from matplotlib.figure import Figure
        fig = Figure(figsize=(8, 4))
        ax = fig.add_subplot(111)
        ax.plot([1, 2, 3], [1, 2, 3])
        html = self.renderer.render_chart(fig, title="测试图")
        self.assertIn("data:image/png;base64,", html)
        self.assertIn("测试图", html)
        import matplotlib.pyplot as plt
        plt.close(fig)

    def test_render_stat_card(self):
        html = self.renderer.render_stat_card("夏普", 1.5, ".2f")
        self.assertIn("夏普", html)
        self.assertIn("1.50", html)

    def test_assemble_page(self):
        fragments = ["<div>section1</div>", "<div>section2</div>"]
        html = self.renderer.assemble_page(fragments, "测试报告")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("测试报告", html)
        self.assertIn("section1", html)
        self.assertIn("section2", html)


class TestMarkdownRenderer(unittest.TestCase):
    """Markdown 渲染器测试"""

    def setUp(self):
        self.renderer = MarkdownRenderer()
        self.df = pd.DataFrame(
            {"A": [1.0, 2.0], "B": [3.5, 4.5]},
            index=["r1", "r2"]
        )

    def test_render_section(self):
        md = self.renderer.render_section("标题", "内容")
        self.assertIn("## 标题", md)
        self.assertIn("内容", md)

    def test_render_table(self):
        md = self.renderer.render_table(self.df, title="表")
        self.assertIn("表", md)

    def test_assemble_page(self):
        fragments = ["## 第一章\n\n内容"]
        md = self.renderer.assemble_page(fragments, "报告标题")
        self.assertIn("# 报告标题", md)
        self.assertIn("第一章", md)


class TestComponents(unittest.TestCase):
    """组件测试"""

    def setUp(self):
        self.theme = Theme()
        self.html_renderer = HtmlRenderer()
        self.md_renderer = MarkdownRenderer()

    def test_chart_component_ic_bar(self):
        """IC 柱状图"""
        dates = pd.date_range("2020-01-01", periods=60, freq="ME")
        df = pd.DataFrame(
            np.random.randn(60, 1) * 0.05 + 0.02,
            index=dates, columns=["factor_A"]
        )
        comp = Chart()
        html = comp.render(df, {"type": "ic_bar", "title": "IC"}, self.theme, self.html_renderer)
        self.assertIn("data:image/png;base64,", html)

    def test_chart_component_nav_curve(self):
        """净值曲线"""
        dates = pd.date_range("2020-01-01", periods=60, freq="ME")
        df = pd.DataFrame(
            np.cumprod(1 + np.random.randn(60, 3) * 0.02, axis=0),
            index=dates, columns=["Q1", "Q2", "Q3"]
        )
        comp = Chart()
        html = comp.render(df, {"type": "nav_curve"}, self.theme, self.html_renderer)
        self.assertIn("data:image/png;base64,", html)

    def test_chart_component_unknown_type(self):
        """未知图表类型抛出异常"""
        comp = Chart()
        with self.assertRaises(ValueError):
            comp.render(pd.DataFrame(), {"type": "unknown_type"}, self.theme, self.html_renderer)

    def test_data_table(self):
        df = pd.DataFrame({"A": [1.0, 2.0]}, index=["x", "y"])
        comp = DataTable()
        html = comp.render(df, {"title": "测试", "precision": 2}, self.theme, self.html_renderer)
        self.assertIn("测试", html)
        self.assertIn("<table", html)

    def test_data_table_empty(self):
        comp = DataTable()
        html = comp.render(pd.DataFrame(), {}, self.theme, self.html_renderer)
        self.assertIsNotNone(html)

    def test_stat_grid(self):
        stat_df = pd.DataFrame(
            {"factor_A": [0.02, 0.5, 0.58]},
            index=["IC均值", "ICIR", "胜率"]
        )
        comp = StatGrid()
        html = comp.render(
            stat_df,
            {
                "title": "IC 概览",
                "metrics": [
                    {"label": "IC 均值", "field": "IC均值", "format": ".4f"},
                    {"label": "ICIR", "field": "ICIR", "format": ".2f"},
                    {"label": "胜率", "field": "胜率", "format": ".1%"},
                ]
            },
            self.theme, self.html_renderer
        )
        self.assertIn("IC 均值", html)
        self.assertIn("stat-card", html)

    def test_factor_summary(self):
        comp = FactorSummary()
        data = {
            "name": "动量因子",
            "dt_start": "2020-01-01",
            "dt_end": "2025-12-31",
            "count": 1,
        }
        params = {"title": "因子概况"}
        html = comp.render(data, params, self.theme, self.html_renderer)
        self.assertIn("动量因子", html)
        self.assertIn("2020-01-01", html)

    def test_section_single_layout(self):
        """章节容器 single 布局"""
        comp = Section()
        params = {
            "title": "测试章节",
            "layout": "single",
            "children": [
                {
                    "component": "data_table",
                    "_resolved_data": pd.DataFrame({"A": [1]}, index=["x"]),
                    "params": {"title": "子表格"}
                }
            ]
        }
        html = comp.render([], params, self.theme, self.html_renderer)
        self.assertIn("测试章节", html)


class TestComponentRegistry(unittest.TestCase):
    """组件注册表测试"""

    def test_builtin_components_registered(self):
        names = ComponentRegistry.list_all()
        self.assertIn("chart", names)
        self.assertIn("data_table", names)
        self.assertIn("stat_grid", names)
        self.assertIn("factor_summary", names)
        self.assertIn("section", names)

    def test_get_unknown(self):
        with self.assertRaises(KeyError):
            ComponentRegistry.get("nonexistent")


class TestLayoutRenderer(unittest.TestCase):
    """LayoutRenderer 端到端测试"""

    def setUp(self):
        self.output = _make_mock_output(["test_factor"])
        self.ctx = DataContext(self.output, ["test_factor"], {})
        self.theme = Theme()
        self.layout = LayoutRenderer()

    def test_render_basic_report(self):
        """端到端：从 report config → 完整 HTML"""
        report_config = {
            "page_title": "{factor_name} 测试报告",
            "sections": [
                {
                    "title": "一、IC 分析",
                    "component": "section",
                    "params": {"layout": "single"},
                    "children": [
                        {
                            "component": "chart",
                            "data": {"source": "0-Rank IC 分析", "key": "IC"},
                            "params": {"type": "ic_bar", "title": "IC 序列"}
                        },
                        {
                            "component": "data_table",
                            "data": {"source": "0-Rank IC 分析", "key": "统计数据"},
                            "params": {"precision": 4}
                        }
                    ]
                }
            ]
        }
        html = self.layout.render(report_config, self.ctx, self.theme, "html")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("test_factor", html)
        self.assertIn("IC 分析", html)
        self.assertIn("data:image/png;base64,", html)

    def test_render_markdown(self):
        """Markdown 格式"""
        report_config = {
            "page_title": "{factor_name} 测试",
            "sections": [
                {
                    "title": "IC 分析",
                    "component": "section",
                    "params": {"layout": "single"},
                    "children": [
                        {
                            "component": "data_table",
                            "data": {"source": "0-Rank IC 分析", "key": "统计数据"},
                            "params": {"precision": 2}
                        }
                    ]
                }
            ]
        }
        md = self.layout.render(report_config, self.ctx, self.theme, "markdown")
        self.assertIn("# test_factor 测试", md)
        self.assertIn("## IC 分析", md)


class TestConfigLoading(unittest.TestCase):
    """配置文件加载测试"""

    def test_load_config_yaml(self):
        import yaml
        config_path = os.path.join(
            os.path.dirname(__file__),
            "..", "QSExt", "ReportGenerator", "scenarios",
            "single_factor", "config.yaml"
        )
        config_path = os.path.abspath(config_path)
        self.assertTrue(os.path.exists(config_path), f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.assertIn("scenario", config)
        self.assertIn("modules", config)
        self.assertIn("report", config)
        self.assertIn("output", config)
        self.assertIn("sections", config["report"])
        self.assertIn("ic", config["modules"])
        self.assertIn("quantile_portfolio", config["modules"])


class TestEndToEnd(unittest.TestCase):
    """完整端到端测试（跳过 Engine，直接用 mock output 渲染）"""

    def test_full_pipeline_with_mock_data(self):
        """模拟完整流程：构造 output → DataContext → LayoutRenderer → 报告"""
        factor_names = ["factor_A", "factor_B", "factor_C"]
        output = _make_mock_output(factor_names)
        theme = Theme()
        layout_renderer = LayoutRenderer()

        # 模拟 report config（使用实际 config.yaml 的结构）
        report_config = {
            "page_title": "{factor_name} — 单因子测试报告",
            "header": {
                "component": "section",
                "params": {"layout": "grid", "columns": 2},
                "children": [
                    {
                        "component": "factor_summary",
                        "data": {"source": "meta", "key": "factor_info"},
                    },
                    {
                        "component": "stat_grid",
                        "data": {"source": "0-Rank IC 分析", "key": "统计数据"},
                        "params": {
                            "metrics": [
                                {"label": "ICIR", "field": "IC_IR", "format": ".2f"},
                            ]
                        }
                    }
                ]
            },
            "sections": [
                {
                    "title": "一、IC 分析",
                    "component": "section",
                    "params": {"layout": "single"},
                    "children": [
                        {
                            "component": "chart",
                            "data": {"source": "0-Rank IC 分析", "key": "IC"},
                            "params": {"type": "ic_bar", "title": "IC"}
                        },
                        {
                            "component": "stat_grid",
                            "data": {"source": "0-Rank IC 分析", "key": "统计数据"},
                            "params": {
                                "title": "指标",
                                "metrics": [
                                    {"label": "IC均值", "field": "平均值", "format": ".4f"},
                                    {"label": "ICIR", "field": "IC_IR", "format": ".2f"},
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        # === 单因子报告 ===
        for fname in factor_names:
            single_output = split_output_for_factor(output, fname)
            ctx = DataContext(single_output, [fname], {})
            ctx.set("meta", "factor_info", {
                "name": fname,
                "dt_start": "2020-01-01",
                "dt_end": "2025-12-31",
                "count": 1,
            })

            html = layout_renderer.render(report_config, ctx, theme, "html")
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn(fname, html)
            self.assertIn("IC 分析", html)

            md = layout_renderer.render(report_config, ctx, theme, "markdown")
            self.assertIn(f"# {fname}", md)

    def test_single_factor_config_structure(self):
        """验证 config.yaml 中引用的 source 名称与 scenario 的 BTNode Name 一致"""
        import yaml
        config_path = os.path.join(
            os.path.dirname(__file__),
            "..", "QSExt", "ReportGenerator", "scenarios",
            "single_factor", "config.yaml"
        )
        config_path = os.path.abspath(config_path)
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # 收集所有 data source 引用
        sources = set()
        def _collect_sources(node):
            if isinstance(node, dict):
                if "data" in node:
                    src = node["data"].get("source")
                    if src and src != "meta":
                        sources.add(src.split("-", 1)[-1] if "-" in src else src)
                if "children" in node:
                    for child in node["children"]:
                        _collect_sources(child)
                if "sections" in node:
                    for sec in node["sections"]:
                        _collect_sources(sec)

        _collect_sources(config["report"])
        # source 名称应该匹配 scenario 中 BTNode 的 Name
        expected_names = {
            "Rank IC 分析", "IC 衰减分析", "分位数组合"
        }
        for name in expected_names:
            found = any(name in s for s in sources)
            self.assertTrue(
                found, f"config 中缺少对 '{name}' 的数据引用，"
                        f"请确认 source 名称与 scenario 中 BTNode Name 一致"
            )


class _MockBTNode:
    """模拟 BTNode：backward_compute 返回预置数据。

    不继承真实 BTNode（避免触发其复杂的 init/prepare 流程），
    仅提供 Engine DAG 遍历所需的最小接口。
    """

    def __init__(self, name, output_data):
        import logging
        self._output = dict(output_data)
        # 模拟 Node 的核心属性
        self._QS_Logger = logging.getLogger(f"mock.{name}")
        self.QSID = name

    @property
    def Name(self):
        return self.QSID

    @property
    def Deps(self):
        return []

    def init_compute(self, path, init_data, context):
        context.NodeDict[self.QSID] = self
        return []

    def forward_compute(self, path, fwd_data, context):
        return [], None

    def backward_compute(self, path, bwd_data_list, context,
                         local_context=None):
        return dict(self._output)

    def prepare_compute(self, prepare_data, context):
        pass


class TestSingleFactorReport(unittest.TestCase):
    """SingleFactorReport 单元测试"""

    def setUp(self):
        self.output = _make_mock_output(["test_factor"])

    def test_node_creation(self):
        """Node 创建和参数设置"""
        mock_bt = _MockBTNode("IC", {"IC": pd.DataFrame({"x": [1]})})
        node = SingleFactorReport(
            data_nodes=[mock_bt],
            factor_names=["test"],
            config_file=None,
        )
        self.assertEqual(len(node.Deps), 1)
        self.assertEqual(node.Deps[0].QSID, "IC")
        self.assertEqual(node._factor_names, ["test"])

    def test_backward_compute(self):
        """backward_compute 输出报告"""
        mock_ic = _MockBTNode("Rank IC 分析", self.output["0-Rank IC 分析"])
        mock_decay = _MockBTNode("IC 衰减分析",
                                 self.output["1-IC 衰减分析"])

        node = SingleFactorReport(
            data_nodes=[mock_ic, mock_decay],
            factor_names=["test_factor"],
            args={"OutputFormats": ["html"]},
        )

        bwd_data = [mock_ic.backward_compute([], [], None),
                     mock_decay.backward_compute([], [], None)]
        result = node.backward_compute([], bwd_data, Context())

        self.assertIn("test_factor", result)
        html = result["test_factor"]["html"]
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("test_factor", html)

    def test_backward_compute_markdown_format(self):
        """Markdown 格式输出"""
        mock_ic = _MockBTNode("Rank IC 分析", self.output["0-Rank IC 分析"])

        node = SingleFactorReport(
            data_nodes=[mock_ic],
            factor_names=["f1"],
            args={"OutputFormats": ["markdown"]},
        )

        bwd_data = [mock_ic.backward_compute([], [], None)]
        result = node.backward_compute([], bwd_data, Context())

        md = result["f1"]["markdown"]
        self.assertIn("# f1", md)

    def test_merge_result(self):
        """merge_result 返回第一个元素"""
        node = SingleFactorReport(data_nodes=[], factor_names=[])
        merged = node.merge_result([{"a": 1}, {"b": 2}], Context())
        self.assertEqual(merged, {"a": 1})


class TestSingleFactorReportIntegration(unittest.TestCase):
    """验证 SingleFactorReport 与 LayoutRenderer 等效的渲染结果"""

    def setUp(self):
        self.output = _make_mock_output(["test_factor"])

    def test_node_output_structure(self):
        """Node 产生的输出结构正确"""
        mock_ic = _MockBTNode("Rank IC 分析", self.output["0-Rank IC 分析"])
        mock_decay = _MockBTNode("IC 衰减分析",
                                 self.output["1-IC 衰减分析"])

        node = SingleFactorReport(
            data_nodes=[mock_ic, mock_decay],
            factor_names=["test_factor"],
            args={"OutputFormats": ["html"]},
        )

        bwd_data = [mock_ic.backward_compute([], [], None),
                     mock_decay.backward_compute([], [], None)]
        reports = node.backward_compute([], bwd_data, Context())

        self.assertIn("test_factor", reports)
        self.assertIn("html", reports["test_factor"])
        self.assertGreater(len(reports["test_factor"]["html"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
