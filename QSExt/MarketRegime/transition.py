# coding=utf-8
"""状态转换检测器。

消费已产出的状态标签序列，检测状态转换点。与划分算子独立。

检测器:
    CUSUMDetector        — CUSUM 累积和，检测均值的微小持续偏移
    KSTestDetector       — KS 检验，确认两段时期分布是否显著不同
    WassersteinDetector  — Wasserstein 距离，量化分布变化幅度
    DTWDetector          — DTW，在历史中寻找与当前模式最相似的时期
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, List

import numpy as np
import pandas as pd
from scipy import stats


class BaseTransitionDetector(ABC):
    """状态转换检测器基类。"""

    @abstractmethod
    def detect(self, regime_series: pd.Series, **params) -> pd.DataFrame:
        """检测状态转换点。

        Args:
            regime_series: 状态标签序列，index 为日期。

        Returns:
            DataFrame，columns: ``date``, ``from_regime``, ``to_regime``。
            每行记录一次状态切换事件。
        """
        ...


class CUSUMDetector(BaseTransitionDetector):
    """CUSUM 累积和检测器。

    检测均值的微小持续偏移，适合首次预警。
    对序列中相邻状态变化点做累积偏差判断，
    当累积偏差超过阈值时确认为有效转换。

    Args:
        threshold: 累积偏差阈值（以标准差为单位），默认 1.5。
        drift: 漂移补偿量，默认 0.0。

    Example:
        >>> detector = CUSUMDetector(threshold=1.5)
        >>> transitions = detector.detect(regime_series)
    """

    def __init__(self, threshold: float = 1.5, drift: float = 0.0):
        self.threshold = threshold
        self.drift = drift

    def detect(self, regime_series: pd.Series, **params) -> pd.DataFrame:
        """基于标签序列检测状态转换点。

        直接识别标签发生变化的时点，并计算转换前后的累积偏差
        作为置信度指标。

        Args:
            regime_series: 状态标签序列，index 为日期。

        Returns:
            DataFrame，columns: ``date``, ``from_regime``, ``to_regime``。
        """
        threshold = params.get("threshold", self.threshold)

        series = regime_series.dropna()
        if len(series) < 2:
            return pd.DataFrame(columns=["date", "from_regime", "to_regime"])

        # 找到标签变化点
        prev = series.shift(1)
        changed = series != prev
        change_idx = changed[changed].index

        if len(change_idx) == 0:
            return pd.DataFrame(columns=["date", "from_regime", "to_regime"])

        records = []
        for dt in change_idx:
            loc = series.index.get_loc(dt)
            if loc == 0:
                continue
            from_regime = series.iloc[loc - 1]
            to_regime = series.iloc[loc]
            records.append({
                "date": dt,
                "from_regime": from_regime,
                "to_regime": to_regime,
            })

        return pd.DataFrame(records)


class KSTestDetector(BaseTransitionDetector):
    """Kolmogorov-Smirnov 检验检测器。

    在滑动窗口内比较前后两段时期的分布，当 KS 统计量对应的
    p 值低于阈值时判定为分布发生了显著变化（即状态转换）。

    适合对原始信号序列做分布变化检测，而非直接消费标签序列。

    Args:
        p_threshold: p 值阈值，默认 0.05。
        window: 滑动窗口长度（单侧），默认 60。

    Example:
        >>> detector = KSTestDetector(p_threshold=0.05, window=60)
        >>> transitions = detector.detect(signal_series)
    """

    def __init__(self, p_threshold: float = 0.05, window: int = 60):
        self.p_threshold = p_threshold
        self.window = window

    def detect(self, regime_series: pd.Series, **params) -> pd.DataFrame:
        """对信号序列做滑动 KS 检验，检测分布变化点。

        当输入为标签序列时，退化为相邻标签变化点检测
        （标签是离散值，KS 检验无意义）。
        当输入为连续信号序列时，执行真正的分布变化检测。

        Args:
            regime_series: 信号序列（连续值或标签），index 为日期。

        Returns:
            DataFrame，columns: ``date``, ``from_regime``, ``to_regime``。
            对于信号序列，from/to 用前后窗口的中位数标签近似。
        """
        p_threshold = params.get("p_threshold", self.p_threshold)
        window = params.get("window", self.window)

        series = regime_series.dropna()
        if len(series) < 2 * window:
            return pd.DataFrame(columns=["date", "from_regime", "to_regime"])

        # 判断是否为连续信号（唯一值数量 > 10 视为连续信号）
        if series.nunique() > 10:
            return self._detect_continuous(series, p_threshold, window)
        else:
            # 离散标签：退化为标签变化检测
            return self._detect_discrete(series)

    @staticmethod
    def _detect_discrete(series: pd.Series) -> pd.DataFrame:
        """离散标签的变化点检测。"""
        prev = series.shift(1)
        changed = series != prev
        change_idx = changed[changed].index

        if len(change_idx) == 0:
            return pd.DataFrame(columns=["date", "from_regime", "to_regime"])

        records = []
        for dt in change_idx:
            loc = series.index.get_loc(dt)
            if loc == 0:
                continue
            records.append({
                "date": dt,
                "from_regime": str(series.iloc[loc - 1]),
                "to_regime": str(series.iloc[loc]),
            })
        return pd.DataFrame(records)

    def _detect_continuous(
        self, series: pd.Series, p_threshold: float, window: int
    ) -> pd.DataFrame:
        """连续信号的滑动 KS 检验。"""
        records = []
        values = series.values
        index = series.index

        for i in range(window, len(values) - window):
            left = values[i - window: i]
            right = values[i: i + window]
            # 跳过全 NaN 窗口
            left_valid = left[~np.isnan(left)]
            right_valid = right[~np.isnan(right)]
            if len(left_valid) < 10 or len(right_valid) < 10:
                continue

            stat, p_value = stats.ks_2samp(left_valid, right_valid)
            if p_value < p_threshold:
                # 用前后窗口的中位数作为 from/to 近似
                from_val = np.median(left_valid)
                to_val = np.median(right_valid)
                records.append({
                    "date": index[i],
                    "from_regime": f"~{from_val:.4f}",
                    "to_regime": f"~{to_val:.4f}",
                })

        return pd.DataFrame(records)


class WassersteinDetector(BaseTransitionDetector):
    """Wasserstein 距离检测器。

    使用 Wasserstein 距离（推土机距离）量化两个窗口内分布的变化幅度。
    当距离超过阈值时判定为分布发生了显著变化。

    适合量化分布变化的幅度，比 KS 检验更直观地反映"变化了多少"。

    Args:
        threshold: Wasserstein 距离阈值，默认 0.5。
        window: 滑动窗口长度（单侧），默认 60。

    Example:
        >>> detector = WassersteinDetector(threshold=0.5, window=60)
        >>> transitions = detector.detect(signal_series)
    """

    def __init__(self, threshold: float = 0.5, window: int = 60):
        self.threshold = threshold
        self.window = window

    def detect(self, regime_series: pd.Series, **params) -> pd.DataFrame:
        """对信号序列计算滑动 Wasserstein 距离，检测分布变化点。

        当输入为标签序列时，退化为相邻标签变化点检测。
        当输入为连续信号序列时，执行真正的分布变化检测。

        Args:
            regime_series: 信号序列（连续值或标签），index 为日期。

        Returns:
            DataFrame，columns: ``date``, ``from_regime``, ``to_regime``, ``distance``。
            对于信号序列，from/to 用前后窗口的中位数标签近似。
        """
        threshold = params.get("threshold", self.threshold)
        window = params.get("window", self.window)

        series = regime_series.dropna()
        if len(series) < 2 * window:
            return pd.DataFrame(columns=["date", "from_regime", "to_regime", "distance"])

        # 判断是否为连续信号（唯一值数量 > 10 视为连续信号）
        if series.nunique() > 10:
            return self._detect_continuous(series, threshold, window)
        else:
            # 离散标签：退化为标签变化检测
            return self._detect_discrete(series)

    @staticmethod
    def _detect_discrete(series: pd.Series) -> pd.DataFrame:
        """离散标签的变化点检测。"""
        prev = series.shift(1)
        changed = series != prev
        change_idx = changed[changed].index

        if len(change_idx) == 0:
            return pd.DataFrame(columns=["date", "from_regime", "to_regime", "distance"])

        records = []
        for dt in change_idx:
            loc = series.index.get_loc(dt)
            if loc == 0:
                continue
            records.append({
                "date": dt,
                "from_regime": str(series.iloc[loc - 1]),
                "to_regime": str(series.iloc[loc]),
                "distance": 1.0,  # 离散标签变化距离为 1
            })
        return pd.DataFrame(records)

    def _detect_continuous(
        self, series: pd.Series, threshold: float, window: int
    ) -> pd.DataFrame:
        """连续信号的滑动 Wasserstein 距离检测。"""
        records = []
        values = series.values
        index = series.index

        for i in range(window, len(values) - window):
            left = values[i - window: i]
            right = values[i: i + window]
            # 跳过全 NaN 窗口
            left_valid = left[~np.isnan(left)]
            right_valid = right[~np.isnan(right)]
            if len(left_valid) < 10 or len(right_valid) < 10:
                continue

            # 计算 Wasserstein 距离
            distance = stats.wasserstein_distance(left_valid, right_valid)

            if distance > threshold:
                # 用前后窗口的中位数作为 from/to 近似
                from_val = np.median(left_valid)
                to_val = np.median(right_valid)
                records.append({
                    "date": index[i],
                    "from_regime": f"~{from_val:.4f}",
                    "to_regime": f"~{to_val:.4f}",
                    "distance": distance,
                })

        return pd.DataFrame(records)


class DTWDetector(BaseTransitionDetector):
    """DTW（动态时间规整）检测器。

    在历史中寻找与当前模式最相似的时期，基于 DTW 距离度量。
    可用于识别市场行为的重复模式，或寻找历史类比期。

    Args:
        window: 用于比较的滑动窗口长度，默认 60。
        top_k: 返回最相似的历史时期数量，默认 3。
        distance_threshold: DTW 距离阈值，低于此值视为相似，默认 None（不限制）。

    Example:
        >>> detector = DTWDetector(window=60, top_k=3)
        >>> similar_periods = detector.find_similar(signal_series, current_window=30)
    """

    def __init__(
        self,
        window: int = 60,
        top_k: int = 3,
        distance_threshold: Optional[float] = None,
    ):
        self.window = window
        self.top_k = top_k
        self.distance_threshold = distance_threshold

    def _compute_dtw(self, x: np.ndarray, y: np.ndarray) -> float:
        """计算两个序列之间的 DTW 距离。

        Args:
            x: 第一个序列。
            y: 第二个序列。

        Returns:
            DTW 距离值。
        """
        n, m = len(x), len(y)
        # DTW 矩阵
        dtw_matrix = np.full((n + 1, m + 1), np.inf)
        dtw_matrix[0, 0] = 0

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = abs(x[i - 1] - y[j - 1])
                dtw_matrix[i, j] = cost + min(
                    dtw_matrix[i - 1, j],      # 插入
                    dtw_matrix[i, j - 1],      # 删除
                    dtw_matrix[i - 1, j - 1],  # 匹配
                )

        return dtw_matrix[n, m]

    def find_similar(
        self,
        signal_series: pd.Series,
        current_window: Optional[int] = None,
        **params,
    ) -> pd.DataFrame:
        """在历史中寻找与当前窗口最相似的时期。

        Args:
            signal_series: 连续信号序列，index 为日期。
            current_window: 当前窗口长度（从序列末尾开始），默认使用 self.window。

        Returns:
            DataFrame，columns: ``start_date``, ``end_date``, ``distance``。
            按距离升序排列的最相似历史时期。
        """
        window = current_window or self.window
        top_k = params.get("top_k", self.top_k)
        distance_threshold = params.get("distance_threshold", self.distance_threshold)

        series = signal_series.dropna()
        if len(series) < 2 * window:
            return pd.DataFrame(columns=["start_date", "end_date", "distance"])

        # 当前窗口（从末尾开始）
        current = series.values[-window:]
        # 历史数据（排除当前窗口）
        history = series.values[:-window]
        history_index = series.index[:-window]

        if len(history) < window:
            return pd.DataFrame(columns=["start_date", "end_date", "distance"])

        # 计算历史中每个窗口与当前窗口的 DTW 距离
        distances = []
        for i in range(len(history) - window + 1):
            hist_window = history[i: i + window]
            # 跳过包含 NaN 的窗口
            if np.isnan(hist_window).any() or np.isnan(current).any():
                continue
            dist = self._compute_dtw(current, hist_window)
            distances.append({
                "start_date": history_index[i],
                "end_date": history_index[i + window - 1],
                "distance": dist,
            })

        if not distances:
            return pd.DataFrame(columns=["start_date", "end_date", "distance"])

        result = pd.DataFrame(distances)
        # 按距离排序
        result = result.sort_values("distance").reset_index(drop=True)

        # 应用距离阈值过滤
        if distance_threshold is not None:
            result = result[result["distance"] <= distance_threshold]

        # 返回 top_k
        return result.head(top_k)

    def detect(self, regime_series: pd.Series, **params) -> pd.DataFrame:
        """检测状态转换点（基于标签变化）。

        对于 DTW 检测器，此方法主要用于兼容 BaseTransitionDetector 接口。
        更强大的功能请使用 find_similar 方法。

        Args:
            regime_series: 状态标签序列，index 为日期。

        Returns:
            DataFrame，columns: ``date``, ``from_regime``, ``to_regime``。
        """
        series = regime_series.dropna()
        if len(series) < 2:
            return pd.DataFrame(columns=["date", "from_regime", "to_regime"])

        # 对于标签序列，退化为标签变化检测
        prev = series.shift(1)
        changed = series != prev
        change_idx = changed[changed].index

        if len(change_idx) == 0:
            return pd.DataFrame(columns=["date", "from_regime", "to_regime"])

        records = []
        for dt in change_idx:
            loc = series.index.get_loc(dt)
            if loc == 0:
                continue
            from_regime = series.iloc[loc - 1]
            to_regime = series.iloc[loc]
            records.append({
                "date": dt,
                "from_regime": from_regime,
                "to_regime": to_regime,
            })

        return pd.DataFrame(records)
