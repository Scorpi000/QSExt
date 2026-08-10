# coding=utf-8
"""市场状态划分算子。

将连续信号因子离散化为状态标签因子。

算子:
    ThresholdClassify — 基于固定阈值，逐点映射（PointOperator）
    QuantileClassify  — 基于滚动分位数（TimeOperator）
"""
import datetime as dt
from typing import Optional, List

import numpy as np

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import PointOperator, TimeOperator


# ============================================================================
# ThresholdClassify — 阈值法
# ============================================================================

class ThresholdClassify(PointOperator):
    """基于固定阈值将连续信号离散化为状态标签。

    逐点映射，对每个 (时点, ID) 的信号值独立与固定阈值比较，
    无截面依赖、无时序依赖。

    Args:
        thresholds: 阈值列表，升序排列。n 个状态需要 n-1 个阈值。
        labels: 状态标签列表，长度 = len(thresholds) + 1。
            默认 ``['低位', '中位', '高位']``（3 状态）。

    Example:
        >>> signal = RollingMean(60)(market_return_factor)
        >>> bull_bear = ThresholdClassify(
        ...     thresholds=[-0.02, 0.02],
        ...     labels=["熊市", "震荡", "牛市"],
        ... )(signal, factor_name="牛熊状态")
    """

    def __init__(
        self,
        thresholds: List[float] = None,
        labels: List[str] = None,
        args: dict = {},
        config_file: Optional[str] = None,
        **kwargs,
    ):
        self._thresholds = thresholds or [-0.02, 0.02]
        self._labels = labels or ['低位', '中位', '高位']

        if len(self._labels) != len(self._thresholds) + 1:
            raise ValueError(
                f"labels 数量 ({len(self._labels)}) 必须等于 thresholds 数量 "
                f"({len(self._thresholds)}) + 1"
            )

        Args = (
            {"Name": "threshold_classify", "DataType": "object"}
            | args
            | {"Arity": 1, "DTMode": "单时点", "IDMode": "多ID"}
        )
        Args["ModelArgs"] = {
            "thresholds": self._thresholds,
            "labels": self._labels,
        } | Args.get("ModelArgs", {})

        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(
        self,
        f: Factor,
        idt: dt.datetime,
        iid: List[str],
        x: List[np.ndarray],
        args: dict,
    ) -> np.ndarray:
        """逐点阈值划分。

        Args:
            f: 该算子所属的因子对象。
            idt: 当前待计算的时点。
            iid: 当前待计算的 ID 列表。
            x: 描述子数据，``x[0]`` 为 ``array(shape=(len(iid),))``，
                各 ID 在 idt 时点的信号值。
            args: 模型参数，包含 ``thresholds`` 和 ``labels``。

        Returns:
            ``array(shape=(len(iid),), dtype=object)``，各 ID 的状态标签。
        """
        signal = x[0]
        thresholds = args.get("thresholds", self._thresholds)
        labels = args.get("labels", self._labels)

        n = len(thresholds)
        result = np.full(len(iid), labels[n // 2], dtype=object)

        for i, th in enumerate(thresholds):
            if i == 0:
                result[signal <= th] = labels[0]
            if i < n - 1:
                result[(signal > thresholds[i]) & (signal <= thresholds[i + 1])] = labels[i + 1]
        result[signal > thresholds[-1]] = labels[-1]

        return result


# ============================================================================
# QuantileClassify — 滚动分位数法
# ============================================================================

class QuantileClassify(TimeOperator):
    """基于滚动分位数将连续信号离散化为状态标签。

    在指定回溯窗口内计算信号的历史分布，根据当前值所处的
    分位数位置分配状态。适合波动率、流动性等需要相对比较的指标。

    Args:
        lookback: 回溯窗口长度（用于计算分位数的历史时点数）。
        low_pct: 低分位阈值，信号值分位数 ≤ 此值 → 最低状态。
        high_pct: 高分位阈值，信号值分位数 ≥ 此值 → 最高状态。
        labels: 状态标签列表，默认 ``['低位', '中位', '高位']``（3 状态）。

    Example:
        >>> vol_signal = RollingStd(20)(daily_return_factor)
        >>> vol_regime = QuantileClassify(
        ...     lookback=252, low_pct=0.2, high_pct=0.8,
        ...     labels=["低波", "中波", "高波"],
        ... )(vol_signal, factor_name="波动率状态")
    """

    def __init__(
        self,
        lookback: int = 252,
        low_pct: float = 0.2,
        high_pct: float = 0.8,
        labels: List[str] = None,
        args: dict = {},
        config_file: Optional[str] = None,
        **kwargs,
    ):
        self._lookback = lookback
        self._low_pct = low_pct
        self._high_pct = high_pct
        self._labels = labels or ['低位', '中位', '高位']

        Args = (
            {"Name": "quantile_classify", "DataType": "object"}
            | args
            | {
                "Arity": 1,
                "DTMode": "单时点",
                "IDMode": "多ID",
                "LookBack": [lookback],
            }
        )
        Args["ModelArgs"] = {
            "lookback": lookback,
            "low_pct": low_pct,
            "high_pct": high_pct,
            "labels": self._labels,
        } | Args.get("ModelArgs", {})

        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(
        self,
        f: Factor,
        idt: dt.datetime,
        iid: List[str],
        x: List[np.ndarray],
        args: dict,
    ) -> np.ndarray:
        """滚动分位数状态划分。

        对每个 ID 计算当前信号值在历史窗口中的分位数位置，
        根据分位数阈值分配状态标签。

        Args:
            f: 该算子所属的因子对象。
            idt: 当前待计算的时点。
            iid: 当前待计算的 ID 列表。
            x: 描述子数据，``x[0]`` 为 ``array(shape=(LookBack+1, len(iid)))``，
                最后一行 ``x[0][-1, :]`` 为当前信号值，
                前 N 行 ``x[0][:-1, :]`` 为历史信号值。
            args: 模型参数，包含 ``low_pct``、``high_pct`` 和 ``labels``。

        Returns:
            ``array(shape=(len(iid),), dtype=object)``，各 ID 的状态标签。
        """
        data = x[0]                              # (LookBack+1, n_ids)
        low_pct = args.get("low_pct", self._low_pct)
        high_pct = args.get("high_pct", self._high_pct)
        labels = args.get("labels", self._labels)

        current = data[-1, :]                    # (n_ids,)
        history = data[:-1, :]                   # (LookBack, n_ids)

        # 对每个 ID 计算当前值在历史中的分位数
        # percentile = (history < current).mean(axis=0)
        n_ids = len(iid)
        percentiles = np.full(n_ids, np.nan, dtype=float)
        for j in range(n_ids):
            hist = history[:, j]
            valid = hist[~np.isnan(hist)]
            if len(valid) > 0:
                percentiles[j] = (valid < current[j]).mean()

        result = np.full(n_ids, labels[1], dtype=object)
        result[percentiles <= low_pct] = labels[0]
        result[percentiles >= high_pct] = labels[-1]
        # NaN percentile (no valid history) → 保留中位状态
        result[np.isnan(percentiles)] = labels[1]

        return result
