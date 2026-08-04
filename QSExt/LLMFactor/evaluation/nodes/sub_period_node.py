# -*- coding: utf-8 -*-
"""子期稳健性评测节点（BTNode）。

基于 CalcSubPeriodStats 算子的输出，生成评测报告。
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
from QSExt.LLMFactor.evaluation.operators.sub_period import CalcSubPeriodStats


def _format_percentage(x, pos):
    return '%.2f%%' % (x * 100)


def _format_pandas_percentage(x):
    return '{0:.2f}%'.format(x * 100)


class SubPeriodNode(BTNode):
    """子期稳健性评测节点。

    基于 CalcSubPeriodStats 算子的输出，计算统计指标并生成报告。

    输出：
        - 统计数据: DataFrame（各子期 IC、ICIR、t统计量、胜率）
        - 汇总统计: 全期统计 + 子期间一致性指标
    """

    class __QS_ArgClass__(BTNode.__QS_ArgClass__):
        Name: str = Field(default="子期稳健性", frozen=True, title="名称")
        FactorNameList: Optional[List[str]] = Field(default=None, frozen=True, title="因子列表")

    def __init__(self, stats: Any, args: dict = {}, config_file: Optional[str] = None, **kwargs):
        super().__init__(deps=[stats], args=args, config_file=config_file, **kwargs)

    @staticmethod
    def genMatplotlibFig(output: dict, file_path: Optional[str] = None) -> Figure:
        """生成子期 IC 柱状图 + 胜率折线图。"""
        stats = output["统计数据"]

        if stats.empty:
            Fig = Figure(figsize=(12, 4))
            ax = Fig.add_subplot(111)
            ax.text(0.5, 0.5, "无数据", ha='center', va='center', transform=ax.transAxes)
            return Fig

        Fig = Figure(figsize=(14, 6))

        # IC 柱状图
        ax1 = Fig.add_subplot(1, 2, 1)
        x = np.arange(len(stats))
        ax1.bar(x, stats["IC均值"].values, color="steelblue", alpha=0.7, label="IC均值")

        # 添加误差线（标准差）
        if "IC标准差" in stats.columns:
            ax1.errorbar(x, stats["IC均值"].values, yerr=stats["IC标准差"].values,
                        fmt='none', ecolor='gray', capsize=3)

        ax1.set_xticks(x)
        ax1.set_xticklabels(stats["period"].values, rotation=45, ha='right')
        ax1.set_ylabel("IC")
        ax1.set_title("各子期 IC")
        ax1.legend()
        ax1.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
        ax1.yaxis.set_major_formatter(FuncFormatter(_format_percentage))

        # 胜率 + t 统计柱状图
        ax2 = Fig.add_subplot(1, 2, 2)
        ax2.bar(x, stats["胜率"].values, color="steelblue", alpha=0.7, label="胜率")
        ax2.set_xticks(x)
        ax2.set_xticklabels(stats["period"].values, rotation=45, ha='right')
        ax2.set_ylabel("胜率")
        ax2.set_title("各子期胜率")
        ax2.set_ylim(0, 1)
        ax2.axhline(y=0.5, color='red', linestyle='--', linewidth=1, label='50%')
        ax2.legend()
        ax2.yaxis.set_major_formatter(FuncFormatter(_format_percentage))

        # t 统计折线图（右轴）
        if "t统计量" in stats.columns:
            ax2_right = ax2.twinx()
            ax2_right.plot(x, stats["t统计量"].values, color="indianred", lw=2, marker='o', label='t统计量')
            ax2_right.set_ylabel("t 统计量")
            ax2_right.axhline(y=3.0, color='green', linestyle=':', linewidth=1, label='t=3.0')
            ax2_right.legend(loc='upper right')

        Fig.tight_layout()
        if file_path is not None:
            Fig.savefig(file_path, dpi=150, bbox_inches='tight')
        return Fig

    @staticmethod
    def genOutputReport(output: dict) -> str:
        """生成 HTML 报告内容。"""
        HTML = ""

        # 汇总统计
        if "汇总" in output and not output["汇总"].empty:
            HTML += "<h4>汇总统计</h4>"
            n_cols = len(output["汇总"].columns)
            # 汇总表的列：因子, 全期IC均值, 子期IC标准差, 子期ICIR, 正IC子期比例, 子期数
            base_formatters = [
                lambda x: str(x),           # 因子
                _format_pandas_percentage,  # 全期IC均值
                lambda x: '{0:.4f}'.format(x),  # 子期IC标准差
                lambda x: '{0:.2f}'.format(x),  # 子期ICIR
                _format_pandas_percentage,  # 正IC子期比例
                lambda x: '{0:.0f}'.format(x),  # 子期数
            ]
            Formatters = (base_formatters * ((n_cols // 6) + 1))[:n_cols]
            iHTML = output["汇总"].to_html(formatters=Formatters, index=False)
            Pos = iHTML.find(">")
            HTML += iHTML[:Pos] + ' align="center"' + iHTML[Pos:]

        # 子期统计表
        if "统计数据" in output and not output["统计数据"].empty:
            HTML += "<h4>各子期统计</h4>"
            n_cols = len(output["统计数据"].columns)
            # 子期表的列：period, IC均值, IC标准差, ICIR, t统计量, 胜率, 有效期数, 平均截面宽度, factor
            base_formatters = [
                lambda x: str(x),               # period
                _format_pandas_percentage,      # IC均值
                _format_pandas_percentage,      # IC标准差
                lambda x: '{0:.4f}'.format(x),  # ICIR
                lambda x: '{0:.2f}'.format(x),  # t统计量
                _format_pandas_percentage,      # 胜率
                lambda x: '{0:.0f}'.format(x),  # 有效期数
                lambda x: '{0:.0f}'.format(x),  # 平均截面宽度
                lambda x: str(x),               # factor
            ]
            Formatters = (base_formatters * ((n_cols // 9) + 1))[:n_cols]
            iHTML = output["统计数据"].to_html(formatters=Formatters, index=False)
            Pos = iHTML.find(">")
            HTML += iHTML[:Pos] + ' align="center"' + iHTML[Pos:]

        # 图表
        Fig = SubPeriodNode.genMatplotlibFig(output)
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
        HTML += f"<li>拆分频率: {self._QSArgs.ModelArgs.get('freq', 'yearly')}</li>"
        if self._QSArgs.FactorNameList:
            HTML += f"<li>因子列表: {self._QSArgs.FactorNameList}</li>"
        HTML += "</ul>"
        HTML += "\n" + SubPeriodNode.genOutputReport(output=output)
        return HTML

    def init_compute(self, path, init_data, context):
        InitData = super().init_compute(path=path, init_data=init_data, context=context)
        from QuantStudio.Factor.Factor import FactorInitData
        return [FactorInitData(DTRange=iInitData.DTRange, SectionIDs=None) for iInitData in InitData]

    def forward_compute(self, path, fwd_data, context):
        from QuantStudio.Factor.Factor import FactorLocalContext
        return [
            FactorLocalContext(
                DTs=fwd_data.DTs,
                IDs=context.NodeState[iDep.QSID]["section_ids"],
                PIDs=context.PIDList,
            ) for iDep in self.Deps
        ], fwd_data

    def backward_compute(self, path, bwd_data_list, context, local_context=None) -> dict:
        """处理算子输出，整理为可读的统计表。"""
        RawData = bwd_data_list[0]

        # 解析数据
        if isinstance(RawData, np.ndarray) and RawData.dtype == object:
            all_stats = RawData[0]
        elif isinstance(RawData, dict):
            all_stats = RawData
        else:
            all_stats = {}

        # 合并所有因子的统计
        combined_stats = []
        for factor_name, stats_df in all_stats.items():
            if isinstance(stats_df, pd.DataFrame) and not stats_df.empty:
                stats_df = stats_df.copy()
                stats_df["factor"] = factor_name
                combined_stats.append(stats_df)

        if combined_stats:
            combined_df = pd.concat(combined_stats, ignore_index=True)
        else:
            combined_df = pd.DataFrame()

        # 计算汇总统计
        summary_rows = []
        for factor_name, stats_df in all_stats.items():
            if isinstance(stats_df, pd.DataFrame) and not stats_df.empty:
                ic_mean = stats_df["IC均值"].mean()
                ic_std = stats_df["IC均值"].std()
                summary_rows.append({
                    "因子": factor_name,
                    "全期IC均值": ic_mean,
                    "子期IC标准差": ic_std,
                    "子期ICIR": ic_mean / ic_std if ic_std > 0 else 0,
                    "正IC子期比例": (stats_df["IC均值"] > 0).mean(),
                    "子期数": len(stats_df),
                })

        summary_df = pd.DataFrame(summary_rows) if summary_rows else pd.DataFrame()

        Output = {
            "统计数据": combined_df,
            "汇总": summary_df,
        }

        # 生成报告
        if self._QSArgs.GenReport:
            Output["Report"] = self.genReport(Output)

        return Output
