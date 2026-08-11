# coding=utf-8
"""市场状态划分算子。

将连续信号因子离散化为状态标签因子。

算子:
    ThresholdClassify — 基于固定阈值，逐点映射（PointOperator）
    QuantileClassify  — 基于滚动分位数（TimeOperator）
    HMMClassify       — 基于 HMM 的多维市场状态发现（PanelOperator）
"""
import datetime as dt
from typing import Optional, List

import numpy as np

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import PointOperator, TimeOperator, PanelOperator


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


# ============================================================================
# HMMClassify — 隐马尔可夫模型
# ============================================================================

class HMMClassify(PanelOperator):
    """基于 HMM 的多维市场状态发现。

    对多个输入因子组成的面板数据联合建模，无监督地发现数据驱动的自然状态。
    在滚动窗口内训练 HMM 模型，对当前时点进行状态预测。

    Args:
        n_components: 状态数量，默认 4。
        lookback: 训练窗口长度（用于拟合 HMM 的历史数据量），默认 500。
        covariance_type: 协方差类型，默认 'full'。
        random_state: 随机种子，默认 42。
        labels: 状态标签列表，默认 None（使用数字标签 0, 1, ...）。

    Example:
        >>> features = [market_return_signal, volatility_signal, volume_change_signal]
        >>> hmm_regime = HMMClassify(n_components=4, lookback=500)(
        ...     *features, factor_name="HMM市场状态"
        ... )
    """

    def __init__(
        self,
        n_components: int = 4,
        lookback: int = 500,
        covariance_type: str = 'full',
        random_state: int = 42,
        labels: List[str] = None,
        args: dict = {},
        config_file: Optional[str] = None,
        **kwargs,
    ):
        self._n_components = n_components
        self._lookback = lookback
        self._covariance_type = covariance_type
        self._random_state = random_state
        self._labels = labels or [f"状态{i}" for i in range(n_components)]
        self._Model = None  # 缓存训练好的模型

        if len(self._labels) != n_components:
            raise ValueError(
                f"labels 数量 ({len(self._labels)}) 必须等于 n_components ({n_components})"
            )

        # 合并参数：如果 args 中已包含 Arity/LookBack 等（来自 new()），则保留
        default_args = {
            "Name": "hmm_classify",
            "DataType": "object",
            "DTMode": "单时点",
        }
        # 只有当 args 中没有这些参数时才设置默认值
        if "Arity" not in args:
            default_args["Arity"] = None  # 动态确定入参数量
        if "LookBack" not in args:
            default_args["LookBack"] = []  # 在 _QS_validate 中动态设置
        if "StartDT" not in args:
            default_args["StartDT"] = []
        if "DescriptorSection" not in args:
            default_args["DescriptorSection"] = []

        Args = default_args | args

        Args["ModelArgs"] = {
            "n_components": n_components,
            "covariance_type": covariance_type,
            "random_state": random_state,
            "labels": self._labels,
            "lookback": lookback,
        } | Args.get("ModelArgs", {})

        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def _QS_validate(self, *x, **kwargs):
        """重写验证方法，动态设置 LookBack。"""
        Arity = len(x)
        if self._QSArgs.Arity is None:
            # 动态设置 Arity、LookBack、StartDT 和 DescriptorSection
            NewArgs = {
                "Arity": Arity,
                "LookBack": [self._lookback] * Arity,
                "StartDT": [None] * Arity,
                "DescriptorSection": [None] * Arity,
            }
            return self.new(args=NewArgs, **kwargs)
        elif Arity != self._QSArgs.Arity:
            from QuantStudio.Core import __QS_Error__
            raise __QS_Error__(
                f"因子算子 {self._QSArgs.Name} 实际传入的因子数量 {Arity} "
                f"和指定的入参数 {self._QSArgs.Arity} 不符!"
            )
        else:
            return self

    def _train_hmm(self, data: np.ndarray, n_components: int = None) -> tuple:
        """训练 HMM 模型。

        Args:
            data: shape=(n_timesteps, n_features) 的面板数据。
            n_components: 状态数量，默认使用 self._n_components。

        Returns:
            (model, states): 训练好的模型和预测的状态序列。
            状态值保证在 [0, n_components) 范围内。
        """
        if n_components is None:
            n_components = self._n_components

        try:
            from hmmlearn.hmm import GaussianHMM
        except ImportError:
            raise ImportError(
                "HMMClassify 需要 hmmlearn 库，请安装: pip install hmmlearn"
            )

        # 处理 NaN 值
        valid_mask = ~np.isnan(data).any(axis=1)
        valid_data = data[valid_mask]

        if len(valid_data) < n_components * 2:
            # 数据不足，返回默认状态
            return None, np.zeros(len(data), dtype=int)

        model = GaussianHMM(
            n_components=n_components,
            covariance_type=self._covariance_type,
            random_state=self._random_state,
            n_iter=100,
        )

        try:
            model.fit(valid_data)
            states = model.predict(valid_data)
            # 确保状态在有效范围内
            states = np.array([min(s, n_components - 1) for s in states], dtype=int)
        except Exception:
            # 训练失败，返回默认状态
            return None, np.zeros(len(data), dtype=int)

        # 将状态映射回包含 NaN 的完整序列
        full_states = np.zeros(len(data), dtype=int)
        full_states[valid_mask] = states
        # NaN 位置使用最近的有效状态
        if not valid_mask[0]:
            first_valid = np.argmax(valid_mask)
            full_states[:first_valid] = full_states[first_valid]

        # 最终检查：确保所有状态都在有效范围内
        full_states = np.array([min(s, n_components - 1) for s in full_states], dtype=int)

        return model, full_states

    def calculate(
        self,
        f: Factor,
        idt: dt.datetime,
        iid: List[str],
        x: List[np.ndarray],
        args: dict,
    ) -> np.ndarray:
        """HMM 状态划分。

        在滚动窗口内训练 HMM 模型，对当前时点进行状态预测。

        Args:
            f: 该算子所属的因子对象。
            idt: 当前待计算的时点。
            iid: 当前待计算的 ID 列表。
            x: 描述子数据，``x[i]`` 为 ``array(shape=(LookBack+1, len(iid)))``，
                最后一行 ``x[i][-1, :]`` 为当前值，前面为历史值。
            args: 模型参数。

        Returns:
            ``array(shape=(len(iid),), dtype=object)``，各 ID 的状态标签。
        """
        labels = args.get("labels", self._labels)
        n_components = args.get("n_components", self._n_components)
        n_ids = len(iid)

        # 合并所有描述子的数据: shape=(LookBack+1, n_ids, n_features)
        n_features = len(x)
        lookback_plus_1 = x[0].shape[0]

        # 构建面板数据: shape=(lookback_plus_1 * n_ids, n_features)
        # 对每个 ID 独立训练 HMM
        result = np.full(n_ids, labels[0], dtype=object)

        for j in range(n_ids):
            # 收集该 ID 在所有描述子上的数据
            id_data = np.column_stack([
                x[k][:, j] for k in range(n_features)
            ])  # shape=(lookback_plus_1, n_features)

            # 训练 HMM 并获取状态序列
            model, states = self._train_hmm(id_data, n_components=n_components)

            # 当前时点的状态（最后一个时间步）
            current_state = int(states[-1])
            # 确保状态索引在有效范围内
            if 0 <= current_state < len(labels):
                result[j] = labels[current_state]
            else:
                # 超出范围时使用默认标签
                result[j] = f"状态{current_state}"

        return result
