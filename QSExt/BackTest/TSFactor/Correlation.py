# coding=utf-8
"""时序因子相关性回测模块

计算因子值与未来收益率之间的滚动时序相关性。
与截面 IC 不同，时序相关性是在单只股票的时间序列上计算的，
反映的是某只股票的因子值与其未来收益之间的时序关系。
"""
import base64
from io import BytesIO
from typing import Optional, Literal, List, Any, Tuple

import numpy as np
import pandas as pd
from pydantic import Field
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from QuantStudio.Core import __QS_Error__
from QuantStudio.Core.Node import DTInitData, DTLocalContext
from QuantStudio.Factor.Factor import Factor, FactorContext, FactorInitData, FactorLocalContext
from QuantStudio.Factor.FactorOperation import PanelOperator, PanelOperation
from QuantStudio.BackTest.BackTestModel import BTNode, ReportNode


def _formatPercentage(x, pos):
    return '%.2f%%' % (x * 100, )


def _formatPandasPercentage(x):
    return '{0:.2f}%'.format(x * 100)


class CalcTimeSeriesCorrelation(PanelOperator):
    """时序相关性算子

    计算因子值与未来收益率之间的滚动时序相关性。
    对每只股票单独计算：corr(factor[t-lag], return[t:t+forecast])。
    """

    def __init__(
        self,
        descriptor_ids: List[str],
        forecast_period: int = 1,
        lag: int = 0,
        summary_window: int = 0,
        min_summary_window: int = 2,
        corr_method: Literal["pearson", "spearman", "kendall"] = "spearman",
        args: dict = {},
        config_file: Optional[str] = None,
        **kwargs,
    ):
        """初始化时序相关性算子

        Args:
            descriptor_ids: 依赖因子的截面 ID 序列（股票列表）
            forecast_period: 预测期数，用未来第几期的收益率
            lag: 滞后期数，用几期前的因子值
            summary_window: 统计窗口长度，0 表示使用扩展窗口（全部历史数据）
            min_summary_window: 最小统计窗口长度
            corr_method: 相关性计算方法
        """
        Arity = args.get("Arity", None) or 1
        Args = {"Name": "calcTimeSeriesCorrelation"} | args | {"DTMode": "多时点", "DataType": "double"}
        Args["ModelArgs"] = {
            "forecast_period": forecast_period,
            "lag": lag,
            "summary_window": summary_window,
            "min_summary_window": min_summary_window,
            "corr_method": corr_method,
        } | Args.get("ModelArgs", {})
        Args["DescriptorSection"] = [args.get("DescriptorSection", [descriptor_ids])[0]] * Arity
        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(self, f: Factor, idt, iid, x: list, args: dict) -> np.ndarray:
        SectionIDs = self._QSArgs.DescriptorSection[0] if self._QSArgs.DescriptorSection[0] else iid
        nDT, nID = len(idt), len(SectionIDs)

        # x[0] = 价格数据 (nDT, nID), x[1:] = 各测试因子的数据 (nDT, nID)
        Price = pd.DataFrame(x[0], columns=SectionIDs, index=idt)
        FactorDataList = x[1:]

        forecast = args["forecast_period"]
        lag = args["lag"]
        summary_window = args["summary_window"]
        min_window = args["min_summary_window"]

        # 计算收益率，并向前移动 forecast 期
        Return = Price.pct_change(fill_method=None).shift(-forecast)

        nFactor = len(FactorDataList)
        Result = np.full((nDT, nFactor), np.nan, dtype=float)

        for i, iFactorData in enumerate(FactorDataList):
            FactorDF = pd.DataFrame(iFactorData, columns=SectionIDs, index=idt).shift(lag)
            CorrList = []
            for jID in SectionIDs:
                ijFactor = FactorDF[jID]
                ijReturn = Return[jID]
                ValidMask = ijFactor.notnull() & ijReturn.notnull()
                ijFactorValid = ijFactor[ValidMask]
                ijReturnValid = ijReturn[ValidMask]
                if len(ijFactorValid) < min_window:
                    CorrList.append(pd.Series(np.nan, index=idt))
                    continue
                if summary_window <= 0:
                    ijCorr = ijFactorValid.expanding(min_periods=min_window).corr(ijReturnValid)
                else:
                    ijCorr = ijFactorValid.rolling(window=summary_window, min_periods=min_window).corr(ijReturnValid)
                CorrList.append(ijCorr.reindex(idt))
            if CorrList:
                CorrMatrix = pd.concat(CorrList, axis=1)
                Result[:, i] = CorrMatrix.mean(axis=1, skipna=True).values

        return Result

    def __call__(
        self,
        *x: Factor,
        price: Factor,
        factor_name_list: Optional[List[str]] = None,
        factor_args: dict = {},
        **kwargs,
    ) -> PanelOperation:
        """将算子作用在若干个测试因子上以产生时序相关性因子

        Args:
            x: 待计算时序相关性的测试因子
            price: 价格因子
            factor_name_list: 测试因子名称列表
            factor_args: 创建时序相关性因子时传递的参数集
            kwargs: 其他入参

        Returns:
            时序相关性因子
        """
        Factors = [price] + list(x)
        if not x:
            raise __QS_Error__("测试因子列表 x 不可为空!")

        factor_args = factor_args.copy()
        if factor_name_list is None:
            factor_name_list = [iFactor.Name for iFactor in x]
            if len(set(factor_name_list)) != len(x):
                PosNum = int(np.log10(max(1, len(x) - 1))) + 1
                factor_name_list = [f"F{str(i).zfill(PosNum)}" for i in range(len(x))]
                self.Logger.info(f"测试因子名称有重复, 自动生成: {factor_name_list}")
        if len(set(factor_name_list)) != len(x):
            raise __QS_Error__(f"因子名称列表长度不等于因子列表长度或有重复!")
        else:
            SortedIdx = np.argsort(factor_name_list)
            if not np.all(SortedIdx == np.arange(len(factor_name_list))):
                self.Logger.warning(f"因子名称列表非升序, 将重新排列")
                x, factor_name_list = [x[i] for i in SortedIdx], [factor_name_list[i] for i in SortedIdx]
        factor_args["SectionIDs"] = factor_name_list
        kwargs["operator_kwargs"] = {"descriptor_ids": self._QSArgs.DescriptorSection[0]} | kwargs.get("operator_kwargs", {})
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)


class TimeSeriesCorrelation(BTNode):
    """时序因子相关性

    计算因子值与未来收益率之间的滚动时序相关性，
    并生成统计数据（平均值、中位数、最小值、最大值）。
    """

    class __QS_ArgClass__(BTNode.__QS_ArgClass__):
        Name: str = Field(default="时序因子相关性", frozen=True, title="名称")
        FactorNameList: Optional[List[str]] = Field(default=None, frozen=True, title="因子列表")
        CorrMethod: str = Field(default="spearman", frozen=True, title="相关性方法")
        ForecastPeriod: int = Field(default=1, frozen=True, title="预测期数")
        Lag: int = Field(default=0, frozen=True, title="滞后期数")

    def __init__(self, ts_corr: Factor, args: dict = {}, config_file: Optional[str] = None, **kwargs):
        return super().__init__(deps=[ts_corr], args=args, config_file=config_file, **kwargs)

    def init_compute(self, path: List[str], init_data: DTInitData, context: FactorContext) -> List[FactorInitData]:
        InitData = super().init_compute(path=path, init_data=init_data, context=context)
        return [FactorInitData(DTRange=iInitData.DTRange) for iInitData in InitData]

    def forward_compute(self, path: List[str], fwd_data: DTLocalContext, context: FactorContext) -> Tuple[List[FactorLocalContext], DTLocalContext]:
        SectionIDs = self.Deps[0].Args.SectionIDs or context.SectionIDs
        return [FactorLocalContext(DTs=fwd_data.DTs, IDs=SectionIDs, PIDs=context.PIDList, SectionIDs=SectionIDs) for _ in self.Deps], DTLocalContext(DTs=fwd_data.DTs)

    def backward_compute(self, path: List[str], bwd_data_list: List[Any], context: FactorContext, local_context: Optional[DTLocalContext] = None) -> dict:
        CorrData = bwd_data_list[0]
        if self._QSArgs.FactorNameList:
            FactorNameList = self._QSArgs.FactorNameList
        else:
            FactorNameList = CorrData.columns.tolist()
        CorrData.columns = FactorNameList
        CorrData = CorrData.dropna(how="all", axis=0)

        Output = {"滚动相关性": CorrData}
        Output["统计数据"] = pd.DataFrame(index=FactorNameList)
        Output["统计数据"]["平均值"] = CorrData.mean()
        Output["统计数据"]["中位数"] = CorrData.median()
        Output["统计数据"]["最小值"] = CorrData.min()
        Output["统计数据"]["最大值"] = CorrData.max()
        Output["统计数据"]["标准差"] = CorrData.std()
        Output["统计数据"]["有效期数"] = CorrData.notnull().sum()
        return Output


class TimeSeriesCorrelationReport(ReportNode):
    """时序因子相关性报告生成节点"""

    class __QS_ArgClass__(ReportNode.__QS_ArgClass__):
        Name: str = Field(default="时序相关性报告", frozen=True, title="名称")

    def __init__(self, ts_corr_node: TimeSeriesCorrelation, args: dict = {}, config_file: Optional[str] = None, **kwargs):
        return super().__init__(deps=[ts_corr_node], args=args, config_file=config_file, **kwargs)

    @staticmethod
    def genMatplotlibFig(output: dict, file_path: Optional[str] = None) -> Figure:
        """生成时序相关性的 matplotlib 图表"""
        iData = output["滚动相关性"]
        nFactor = iData.shape[1]
        xData = np.arange(0, iData.shape[0])
        xTicks = np.arange(0, iData.shape[0], max(1, iData.shape[0] // 10))
        xTickLabels = [iData.index[i].strftime("%Y-%m-%d") for i in xTicks]
        nRow, nCol = nFactor // 3 + (nFactor % 3 != 0), min(3, nFactor)
        Fig = Figure(figsize=(min(32, 16 + (nCol - 1) * 8), 8 * nRow))
        yMajorFormatter = FuncFormatter(_formatPercentage)
        for j in range(nFactor):
            iAxes = Fig.add_subplot(nRow, nCol, j + 1)
            iAxes.yaxis.set_major_formatter(yMajorFormatter)
            iAxes.bar(xData, iData.iloc[:, j].values, color="steelblue")
            iAxes.set_xticks(xTicks)
            iAxes.set_xticklabels(xTickLabels)
            iAxes.set_title(iData.columns[j])
        if file_path is not None:
            Fig.savefig(file_path, dpi=150, bbox_inches='tight')
        return Fig

    @staticmethod
    def genOutputReport(output: dict) -> str:
        """生成时序相关性的 HTML 报告"""
        HTML = ""
        Formatters = [_formatPandasPercentage] * 5 + [lambda x: '{0:.0f}'.format(x)]
        iHTML = output["统计数据"].to_html(formatters=Formatters)
        Pos = iHTML.find(">")
        HTML += iHTML[:Pos] + ' align="center"' + iHTML[Pos:]
        Fig = TimeSeriesCorrelationReport.genMatplotlibFig(output)
        Buffer = BytesIO()
        Fig.savefig(Buffer, bbox_inches='tight')
        PlotData = Buffer.getvalue()
        ImgStr = "data:image/png;base64," + base64.b64encode(PlotData).decode()
        HTML += ('<img src="%s">' % ImgStr)
        return HTML

    def backward_compute(self, path: List[str], bwd_data_list: List[Any], context: FactorContext, local_context: Optional[DTLocalContext] = None) -> dict:
        Output = bwd_data_list[0]
        ts_corr_node = self.Deps[0]
        HTML = "参数设置: "
        HTML += '<ul align="left">'
        HTML += f"<li>相关性方法: {ts_corr_node._QSArgs.CorrMethod}</li>"
        HTML += f"<li>预测期数: {ts_corr_node._QSArgs.ForecastPeriod}</li>"
        HTML += f"<li>滞后期数: {ts_corr_node._QSArgs.Lag}</li>"
        HTML += "</ul>"
        HTML += "\n" + TimeSeriesCorrelationReport.genOutputReport(output=Output)
        Output[self._QSArgs.ReportKey] = HTML
        return Output


def createTimeSeriesCorrelationNodes(
    factors: List[Factor],
    price: Factor,
    descriptor_ids: List[str],
    forecast_period: int = 1,
    lag: int = 0,
    summary_window: int = 0,
    min_summary_window: int = 2,
    corr_method: Literal["pearson", "spearman", "kendall"] = "spearman",
    factor_name_list: Optional[List[str]] = None,
    factor_args: dict = {},
) -> Tuple[CalcTimeSeriesCorrelation, PanelOperation, TimeSeriesCorrelation, TimeSeriesCorrelationReport]:
    """创建时序相关性回测的计算节点

    Args:
        factors: 待测试的因子列表
        price: 价格因子
        descriptor_ids: 截面 ID 序列（股票列表）
        forecast_period: 预测期数
        lag: 滞后期数
        summary_window: 统计窗口长度，0 表示扩展窗口
        min_summary_window: 最小统计窗口长度
        corr_method: 相关性计算方法
        factor_name_list: 因子名称列表
        factor_args: 额外的因子参数

    Returns:
        (算子, 时序相关性因子, 回测节点, 报告节点) 的元组
    """
    # 创建算子
    Operator = CalcTimeSeriesCorrelation(
        descriptor_ids=descriptor_ids,
        forecast_period=forecast_period,
        lag=lag,
        summary_window=summary_window,
        min_summary_window=min_summary_window,
        corr_method=corr_method,
    )

    # 创建时序相关性因子
    TSCorrFactor = Operator(
        *factors,
        price=price,
        factor_name_list=factor_name_list,
        factor_args=factor_args,
    )

    # 创建回测节点
    TSCorrNode = TimeSeriesCorrelation(
        ts_corr=TSCorrFactor,
        args={
            "Name": "时序因子相关性",
            "FactorNameList": factor_name_list or [f.Name for f in factors],
            "CorrMethod": corr_method,
            "ForecastPeriod": forecast_period,
            "Lag": lag,
        },
    )

    # 创建报告节点
    ReportNode = TimeSeriesCorrelationReport(
        ts_corr_node=TSCorrNode,
        args={"Name": "时序相关性报告", "ReportKey": "Report"},
    )

    return Operator, TSCorrFactor, TSCorrNode, ReportNode
