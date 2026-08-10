# coding=utf-8
"""MarketRegime —— 通用市场状态划分模块。

提供基于 QuantStudio Factor 框架的状态划分算子，
将连续信号因子转换为离散状态标签因子。

核心算子:
    - ThresholdClassify(PointOperator): 基于固定阈值的状态划分
    - QuantileClassify(TimeOperator):  基于滚动分位数的状态划分

Example:
    >>> from QuantStudio.Factor.Factor import DataFactor
    >>> from QSExt.MarketRegime import ThresholdClassify
    >>> signal = RollingMean(60)(market_return_factor)
    >>> regime = ThresholdClassify(
    ...     thresholds=[-0.02, 0.02],
    ...     labels=["熊市", "震荡", "牛市"],
    ... )(signal, factor_name="牛熊状态")
    >>> labels = regime.readData(ids=["000001"], dts=date_range)
"""

from QSExt.MarketRegime.operators import ThresholdClassify, QuantileClassify
from QSExt.MarketRegime.regime_report import RegimePerformanceReport

__all__ = ["ThresholdClassify", "QuantileClassify", "RegimePerformanceReport"]
