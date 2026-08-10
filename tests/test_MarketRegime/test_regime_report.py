# coding=utf-8
"""RegimePerformanceReport BTNode 测试。

验证通过回测计算图运行 RegimePerformanceReport：
1. 构建净值 Factor + 标签 Factor
2. 通过 Engine.run 执行 BTNode
3. 验证 Output dict 中各 key 的正确性
"""
import sys
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Core.Node import DTLocalContext, DTInitData
from QuantStudio.Factor.Factor import (
    DataFactor, FactorContext, FactorLocalContext, FactorInitData,
)
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QuantStudio.BackTest.BackTestModel import BTReport
from QSExt.MarketRegime.regime_report import RegimePerformanceReport


def _make_test_data():
    """构建测试数据：净值序列 + 牛熊标签。"""
    np.random.seed(42)
    dates = pd.bdate_range('2020-01-01', '2022-12-31')
    n = len(dates)

    # 净值：带牛熊特征的随机游走
    base = np.random.randn(n) * 0.012
    base[dates.year == 2020] += 0.001     # 牛市漂移
    base[dates.year == 2022] -= 0.001     # 熊市漂移
    nav = 1.0 * np.cumprod(1 + base)

    # 标签：按年度分配
    regime = np.full(n, "震荡", dtype=object)
    regime[dates.year == 2020] = "牛市"
    regime[dates.year == 2022] = "熊市"

    return dates, nav, regime


class TestRegimePerformanceReport:
    """RegimePerformanceReport BTNode 集成测试。"""

    def test_backward_compute(self):
        """backward_compute 返回完整的 Output dict。"""
        dates, nav, regime = _make_test_data()
        ids = ["000001"]

        nv_data = pd.DataFrame(nav, index=dates, columns=ids)
        label_data = pd.DataFrame(regime, index=dates, columns=ids)

        f_nv = DataFactor(nv_data, factor_name="策略净值")
        f_label = DataFactor(label_data, factor_name="牛熊状态",
                             args={"DataType": "string"})

        report = RegimePerformanceReport(nv=f_nv, regime_label=f_label)

        # 通过 Engine.run 执行
        ExecEngine = Engine()
        context = FactorContext(
            PID="0", PIDList=["0"],
            DTRuler=dates,
            SectionIDs=ids,
        )
        fwd = FactorLocalContext(DTs=dates, IDs=ids)
        init = FactorInitData(DTRange=(dates[0], dates[-1]), SectionIDs=ids)

        Rslt = ExecEngine.run(
            [report], context,
            fwd_data_list=[fwd], init_data_list=[init],
        )
        output = Rslt[0]

        # 验证 key 存在
        assert "各状态表现" in output, "缺少 '各状态表现'"
        assert "适应性热力图" in output, "缺少 '适应性热力图'"
        assert "MRP" in output, "缺少 'MRP'"
        assert "各状态夏普" in output, "缺少 '各状态夏普'"

        # 验证各状态表现 DataFrame
        perf = output["各状态表现"]
        assert isinstance(perf, pd.DataFrame)
        assert "牛市" in perf.index
        assert "熊市" in perf.index
        assert "年化收益" in perf.columns
        assert "夏普比率" in perf.columns

        # 牛市收益应高于熊市
        assert perf.loc["牛市", "年化收益"] > perf.loc["熊市", "年化收益"], (
            f"牛市({perf.loc['牛市', '年化收益']:.4f}) "
            f"应 > 熊市({perf.loc['熊市', '年化收益']:.4f})"
        )

        # 验证热力图
        heatmap = output["适应性热力图"]
        assert isinstance(heatmap, pd.DataFrame)
        assert len(heatmap.index) >= 2  # 至少牛市/熊市

        # 验证 MRP
        mrp = output["MRP"]
        assert isinstance(mrp, pd.DataFrame)
        assert "MRP" in mrp.columns
        assert "最差状态" in mrp.columns

    def test_gen_report(self):
        """GenReport=True 时生成 HTML 报告。"""
        dates, nav, regime = _make_test_data()
        ids = ["000001"]

        nv_data = pd.DataFrame(nav, index=dates, columns=ids)
        label_data = pd.DataFrame(regime, index=dates, columns=ids)

        f_nv = DataFactor(nv_data, factor_name="策略净值")
        f_label = DataFactor(label_data, factor_name="牛熊状态",
                             args={"DataType": "string"})

        report = RegimePerformanceReport(
            nv=f_nv, regime_label=f_label,
            args={"GenReport": True},
        )

        ExecEngine = Engine()
        context = FactorContext(
            PID="0", PIDList=["0"],
            DTRuler=dates,
            SectionIDs=ids,
        )
        fwd = FactorLocalContext(DTs=dates, IDs=ids)
        init = FactorInitData(DTRange=(dates[0], dates[-1]), SectionIDs=ids)

        Rslt = ExecEngine.run(
            [report], context,
            fwd_data_list=[fwd], init_data_list=[init],
        )
        output = Rslt[0]

        assert "Report" in output, "GenReport=True 时应生成 Report"
        html = output["Report"]
        assert isinstance(html, str)
        assert "<table" in html, "Report 应包含 HTML 表格"
        assert "<img" in html, "Report 应包含图表"

    def test_with_bt_report(self):
        """与 BTReport 聚合报告集成。"""
        dates, nav, regime = _make_test_data()
        ids = ["000001"]

        nv_data = pd.DataFrame(nav, index=dates, columns=ids)
        label_data = pd.DataFrame(regime, index=dates, columns=ids)

        f_nv = DataFactor(nv_data, factor_name="策略净值")
        f_label = DataFactor(label_data, factor_name="牛熊状态",
                             args={"DataType": "string"})

        report_node = RegimePerformanceReport(
            nv=f_nv, regime_label=f_label,
            args={"GenReport": True},
        )

        bt_report = BTReport(bt_node_list=[report_node])

        ExecEngine = Engine()
        context = FactorContext(
            PID="0", PIDList=["0"],
            DTRuler=dates,
            SectionIDs=ids,
        )
        fwd = DTLocalContext(DTs=dates)
        init = DTInitData(DTRange=(dates[0], dates[-1]))

        Rslt = ExecEngine.run(
            [bt_report], context,
            fwd_data_list=[fwd], init_data_list=[init],
        )
        output = Rslt[0]

        assert "Report" in output, "BTReport 应包含聚合 Report"
        assert isinstance(output["Report"], str)

    def test_custom_params(self):
        """自定义 HeatmapFreq 参数。"""
        dates, nav, regime = _make_test_data()
        ids = ["000001"]

        nv_data = pd.DataFrame(nav, index=dates, columns=ids)
        label_data = pd.DataFrame(regime, index=dates, columns=ids)

        f_nv = DataFactor(nv_data, factor_name="策略净值")
        f_label = DataFactor(label_data, factor_name="牛熊状态",
                             args={"DataType": "string"})

        report = RegimePerformanceReport(
            nv=f_nv, regime_label=f_label,
            args={"HeatmapFreq": "Y"},
        )

        ExecEngine = Engine()
        context = FactorContext(
            PID="0", PIDList=["0"],
            DTRuler=dates,
            SectionIDs=ids,
        )
        fwd = FactorLocalContext(DTs=dates, IDs=ids)
        init = FactorInitData(DTRange=(dates[0], dates[-1]), SectionIDs=ids)

        Rslt = ExecEngine.run(
            [report], context,
            fwd_data_list=[fwd], init_data_list=[init],
        )
        output = Rslt[0]

        heatmap = output["适应性热力图"]
        # 频率 Y → 应只有 3 个年度列
        assert len(heatmap.columns) == 3


if __name__ == "__main__":
    sys.exit(
        __import__("pytest").main([__file__, "-v", "-s"])
    )
