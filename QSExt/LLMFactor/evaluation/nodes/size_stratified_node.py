# -*- coding: utf-8 -*-
"""规模分层 Alpha 评测节点（BTNode）。

基于 CalcSizeStratifiedAlpha 算子的输出，生成评测报告。
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
from QSExt.LLMFactor.evaluation.operators.size_stratified import CalcSizeStratifiedAlpha


def _format_percentage(x, pos):
    return '%.2f%%' % (x * 100)


def _format_pandas_percentage(x):
    return '{0:.2f}%'.format(x * 100)


class SizeStratifiedAlphaNode(BTNode):
    """规模分层 Alpha 评测节点。

    基于 CalcSizeStratifiedAlpha 算子的输出，计算统计指标并生成报告。

    输出：
        - 统计数据: DataFrame（各组年化收益、Alpha、t统计量）
        - Alpha图: 各组 Alpha 柱状图
    """

    class __QS_ArgClass__(BTNode.__QS_ArgClass__):
        Name: str = Field(default="规模分层 Alpha", frozen=True, title="名称")
        FactorNameList: Optional[List[str]] = Field(default=None, frozen=True, title="因子列表")
        GroupNum: int = Field(default=5, frozen=True, title="分组数")

    def __init__(self, alpha: Any, args: dict = {}, config_file: Optional[str] = None, **kwargs):
        super().__init__(deps=[alpha], args=args, config_file=config_file, **kwargs)

    @staticmethod
    def genMatplotlibFig(output: dict, file_path: Optional[str] = None) -> Figure:
        """生成各组 Alpha 柱状图。"""
        stats = output["统计数据"]
        group_num = len([c for c in stats.columns if "Alpha" in c])

        Fig = Figure(figsize=(14, 6))

        # Alpha 柱状图
        ax1 = Fig.add_subplot(1, 2, 1)
        alpha_cols = [f"G{i} Alpha" for i in range(group_num) if f"G{i} Alpha" in stats.columns]
        if alpha_cols:
            x = np.arange(len(stats))
            width = 0.8 / len(alpha_cols)
            for i, col in enumerate(alpha_cols):
                ax1.bar(x + i * width, stats[col].values, width, label=col)
            ax1.set_xticks(x + width * len(alpha_cols) / 2)
            ax1.set_xticklabels(stats.index, rotation=45, ha='right')
            ax1.set_ylabel("年化 Alpha")
            ax1.set_title("各组 CAPM Alpha")
            ax1.legend()
            ax1.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
            ax1.yaxis.set_major_formatter(FuncFormatter(_format_percentage))

        # t 统计柱状图
        ax2 = Fig.add_subplot(1, 2, 2)
        t_cols = [f"G{i} t统计量" for i in range(group_num) if f"G{i} t统计量" in stats.columns]
        if t_cols:
            x = np.arange(len(stats))
            width = 0.8 / len(t_cols)
            for i, col in enumerate(t_cols):
                ax2.bar(x + i * width, stats[col].values, width, label=col)
            ax2.set_xticks(x + width * len(t_cols) / 2)
            ax2.set_xticklabels(stats.index, rotation=45, ha='right')
            ax2.set_ylabel("t 统计量")
            ax2.set_title("各组 t 统计量")
            ax2.legend()
            ax2.axhline(y=3.0, color='red', linestyle='--', linewidth=1, label='t=3.0')
            ax2.axhline(y=-3.0, color='red', linestyle='--', linewidth=1)
            ax2.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)

        Fig.tight_layout()
        if file_path is not None:
            Fig.savefig(file_path, dpi=150, bbox_inches='tight')
        return Fig

    @staticmethod
    def genOutputReport(output: dict) -> str:
        """生成 HTML 报告内容。"""
        HTML = ""

        # 统计表格
        n_cols = len(output["统计数据"].columns)
        # 每 3 列一组（年化收益、Alpha、t统计量）
        base_formatters = [
            _format_pandas_percentage,  # 年化收益
            _format_pandas_percentage,  # Alpha
            lambda x: '{0:.2f}'.format(x),  # t统计量
        ]
        # 根据列数扩展 formatters
        Formatters = (base_formatters * ((n_cols // 3) + 1))[:n_cols]
        iHTML = output["统计数据"].to_html(formatters=Formatters)
        Pos = iHTML.find(">")
        HTML += iHTML[:Pos] + ' align="center"' + iHTML[Pos:]

        # 图表
        Fig = SizeStratifiedAlphaNode.genMatplotlibFig(output)
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
        HTML += f"<li>分组数: {self._QSArgs.GroupNum}</li>"
        if self._QSArgs.FactorNameList:
            HTML += f"<li>因子列表: {self._QSArgs.FactorNameList}</li>"
        HTML += "</ul>"
        HTML += "\n" + SizeStratifiedAlphaNode.genOutputReport(output=output)
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
        group_num = self._QSArgs.GroupNum

        # 解析结构化数据
        if isinstance(RawData, np.ndarray):
            data = RawData
        else:
            data = np.array(RawData.tolist()) if hasattr(RawData, 'tolist') else np.array(RawData)

        # 构建统计表
        FactorNameList = self._QSArgs.FactorNameList or [f"Factor_{i}" for i in range(data.shape[0])]
        columns = []
        for g in range(group_num):
            columns.extend([f"G{g} 年化收益", f"G{g} Alpha", f"G{g} t统计量"])

        stats_df = pd.DataFrame(data, index=FactorNameList, columns=columns[:data.shape[1]])

        Output = {
            "统计数据": stats_df,
        }

        # 生成报告
        if self._QSArgs.GenReport:
            Output["Report"] = self.genReport(Output)

        return Output
