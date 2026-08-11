# coding=utf-8
"""MarketRegime —— 通用市场状态划分与转换检测模块。

提供基于 QuantStudio Factor 框架的状态划分算子，
将连续信号因子转换为离散状态标签因子，以及状态转换检测器。

核心算子:
    - ThresholdClassify(PointOperator): 基于固定阈值的状态划分
    - QuantileClassify(TimeOperator):  基于滚动分位数的状态划分
    - HMMClassify(PanelOperator):     基于 HMM 的多维市场状态发现

转换检测器:
    - CUSUMDetector:        CUSUM 累积和，检测均值的微小持续偏移
    - KSTestDetector:       KS 检验，确认两段时期分布是否显著不同
    - WassersteinDetector:  Wasserstein 距离，量化分布变化幅度
    - DTWDetector:          DTW，在历史中寻找与当前模式最相似的时期

Example:
    >>> from QuantStudio.Factor.Factor import DataFactor
    >>> from QSExt.MarketRegime import ThresholdClassify
    >>> signal = RollingMean(60)(market_return_factor)
    >>> regime = ThresholdClassify(
    ...     thresholds=[-0.0003, 0.0003],
    ...     labels=["熊市", "震荡", "牛市"],
    ... )(signal, factor_name="牛熊状态")
    >>> labels = regime.readData(ids=["000001"], dts=date_range)
"""

from QSExt.MarketRegime.operators import ThresholdClassify, QuantileClassify, HMMClassify
from QSExt.MarketRegime.transition import (
    CUSUMDetector, KSTestDetector, WassersteinDetector, DTWDetector
)
from QSExt.MarketRegime.regime_report import RegimePerformanceReport

__all__ = [
    "ThresholdClassify", "QuantileClassify", "HMMClassify",
    "CUSUMDetector", "KSTestDetector", "WassersteinDetector", "DTWDetector",
    "RegimePerformanceReport",
]
