# coding=utf-8
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
