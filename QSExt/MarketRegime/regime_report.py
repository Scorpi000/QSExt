# coding=utf-8
"""市场状态适应性分析回测报告节点。

将 StrategyRegimeAnalyzer 包装为 BTNode，接入 QuantStudio 回测计算图。
"""
from __future__ import annotations

import base64
from io import BytesIO
from typing import Optional, List, Any

import numpy as np
import pandas as pd
from pydantic import Field
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from QuantStudio.BackTest.BackTestModel import BTNode
from QuantStudio.Factor.Factor import Factor, FactorInitData, FactorLocalContext
from QSExt.MarketRegime.strategy_analysis import StrategyRegimeAnalyzer
from QSExt.MarketRegime.transition import CUSUMDetector, KSTestDetector


def _fmt_pct(x, pos=None):
    return '%.2f%%' % (x * 100)


class RegimePerformanceReport(BTNode):
    """市场状态适应性分析报告。

    消费策略净值 Factor 和市场状态标签 Factor，输出各状态下的表现统计、
    适应性热力图和最小状态表现 (MRP)。

    Args:
        nv: 策略净值 Factor，DataFrame(index=dts, columns=ids)，取第一列。
        regime_label: 市场状态标签 Factor，DataFrame(index=dts, columns=ids)，
            值为状态标签字符串。多列时每列代表一个状态维度。
        args: 参数集，支持 ``GenReport``、``HeatmapFreq``、``Dimension``、
            ``TransitionDetector``（可选值: ``"default"`` / ``"CUSUM"`` / ``"KS"``）。
    """

    class __QS_ArgClass__(BTNode.__QS_ArgClass__):
        Name: str = Field(default="状态适应性分析", frozen=True, title="名称")
        HeatmapFreq: str = Field(default="Q", frozen=True, title="热力图频率")
        Dimension: Optional[str] = Field(default=None, frozen=True, title="状态维度")
        TransitionDetector: str = Field(default="default", frozen=True,
                                        title="转换检测器")

    def __init__(self, nv: Factor, regime_label: Factor,
                 args: dict = {}, config_file: Optional[str] = None, **kwargs):
        super().__init__(deps=[nv, regime_label], args=args,
                         config_file=config_file, **kwargs)

    # ------------------------------------------------------------------
    # init / forward
    # ------------------------------------------------------------------

    def init_compute(self, path: List[str], init_data: FactorInitData,
                     context) -> List[FactorInitData]:
        InitData = super().init_compute(path=path, init_data=init_data,
                                        context=context)
        return [FactorInitData(DTRange=iInitData.DTRange, SectionIDs=context.SectionIDs)
                for iInitData in InitData]

    def forward_compute(self, path: List[str], fwd_data, context):
        # 为每个 dep 构造 FactorLocalContext
        # 优先使用 fwd_data 中的 IDs，回退到 context.SectionIDs
        ids = getattr(fwd_data, 'IDs', None) or context.SectionIDs
        return [
            FactorLocalContext(
                DTs=fwd_data.DTs,
                IDs=context.NodeState.get(iDep.QSID, {}).get("section_ids", ids),
                PIDs=context.PIDList,
            ) for iDep in self.Deps
        ], fwd_data

    # ------------------------------------------------------------------
    # backward
    # ------------------------------------------------------------------

    def backward_compute(self, path: List[str], bwd_data_list: List[Any],
                         context, local_context=None) -> dict:
        # 提取净值序列 → 日收益率
        nv_df: pd.DataFrame = bwd_data_list[0]
        nv_series = nv_df.iloc[:, 0].dropna()
        returns = nv_series.pct_change().dropna()

        # 提取标签
        label_df: pd.DataFrame = bwd_data_list[1]

        # 对齐索引
        common_idx = returns.index.intersection(label_df.index)
        returns = returns.loc[common_idx]
        label_df = label_df.loc[common_idx]

        # 分析
        analyzer = StrategyRegimeAnalyzer(returns, label_df)
        dimension = self._QSArgs.Dimension

        Output = {}

        perf = analyzer.compute_regime_performance(dimension=dimension)
        Output["各状态表现"] = perf

        heatmap = analyzer.compute_adaptation_heatmap(
            dimension=dimension, freq=self._QSArgs.HeatmapFreq)
        Output["适应性热力图"] = heatmap

        mrp_dict = analyzer.compute_mrp(dimension=dimension)
        # 将 regime_sharpes dict 展开为 DataFrame 便于展示
        mrp_summary = pd.DataFrame([{
            "MRP": mrp_dict["mrp"],
            "最差状态": mrp_dict["worst_regime"],
            "最差夏普": mrp_dict["worst_sharpe"],
            "MRP/整体夏普": mrp_dict["mrp_vs_total"],
        }])
        regime_sharpes = pd.DataFrame(
            list(mrp_dict["regime_sharpes"].items()),
            columns=["状态", "夏普比率"],
        )
        Output["MRP"] = mrp_summary
        Output["各状态夏普"] = regime_sharpes

        # 转换冲击分析
        detector_name = getattr(self._QSArgs, "TransitionDetector", "default")
        detector = None
        if detector_name == "CUSUM":
            detector = CUSUMDetector()
        elif detector_name == "KS":
            detector = KSTestDetector()
        # "default" → detector=None，使用相邻标签变化检测

        transition_result = analyzer.transition_impact_analysis(
            dimension=dimension, detector=detector)
        Output["转换冲击"] = transition_result

        if self._QSArgs.GenReport:
            Output["Report"] = self.genReport(Output)

        return Output

    # ------------------------------------------------------------------
    # report
    # ------------------------------------------------------------------

    @staticmethod
    def genMatplotlibFig(output: dict, file_path: Optional[str] = None) -> Figure:
        """生成状态表现柱状图 + 热力图。"""
        perf = output.get("各状态表现")
        heatmap = output.get("适应性热力图")

        has_perf = perf is not None and not perf.empty
        has_heatmap = heatmap is not None and not heatmap.empty
        n_col = int(has_perf) + int(has_heatmap)
        if n_col == 0:
            Fig = Figure(figsize=(12, 4))
            ax = Fig.add_subplot(111)
            ax.text(0.5, 0.5, "无数据", ha='center', va='center',
                    transform=ax.transAxes)
            return Fig

        Fig = Figure(figsize=(7 * n_col, 6))
        col_idx = 1

        if has_perf:
            ax = Fig.add_subplot(1, n_col, col_idx)
            x = np.arange(len(perf))
            width = 0.35
            ax.bar(x - width / 2, perf["年化收益"].values, width,
                   label="年化收益", color="steelblue", alpha=0.8)
            ax.bar(x + width / 2, perf["年化波动"].values, width,
                   label="年化波动", color="indianred", alpha=0.8)
            ax.set_xticks(x)
            ax.set_xticklabels(perf.index, rotation=30, ha='right')
            ax.set_title("各状态收益与波动")
            ax.legend()
            ax.yaxis.set_major_formatter(FuncFormatter(_fmt_pct))
            ax.axhline(y=0, color='gray', linewidth=0.5)
            col_idx += 1

        if has_heatmap:
            ax = Fig.add_subplot(1, n_col, col_idx)
            # heatmap: index=状态, columns=时间段
            data = heatmap.values.astype(float)
            im = ax.imshow(data, aspect='auto', cmap='RdYlGn')
            ax.set_xticks(np.arange(len(heatmap.columns)))
            ax.set_xticklabels([str(c) for c in heatmap.columns],
                               rotation=45, ha='right', fontsize=8)
            ax.set_yticks(np.arange(len(heatmap.index)))
            ax.set_yticklabels(heatmap.index)
            ax.set_title("适应性热力图（年化收益）")
            Fig.colorbar(im, ax=ax, shrink=0.8)
            # 在格子中标注数值
            for i in range(data.shape[0]):
                for j in range(data.shape[1]):
                    v = data[i, j]
                    if not np.isnan(v):
                        ax.text(j, i, f'{v:.1%}', ha='center', va='center',
                                fontsize=7)

        Fig.tight_layout()
        if file_path is not None:
            Fig.savefig(file_path, dpi=150, bbox_inches='tight')
        return Fig

    @staticmethod
    def genOutputReport(output: dict) -> str:
        """生成 HTML 报告内容。"""
        HTML = ""

        # 各状态表现表
        perf = output.get("各状态表现")
        if perf is not None and not perf.empty:
            HTML += "<h4>各状态表现</h4>"
            fmt_perf = perf.copy()
            for col in ["年化收益", "年化波动", "最大回撤", "胜率", "占比"]:
                if col in fmt_perf.columns:
                    fmt_perf[col] = fmt_perf[col].apply(
                        lambda x: f"{x:.2%}" if pd.notnull(x) else "")
            if "夏普比率" in fmt_perf.columns:
                fmt_perf["夏普比率"] = fmt_perf["夏普比率"].apply(
                    lambda x: f"{x:.2f}" if pd.notnull(x) else "")
            iHTML = fmt_perf.to_html()
            Pos = iHTML.find(">")
            HTML += iHTML[:Pos] + ' align="center"' + iHTML[Pos:]

        # MRP 表
        mrp = output.get("MRP")
        if mrp is not None and not mrp.empty:
            HTML += "<h4>最小状态表现 (MRP)</h4>"
            fmt_mrp = mrp.copy()
            for col in ["MRP", "最差夏普", "MRP/整体夏普"]:
                if col in fmt_mrp.columns:
                    fmt_mrp[col] = fmt_mrp[col].apply(
                        lambda x: f"{x:.2f}" if pd.notnull(x) else "")
            iHTML = fmt_mrp.to_html(index=False)
            Pos = iHTML.find(">")
            HTML += iHTML[:Pos] + ' align="center"' + iHTML[Pos:]

        # 各状态夏普
        rs = output.get("各状态夏普")
        if rs is not None and not rs.empty:
            HTML += "<h4>各状态夏普比率</h4>"
            fmt_rs = rs.copy()
            fmt_rs["夏普比率"] = fmt_rs["夏普比率"].apply(
                lambda x: f"{x:.2f}" if pd.notnull(x) else "")
            iHTML = fmt_rs.to_html(index=False)
            Pos = iHTML.find(">")
            HTML += iHTML[:Pos] + ' align="center"' + iHTML[Pos:]

        # 转换冲击分析
        ti = output.get("转换冲击")
        if ti is not None:
            transitions = ti.get("transitions")
            if transitions is not None and not transitions.empty:
                HTML += "<h4>状态转换点</h4>"
                iHTML = transitions.to_html(index=False)
                Pos = iHTML.find(">")
                HTML += iHTML[:Pos] + ' align="center"' + iHTML[Pos:]

            window_df = ti.get("window_returns")
            if window_df is not None and not window_df.empty:
                HTML += "<h4>转换窗口期收益</h4>"
                fmt_wr = window_df.copy()
                for col in fmt_wr.columns:
                    fmt_wr[col] = fmt_wr[col].apply(
                        lambda x: f"{x:.2%}" if pd.notnull(x) else "")
                iHTML = fmt_wr.to_html()
                Pos = iHTML.find(">")
                HTML += iHTML[:Pos] + ' align="center"' + iHTML[Pos:]

            direction_df = ti.get("direction_impact")
            if direction_df is not None and not direction_df.empty:
                HTML += "<h4>方向敏感性</h4>"
                fmt_di = direction_df.copy()
                if "平均转换后收益" in fmt_di.columns:
                    fmt_di["平均转换后收益"] = fmt_di["平均转换后收益"].apply(
                        lambda x: f"{x:.2%}" if pd.notnull(x) else "")
                iHTML = fmt_di.to_html()
                Pos = iHTML.find(">")
                HTML += iHTML[:Pos] + ' align="center"' + iHTML[Pos:]

            loss_ratio = ti.get("transition_loss_ratio")
            if loss_ratio is not None and not np.isnan(loss_ratio):
                HTML += f"<p>转换期亏损占比: <b>{loss_ratio:.2%}</b></p>"

        # 图表
        Fig = RegimePerformanceReport.genMatplotlibFig(output)
        Buffer = BytesIO()
        Fig.savefig(Buffer, bbox_inches='tight')
        PlotData = Buffer.getvalue()
        ImgStr = "data:image/png;base64," + base64.b64encode(PlotData).decode()
        HTML += '<img src="%s">' % ImgStr

        return HTML

    def genReport(self, output: dict) -> str:
        """生成完整 HTML 报告。"""
        HTML = "参数设置: "
        HTML += '<ul align="left">'
        HTML += f"<li>热力图频率: {self._QSArgs.HeatmapFreq}</li>"
        if self._QSArgs.Dimension:
            HTML += f"<li>状态维度: {self._QSArgs.Dimension}</li>"
        detector_name = getattr(self._QSArgs, "TransitionDetector", "default")
        HTML += f"<li>转换检测器: {detector_name}</li>"
        HTML += "</ul>"
        HTML += "\n" + RegimePerformanceReport.genOutputReport(output=output)
        return HTML
