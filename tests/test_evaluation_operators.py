# -*- coding: utf-8 -*-
"""因子评测算子和节点测试。

测试覆盖：
  - 算子实例化（CalcIncrementalIC, CalcSizeStratifiedAlpha, CalcSubPeriodStats）
  - 节点实例化（IncrementalICNode, SizeStratifiedAlphaNode, SubPeriodNode）
  - 节点 backward_compute 逻辑（模拟数据输入）
  - 统计数据计算正确性

运行方式：
    pytest tests/test_evaluation_operators.py -v

注意：
    算子的 calculate 方法需要 QuantStudio 完整计算图环境，
    此处主要测试实例化和节点后处理逻辑。
"""
from __future__ import annotations

import datetime as dt
import numpy as np
import pandas as pd
import pytest


# ============================================================
# 算子实例化测试
# ============================================================


class TestCalcIncrementalICInit:
    """CalcIncrementalIC 算子实例化测试。"""

    def test_import(self):
        """应能正确导入算子。"""
        from QSExt.LLMFactor.evaluation.operators.incremental_ic import CalcIncrementalIC
        assert CalcIncrementalIC is not None

    def test_init_default(self):
        """默认参数实例化。"""
        from QSExt.LLMFactor.evaluation.operators.incremental_ic import CalcIncrementalIC
        descriptor_ids = ["000001.SZ", "000002.SZ", "600000.SH"]
        op = CalcIncrementalIC(descriptor_ids=descriptor_ids)
        assert op._QSArgs.Name == "calcIncrementalIC"
        assert op._QSArgs.DescriptorSection[0] == descriptor_ids
        assert op._QSArgs.LookBack[0] == 31

    def test_init_custom_params(self):
        """自定义参数实例化。"""
        from QSExt.LLMFactor.evaluation.operators.incremental_ic import CalcIncrementalIC
        descriptor_ids = ["000001.SZ", "000002.SZ"]
        op = CalcIncrementalIC(
            descriptor_ids=descriptor_ids,
            lookback=60,
            period_lookback=3,
            corr_method="pearson",
        )
        assert op._QSArgs.LookBack[0] == 60
        assert op._QSArgs.ModelArgs["period_lookback"] == 3
        assert op._QSArgs.ModelArgs["corr_method"] == "pearson"

    def test_compound_type(self):
        """输出应包含 IC、MaxCorrelation、Breadth 三个字段。"""
        from QSExt.LLMFactor.evaluation.operators.incremental_ic import CalcIncrementalIC
        op = CalcIncrementalIC(descriptor_ids=["000001.SZ"])
        compound_type = op._QSArgs.CompoundType
        field_names = [ct[0] for ct in compound_type]
        assert "IC" in field_names
        assert "MaxCorrelation" in field_names
        assert "Breadth" in field_names


class TestCalcSizeStratifiedAlphaInit:
    """CalcSizeStratifiedAlpha 算子实例化测试。"""

    def test_import(self):
        """应能正确导入算子。"""
        from QSExt.LLMFactor.evaluation.operators.size_stratified import CalcSizeStratifiedAlpha
        assert CalcSizeStratifiedAlpha is not None

    def test_init_default(self):
        """默认参数实例化。"""
        from QSExt.LLMFactor.evaluation.operators.size_stratified import CalcSizeStratifiedAlpha
        descriptor_ids = ["000001.SZ", "000002.SZ"]
        op = CalcSizeStratifiedAlpha(descriptor_ids=descriptor_ids)
        assert op._QSArgs.Name == "calcSizeStratifiedAlpha"
        assert op._QSArgs.ModelArgs["group_num"] == 5

    def test_init_custom_group_num(self):
        """自定义分组数。"""
        from QSExt.LLMFactor.evaluation.operators.size_stratified import CalcSizeStratifiedAlpha
        op = CalcSizeStratifiedAlpha(
            descriptor_ids=["000001.SZ"],
            group_num=10,
        )
        assert op._QSArgs.ModelArgs["group_num"] == 10

    def test_compound_type(self):
        """输出应包含各组的 Return、Alpha、tStat。"""
        from QSExt.LLMFactor.evaluation.operators.size_stratified import CalcSizeStratifiedAlpha
        op = CalcSizeStratifiedAlpha(descriptor_ids=["000001.SZ"], group_num=3)
        compound_type = op._QSArgs.CompoundType
        field_names = [ct[0] for ct in compound_type]
        # 应有 3 组 × 3 个字段 = 9 个
        assert len(field_names) == 9
        assert "Return_G0" in field_names
        assert "Alpha_G0" in field_names
        assert "tStat_G0" in field_names
        assert "Return_G2" in field_names
        assert "Alpha_G2" in field_names
        assert "tStat_G2" in field_names


class TestCalcSubPeriodStatsInit:
    """CalcSubPeriodStats 算子实例化测试。"""

    def test_import(self):
        """应能正确导入算子。"""
        from QSExt.LLMFactor.evaluation.operators.sub_period import CalcSubPeriodStats
        assert CalcSubPeriodStats is not None

    def test_init_default(self):
        """默认参数实例化。"""
        from QSExt.LLMFactor.evaluation.operators.sub_period import CalcSubPeriodStats
        op = CalcSubPeriodStats(descriptor_ids=["000001.SZ"])
        assert op._QSArgs.Name == "calcSubPeriodStats"
        assert op._QSArgs.ModelArgs["freq"] == "yearly"
        assert op._QSArgs.ModelArgs["corr_method"] == "spearman"

    def test_init_quarterly(self):
        """按季度拆分。"""
        from QSExt.LLMFactor.evaluation.operators.sub_period import CalcSubPeriodStats
        op = CalcSubPeriodStats(
            descriptor_ids=["000001.SZ"],
            freq="quarterly",
        )
        assert op._QSArgs.ModelArgs["freq"] == "quarterly"


# ============================================================
# 节点实例化测试
# ============================================================


class TestIncrementalICNodeInit:
    """IncrementalICNode 节点实例化测试。"""

    def test_import(self):
        """应能正确导入节点。"""
        from QSExt.LLMFactor.evaluation.nodes.incremental_ic_node import IncrementalICNode
        assert IncrementalICNode is not None

    def test_args_class(self):
        """参数类应包含正确的字段。"""
        from QSExt.LLMFactor.evaluation.nodes.incremental_ic_node import IncrementalICNode
        args_cls = IncrementalICNode.__QS_ArgClass__
        # 检查默认值
        defaults = args_cls()
        assert defaults.Name == "增量 IC 检验"
        assert defaults.RollingAvgPeriod == 12
        assert defaults.GenReport is False


class TestSizeStratifiedAlphaNodeInit:
    """SizeStratifiedAlphaNode 节点实例化测试。"""

    def test_import(self):
        """应能正确导入节点。"""
        from QSExt.LLMFactor.evaluation.nodes.size_stratified_node import SizeStratifiedAlphaNode
        assert SizeStratifiedAlphaNode is not None

    def test_args_class(self):
        """参数类应包含正确的字段。"""
        from QSExt.LLMFactor.evaluation.nodes.size_stratified_node import SizeStratifiedAlphaNode
        args_cls = SizeStratifiedAlphaNode.__QS_ArgClass__
        defaults = args_cls()
        assert defaults.Name == "规模分层 Alpha"
        assert defaults.GroupNum == 5


class TestSubPeriodNodeInit:
    """SubPeriodNode 节点实例化测试。"""

    def test_import(self):
        """应能正确导入节点。"""
        from QSExt.LLMFactor.evaluation.nodes.sub_period_node import SubPeriodNode
        assert SubPeriodNode is not None

    def test_args_class(self):
        """参数类应包含正确的字段。"""
        from QSExt.LLMFactor.evaluation.nodes.sub_period_node import SubPeriodNode
        args_cls = SubPeriodNode.__QS_ArgClass__
        defaults = args_cls()
        assert defaults.Name == "子期稳健性"


# ============================================================
# 节点 backward_compute 测试（模拟数据）
# ============================================================


class TestIncrementalICNodeCompute:
    """IncrementalICNode backward_compute 测试。"""

    def _make_mock_node(self):
        """创建模拟节点用于测试。"""
        from QSExt.LLMFactor.evaluation.nodes.incremental_ic_node import IncrementalICNode
        # 创建一个模拟的节点对象，仅用于测试 backward_compute
        class MockDep:
            QSID = "mock_dep_001"

        class MockNode(IncrementalICNode):
            def __init__(self):
                # 跳过父类 __init__，直接设置必要属性
                self._QSArgs = type('Args', (), {
                    'FactorNameList': ['test_factor'],
                    'RollingAvgPeriod': 3,
                    'GenReport': False,
                    'Name': '增量 IC 检验',
                })()
                self.Deps = [MockDep()]

        return MockNode()

    def test_backward_compute_basic(self):
        """基本的 backward_compute 测试。"""
        node = self._make_mock_node()

        # 构造模拟输入数据：(IC, MaxCorrelation, Breadth)
        # 注意：列名必须与 FactorNameList 匹配
        dates = pd.date_range('2020-01-01', periods=10, freq='ME')
        mock_data = pd.DataFrame(
            [[(0.05, 0.3, 100)] for _ in range(10)],
            index=dates,
            columns=['test_factor'],
        )

        output = node.backward_compute(path=[], bwd_data_list=[mock_data], context=None)

        # 验证输出结构
        assert "IC" in output
        assert "最大相关性" in output
        assert "截面宽度" in output
        assert "统计数据" in output

    def test_backward_compute_statistics(self):
        """统计数据应包含正确字段。"""
        node = self._make_mock_node()

        dates = pd.date_range('2020-01-01', periods=20, freq='ME')
        # 使用更稳定的 IC 值
        ic_values = [0.04, 0.05, 0.03, 0.06, 0.04, 0.05, 0.03, 0.04, 0.05, 0.06,
                     0.04, 0.05, 0.03, 0.04, 0.05, 0.06, 0.04, 0.05, 0.03, 0.04]
        mock_data = pd.DataFrame(
            [[(ic, 0.3, 100)] for ic in ic_values],
            index=dates,
            columns=['test_factor'],
        )

        output = node.backward_compute(path=[], bwd_data_list=[mock_data], context=None)
        stats = output["统计数据"]

        # 验证统计字段
        assert "增量IC均值" in stats.columns
        assert "标准差" in stats.columns
        assert "IC_IR" in stats.columns
        assert "增量IC t统计量" in stats.columns
        assert "最大相关性均值" in stats.columns
        assert "有效期数" in stats.columns

    def test_backward_compute_ic_values(self):
        """IC 值应正确提取。"""
        node = self._make_mock_node()

        dates = pd.date_range('2020-01-01', periods=5, freq='ME')
        mock_data = pd.DataFrame(
            [[(0.05, 0.3, 100)], [(0.03, 0.4, 100)], [(0.06, 0.2, 100)],
             [(0.04, 0.35, 100)], [(0.02, 0.45, 100)]],
            index=dates,
            columns=['test_factor'],
        )

        output = node.backward_compute(path=[], bwd_data_list=[mock_data], context=None)
        ic_df = output["IC"]

        # 验证 IC 值
        assert len(ic_df) == 5
        assert ic_df.iloc[0, 0] == pytest.approx(0.05)
        assert ic_df.iloc[1, 0] == pytest.approx(0.03)

    def test_backward_compute_with_nan(self):
        """NaN 值应被正确处理。"""
        node = self._make_mock_node()

        dates = pd.date_range('2020-01-01', periods=5, freq='ME')
        mock_data = pd.DataFrame(
            [[(0.05, 0.3, 100)], [(np.nan, np.nan, np.nan)], [(0.06, 0.2, 100)],
             [(0.04, 0.35, 100)], [(np.nan, np.nan, np.nan)]],
            index=dates,
            columns=['test_factor'],
        )

        output = node.backward_compute(path=[], bwd_data_list=[mock_data], context=None)
        ic_df = output["IC"]

        # 验证 NaN 被正确保留
        assert pd.notnull(ic_df.iloc[0, 0])
        assert pd.isnull(ic_df.iloc[1, 0])
        assert pd.notnull(ic_df.iloc[2, 0])


class TestSizeStratifiedAlphaNodeCompute:
    """SizeStratifiedAlphaNode backward_compute 测试。"""

    def _make_mock_node(self):
        """创建模拟节点用于测试。"""
        from QSExt.LLMFactor.evaluation.nodes.size_stratified_node import SizeStratifiedAlphaNode

        class MockDep:
            QSID = "mock_dep_002"

        class MockNode(SizeStratifiedAlphaNode):
            def __init__(self):
                self._QSArgs = type('Args', (), {
                    'FactorNameList': ['test_factor'],
                    'GroupNum': 3,
                    'GenReport': False,
                    'Name': '规模分层 Alpha',
                })()
                self.Deps = [MockDep()]

        return MockNode()

    def test_backward_compute_basic(self):
        """基本的 backward_compute 测试。"""
        node = self._make_mock_node()

        # 构造模拟输入：每组 3 个字段 (Return, Alpha, tStat)
        # 3 组 × 3 字段 = 9 列
        mock_data = np.array([
            [0.08, 0.06, 2.5, 0.10, 0.08, 3.0, 0.12, 0.10, 3.5],  # factor 1
        ])

        output = node.backward_compute(path=[], bwd_data_list=[mock_data], context=None)

        # 验证输出结构
        assert "统计数据" in output
        stats = output["统计数据"]
        assert len(stats) == 1
        assert "G0 年化收益" in stats.columns
        assert "G0 Alpha" in stats.columns
        assert "G0 t统计量" in stats.columns

    def test_backward_compute_multiple_factors(self):
        """多个因子的 backward_compute 测试。"""
        node = self._make_mock_node()
        node._QSArgs.FactorNameList = ['factor_a', 'factor_b']

        mock_data = np.array([
            [0.08, 0.06, 2.5, 0.10, 0.08, 3.0, 0.12, 0.10, 3.5],
            [0.05, 0.04, 1.8, 0.07, 0.06, 2.2, 0.09, 0.08, 2.8],
        ])

        output = node.backward_compute(path=[], bwd_data_list=[mock_data], context=None)
        stats = output["统计数据"]

        assert len(stats) == 2
        assert 'factor_a' in stats.index
        assert 'factor_b' in stats.index


class TestSubPeriodNodeCompute:
    """SubPeriodNode backward_compute 测试。"""

    def _make_mock_node(self):
        """创建模拟节点用于测试。"""
        from QSExt.LLMFactor.evaluation.nodes.sub_period_node import SubPeriodNode

        class MockDep:
            QSID = "mock_dep_003"

        class MockNode(SubPeriodNode):
            def __init__(self):
                self._QSArgs = type('Args', (), {
                    'FactorNameList': ['test_factor'],
                    'GenReport': False,
                    'Name': '子期稳健性',
                    'ModelArgs': {'freq': 'yearly'},
                })()
                self.Deps = [MockDep()]

        return MockNode()

    def test_backward_compute_basic(self):
        """基本的 backward_compute 测试。"""
        node = self._make_mock_node()

        # 构造模拟输入：字典格式 {factor_name: DataFrame}
        mock_data = np.array([{
            'test_factor': pd.DataFrame({
                'period': ['2020', '2021', '2022'],
                'IC均值': [0.04, 0.05, 0.03],
                'IC标准差': [0.02, 0.025, 0.018],
                'ICIR': [2.0, 2.0, 1.67],
                't统计量': [3.46, 3.46, 2.87],
                '胜率': [0.65, 0.70, 0.60],
                '有效期数': [12, 12, 12],
                '平均截面宽度': [3000, 3000, 3000],
            })
        }], dtype=object)

        output = node.backward_compute(path=[], bwd_data_list=[mock_data], context=None)

        # 验证输出结构
        assert "统计数据" in output
        assert "汇总" in output

    def test_backward_compute_statistics_structure(self):
        """统计数据应包含正确字段。"""
        node = self._make_mock_node()

        mock_data = np.array([{
            'test_factor': pd.DataFrame({
                'period': ['2020', '2021', '2022'],
                'IC均值': [0.04, 0.05, 0.03],
                'IC标准差': [0.02, 0.025, 0.018],
                'ICIR': [2.0, 2.0, 1.67],
                't统计量': [3.46, 3.46, 2.87],
                '胜率': [0.65, 0.70, 0.60],
                '有效期数': [12, 12, 12],
                '平均截面宽度': [3000, 3000, 3000],
            })
        }], dtype=object)

        output = node.backward_compute(path=[], bwd_data_list=[mock_data], context=None)

        # 验证统计数据
        stats = output["统计数据"]
        assert len(stats) == 3
        assert "factor" in stats.columns

        # 验证汇总数据
        summary = output["汇总"]
        assert len(summary) == 1
        assert "因子" in summary.columns
        assert "全期IC均值" in summary.columns
        assert "子期IC标准差" in summary.columns
        assert "子期ICIR" in summary.columns
        assert "正IC子期比例" in summary.columns
        assert "子期数" in summary.columns

    def test_backward_compute_summary_values(self):
        """汇总统计值应正确计算。"""
        node = self._make_mock_node()

        mock_data = np.array([{
            'test_factor': pd.DataFrame({
                'period': ['2020', '2021', '2022'],
                'IC均值': [0.04, 0.05, 0.03],
                'IC标准差': [0.02, 0.025, 0.018],
                'ICIR': [2.0, 2.0, 1.67],
                't统计量': [3.46, 3.46, 2.87],
                '胜率': [0.65, 0.70, 0.60],
                '有效期数': [12, 12, 12],
                '平均截面宽度': [3000, 3000, 3000],
            })
        }], dtype=object)

        output = node.backward_compute(path=[], bwd_data_list=[mock_data], context=None)
        summary = output["汇总"]

        # 全期 IC 均值 = (0.04 + 0.05 + 0.03) / 3 = 0.04
        assert summary.iloc[0]["全期IC均值"] == pytest.approx(0.04, abs=1e-6)

        # 正 IC 子期比例 = 3/3 = 1.0（所有子期 IC 均值 > 0）
        assert summary.iloc[0]["正IC子期比例"] == pytest.approx(1.0)

        # 子期数 = 3
        assert summary.iloc[0]["子期数"] == 3

    def test_backward_compute_empty_data(self):
        """空数据应返回空 DataFrame。"""
        node = self._make_mock_node()

        mock_data = np.array([{}], dtype=object)

        output = node.backward_compute(path=[], bwd_data_list=[mock_data], context=None)
        assert output["统计数据"].empty
        assert output["汇总"].empty


# ============================================================
# 图表生成测试
# ============================================================


class TestNodeCharts:
    """节点图表生成测试。"""

    def test_incremental_ic_chart(self):
        """IncrementalICNode 图表应能正常生成。"""
        from QSExt.LLMFactor.evaluation.nodes.incremental_ic_node import IncrementalICNode

        dates = pd.date_range('2020-01-01', periods=24, freq='ME')
        output = {
            "IC": pd.DataFrame(
                np.random.randn(24, 1) * 0.02 + 0.04,
                index=dates,
                columns=['test_factor'],
            ),
            "最大相关性": pd.DataFrame(
                np.random.rand(24, 1) * 0.3 + 0.2,
                index=dates,
                columns=['test_factor'],
            ),
            "IC的移动平均": pd.DataFrame(
                np.random.randn(24, 1) * 0.02 + 0.04,
                index=dates,
                columns=['test_factor'],
            ),
        }

        fig = IncrementalICNode.genMatplotlibFig(output)
        assert fig is not None
        import matplotlib.pyplot as plt
        plt.close(fig)

    def test_size_stratified_chart(self):
        """SizeStratifiedAlphaNode 图表应能正常生成。"""
        from QSExt.LLMFactor.evaluation.nodes.size_stratified_node import SizeStratifiedAlphaNode

        output = {
            "统计数据": pd.DataFrame({
                "G0 年化收益": [0.08],
                "G0 Alpha": [0.06],
                "G0 t统计量": [2.5],
                "G1 年化收益": [0.10],
                "G1 Alpha": [0.08],
                "G1 t统计量": [3.0],
                "G2 年化收益": [0.12],
                "G2 Alpha": [0.10],
                "G2 t统计量": [3.5],
            }, index=['test_factor']),
        }

        fig = SizeStratifiedAlphaNode.genMatplotlibFig(output)
        assert fig is not None
        import matplotlib.pyplot as plt
        plt.close(fig)

    def test_sub_period_chart(self):
        """SubPeriodNode 图表应能正常生成。"""
        from QSExt.LLMFactor.evaluation.nodes.sub_period_node import SubPeriodNode

        output = {
            "统计数据": pd.DataFrame({
                'period': ['2020', '2021', '2022'],
                'IC均值': [0.04, 0.05, 0.03],
                'IC标准差': [0.02, 0.025, 0.018],
                'ICIR': [2.0, 2.0, 1.67],
                't统计量': [3.46, 3.46, 2.87],
                '胜率': [0.65, 0.70, 0.60],
                '有效期数': [12, 12, 12],
            }),
        }

        fig = SubPeriodNode.genMatplotlibFig(output)
        assert fig is not None
        import matplotlib.pyplot as plt
        plt.close(fig)

    def test_sub_period_chart_empty(self):
        """空数据的图表应能正常处理。"""
        from QSExt.LLMFactor.evaluation.nodes.sub_period_node import SubPeriodNode

        output = {
            "统计数据": pd.DataFrame(),
        }

        fig = SubPeriodNode.genMatplotlibFig(output)
        assert fig is not None
        import matplotlib.pyplot as plt
        plt.close(fig)


# ============================================================
# 报告生成测试
# ============================================================


class TestNodeReports:
    """节点报告生成测试。"""

    def test_incremental_ic_report(self):
        """IncrementalICNode 报告应能正常生成。"""
        from QSExt.LLMFactor.evaluation.nodes.incremental_ic_node import IncrementalICNode

        dates = pd.date_range('2020-01-01', periods=10, freq='ME')
        output = {
            "IC": pd.DataFrame(
                np.random.randn(10, 1) * 0.02 + 0.04,
                index=dates,
                columns=['test_factor'],
            ),
            "最大相关性": pd.DataFrame(
                np.random.rand(10, 1) * 0.3 + 0.2,
                index=dates,
                columns=['test_factor'],
            ),
            "IC的移动平均": pd.DataFrame(
                np.random.randn(10, 1) * 0.02 + 0.04,
                index=dates,
                columns=['test_factor'],
            ),
            "统计数据": pd.DataFrame({
                "增量IC均值": [0.04],
                "标准差": [0.02],
                "IC_IR": [2.0],
                "增量IC t统计量": [3.46],
                "最大相关性均值": [0.35],
                "有效期数": [10],
            }, index=['test_factor']),
        }

        html = IncrementalICNode.genOutputReport(output)
        assert isinstance(html, str)
        assert len(html) > 0
        assert "data:image/png;base64," in html

    def test_size_stratified_report(self):
        """SizeStratifiedAlphaNode 报告应能正常生成。"""
        from QSExt.LLMFactor.evaluation.nodes.size_stratified_node import SizeStratifiedAlphaNode

        output = {
            "统计数据": pd.DataFrame({
                "G0 年化收益": [0.08],
                "G0 Alpha": [0.06],
                "G0 t统计量": [2.5],
                "G1 年化收益": [0.10],
                "G1 Alpha": [0.08],
                "G1 t统计量": [3.0],
            }, index=['test_factor']),
        }

        html = SizeStratifiedAlphaNode.genOutputReport(output)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_sub_period_report(self):
        """SubPeriodNode 报告应能正常生成。"""
        from QSExt.LLMFactor.evaluation.nodes.sub_period_node import SubPeriodNode

        output = {
            "统计数据": pd.DataFrame({
                'period': ['2020', '2021'],
                'IC均值': [0.04, 0.05],
                'IC标准差': [0.02, 0.025],
                'ICIR': [2.0, 2.0],
                't统计量': [3.46, 3.46],
                '胜率': [0.65, 0.70],
                '有效期数': [12, 12],
            }),
            "汇总": pd.DataFrame({
                "因子": ["test_factor"],
                "全期IC均值": [0.045],
                "子期IC标准差": [0.005],
                "子期ICIR": [9.0],
                "正IC子期比例": [1.0],
                "子期数": [2],
            }),
        }

        html = SubPeriodNode.genOutputReport(output)
        assert isinstance(html, str)
        assert len(html) > 0
