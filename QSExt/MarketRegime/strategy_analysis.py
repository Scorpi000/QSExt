# coding=utf-8
import numpy as np
import pandas as pd

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