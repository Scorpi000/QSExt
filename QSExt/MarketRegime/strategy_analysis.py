# coding=utf-8
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from QSExt.MarketRegime.transition import BaseTransitionDetector

# ============================================================================
# StrategyRegimeAnalyzer — 策略市场状态适应性分析
# ============================================================================

class StrategyRegimeAnalyzer:
    """策略市场状态适应性分析器。

    消费市场状态标签序列，分析策略在各市场状态下的表现差异和适应性。

    Args:
        strategy_returns: 策略日收益率序列，index 为日期（DatetimeIndex）。
        regime_labels: 市场状态标签，index 为日期。
            若为 DataFrame 则每列代表一个状态维度。

    Example:
        >>> analyzer = StrategyRegimeAnalyzer(strategy_returns, regime_labels)
        >>> perf = analyzer.compute_regime_performance(dimension='bull_bear')
        >>> heatmap = analyzer.compute_adaptation_heatmap(dimension='bull_bear')
    """

    def __init__(self, strategy_returns: pd.Series, regime_labels: 'pd.DataFrame | pd.Series'):
        self._returns = pd.Series(strategy_returns)
        if isinstance(regime_labels, pd.Series):
            self._regimes = pd.DataFrame({'regime': regime_labels})
        else:
            self._regimes = pd.DataFrame(regime_labels)

        # 对齐索引
        common_idx = self._returns.index.intersection(self._regimes.index)
        self._returns = self._returns.loc[common_idx]
        self._regimes = self._regimes.loc[common_idx]

    @property
    def dimensions(self) -> list:
        """可用的状态维度列表。"""
        return list(self._regimes.columns)

    # ---- 状态条件表现 ----

    def compute_regime_performance(
        self, dimension: str = None
    ) -> pd.DataFrame:
        """各市场状态下的策略表现统计。

        Args:
            dimension: 状态维度名。若为 None 则使用第一个维度。

        Returns:
            DataFrame，index 为状态名，columns 包含:
            占比 / 年化收益 / 年化波动 / 夏普比率 / 最大回撤 / 胜率。
        """
        if dimension is None:
            dimension = self.dimensions[0]

        labels = self._regimes[dimension]
        results = []
        for regime in sorted(labels.dropna().unique()):
            mask = (labels == regime).values
            sub_returns = self._returns[mask]

            if len(sub_returns) < 2:
                continue

            ann_ret = sub_returns.mean() * 252
            ann_vol = sub_returns.std() * np.sqrt(252)
            sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
            cumret = (1 + sub_returns).cumprod()
            dd = (cumret / cumret.cummax() - 1).min()

            results.append({
                '状态': regime,
                '占比': mask.mean(),
                '年化收益': ann_ret,
                '年化波动': ann_vol,
                '夏普比率': sharpe,
                '最大回撤': dd,
                '胜率': (sub_returns > 0).mean(),
            })

        df = pd.DataFrame(results)
        return df.set_index('状态') if len(df) > 0 else df

    # ---- 适应性热力图 ----

    def compute_adaptation_heatmap(
        self, dimension: str = None, freq: str = 'Q'
    ) -> pd.DataFrame:
        """状态 × 时间段的二维收益矩阵。

        Args:
            dimension: 状态维度名。若为 None 则使用第一个维度。
            freq: 时间聚合频率，``'M'``（月）/ ``'Q'``（季）/ ``'Y'``（年）。

        Returns:
            DataFrame，index 为状态，columns 为时间段，
            values 为策略在该状态-时期的年化收益。
        """
        if dimension is None:
            dimension = self.dimensions[0]

        labels = self._regimes[dimension]
        periods = self._returns.index.to_period(freq)

        all_regimes = sorted(labels.dropna().unique())
        all_periods = sorted(periods.unique())

        heatmap = pd.DataFrame(
            index=all_regimes, columns=all_periods, dtype=float
        )
        for regime in all_regimes:
            for period in all_periods:
                mask = ((labels == regime).values &
                        (periods == period))
                sub = self._returns[mask]
                heatmap.loc[regime, period] = (
                    sub.mean() * 252 if len(sub) > 0 else np.nan
                )

        return heatmap

    # ---- Minimum Regime Performance ----

    def compute_mrp(self, dimension: str = None) -> dict:
        """最小状态表现 (Minimum Regime Performance)。

        来源：JPM "Measuring Strategy-Decay Risk"。

        Args:
            dimension: 状态维度名。若为 None 则使用第一个维度。

        Returns:
            dict，包含以下键:
            - ``mrp``: 最差状态夏普比率（Minimum Regime Performance）
            - ``worst_regime``: 最差状态名称
            - ``worst_sharpe``: 最差夏普值
            - ``regime_sharpes``: 各状态夏普比率字典
            - ``mrp_vs_total``: 最差夏普与整体夏普的比值
        """
        if dimension is None:
            dimension = self.dimensions[0]

        labels = self._regimes[dimension]
        if self._returns.std() > 0:
            total_sharpe = (self._returns.mean() / self._returns.std()
                            * np.sqrt(252))
        else:
            total_sharpe = np.nan

        regime_sharpes = {}
        for regime in labels.dropna().unique():
            sub = self._returns[labels == regime]
            if sub.std() > 0 and len(sub) > 1:
                regime_sharpes[regime] = (sub.mean() / sub.std()
                                          * np.sqrt(252))
            else:
                regime_sharpes[regime] = np.nan

        sharpe_vals = [v for v in regime_sharpes.values()
                       if not np.isnan(v)]
        if sharpe_vals:
            worst_regime = min(regime_sharpes, key=regime_sharpes.get)
            worst_sharpe = min(sharpe_vals)
            mrp = worst_sharpe
        else:
            worst_regime = None
            worst_sharpe = np.nan
            mrp = np.nan

        return {
            'mrp': mrp,
            'worst_regime': worst_regime,
            'worst_sharpe': worst_sharpe,
            'regime_sharpes': regime_sharpes,
            'mrp_vs_total': (mrp / total_sharpe
                             if not np.isnan(total_sharpe) else np.nan),
        }

    # ---- 状态转换冲击分析 ----

    def transition_impact_analysis(
        self,
        dimension: str = None,
        detector: 'BaseTransitionDetector | None' = None,
        windows: list[int] = [5, 10, 20],
    ) -> dict:
        """状态转换冲击分析。

        检测状态转换点，计算转换前后的收益表现差异。

        Args:
            dimension: 状态维度名。若为 None 则使用第一个维度。
            detector: 转换检测器。若为 None 则使用相邻标签变化检测。
            windows: 转换前后观察窗口列表（交易日数）。

        Returns:
            dict，包含以下键:
            - ``transitions``: 转换点明细 DataFrame
              (columns: date, from_regime, to_regime)
            - ``window_returns``: 各窗口期的平均转换收益 DataFrame
              (index: 窗口名, columns: 转换前收益, 转换后收益)
            - ``direction_impact``: 方向敏感性 DataFrame
              (index: from→to, columns: 平均转换后收益, 转换次数)
            - ``transition_loss_ratio``: 转换期亏损占总亏损的比例
        """
        if dimension is None:
            dimension = self.dimensions[0]

        labels = self._regimes[dimension]

        # 检测转换点
        if detector is not None:
            transitions = detector.detect(labels)
        else:
            transitions = self._default_detect_transitions(labels)

        if transitions.empty:
            return {
                "transitions": transitions,
                "window_returns": pd.DataFrame(),
                "direction_impact": pd.DataFrame(),
                "transition_loss_ratio": np.nan,
            }

        returns = self._returns

        # ---- 各窗口期转换收益 ----
        window_records = []
        for w in windows:
            pre_returns = []
            post_returns = []
            for _, row in transitions.iterrows():
                dt = row["date"]
                loc = returns.index.get_loc(dt)
                if loc is None:
                    continue
                # 转换前 w 日
                start = max(0, loc - w)
                pre = returns.iloc[start:loc]
                if len(pre) > 0:
                    pre_returns.append(pre.mean() * 252)
                # 转换后 w 日
                end = min(len(returns), loc + w)
                post = returns.iloc[loc:end]
                if len(post) > 0:
                    post_returns.append(post.mean() * 252)

            window_records.append({
                "窗口": f"±{w}日",
                "转换前收益": np.mean(pre_returns) if pre_returns else np.nan,
                "转换后收益": np.mean(post_returns) if post_returns else np.nan,
            })

        window_df = pd.DataFrame(window_records).set_index("窗口")

        # ---- 方向敏感性 ----
        direction_groups = {}
        for _, row in transitions.iterrows():
            dt = row["date"]
            key = f"{row['from_regime']}→{row['to_regime']}"
            loc = returns.index.get_loc(dt)
            # 转换后收益（取最大窗口）
            max_w = max(windows)
            end = min(len(returns), loc + max_w)
            post = returns.iloc[loc:end]
            if len(post) > 0:
                direction_groups.setdefault(key, []).append(post.mean() * 252)

        direction_records = []
        for key, vals in direction_groups.items():
            direction_records.append({
                "转换方向": key,
                "平均转换后收益": np.mean(vals),
                "转换次数": len(vals),
            })
        direction_df = pd.DataFrame(direction_records).set_index("转换方向")

        # ---- 转换期亏损占比 ----
        # 转换窗口内的负收益 / 全部负收益
        max_w = max(windows)
        transition_neg = 0.0
        for _, row in transitions.iterrows():
            dt = row["date"]
            loc = returns.index.get_loc(dt)
            start = max(0, loc - max_w)
            end = min(len(returns), loc + max_w)
            sub = returns.iloc[start:end]
            transition_neg += sub[sub < 0].sum()

        total_neg = returns[returns < 0].sum()
        loss_ratio = (transition_neg / total_neg
                      if abs(total_neg) > 1e-12 else np.nan)

        return {
            "transitions": transitions,
            "window_returns": window_df,
            "direction_impact": direction_df,
            "transition_loss_ratio": loss_ratio,
        }

    @staticmethod
    def _default_detect_transitions(labels: pd.Series) -> pd.DataFrame:
        """默认转换点检测：相邻标签变化。"""
        prev = labels.shift(1)
        changed = labels != prev
        change_idx = changed[changed].index

        if len(change_idx) == 0:
            return pd.DataFrame(columns=["date", "from_regime", "to_regime"])

        records = []
        for dt in change_idx:
            loc = labels.index.get_loc(dt)
            if loc == 0:
                continue
            from_val = labels.iloc[loc - 1]
            to_val = labels.iloc[loc]
            # 跳过 NaN
            if pd.isna(from_val) or pd.isna(to_val):
                continue
            records.append({
                "date": dt,
                "from_regime": str(from_val),
                "to_regime": str(to_val),
            })
        return pd.DataFrame(records)