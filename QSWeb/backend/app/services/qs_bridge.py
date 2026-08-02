"""
QSBridge 桥接层

桥接 FactorService / RegistryService 与 QuantStudio 回测框架。
负责因子解析、回测节点构造、引擎执行和结果转换。
"""

import datetime as dt
import json
import logging
import os
from typing import List, Optional, Dict, Any

import pandas as pd
import numpy as np
import yaml

from app.models.backtest import (
    FactorRef,
    PriceRef,
    ModuleRunConfig,
    ResultNode,
    BACKTEST_MODULE_REGISTRY,
)

logger = logging.getLogger(__name__)

# ─── 全局回测配置 ─────────────────────────────────────────────────

from app.core.config import settings

DEFAULT_BACKTEST_CONFIG = {
    "dtruler_lookback_years": 10,
    "trading_day_source": None,
    "section_id_sources": {},
}


def _load_backtest_config() -> dict:
    """从 QSWebConfig.yaml 加载回测配置节"""
    if os.path.exists(settings.QS_CONFIG_PATH):
        try:
            with open(settings.QS_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            bt_cfg = cfg.get("backtest", {})
            merged = {**DEFAULT_BACKTEST_CONFIG, **bt_cfg}
            if "trading_day_source" not in bt_cfg:
                merged["trading_day_source"] = None
            return merged
        except Exception:
            logger.warning("加载回测配置失败，使用默认配置")
    return dict(DEFAULT_BACKTEST_CONFIG)


# ─── 声明式回测模块构造器 ────────────────────────────────────────

_BT_NODE_BUILDERS = {
    "ic": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.IC",
        "calc_class": "CalcIC",
        "node_module": "QuantStudio.BackTest.SectionFactor.IC",
        "node_class": "IC",
        "requires_price": True,
        "calc_params": ["lookback", "period_lookback", "corr_method"],
        "node_params_map": {"RollingAvgPeriod": "rolling_avg_period"},
        "default_node_params": {"GenReport": False},
    },
    "ic_decay": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.IC",
        "calc_class": "CalcIC",
        "node_module": "QuantStudio.BackTest.SectionFactor.IC",
        "node_class": "ICDecay",
        "requires_price": True,
        "per_factor": True,  # 每个因子分别构造 calc
        "calc_params": ["lookback", "period_lookback", "corr_method"],
        "default_node_params": {"GenReport": False},
    },
    "multi_portfolio": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.QuantilePortfolio",
        "calc_class": "makeQuantilePortfolio",
        "node_module": "QuantStudio.BackTest.SectionFactor.QuantilePortfolio",
        "node_class": "MultiPortfolio",
        "requires_price": False,
        "calc_params": ["group_num", "ascending"],
        "portfolios_mode": True,  # 直接返回 portfolio_list
        "default_node_params": {"GenReport": False},
    },
    "factor_turnover": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.Correlation",
        "calc_class": "CalcFactorTurnover",
        "node_module": "QuantStudio.BackTest.SectionFactor.Correlation",
        "node_class": "FactorTurnover",
        "requires_price": False,
        "calc_params": ["lookback", "period_lookback", "corr_method"],
        "default_node_params": {"GenReport": False},
    },
    "section_correlation": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.Correlation",
        "calc_class": "CalcSectionCorrelation",
        "node_module": "QuantStudio.BackTest.SectionFactor.Correlation",
        "node_class": "SectionCorrelation",
        "requires_price": False,
        "calc_params": ["corr_method"],
        "default_node_params": {"GenReport": False},
    },
    "fama_macbeth": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.ReturnDecomposition",
        "calc_class": "CalcFamaMacBethRegression",
        "node_module": "QuantStudio.BackTest.SectionFactor.ReturnDecomposition",
        "node_class": "FamaMacBethRegression",
        "requires_price": True,
        "calc_params": ["lookback", "period_lookback"],
        "node_params_map": {"RollingAvgPeriod": "rolling_avg_period"},
        "default_node_params": {"GenReport": False},
    },
}


class QSBridge:
    """QuantStudio 回测桥接层"""

    def __init__(self, factor_service, registry_service=None):
        """
        Parameters
        ----------
        factor_service : FactorService
            因子数据服务（管理 FactorDB 连接）
        registry_service : RegistryService, optional
            QSRegistry 服务（后续接入 QSRegistry 因子源时使用）
        """
        self._factor_service = factor_service
        self._registry_service = registry_service

    # ─── 因子获取 ─────────────────────────────────────────────

    async def _get_factor_from_db(
        self, conn_id: str, table_name: str, factor_name: str
    ):
        """从 FactorDB 获取单个 Factor 对象"""
        db = await self._factor_service._get_factor_db(conn_id)

        import asyncio
        loop = asyncio.get_running_loop()

        def _sync():
            ft = db.getTable(table_name)
            return ft.getFactor(factor_name)

        return await loop.run_in_executor(None, _sync)

    # ─── 时点和截面 ───────────────────────────────────────────

    async def _get_dtruler_and_dts(
        self, conn_id: str, table_name: str, factor_name: str,
        start_date: str, end_date: str, dt_mode: str = "natural"
    ):
        """获取时点标尺和计算时点

        DTRuler 根据全局配置中的 dtruler_lookback_years 前推起始时间；
        DTs 按 dt_mode 参数选择自然日或交易日（由前端用户选择）。

        Returns
        -------
        Tuple[List[datetime], List[datetime]]
            (DTRuler, DTs)
        """
        db = await self._factor_service._get_factor_db(conn_id)
        cfg = _load_backtest_config()

        import asyncio
        loop = asyncio.get_running_loop()

        # 交易日模式：通过 FactorService 获取配置的 FactorDB 实例（复用缓存）
        trading_db = None
        trading_method = None
        trading_method_args = {}
        if dt_mode == "trading":
            tds = cfg.get("trading_day_source")
            if tds and tds.get("conn_id"):
                trading_db = await self._factor_service._get_factor_db(tds["conn_id"])
                trading_method = tds.get("method", "getTradeDay")
                trading_method_args = tds.get("method_args", {})

        def _sync():
            ft = db.getTable(table_name)
            start_dt = dt.datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = dt.datetime.strptime(end_date, "%Y-%m-%d")

            lookback_years = cfg.get("dtruler_lookback_years", 10)
            ruler_start_dt = start_dt - dt.timedelta(days=365 * lookback_years + 1)

            if dt_mode == "trading" and trading_db is not None and trading_method is not None:
                # 交易日模式：DTRuler 和 DTs 都从交易日源获取，保持一致
                method = getattr(trading_db, trading_method)
                dtruler = method(start_date=ruler_start_dt, end_date=end_dt, **trading_method_args)
                dts = method(start_date=start_dt, end_date=end_dt, **trading_method_args)
            else:
                # 自然日模式：两者都从因子表获取
                dtruler = ft.getDateTime(
                    ifactor_name=factor_name, iid=None,
                    start_dt=ruler_start_dt, end_dt=end_dt
                )
                dts = ft.getDateTime(
                    ifactor_name=factor_name, iid=None,
                    start_dt=start_dt, end_dt=end_dt
                )

            return dtruler, dts

        return await loop.run_in_executor(None, _sync)

    async def _get_section_ids(
        self, conn_id: str, table_name: str, factor_name: str,
        descriptor_ids: Optional[List[str]] = None
    ) -> List[str]:
        """获取截面 ID 列表"""
        if descriptor_ids:
            return descriptor_ids

        db = await self._factor_service._get_factor_db(conn_id)

        import asyncio
        loop = asyncio.get_running_loop()

        def _sync():
            ft = db.getTable(table_name)
            return ft.getID(ifactor_name=factor_name, idt=None)

        return await loop.run_in_executor(None, _sync)

    # ─── CalcDTs 变换 ──────────────────────────────────────────

    @staticmethod
    def _compute_calc_dts(dts: List[dt.datetime], rule: str) -> List[dt.datetime]:
        """根据规则将 DTs 按频率采样为计算时点序列

        Parameters
        ----------
        dts : List[datetime]
            原始时点序列
        rule : str
            格式 <数字><单位>，单位 m=月, w=周, q=季度, y=年。
            例如: "1m"=月末, "2w"=双周, "3m"=季末, "1y"=年末

        Returns
        -------
        List[datetime]
        """
        import re
        if not rule or not dts:
            return []

        m = re.match(r"^(\d+)([mwqy])$", rule.strip())
        if not m:
            return []

        n = int(m.group(1))
        unit = m.group(2)
        dts = sorted(dts)
        result = [dts[0]]

        if unit == "m":
            # 每 N 个月取最后一天
            for d in dts:
                months_since = (d.year - result[-1].year) * 12 + (d.month - result[-1].month)
                if months_since >= n:
                    result.append(d)
                else:
                    result[-1] = d
        elif unit == "w":
            # 每 N 周取最后一天（按 ISO 周分组）
            first_week = result[0].isocalendar()[:2]  # (year, week)
            for d in dts:
                cur_week = d.isocalendar()[:2]
                weeks_diff = (cur_week[0] - first_week[0]) * 52 + (cur_week[1] - first_week[1])
                if weeks_diff >= n:
                    result.append(d)
                    first_week = d.isocalendar()[:2]
                else:
                    result[-1] = d
        elif unit == "q":
            # 每 N 个季度取最后一天
            for d in dts:
                q_since = (d.year - result[-1].year) * 4 + ((d.month - 1) // 3 - (result[-1].month - 1) // 3)
                if q_since >= n:
                    result.append(d)
                else:
                    result[-1] = d
        elif unit == "y":
            # 每 N 年取最后一天
            for d in dts:
                if d.year - result[-1].year >= n:
                    result.append(d)
                else:
                    result[-1] = d

        return result

    # ─── 回测节点构造 ─────────────────────────────────────────

    def _build_node_sync(
        self, cfg: ModuleRunConfig, price_factor,
        descriptor_ids: List[str], dts: List[dt.datetime]
    ):
        """通用回测节点构造器（声明式）

        根据 _BT_NODE_BUILDERS 中的模块定义自动构造 Calc + Node。
        """
        import importlib

        builder = _BT_NODE_BUILDERS.get(cfg.module_key)
        if builder is None:
            raise ValueError(f"未知的回测模块: {cfg.module_key}")

        params = cfg.params

        # 动态导入 calc 和 node 类
        calc_mod = importlib.import_module(builder["calc_module"])
        calc_cls = getattr(calc_mod, builder["calc_class"])
        node_mod = importlib.import_module(builder["node_module"])
        node_cls = getattr(node_mod, builder["node_class"])

        # CalcDTRuler
        calc_dt_rule = params.get("calc_dt_rule", "")
        calc_dtruler = None
        if calc_dt_rule:
            calc_dtruler = self._compute_calc_dts(dts, calc_dt_rule)
        factor_args = {"CalcDTRuler": calc_dtruler} if calc_dtruler else {}

        # 提取 calc 参数
        calc_kwargs = {}
        for pname in builder.get("calc_params", []):
            if pname in params:
                calc_kwargs[pname] = params[pname]

        label = cfg.instance_label or cfg.module_key

        # 构造 node_params
        node_params = dict(builder.get("default_node_params", {}))
        node_params["Name"] = label
        for node_key, param_key in builder.get("node_params_map", {}).items():
            if param_key in params:
                node_params[node_key] = params[param_key]

        # 特殊模式：portfolios_mode（分位数组合）
        if builder.get("portfolios_mode"):
            factor = cfg._resolved_factors[0]
            portfolio_list = calc_cls(
                factor=factor,
                descriptor_ids=descriptor_ids,
                **calc_kwargs,
            )
            return node_cls(
                portfolio_list[0] if portfolio_list else None,
                portfolio_list=portfolio_list,
                args=node_params,
            )

        # per_factor 模式：每个因子分别构造 calc
        if builder.get("per_factor"):
            calc_factors = []
            for factor in cfg._resolved_factors:
                cf = calc_cls(
                    descriptor_ids=descriptor_ids,
                    **calc_kwargs,
                )(
                    factor,
                    price=price_factor,
                    factor_args=factor_args,
                )
                calc_factors.append(cf)
            return node_cls(calc_factors, args=node_params)

        # 标准模式：所有因子传给同一个 calc
        calc_kwargs_with_base = {"descriptor_ids": descriptor_ids, **calc_kwargs}
        calc_factor = calc_cls(**calc_kwargs_with_base)(
            *cfg._resolved_factors,
            price=price_factor,
            factor_args=factor_args,
        )
        return node_cls(calc_factor, args=node_params)

    # ─── 回测执行 ─────────────────────────────────────────────

    async def run_backtest(
        self,
        module_configs: List[ModuleRunConfig],
        start_date: str,
        end_date: str,
        dt_mode: str = "natural",
        rebalance_dts: Optional[List[str]] = None,
    ) -> ResultNode:
        """执行回测并返回结果树

        Parameters
        ----------
        module_configs : List[ModuleRunConfig]
            模块配置列表（每个模块自含 price_ref 和 descriptor_ids）
        start_date : str
            YYYY-MM-DD
        end_date : str
            YYYY-MM-DD
        dt_mode : str
            时点模式："natural"=自然日, "trading"=交易日
        rebalance_dts : List[str], optional
            再平衡时点

        Returns
        -------
        ResultNode
            结果树
        """
        import asyncio
        loop = asyncio.get_running_loop()

        # Step 1: 收集所有因子引用
        all_factor_refs: List[FactorRef] = []
        for cfg in module_configs:
            for ref in cfg.factor_refs:
                all_factor_refs.append(ref)

        if not all_factor_refs:
            raise ValueError("至少需要选择一个因子")

        # Step 2: 获取时点标尺（优先使用 FactorDB 来源的因子引用）
        db_ref = next((r for r in all_factor_refs if r.source == "db" and r.conn_id and r.table_name), None)
        registry_ref = next((r for r in all_factor_refs if r.source == "registry"), None)

        if db_ref:
            dtruler, dts = await self._get_dtruler_and_dts(
                db_ref.conn_id, db_ref.table_name,
                db_ref.name, start_date, end_date, dt_mode
            )
        elif registry_ref and self._registry_service:
            # QSRegistry 来源：自行注册 FactorDB 后再获取 DTRuler
            await self.register_factor_dbs()
            raise ValueError("QSRegistry 因子源暂不支持直接获取 DTRuler，请至少选择一个 FactorDB 因子作为时点参考")
        else:
            raise ValueError("至少需要一个有效的因子引用")

        # Step 3: 解析所有因子为 Factor 对象（双源）
        resolved_factors: Dict[str, Any] = {}
        all_resolved = []
        for ref in all_factor_refs:
            if ref.source == "registry":
                cache_key = f"registry:{ref.name}"
                if cache_key not in resolved_factors:
                    f = await self._get_factor_from_registry(ref.name)
                    resolved_factors[cache_key] = f
                all_resolved.append(resolved_factors[cache_key])
            else:
                cache_key = f"db:{ref.conn_id}:{ref.table_name}:{ref.name}"
                if cache_key not in resolved_factors:
                    f = await self._get_factor_from_db(
                        ref.conn_id, ref.table_name, ref.name
                    )
                    resolved_factors[cache_key] = f
                all_resolved.append(resolved_factors[cache_key])

        # 将解析后的因子对象关联到对应的 ModuleRunConfig
        factor_idx = 0
        for cfg in module_configs:
            n_factors = len(cfg.factor_refs)
            cfg._resolved_factors = all_resolved[factor_idx:factor_idx + n_factors]
            factor_idx += n_factors

        # Step 4: 为每个模块解析价格因子（模块级）
        for cfg in module_configs:
            if cfg.price_ref:
                cfg._resolved_price = await self._get_factor_from_db(
                    cfg.price_ref.conn_id,
                    cfg.price_ref.table_name,
                    cfg.price_ref.factor_name,
                )
            else:
                cfg._resolved_price = None

        # Step 5: 为每个模块解析截面 ID（模块级——支持描述子源和自定义）
        cfg_dict = _load_backtest_config()
        for cfg in module_configs:
            if cfg.descriptor_source:
                # 使用配置中的截面 ID 源
                sources = cfg_dict.get("section_id_sources", {})
                src = sources.get(cfg.descriptor_source)
                if src and src.get("conn_id"):
                    src_db = await self._factor_service._get_factor_db(src["conn_id"])
                    method_name = src.get("method", "getStockID")
                    method_args = src.get("method_args", {})
                    import asyncio as _asyncio
                    _loop = _asyncio.get_running_loop()

                    def _call_section_method():
                        method = getattr(src_db, method_name)
                        return method(**method_args)
                    cfg._resolved_section_ids = await _loop.run_in_executor(None, _call_section_method)
                else:
                    cfg._resolved_section_ids = []
            else:
                cfg._resolved_section_ids = await self._get_section_ids(
                    ref_factor_ref.conn_id, ref_factor_ref.table_name,
                    ref_factor_ref.name, cfg.descriptor_ids
                )

        # Step 6: 解析再平衡时点
        parsed_rebalance_dts = None
        if rebalance_dts:
            parsed_rebalance_dts = [
                dt.datetime.strptime(d, "%Y-%m-%d") for d in rebalance_dts
            ]

        # Step 7: 在 executor 中执行
        return await loop.run_in_executor(
            None,
            self._run_backtest_sync,
            module_configs, dtruler, dts, parsed_rebalance_dts,
        )

    def _run_backtest_sync(
        self,
        module_configs: List[ModuleRunConfig],
        dtruler: List[dt.datetime],
        dts: List[dt.datetime],
        rebalance_dts: Optional[List[dt.datetime]],
    ) -> ResultNode:
        """同步执行回测（在 executor 中运行）"""
        from QuantStudio.Core.CalcEngine import Engine
        from QuantStudio.Core.Node import DTInitData, DTLocalContext
        from QuantStudio.Factor.Factor import FactorContext
        from QuantStudio.BackTest.BackTestModel import BTReport

        if not dts:
            raise ValueError("计算时点列表为空，请检查日期范围")

        # 构造 BTNode 列表（每个模块用自己的 price 和 section_ids）
        bt_nodes = []
        # 收集所有用到的 section_ids 用于构建 Context
        all_section_ids: set = set()

        for cfg in module_configs:
            module_def = BACKTEST_MODULE_REGISTRY.get(cfg.module_key)
            if module_def is None:
                raise ValueError(f"未知的回测模块: {cfg.module_key}")

            section_ids = cfg._resolved_section_ids
            for sid in section_ids:
                all_section_ids.add(sid)

            requires_price = module_def.get("requires_price", False)
            if requires_price and cfg._resolved_price is None:
                raise ValueError(f"模块 '{cfg.module_key}' 需要价格因子，但未配置")

            node = self._build_node_sync(
                cfg, cfg._resolved_price, section_ids, dts,
            )

            bt_nodes.append(node)

        if not bt_nodes:
            raise ValueError("没有可运行的回测模块")

        # 打包 BTReport
        report = BTReport(bt_node_list=bt_nodes)

        start_dt = dts[0] if isinstance(dts[0], dt.datetime) else dt.datetime.combine(dts[0], dt.datetime.min.time()) if hasattr(dts[0], 'date') else dts[0]
        end_dt = dts[-1] if isinstance(dts[-1], dt.datetime) else dt.datetime.combine(dts[-1], dt.datetime.min.time()) if hasattr(dts[-1], 'date') else dts[-1]

        # 构建 Context
        context = FactorContext(
            PID="0",
            PIDList=["0"],
            DTRuler=dtruler,
            SectionIDs=list(all_section_ids) if all_section_ids else section_ids,
        )

        # 执行
        with Engine() as exec_engine:
            output, = exec_engine.run(
                [report],
                context,
                fwd_data_list=[DTLocalContext(DTs=dts)],
                init_data_list=[DTInitData(DTRange=(start_dt, end_dt))],
            )

        # 转换为结果树
        return self._output_to_tree(output)

    # ─── 结果转换 ─────────────────────────────────────────────

    def _output_to_tree(self, output: dict) -> ResultNode:
        """将回测输出 dict 递归转换为 ResultNode 树"""
        children = []
        for key, val in output.items():
            if key == "Report":
                continue
            children.append(self._value_to_node(key, val))

        return ResultNode(
            key="root",
            label="回测结果",
            type="branch",
            children=children,
        )

    def _value_to_node(self, key: str, val: Any) -> ResultNode:
        """将单个值转换为 ResultNode"""
        if isinstance(val, dict):
            sub_children = []
            for sub_key, sub_val in val.items():
                if sub_key == "Report":
                    continue
                sub_children.append(self._value_to_node(str(sub_key), sub_val))
            return ResultNode(
                key=str(key),
                label=str(key),
                type="branch",
                children=sub_children,
            )
        elif isinstance(val, pd.DataFrame):
            return self._dataframe_to_node(key, val)
        elif isinstance(val, pd.Series):
            return self._series_to_node(key, val)
        elif isinstance(val, (int, float, str, bool)):
            return ResultNode(
                key=str(key),
                label=str(key),
                type="scalar",
                data=self._safe_value(val),
            )
        elif val is None:
            return ResultNode(
                key=str(key),
                label=str(key),
                type="scalar",
                data=None,
            )
        else:
            try:
                return ResultNode(
                    key=str(key),
                    label=str(key),
                    type="scalar",
                    data=str(val),
                )
            except Exception:
                return ResultNode(
                    key=str(key),
                    label=str(key),
                    type="scalar",
                    data=f"<{type(val).__name__}>",
                )

    def _dataframe_to_node(self, key: str, df: pd.DataFrame) -> ResultNode:
        """将 DataFrame 转换为 ResultNode"""
        try:
            if isinstance(df.columns, pd.MultiIndex):
                columns = [str(c) for c in df.columns]
            else:
                columns = [str(c) for c in df.columns]

            index = []
            for i in df.index:
                if hasattr(i, 'strftime'):
                    index.append(i.strftime("%Y-%m-%d"))
                else:
                    index.append(str(i))

            data_matrix = []
            for _, row in df.iterrows():
                row_data = []
                for v in row.values:
                    row_data.append(self._safe_value(v))
                data_matrix.append(row_data)

            return ResultNode(
                key=str(key),
                label=str(key),
                type="dataframe",
                data={
                    "columns": columns,
                    "index": index,
                    "data": data_matrix,
                },
            )
        except Exception:
            return ResultNode(
                key=str(key),
                label=str(key),
                type="scalar",
                data=str(df),
            )

    def _series_to_node(self, key: str, series: pd.Series) -> ResultNode:
        """将 Series 转换为 ResultNode"""
        try:
            index = []
            values = []
            for i, v in series.items():
                if hasattr(i, 'strftime'):
                    index.append(i.strftime("%Y-%m-%d"))
                else:
                    index.append(str(i))
                values.append(self._safe_value(v))

            return ResultNode(
                key=str(key),
                label=str(key),
                type="series",
                data={
                    "index": index,
                    "values": values,
                },
            )
        except Exception:
            return ResultNode(
                key=str(key),
                label=str(key),
                type="scalar",
                data=str(series),
            )

    @staticmethod
    def _safe_value(v: Any) -> Any:
        """将值转换为 JSON 安全类型"""
        if isinstance(v, (int, float)):
            if pd.isna(v):
                return None
            if np.isinf(v):
                return None
            return v
        elif isinstance(v, (np.integer,)):
            return int(v)
        elif isinstance(v, (np.floating,)):
            if pd.isna(v):
                return None
            return float(v)
        elif isinstance(v, (np.bool_,)):
            return bool(v)
        elif isinstance(v, (str, bool)):
            return v
        elif v is None or pd.isna(v):
            return None
        else:
            return str(v)

    # ─── QSRegistry 因子源 ────────────────────────────────────

    async def _get_factor_from_registry(self, name: str):
        """从 QSRegistry 获取 Factor 对象

        通过 QSGraphDB.searchFactors 查找因子，再调用 reconstructFactor 重建。
        """
        if self._registry_service is None:
            raise RuntimeError("QSRegistry 服务未初始化，无法从注册中心获取因子")

        gdb = await self._registry_service._get_gdb()

        import asyncio as _asyncio
        loop = _asyncio.get_running_loop()

        def _sync():
            # 1. 搜索因子
            results = gdb.searchFactors(name=name, limit=5)
            if not results:
                raise ValueError(f"在 QSRegistry 中未找到因子: {name}")

            # 2. 精确匹配因子名
            qsid = None
            for r in results:
                if r.get("Name") == name:
                    qsid = r.get("QSID")
                    break

            if qsid is None:
                # 模糊匹配：取第一个结果
                qsid = results[0].get("QSID")
                logger.info(f"因子 '{name}' 未精确匹配，使用最相似结果: {results[0].get('Name')} (QSID: {qsid})")

            if qsid is None:
                raise ValueError(f"在 QSRegistry 中未找到因子: {name}")

            # 3. 重建 Factor 对象
            return gdb.reconstructFactor(qsid)

        return await loop.run_in_executor(None, _sync)

    async def register_factor_dbs(self):
        """将 FactorService 中已连接的 FactorDB 注册到 QSGraphDB

        QSGraphDB.reconstructFactor 需要对应的 FactorDB 已注册才能工作。
        此方法遍历 FactorService 中所有已连接的 FactorDB 实例并注册它们。
        """
        if self._registry_service is None:
            logger.warning("QSRegistry 服务未初始化，跳过 FactorDB 注册")
            return

        gdb = await self._registry_service._get_gdb()

        import asyncio as _asyncio
        loop = _asyncio.get_running_loop()

        registered_count = 0
        for conn_id, fdb in self._factor_service._factor_dbs.items():
            try:
                # 在 executor 中运行同步方法
                await loop.run_in_executor(None, gdb.registerFactorDB, fdb)
                registered_count += 1
            except Exception as e:
                logger.warning(f"注册 FactorDB '{conn_id}' 到 QSGraphDB 失败: {e}")

        logger.info(f"已将 {registered_count} 个 FactorDB 注册到 QSGraphDB")
