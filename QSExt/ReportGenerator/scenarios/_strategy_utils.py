# -*- coding: utf-8 -*-
"""策略报告共享数据构建函数

从 AccountStats 输出 dict 中提取数据并注入 DataContext，供
SingleStrategyReport 和 MultiStrategyReport 共同使用。
"""

import pandas as pd

from QSExt.ReportGenerator.core import DataContext


# ============================================================
# 元信息注入
# ============================================================

def inject_strategy_info(ctx: DataContext, strategy_name: str,
                         output: dict) -> None:
    """注入策略元信息到 meta 通道。

    Args:
        ctx: 数据上下文
        strategy_name: 策略名称
        output: AccountStats 输出字典
    """
    time_series = output.get("时间序列", pd.DataFrame())
    dt_start = time_series.index[0] if len(time_series) > 0 else "未指定"
    dt_end = time_series.index[-1] if len(time_series) > 0 else "未指定"
    ctx.set("meta", "strategy_info", {
        "name": strategy_name or "策略",
        "count": 1,
        "dt_start": dt_start,
        "dt_end": dt_end,
    })


# ============================================================
# 单策略数据构建
# ============================================================

def build_performance_stats(ctx: DataContext, output: dict) -> None:
    """从 AccountStats output 构建绩效统计数据。"""
    stats = output.get("统计数据", pd.DataFrame())
    if stats.empty:
        return
    if "绝对表现" in stats.columns:
        ctx.set("0-绩效统计", "绝对表现", stats[["绝对表现"]])
    ctx.set("0-绩效统计", "统计全表", stats)


def build_nav_data(ctx: DataContext, output: dict) -> None:
    """从 AccountStats output 构建净值走势数据。"""
    ts = output.get("时间序列", pd.DataFrame())
    if ts.empty:
        return

    nav_cols = ["净值"]
    if "基准净值" in ts.columns:
        nav_cols.append("基准净值")
    if "相对净值" in ts.columns:
        nav_cols.append("相对净值")
    ctx.set("1-净值走势", "净值", ts[nav_cols])

    ret_cols = ["收益率"]
    if "基准收益率" in ts.columns:
        ret_cols.append("基准收益率")
    ctx.set("1-净值走势", "收益率", ts[ret_cols])


def build_drawdown_data(ctx: DataContext, output: dict) -> None:
    """从 AccountStats output 构建回撤分析数据。"""
    ts = output.get("时间序列", pd.DataFrame())
    if ts.empty or "净值" not in ts.columns:
        return

    nav = ts["净值"].dropna()
    if nav.empty:
        return

    cummax = nav.cummax()
    drawdown = nav / cummax - 1
    drawdown_df = drawdown.to_frame("回撤")
    ctx.set("2-回撤分析", "回撤序列", drawdown_df)

    events = identify_drawdown_events(nav, min_pct=0.05, top_n=5)
    if not events.empty:
        ctx.set("2-回撤分析", "回撤事件", events)


def build_period_returns(ctx: DataContext, output: dict) -> None:
    """从 AccountStats output 构建分时段收益数据。"""
    ts = output.get("时间序列", pd.DataFrame())
    if ts.empty or "净值" not in ts.columns:
        return

    nav = ts["净值"].dropna()
    if len(nav) < 2:
        return

    annual = calc_annual_returns(nav)
    if not annual.empty:
        ctx.set("3-分时段收益", "年度收益", annual)

    monthly = calc_monthly_returns(nav)
    if not monthly.empty:
        ctx.set("3-分时段收益", "月度收益", monthly)


def build_trade_stats(ctx: DataContext, output: dict,
                      trade_freq: str = "M") -> None:
    """从 AccountStats output 构建交易统计数据。

    Args:
        ctx: 数据上下文
        output: AccountStats 输出字典
        trade_freq: 交易统计频率，可选 D(日)/W(周)/M(月)/Q(季)/Y(年)
    """
    trade_record = output.get("交易记录", pd.DataFrame())
    position_num = output.get("持仓数量", pd.DataFrame())

    if trade_record.empty:
        return

    # 交易概要指标
    n_trades = len(trade_record)
    buy_count = len(trade_record[trade_record["交易量"] > 0]) if "交易量" in trade_record.columns else 0
    sell_count = len(trade_record[trade_record["交易量"] < 0]) if "交易量" in trade_record.columns else 0
    avg_holdings = (position_num > 0).sum(axis=1).mean() if not position_num.empty else 0

    summary = pd.DataFrame({
        "绝对表现": {
            "总交易次数": n_trades,
            "买入次数": buy_count,
            "卖出次数": sell_count,
            "平均持仓数": avg_holdings,
        }
    })
    ctx.set("4-交易统计", "交易概要", summary)

    # 按频率汇总交易数据（用于图表）
    if "交易时点" not in trade_record.columns:
        return

    tr = trade_record.copy()
    tr["交易时点"] = pd.to_datetime(tr["交易时点"])

    if "交易量" in tr.columns and "成交价" in tr.columns:
        tr["交易金额"] = (tr["交易量"].abs() * tr["成交价"]).fillna(0)
    else:
        tr["交易金额"] = 0.0

    _FREQ_LABEL = {"D": "日", "W": "周", "M": "月", "Q": "季", "Y": "年"}
    freq_label = _FREQ_LABEL.get(trade_freq.upper(), trade_freq)
    period_key = tr["交易时点"].dt.to_period(trade_freq.upper())

    agg = tr.groupby(period_key).agg(
        交易次数=("交易量", "size"),
        交易金额=("交易金额", "sum"),
    )
    agg.index = agg.index.to_timestamp()
    agg.index.name = f"按{freq_label}统计"

    ctx.set("4-交易统计", "交易频率", agg[["交易次数"]])
    ctx.set("4-交易统计", "交易金额", agg[["交易金额"]])

    # 换手率 = 期间交易金额 / 期间账户价值均值
    ts = output.get("时间序列", pd.DataFrame())
    if not ts.empty and "账户价值" in ts.columns:
        acct_val = ts["账户价值"].dropna()
        if not acct_val.empty:
            avg_val = acct_val.groupby(acct_val.index.to_period(trade_freq.upper())).mean()
            avg_val.index = avg_val.index.to_timestamp()
            turnover = agg["交易金额"] / avg_val.reindex(agg.index)
            turnover = turnover.dropna().to_frame("换手率")
            if not turnover.empty:
                turnover.index.name = f"按{freq_label}统计"
                ctx.set("4-交易统计", "换手率", turnover)


# ============================================================
# 辅助函数
# ============================================================

def identify_drawdown_events(nav: pd.Series, min_pct: float = 0.05,
                              top_n: int = 5) -> pd.DataFrame:
    """识别主要回撤事件。

    Args:
        nav: 净值序列
        min_pct: 最小回撤幅度阈值
        top_n: 最多返回的事件数

    Returns:
        DataFrame，columns=[开始时点, 最低点时点, 最大回撤, 持续天数]
    """
    cummax = nav.cummax()
    drawdown = nav / cummax - 1

    events = []
    in_event = False
    start_dt = None
    trough_dt = None
    trough_val = 0.0

    for dt, val in drawdown.items():
        if val < 0 and not in_event:
            in_event = True
            start_dt = dt
            trough_dt = dt
            trough_val = val
        elif val < 0 and in_event:
            if val < trough_val:
                trough_dt = dt
                trough_val = val
        elif val >= 0 and in_event:
            in_event = False
            if trough_val <= -min_pct:
                duration = (dt - start_dt).days if hasattr((dt - start_dt), "days") else 0
                events.append({
                    "开始时点": start_dt,
                    "最低点时点": trough_dt,
                    "最大回撤": trough_val,
                    "持续天数": duration,
                })
            start_dt = None
            trough_dt = None
            trough_val = 0.0

    if in_event and trough_val <= -min_pct:
        duration = (nav.index[-1] - start_dt).days if hasattr((nav.index[-1] - start_dt), "days") else 0
        events.append({
            "开始时点": start_dt,
            "最低点时点": trough_dt,
            "最大回撤": trough_val,
            "持续天数": duration,
        })

    if not events:
        return pd.DataFrame()

    df = pd.DataFrame(events).sort_values("最大回撤").head(top_n).reset_index(drop=True)
    return df


def calc_annual_returns(nav: pd.Series) -> pd.DataFrame:
    """计算年度收益率。"""
    if not isinstance(nav.index, pd.DatetimeIndex):
        return pd.DataFrame()

    yearly = nav.resample("YE").last()
    if len(yearly) < 1:
        return pd.DataFrame()

    returns = yearly.pct_change()
    returns.iloc[0] = yearly.iloc[0] / 1.0 - 1

    result = pd.DataFrame({
        "年末净值": yearly.values,
        "年度收益率": returns.values,
    }, index=[dt.year for dt in yearly.index])
    result.index.name = "年度"
    return result


def calc_monthly_returns(nav: pd.Series) -> pd.DataFrame:
    """计算月度收益矩阵（行=年份，列=月份）。"""
    if not isinstance(nav.index, pd.DatetimeIndex):
        return pd.DataFrame()

    monthly = nav.resample("ME").last()
    if len(monthly) < 2:
        return pd.DataFrame()

    returns = monthly.pct_change().dropna()
    if returns.empty:
        return pd.DataFrame()

    matrix = {}
    for dt, ret in returns.items():
        year = dt.year
        month = dt.month
        matrix.setdefault(year, {})[month] = ret

    df = pd.DataFrame(matrix).T
    df.index.name = "年度"
    df.columns = [f"{m}月" for m in sorted(df.columns)]
    return df
