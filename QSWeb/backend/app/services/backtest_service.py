"""
回测服务

实现截面因子测试（IC 分析、分位数组合、换手率）和策略回测。
因子数据通过 FactorService 读取，统计计算基于 numpy/pandas 实现。
"""

import asyncio
import datetime
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd

from app.services.factor_service import factor_service
from app.tasks.manager import task_manager


class BacktestService:
    """回测服务"""

    def __init__(self):
        self._history: List[Dict[str, Any]] = []  # 回测历史（内存存储）

    # ─── 工具方法 ─────────────────────────────────────────────

    async def _read_factor_and_price(
        self,
        conn_id: str,
        table_name: str,
        factor_name: str,
        price_table_name: str,
        price_field: str,
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        读取因子数据和价格数据，返回对齐的 DataFrame。

        Returns
        -------
        factor_df : pd.DataFrame
            因子数据，MultiIndex [datetime, code]，列: factor_value
        price_df : pd.DataFrame
            价格数据（日频收益率），MultiIndex [datetime, code]，列: return
        """
        db = await factor_service._get_factor_db(conn_id)

        price_tbl = price_table_name or table_name
        factor_names = [factor_name]

        loop = asyncio.get_running_loop()

        def _sync():
            ft = db.getTable(table_name)
            dts = ft.getDateTime(ifactor_name=factor_name, iid=None)
            if start_date:
                start_dt = datetime.datetime.combine(start_date, datetime.datetime.min.time())
                dts = [d for d in dts if d >= start_dt]
            if end_date:
                end_dt = datetime.datetime.combine(end_date, datetime.datetime.min.time())
                dts = [d for d in dts if d <= end_dt]

            ids_list = ft.getID(ifactor_name=factor_name, idt=None)
            if len(ids_list) > 500:
                ids_list = ids_list[:500]

            factor_data = ft.readData(
                factor_names=factor_names,
                ids=ids_list,
                dts=dts
            )

            # 提取因子值
            if hasattr(factor_data, 'iloc'):
                factor_series = factor_data.iloc[:, 0] if factor_data.ndim > 1 else factor_data
            else:
                factor_series = factor_data[factor_name]

            factor_df = factor_series.to_frame("factor_value") if hasattr(factor_series, 'to_frame') else pd.DataFrame({"factor_value": factor_series})
            if factor_df.index.nlevels >= 2:
                # MultiIndex [datetime, code]
                pass
            elif isinstance(factor_df.index, pd.DatetimeIndex):
                factor_df["code"] = ""
                factor_df = factor_df.reset_index().set_index(["datetime", "code"])  # type: ignore[union-attr]

            factor_df.index.names = ["datetime", "code"]

            # 读取价格数据
            pft = db.getTable(price_tbl)
            price_dts = [d for d in dts if d in pft.getDateTime(ifactor_name=price_field, iid=None)]
            if not price_dts:
                price_dts = dts

            price_raw = pft.readData(
                factor_names=[price_field],
                ids=ids_list,
                dts=price_dts
            )

            if hasattr(price_raw, 'iloc'):
                price_series = price_raw.iloc[:, 0] if price_raw.ndim > 1 else price_raw
            else:
                price_series = price_raw[price_field]

            price_df = price_series.to_frame("price") if hasattr(price_series, 'to_frame') else pd.DataFrame({"price": price_series})
            if price_df.index.nlevels < 2:
                price_df["code"] = ""
                price_df = price_df.reset_index().set_index(["datetime", "code"])

            price_df.index.names = ["datetime", "code"]

            # 计算收益率
            price_df = price_df.sort_index()
            returns = price_df.groupby("code")["price"].pct_change()
            price_df["return"] = returns

            return factor_df, price_df

        return await loop.run_in_executor(None, _sync)

    @staticmethod
    def _align_data(factor_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
        """对齐因子和价格数据"""
        merged = factor_df.join(price_df[["return"]], how="inner")
        merged = merged.dropna()
        return merged

    # ─── IC 分析 ─────────────────────────────────────────────

    async def run_ic_analysis(self, req) -> Dict[str, Any]:
        """运行 IC 分析"""
        factor_df, price_df = await self._read_factor_and_price(
            req.conn_id, req.table_name, req.factor_name,
            req.price_table_name, req.price_field,
            req.start_date, req.end_date
        )
        return await self._ic_analysis_sync(req, factor_df, price_df)

    async def _ic_analysis_sync(self, req, factor_df: pd.DataFrame, price_df: pd.DataFrame) -> Dict[str, Any]:
        """同步 IC 分析计算"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _calc_ic_analysis, req, factor_df, price_df)

    # ─── 分位数组合 ─────────────────────────────────────────

    async def run_quantile_portfolio(self, req) -> Dict[str, Any]:
        """运行分位数组合分析"""
        factor_df, price_df = await self._read_factor_and_price(
            req.conn_id, req.table_name, req.factor_name,
            req.price_table_name, req.price_field,
            req.start_date, req.end_date
        )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _calc_quantile_portfolio, req, factor_df, price_df)

    # ─── 换手率 ─────────────────────────────────────────────

    async def run_turnover(self, req) -> Dict[str, Any]:
        """运行换手率分析"""
        factor_df, price_df = await self._read_factor_and_price(
            req.conn_id, req.table_name, req.factor_name,
            req.price_table_name or req.table_name, req.price_field or "复权收盘价",
            req.start_date, req.end_date
        )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _calc_turnover, req, factor_df)

    # ─── 策略回测 ──────────────────────────────────────────

    async def submit_strategy_backtest(self, req) -> str:
        """提交策略回测异步任务，返回 task_id"""
        name = f"策略回测-{req.factor_name}"

        async def _run_with_id(task_id: str):
            """闭包捕获 task_id 执行回测"""
            await task_manager.update_progress(task_id, 5, "读取因子数据...")
            factor_df, price_df = await self._read_factor_and_price(
                req.conn_id, req.table_name, req.factor_name,
                req.price_table_name, req.price_field,
                req.start_date, req.end_date
            )

            await task_manager.update_progress(task_id, 20, "数据对齐...")
            loop = asyncio.get_running_loop()

            await task_manager.update_progress(task_id, 30, "运行回测...")
            result = await loop.run_in_executor(
                None, _run_strategy_backtest, req, factor_df, price_df
            )

            await task_manager.update_progress(task_id, 95, "保存结果...")

            # 保存到历史
            history_entry = {
                "task_id": task_id,
                "name": name,
                "factor_name": req.factor_name,
                "params": req.model_dump(mode="json"),
                "summary": result.get("summary", {}),
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            self._history.append(history_entry)

            return result

        # 先分配 task_id
        import uuid
        task_id = uuid.uuid4().hex[:12]
        # 提交包含 task_id 的协程
        task_id = await task_manager.submit(name, _run_with_id(task_id), task_id=task_id)
        return task_id

    # ─── 回测结果 ──────────────────────────────────────────

    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取异步任务结果"""
        task = task_manager.get_task(task_id)
        if task is None:
            return None
        return task.result if task.status.value == "completed" else None

    # ─── 回测历史 ──────────────────────────────────────────

    def get_history(self, factor_name: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """获取回测历史"""
        results = self._history
        if factor_name:
            results = [r for r in results if r.get("factor_name") == factor_name]

        results = sorted(results, key=lambda r: r.get("created_at", ""), reverse=True)
        return results[:limit]

    # ─── 回测注册 ───────────────────────────────────────────

    async def register_backtest(self, task_id: str, name: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
        """注册回测到 QSRegistry"""
        task = task_manager.get_task(task_id)
        if task is None:
            raise ValueError(f"任务不存在: {task_id}")
        if task.status.value != "completed":
            raise ValueError(f"任务未完成: {task.status.value}")

        result = task.result or {}
        bt_name = name or task.name

        # 注册到 Neo4j
        try:
            from app.services.registry_service import registry_service
            gdb = await registry_service._get_gdb()

            import hashlib
            import json
            raw = f"bt-{task_id}"
            bt_qsid = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()

            cat = category or "SectionFactor"
            summary_json = json.dumps(result.get("summary", {}), ensure_ascii=False, default=str)
            params_json = json.dumps(result.get("params", {}), ensure_ascii=False, default=str)

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: gdb._runCypher("""
                MERGE (bt:`回测` {QSID: $qsid})
                SET bt += {
                    Name: $name,
                    Category: $category,
                    SummaryJSON: $summary_json,
                    ParamsJSON: $params_json,
                    CreatedAt: $now
                }
            """, {
                "qsid": bt_qsid,
                "name": bt_name,
                "category": cat,
                "summary_json": summary_json,
                "params_json": params_json,
                "now": now,
            }))

            # 关联因子
            factor_name = result.get("params", {}).get("factor_name", "")
            if factor_name:
                factor_results = gdb._runCypher(
                    "MATCH (f:`因子` {Name: $name}) RETURN f.QSID",
                    {"name": factor_name}
                )
                for fr in factor_results:
                    await loop.run_in_executor(None, lambda: gdb._runCypher("""
                        MATCH (bt:`回测` {QSID: $bt_qsid})
                        MATCH (f:`因子` {QSID: $f_qsid})
                        MERGE (bt)-[:`分析因子`]->(f)
                    """, {"bt_qsid": bt_qsid, "f_qsid": fr["f.QSID"]}))

            return {"message": f"回测已注册到 QSRegistry", "qsid": bt_qsid, "name": bt_name}
        except ImportError:
            return {"message": "QSRegistry 不可用，跳过注册", "name": bt_name}
        except Exception as e:
            raise ValueError(f"注册失败: {str(e)}")


# 全局实例
backtest_service = BacktestService()


# ─── 同步计算函数（在 executor 中运行）───────────────────────


def _calc_ic_analysis(req, factor_df: pd.DataFrame, price_df: pd.DataFrame) -> Dict[str, Any]:
    """IC 分析计算"""
    merged = factor_df.join(price_df[["return"]], how="inner").dropna()

    ic_records = []
    dts = sorted(set(merged.index.get_level_values("datetime")))

    for dt in dts:
        cross = merged.loc[dt] if dt in merged.index.get_level_values("datetime") else None
        if cross is None or len(cross) < 10:
            continue

        f_vals = cross["factor_value"]
        ret_vals = cross["return"]

        # 计算 IC（Spearman 或 Pearson）
        if req.corr_method == "spearman":
            ic_val = f_vals.rank().corr(ret_vals.rank(), method="pearson")
        else:
            ic_val = f_vals.corr(ret_vals)

        ic_records.append({
            "date": str(dt)[:10] if hasattr(dt, 'strftime') else str(dt),
            "ic": float(ic_val) if not np.isnan(ic_val) else 0.0,
        })

    ic_series = ic_records
    ic_values = [r["ic"] for r in ic_records]

    # 统计摘要
    if ic_values:
        arr = np.array(ic_values)
        positive_ratio = float(np.mean(arr > 0)) if len(arr) > 0 else 0.0
        summary = {
            "mean_ic": float(np.mean(arr)),
            "std_ic": float(np.std(arr)),
            "ir": float(np.mean(arr) / np.std(arr)) if np.std(arr) > 0 else 0.0,
            "positive_ratio": positive_ratio,
            "n_periods": len(arr),
            "max_ic": float(np.max(arr)),
            "min_ic": float(np.min(arr)),
        }
    else:
        summary = {"mean_ic": 0, "std_ic": 0, "ir": 0, "positive_ratio": 0, "n_periods": 0}

    # IC 衰减（简化：多期滞后）
    ic_decay = []
    if len(ic_series) > 1:
        for lag in range(1, min(6, len(ic_series))):
            lag_corr = np.corrcoef(ic_values[:-lag], ic_values[lag:])[0, 1] if len(ic_values) > lag else 0
            ic_decay.append({"lag": lag, "autocorr": float(lag_corr) if not np.isnan(lag_corr) else 0.0})

    return {
        "ic_series": ic_series,
        "ic_decay": ic_decay,
        "summary": summary,
        "factor_name": req.factor_name,
        "corr_method": req.corr_method,
    }


def _calc_quantile_portfolio(req, factor_df: pd.DataFrame, price_df: pd.DataFrame) -> Dict[str, Any]:
    """分位数组合计算"""
    merged = factor_df.join(price_df[["return"]], how="inner").dropna()

    n_groups = req.n_groups
    dts = sorted(set(merged.index.get_level_values("datetime")))

    # 按再平衡频率选择时点
    if req.rebalance_freq == "monthly":
        rebal_dts = [d for i, d in enumerate(dts) if i == 0 or d.month != dts[i - 1].month]
    elif req.rebalance_freq == "weekly":
        rebal_dts = [d for i, d in enumerate(dts) if i == 0 or d.isocalendar()[1] != dts[i - 1].isocalendar()[1]]
    else:
        rebal_dts = dts

    # 构建持仓矩阵：每个再平衡日，每只股票属于哪个分组
    dt_list = list(dts)
    all_codes = sorted(set(merged.index.get_level_values("code")))
    portfolio_returns = {g: [] for g in range(n_groups)}

    current_groups = {code: -1 for code in all_codes}
    rebal_idx = 0

    for i, dt in enumerate(dt_list):
        # 再平衡
        if rebal_idx < len(rebal_dts) and dt == rebal_dts[rebal_idx]:
            cross = merged.loc[dt] if dt in merged.index.get_level_values("datetime") else None
            if cross is not None and len(cross) >= n_groups:
                sorted_codes = cross["factor_value"].sort_values().index.tolist()
                group_size = max(1, len(sorted_codes) // n_groups)
                for g in range(n_groups):
                    start = g * group_size
                    end = start + group_size if g < n_groups - 1 else len(sorted_codes)
                    for code in sorted_codes[start:end]:
                        current_groups[code] = g
            rebal_idx += 1

        # 计算当日各分组收益率
        cross_ret = merged.loc[dt] if dt in merged.index.get_level_values("datetime") else None
        if cross_ret is not None:
            for g in range(n_groups):
                codes_in_group = [c for c, grp in current_groups.items() if grp == g]
                group_rets = cross_ret.loc[cross_ret.index.isin(codes_in_group), "return"] if hasattr(cross_ret, 'loc') else pd.Series(dtype=float)
                if len(group_rets) > 0:
                    portfolio_returns[g].append({"date": str(dt)[:10] if hasattr(dt, 'strftime') else str(dt), "return": float(group_rets.mean())})

    # 计算净值曲线
    nav_series = []
    for g in range(n_groups):
        nav = 1.0
        nav_data = []
        for r in portfolio_returns[g]:
            nav *= (1 + r["return"])
            nav_data.append({"date": r["date"], "nav": round(nav, 6)})
        nav_series.append({"group": g + 1, "label": f"Q{g + 1}", "data": nav_data})

    # 多空净值（Q1 - Qn）
    if len(nav_series) >= 2:
        long_nav = {p["date"]: p["nav"] for p in nav_series[-1]["data"]}  # Qn (最差组)
        short_nav = {p["date"]: p["nav"] for p in nav_series[0]["data"]}  # Q1 (最好组)
        ls_data = []
        for date in sorted(set(long_nav.keys()) & set(short_nav.keys())):
            ls_data.append({"date": date, "nav": round(short_nav[date] - long_nav[date] + 1, 6)})
    else:
        ls_data = []

    # 统计摘要
    summary = {}
    for g_data in nav_series:
        navs = [p["nav"] for p in g_data["data"]]
        if len(navs) >= 2:
            total_return = navs[-1] / navs[0] - 1
            n_years = len(navs) / 252
            ann_return = (navs[-1] / navs[0]) ** (1 / n_years) - 1 if n_years > 0 else 0
            summary[f"Q{g_data['group']}"] = {
                "total_return": round(total_return * 100, 2),
                "annual_return": round(ann_return * 100, 2),
            }

    return {
        "nav_series": [g for g in nav_series],
        "long_short_nav": ls_data,
        "summary": summary,
        "factor_name": req.factor_name,
        "n_groups": n_groups,
    }


def _calc_turnover(req, factor_df: pd.DataFrame) -> Dict[str, Any]:
    """换手率计算"""
    dts = sorted(set(factor_df.index.get_level_values("datetime")))

    if req.rebalance_freq == "monthly":
        rebal_dts = [d for i, d in enumerate(dts) if i == 0 or d.month != dts[i - 1].month]
    elif req.rebalance_freq == "weekly":
        rebal_dts = [d for i, d in enumerate(dts) if i == 0 or d.isocalendar()[1] != dts[i - 1].isocalendar()[1]]
    else:
        rebal_dts = dts

    turnover_records = []
    prev_top_codes = set()

    for dt in rebal_dts:
        cross = factor_df.loc[dt] if dt in factor_df.index.get_level_values("datetime") else None
        if cross is None or len(cross) < 2:
            continue

        n_top = max(1, int(len(cross) * req.top_pct))
        top_codes = set(cross["factor_value"].sort_values(ascending=False).head(n_top).index.tolist())

        if prev_top_codes:
            staying = len(top_codes & prev_top_codes)
            turnover = 1.0 - staying / len(prev_top_codes) if prev_top_codes else 0.0
        else:
            turnover = 0.0

        turnover_records.append({
            "date": str(dt)[:10] if hasattr(dt, 'strftime') else str(dt),
            "turnover": round(turnover, 4),
        })
        prev_top_codes = top_codes

    avg_turnover = float(np.mean([r["turnover"] for r in turnover_records])) if turnover_records else 0.0

    return {
        "turnover_series": turnover_records,
        "avg_turnover": round(avg_turnover, 4),
        "factor_name": req.factor_name,
    }


def _run_strategy_backtest(
    req,
    factor_df: pd.DataFrame,
    price_df: pd.DataFrame,
) -> Dict[str, Any]:
    """策略回测（同步计算）"""
    merged = factor_df.join(price_df[["return"]], how="inner").dropna()

    dts = sorted(set(merged.index.get_level_values("datetime")))
    if not dts:
        return {"nav_series": [], "daily_returns": [], "trades": [], "summary": {}}

    # 再平衡时点
    if req.rebalance_freq == "monthly":
        rebal_dts = set(d for i, d in enumerate(dts) if i == 0 or d.month != dts[i - 1].month)
    elif req.rebalance_freq == "weekly":
        rebal_dts = set(d for i, d in enumerate(dts) if i == 0 or d.isocalendar()[1] != dts[i - 1].isocalendar()[1])
    else:
        rebal_dts = set(dts)

    initial_capital = req.initial_capital
    commission = req.commission_rate
    slippage = req.slippage
    top_n = req.top_n
    direction = req.signal_direction

    cash = initial_capital
    holdings: Dict[str, float] = {}  # code -> shares
    nav = 1.0
    nav_series = []
    daily_returns = []
    trades = []
    prev_prices = {}

    total_steps = len(dts)
    for step, dt in enumerate(dts):
        cross = merged.loc[dt] if dt in merged.index.get_level_values("datetime") else None
        if cross is None:
            continue

        prices = {}
        for code in cross.index:
            if "return" in cross.columns:
                if code not in prev_prices:
                    prev_prices[code] = 1.0
                prev_prices[code] = prev_prices[code] * (1 + cross.loc[code, "return"])
                prices[code] = prev_prices[code]

        # 再平衡
        if dt in rebal_dts and len(cross) >= top_n:
            f_vals = cross["factor_value"].sort_values(ascending=direction in ("long", "long_short"))

            if direction == "long" or direction == "long_short":
                target_codes = set(f_vals.head(top_n).index.tolist())
            elif direction == "short":
                target_codes = set(f_vals.index.tolist()[-top_n:])
            else:
                target_codes = set(f_vals.head(top_n).index.tolist())

            # 卖出不在目标中的持仓
            for code in list(holdings.keys()):
                if code not in target_codes and code in prices:
                    sell_price = prices[code] * (1 - slippage)
                    cash += holdings[code] * sell_price * (1 - commission)
                    trades.append({
                        "date": str(dt)[:10] if hasattr(dt, 'strftime') else str(dt),
                        "code": str(code),
                        "action": "sell",
                        "shares": round(holdings[code], 2),
                        "price": round(sell_price, 4),
                    })
                    del holdings[code]

            # 买入目标中的
            n_target = len(target_codes)
            if n_target > 0 and cash > 0:
                budget_per_stock = cash / n_target
                for code in target_codes:
                    if code in prices:
                        buy_price = prices[code] * (1 + slippage)
                        shares = (budget_per_stock * (1 - commission)) / buy_price
                        if shares > 0:
                            cost = shares * buy_price * (1 + commission)
                            cash -= cost
                            holdings[code] = holdings.get(code, 0) + shares
                            trades.append({
                                "date": str(dt)[:10] if hasattr(dt, 'strftime') else str(dt),
                                "code": str(code),
                                "action": "buy",
                                "shares": round(shares, 2),
                                "price": round(buy_price, 4),
                            })

        # 计算当日净值
        portfolio_value = cash
        for code, shares in holdings.items():
            if code in prices:
                portfolio_value += shares * prices[code]

        if initial_capital > 0:
            current_nav = portfolio_value / initial_capital
        else:
            current_nav = nav

        daily_return = (current_nav / nav - 1) if nav > 0 else 0
        nav = current_nav

        nav_series.append({
            "date": str(dt)[:10] if hasattr(dt, 'strftime') else str(dt),
            "nav": round(nav, 6),
        })
        daily_returns.append({
            "date": str(dt)[:10] if hasattr(dt, 'strftime') else str(dt),
            "return": round(daily_return, 6),
        })

    # 统计指标
    returns = np.array([r["return"] for r in daily_returns])
    summary = {}
    if len(returns) > 1:
        total_return = nav - 1
        n_years = len(returns) / 252
        ann_return = (nav ** (1 / n_years) - 1) if n_years > 0 else 0
        ann_vol = float(np.std(returns) * np.sqrt(252))
        max_dd = float(_calc_max_drawdown([r["nav"] for r in nav_series]))
        sharpe = float(ann_return / ann_vol) if ann_vol > 0 else 0
        win_rate = float(np.mean(returns > 0))
        summary = {
            "total_return": round(total_return * 100, 2),
            "annual_return": round(ann_return * 100, 2),
            "annual_volatility": round(ann_vol * 100, 2),
            "max_drawdown": round(max_dd * 100, 2),
            "sharpe_ratio": round(sharpe, 4),
            "win_rate": round(win_rate * 100, 2),
            "n_trades": len([t for t in trades if t["action"] == "buy"]),
            "info_ratio": round(sharpe, 4),
        }

    return {
        "nav_series": nav_series,
        "daily_returns": daily_returns,
        "trades": trades,
        "summary": summary,
        "params": req.model_dump(mode="json"),
    }


def _calc_max_drawdown(navs: List[float]) -> float:
    """计算最大回撤"""
    if not navs:
        return 0.0
    peak = navs[0]
    max_dd = 0.0
    for n in navs:
        if n > peak:
            peak = n
        dd = (peak - n) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd
