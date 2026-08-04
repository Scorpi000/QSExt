# -*- coding: utf-8 -*-
"""增量 IC 评测节点（BTNode）。

基于 CalcIncrementalIC 算子的输出，生成评测报告。
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
from QSExt.LLMFactor.evaluation.operators.incremental_ic import CalcIncrementalIC


def _format_percentage(x, pos):
    return '%.2f%%' % (x * 100)


def _format_pandas_percentage(x):
    return '{0:.2f}%'.format(x * 100)


class IncrementalICNode(BTNode):
    """增量 IC 评测节点。

    基于 CalcIncrementalIC 算子的输出，计算统计指标并生成报告。

    输出：
        - IC: 增量 IC 时间序列 DataFrame
        - 最大相关性: 与已有因子的最大相关性时间序列
        - 截面宽度: 有效样本数时间序列
        - 统计数据: DataFrame（均值、标准差、IC_IR、t 统计量、最大相关性均值）
    """

    class __QS_ArgClass__(BTNode.__QS_ArgClass__):
        Name: str = Field(default="增量 IC 检验", frozen=True, title="名称")
        FactorNameList: Optional[List[str]] = Field(default=None, frozen=True, title="因子列表")
        RollingAvgPeriod: int = Field(default=12, frozen=True, title="移动平均期数")

    def __init__(self, ic: Any, args: dict = {}, config_file: Optional[str] = None, **kwargs):
        super().__init__(deps=[ic], args=args, config_file=config_file, **kwargs)

    @staticmethod
    def genMatplotlibFig(output: dict, file_path: Optional[str] = None) -> Figure:
        """生成增量 IC 柱状图 + 移动平均线 + 最大相关性折线图。"""
        ic_data = output["IC"]
        n_factors = ic_data.shape[1]
        nRow = n_factors // 3 + (n_factors % 3 != 0)
        nCol = min(3, n_factors)

        Fig = Figure(figsize=(min(32, 16 + (nCol - 1) * 8), 8 * nRow))
        xData = np.arange(0, ic_data.shape[0])
        xTicks = np.arange(0, ic_data.shape[0], max(1, int(ic_data.shape[0] / 10)))
        xTickLabels = [ic_data.index[i].strftime("%Y-%m-%d") for i in xTicks if i < len(ic_data.index)]
        yMajorFormatter = FuncFormatter(_format_percentage)

        for i in range(n_factors):
            iAxes = Fig.add_subplot(nRow, nCol, i + 1)
            iAxes.yaxis.set_major_formatter(yMajorFormatter)

            # IC 柱状图
            iAxes.bar(xData, ic_data.iloc[:, i].values, label="增量IC", color="steelblue", alpha=0.7)

            # 移动平均线
            if "IC的移动平均" in output:
                iAxes.plot(xData, output["IC的移动平均"].iloc[:, i].values,
                          label="IC移动平均", color="indianred", lw=2.5)

            # 最大相关性（右轴）
            if "最大相关性" in output:
                iRightAxes = iAxes.twinx()
                iRightAxes.plot(xData, output["最大相关性"].iloc[:, i].values,
                               label="最大相关性", color="green", lw=1.5, linestyle="--")
                iRightAxes.set_ylim(0, 1)
                iRightAxes.legend(loc="upper right")

            iAxes.set_xticks(xTicks[:len(xTickLabels)])
            iAxes.set_xticklabels(xTickLabels[:len(xTicks)], rotation=45, ha='right')
            iAxes.legend(loc="upper left")
            iAxes.set_title(ic_data.columns[i] if i < len(ic_data.columns) else f"Factor_{i}")
            iAxes.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)

        Fig.tight_layout()
        if file_path is not None:
            Fig.savefig(file_path, dpi=150, bbox_inches='tight')
        return Fig

    @staticmethod
    def genOutputReport(output: dict) -> str:
        """生成 HTML 报告内容。"""
        HTML = ""

        # 统计表格
        Formatters = [
            _format_pandas_percentage, _format_pandas_percentage,
            lambda x: '{0:.4f}'.format(x), lambda x: '{0:.2f}'.format(x),
            _format_pandas_percentage, lambda x: '{0:.0f}'.format(x),
        ]
        iHTML = output["统计数据"].to_html(formatters=Formatters[:len(output["统计数据"].columns)])
        Pos = iHTML.find(">")
        HTML += iHTML[:Pos] + ' align="center"' + iHTML[Pos:]

        # 图表
        Fig = IncrementalICNode.genMatplotlibFig(output)
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
        if isinstance(getattr(self.Deps[0], "Operator", None), CalcIncrementalIC):
            ModelArgs = self.Deps[0].Operator._QSArgs.ModelArgs
            HTML += f"<li>相关性方法: {ModelArgs.get('corr_method', 'spearman')}</li>"
            HTML += f"<li>回溯期数: {ModelArgs.get('period_lookback', 1)}</li>"
            HTML += f"<li>基准因子数: {ModelArgs.get('n_base_factors', 0)}</li>"
        HTML += f"<li>移动平均期数: {self._QSArgs.RollingAvgPeriod}</li>"
        HTML += "</ul>"
        HTML += "\n" + IncrementalICNode.genOutputReport(output=output)
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
        """处理算子输出，计算统计指标。"""
        RawData = bwd_data_list[0].dropna(how="all", axis=0)

        # 分离 IC、MaxCorrelation、Breadth
        IC = RawData.map(lambda x: x[0] if pd.notnull(x) else np.nan)
        MaxCorr = RawData.map(lambda x: x[1] if pd.notnull(x) else np.nan)
        Breadth = RawData.map(lambda x: x[2] if pd.notnull(x) else np.nan)

        # 设置列名
        if self._QSArgs.FactorNameList:
            FactorNameList = self._QSArgs.FactorNameList
        else:
            FactorNameList = IC.columns.tolist()
        IC.columns = MaxCorr.columns = Breadth.columns = FactorNameList
        Breadth = Breadth.reindex(index=IC.index)
        MaxCorr = MaxCorr.reindex(index=IC.index)

        Output = {
            "IC": IC,
            "最大相关性": MaxCorr,
            "截面宽度": Breadth,
        }

        # 移动平均
        Output["IC的移动平均"] = Output["IC"].copy()
        for i in range(Output["IC"].shape[0]):
            if i < self._QSArgs.RollingAvgPeriod - 1:
                Output["IC的移动平均"].iloc[i, :] = np.nan
            else:
                Output["IC的移动平均"].iloc[i, :] = (
                    Output["IC"].iloc[i - self._QSArgs.RollingAvgPeriod + 1:i + 1, :].mean()
                )

        # 统计数据
        Output["统计数据"] = pd.DataFrame(index=Output["IC"].columns)
        Output["统计数据"]["增量IC均值"] = Output["IC"].mean()
        Output["统计数据"]["标准差"] = Output["IC"].std()
        Output["统计数据"]["IC_IR"] = Output["统计数据"]["增量IC均值"] / Output["统计数据"]["标准差"]
        Output["统计数据"]["增量IC t统计量"] = np.nan
        Output["统计数据"]["最大相关性均值"] = Output["最大相关性"].mean()
        Output["统计数据"]["平均截面宽度"] = Output["截面宽度"].mean()
        Output["统计数据"]["有效期数"] = 0.0

        for iFactor in Output["IC"]:
            Output["统计数据"].loc[iFactor, "有效期数"] = pd.notnull(Output["IC"][iFactor]).sum()

        Output["统计数据"]["增量IC t统计量"] = (
            Output["统计数据"]["有效期数"] ** 0.5 * Output["统计数据"]["IC_IR"]
        )

        # 生成报告
        if self._QSArgs.GenReport:
            Output["Report"] = self.genReport(Output)

        return Output
