# coding=utf-8
import numpy as np
import pandas as pd

def identify_drawdowns(nav_series, threshold=0.05):
    """识别所有超过阈值的回撤事件。

    回撤定义为净值从峰值下跌到恢复至前高的全过程。一个回撤事件起始于峰值，
    终止于净值恢复到峰值的时点。若序列结束时仍未恢复，则 end 和 recovery_days 为 None。

    当输入为 DatetimeIndex 的 Series 时，start/end/trough 返回日期标签，
    duration/recovery_days 返回日历日数；否则返回索引标签和标签差值。

    Args:
        nav_series: 净值序列，支持 array-like 或 pd.Series。
        threshold: 回撤幅度阈值，默认 0.05（5%），仅返回深度超过该值的回撤事件。

    Returns:
        list[dict]: 回撤事件列表，按时间排序。每个事件包含以下字段：
            - start: 回撤开始位置（DatetimeIndex 时为日期，否则为索引标签）
            - end: 回撤恢复位置，若未恢复则为 None
            - trough: 回撤最低点位置
            - depth: 最大回撤幅度（正值，如 0.15 表示 15%）
            - duration: 回撤持续长度（DatetimeIndex 时为日历日数，否则为索引标签差）
            - recovery_days: 从最低点到恢复的长度，若未恢复则为 None
    """
    nav_series = pd.Series(nav_series)
    is_datetime = isinstance(nav_series.index, pd.DatetimeIndex)
    if is_datetime: nav_series = nav_series.sort_index()
    n = len(nav_series)
    if n <= 1: return []
    
    # 计算回撤序列：drawdown = nav / cummax(nav) - 1  (<= 0)
    peak = nav_series.cummax()
    drawdown = nav_series / peak - 1

    # 找到所有峰值点（drawdown == 0 的位置）
    is_peak = drawdown == 0
    peak_indices = [i for i, v in enumerate(is_peak) if v]

    drawdowns = []

    for j in range(len(peak_indices)):
        start_pos = peak_indices[j]

        # 确定回撤区间终点
        if j + 1 < len(peak_indices):
            end_pos = peak_indices[j + 1]      # 下一个峰值，包含在内
            recovered = True
        else:
            end_pos = n                         # 切片右边界（不包含）
            recovered = drawdown.iloc[-1] == 0

        # 相邻峰值之间无回撤，跳过
        if end_pos - start_pos <= 1:
            continue

        # 该区间内的回撤序列
        period_dd = drawdown.iloc[start_pos:end_pos]
        max_depth = abs(period_dd.min())

        if max_depth < threshold:
            continue

        trough_label = period_dd.idxmin()

        if recovered:
            end_label = nav_series.index[end_pos]
            start_label = nav_series.index[start_pos]
            if is_datetime:
                duration = (end_label - start_label).days
                recovery_days = (end_label - trough_label).days
            else:
                duration = end_label - start_label
                recovery_days = end_label - trough_label
        else:
            end_label = None
            recovery_days = None
            if is_datetime:
                duration = (nav_series.index[-1] - nav_series.index[start_pos]).days
            else:
                duration = nav_series.index[-1] - nav_series.index[start_pos]

        drawdowns.append({
            'start': nav_series.index[start_pos],
            'end': end_label,
            'trough': trough_label,
            'depth': max_depth,
            'duration': duration,
            'recovery_days': recovery_days,
        })

    return drawdowns


# ============================================================================
# StrategyRegimeAnalyzer — 策略市场状态适应性分析
# ============================================================================

class StrategyRegimeAnalyzer:
    """策略市场状态适应性分析器。

    消费市场状态标签序列（来自 MarketRegime 算子的 readData 结果），
    分析策略在各市场状态下的表现差异和适应性。

    Args:
        strategy_returns: 策略日收益率序列，index 为日期（DatetimeIndex）。
        regime_labels: 市场状态标签，index 为日期。
            若为 DataFrame 则每列代表一个状态维度。

    Example:
        >>> analyzer = StrategyRegimeAnalyzer(strategy_returns, regime_labels)
        >>> perf = analyzer.compute_regime_performance(dimension='bull_bear')
        >>> heatmap = analyzer.compute_adaptation_heatmap(dimension='bull_bear')
    """

    def __init__(self, strategy_returns: pd.Series,
                 regime_labels: 'pd.DataFrame | pd.Series'):
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