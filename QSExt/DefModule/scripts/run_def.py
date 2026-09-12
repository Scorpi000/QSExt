# coding=utf-8
"""
统一定义执行脚本 —— 根据配置文件运行因子定义和策略定义流水线。

支持三种配置格式：
    FACTOR_PROFILES — 仅因子
    STRATEGY_PROFILES — 仅策略
    DEF_PROFILES — 混合（因子 + 策略，同一个引擎环境中执行）

使用方式:
    python run_def.py                                    # 默认配置
    python run_def.py --settings settings_prod           # 指定配置
    python run_def.py --use-proxy                        # 使用代理因子库
    python run_def.py --debug --end-dt 2026-06-30        # 覆盖参数
    python run_def.py --dry-run                           # 仅分析, 不执行
"""
import os
import logging
import argparse
import datetime as dt

import pandas as pd

from QuantStudio.Core import setDefaultLogLevel
from QuantStudio.Core import __QS_Logger__ as Logger
from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Core.ParallelEngine import ParallelEngine
from QuantStudio.Factor.Factor import FactorContext, FactorLocalContext, FactorInitData
from QuantStudio.BackTest.BackTestModel import DTInitData, DTLocalContext
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QuantStudio.Factor.FactorStorer import FactorStorer
from QuantStudio.BackTest.Strategy.Strategy import AccountStats
from QuantStudio.BackTest.BTResultDB import HDF5BTResultDB
from QuantStudio.BackTest.BTStorer import BTStorer
from QSExt.DefModule.DefContent import (
    DefSettings, DefInputBuilder, Def,
    build_dep_fd, build_dep_sd, DefInput, DefMeta,
    make_def_key,
)
from QSExt.Tools.TraceBack import filterWarnings
filterWarnings()


__NOW__ = dt.datetime.now()
__FILE_NAME__ = os.path.splitext(os.path.basename(__file__))[0]


def main(settings_path: str = "settings", use_proxy: bool = False, register_graph: bool = False, **cmd_overrides):
    """统一执行入口

    Args:
        settings_path: settings 模块路径
        use_proxy: 是否使用代理因子库
        register_graph: 是否注册到图数据库
        **cmd_overrides: 命令行覆盖参数
    """
    # 1. 加载配置
    settings = DefSettings.from_module(settings_path, **cmd_overrides)
    setDefaultLogLevel(getattr(logging, settings.log_level))
    Logger.info(f"配置已加载: {settings_path} (debug={settings.debug}, workers={settings.workers})")
    Logger.info(f"统一定义流水线启动 — 进程: {os.getpid()}, 时间: {__NOW__}")

    if settings.dry_run:
        _dry_run(settings)
        return

    # 2. 初始化 Builder
    with DefInputBuilder(settings) as builder:
        pool = builder._pool
        profiles = settings.iter_profiles()

        Logger.info(f"PROFILES: {len(profiles)} 个")
        for i, p in enumerate(profiles):
            Logger.info(f"  Profile {i+1}: collect_mode={p.collect_mode}, "
                        f"factor_modules={len(p.factor_modules)}, strategy_modules={len(p.strategy_modules)}")

        # 3. 共享时间范围
        dts, dtruler = builder.resolve_dts()
        if not dts:
            Logger.warning("计算时点为空，终止执行")
            return
        Logger.info(f"计算时点区间: {dts[0]} ~ {dts[-1]}, 共 {len(dts)} 个时点")

        # 4. 按 profile 构建
        all_storers = []
        all_fwd = []
        all_init = []

        for profile in profiles:
            ids, section_ids = builder.resolve_ids_for(profile)
            di = builder.build_for_profile(profile, dts=dts, dtruler=dtruler)

            if not ids:
                Logger.warning(f"IDs 为空，跳过该 profile")
                continue

            # 因子模块
            if profile.factor_modules and profile.collect_mode in ("factor", "both"):
                factor_modules = builder.resolve_modules_for(profile.factor_modules, kind="factor")
                Logger.info(f"因子模块: {len(factor_modules)}")
                storer_list, fwd_list, init_list, dtruler, mixed_defs = _build_factor_storers(
                    settings, pool, di, factor_modules, profile=profile, dtruler=dtruler,
                    use_proxy=use_proxy, proxy_tables=profile.proxy_tables,
                    collect_mixed=(profile.collect_mode == "both"),
                )
                all_storers.extend(storer_list)
                all_fwd.extend(fwd_list)
                all_init.extend(init_list)

                # collect_mode="both" 时，因子模块中可能产出策略，也需要构建策略 storers
                if mixed_defs:
                    mixed_storer_list, mixed_fwd, mixed_init = _build_strategy_storers_from_defs(
                        settings, pool, di, mixed_defs, profile=profile, dtruler=dtruler,
                    )
                    all_storers.extend(mixed_storer_list)
                    all_fwd.extend(mixed_fwd)
                    all_init.extend(mixed_init)

            # 策略模块
            if profile.strategy_modules and profile.collect_mode in ("strategy", "both"):
                strategy_modules = builder.resolve_modules_for(profile.strategy_modules, kind="strategy")
                Logger.info(f"策略模块: {len(strategy_modules)}")
                storer_list, fwd_list, init_list = _build_strategy_storers(
                    settings, pool, di, strategy_modules, profile=profile, dtruler=dtruler,
                )
                all_storers.extend(storer_list)
                all_fwd.extend(fwd_list)
                all_init.extend(init_list)

        if not all_storers:
            Logger.warning("没有 Storer 需要执行")
            return

        # 5. 一次性提交执行
        _execute(settings, all_storers, all_fwd, all_init, dtruler)

    if register_graph:
        Logger.info("注册到图数据库...")
        try:
            from QSExt.DefModule.scripts.register_to_graphdb import main as register_main
            register_main(settings_path=settings_path)
        except Exception as e:
            Logger.warning(f"图数据库注册失败: {e}")

    Logger.info("统一定义流水线执行完成")


# ============================================================
# 因子 Storer 构建（移植自 run_factor_def.py）
# ============================================================

def _build_factor_storers(settings, pool, di, modules, profile=None, dtruler=None,
                          use_proxy=False, proxy_tables=None, collect_mixed=False):
    """构建因子 FactorStorer 列表。

    Args:
        collect_mixed: True 时额外返回含 StrategyList 的 Def 列表（用于 collect_mode="both"）
    """
    if dtruler is None:
        dtruler = di.DTRuler

    target_db_name = profile.target_db if profile and profile.target_db else settings.target_db
    if isinstance(target_db_name, list):
        target_db_name = target_db_name[0]
    TDB = pool[target_db_name]

    storer_config = dict(settings.factor_storer_config)
    if profile and profile.factor_storer_config:
        storer_config.update(profile.factor_storer_config)

    MaxLookBack = settings.max_lookback

    proxy_db = pool.get_proxy() if use_proxy else None
    proxy_table_mapping = settings.proxy_table_mapping if use_proxy else None
    effective_proxy_tables = proxy_tables if use_proxy else None

    if use_proxy and proxy_db:
        Logger.info(f"代理模式已启用，代理库: {proxy_db.__class__.__name__}")

    Logger.info("正在解析因子依赖并执行定义...")
    dep_dict, factor_defs = build_dep_fd(
        modules, di, proxy_db=proxy_db, proxy_table_mapping=proxy_table_mapping, proxy_tables=effective_proxy_tables
    )

    # 按 TargetTable 分组
    table_groups: dict = {}
    for iDef, meta in factor_defs:
        if iDef is None:
            Logger.warning("跳过未能解析的模块")
            continue

        # 只收集因子列表（忽略策略）
        factors = iDef.FactorList
        if not factors:
            continue

        target_table = iDef.Meta.TargetTable
        if target_table not in table_groups:
            table_groups[target_table] = {
                "defs": [],
                "table_meta": {
                    "Description": iDef.Meta.Description,
                    "IDType": iDef.Meta.IDType,
                    "Author": iDef.Meta.Author,
                    "DefScriptPath": iDef.Meta.DefScriptPath,
                },
                "factors": [],
                "factor_names": set(),
            }

        group = table_groups[target_table]
        group["defs"].append(iDef)
        for f in factors:
            fname = f._QSArgs.Name
            if fname in group["factor_names"]:
                raise ValueError(f"因子名冲突: '{fname}' 在 TargetTable='{target_table}' 中被多个模块定义")
            group["factor_names"].add(fname)
            group["factors"].append(f)

    StorerList, fwd_data, init_data = [], [], []

    for target_table, group in table_groups.items():
        iDef = group["defs"][0]
        factor_count = len(group["factors"])

        if iDef.Meta.MaxLookBack > MaxLookBack:
            MaxLookBack = iDef.Meta.MaxLookBack
            end_dt = DefInputBuilder._parse_end_dt(settings.end_dt)
            start_dt = pd.to_datetime(settings.start_dt) if settings.start_dt else end_dt - dt.timedelta(settings.lookback)
            dtruler_start = start_dt - dt.timedelta(MaxLookBack)
            if settings.dt_type == "自然日":
                dtruler = pd.date_range(start=dtruler_start, end=end_dt, freq='D').tolist()
            else:
                tds = settings.trading_day_source
                dt_source = pool[tds.get("name", "JYDB")]
                dtruler = getattr(dt_source, tds.get("method", "getTradeDay"))(start_date=dtruler_start, end_date=end_dt, **tds.get("method_args", {}))
            dtruler = DefInputBuilder.apply_dt_freq(dtruler, settings.dt_freq)
            di.DTRuler = dtruler
            Logger.info(f"MaxLookBack 更新为 {MaxLookBack}，DTRuler 已扩展")

        storer_args = {"TargetFDB": TDB, "TargetTable": target_table, "TableMeta": group["table_meta"], **storer_config}
        iStorer = FactorStorer(deps=group["factors"], args=storer_args)
        StorerList.append(iStorer)
        fwd_data.append(FactorLocalContext(DTs=di.DTs, IDs=di.IDs, SectionIDs=di.SectionIDs))
        init_data.append(FactorInitData(DTRange=(di.DTs[0], di.DTs[-1]), SectionIDs=di.SectionIDs))
        Logger.info(f"  → TargetTable='{target_table}', 因子数={factor_count}")

    # 收集含策略的 Def（collect_mixed 模式）
    mixed_defs = []
    if collect_mixed:
        for iDef, meta in factor_defs:
            if iDef is not None and iDef.StrategyList:
                mixed_defs.append((iDef, meta))

    return StorerList, fwd_data, init_data, dtruler, mixed_defs


# ============================================================
# 策略 Storer 构建（移植自 run_strategy_def.py）
# ============================================================

def _build_strategy_storers_from_defs(settings, pool, di, def_results, profile=None, dtruler=None):
    """从已解析的 Def 结果构建策略 Storer（用于 collect_mode="both" 中混合模块产出的策略）。"""
    if dtruler is None:
        dtruler = di.DTRuler

    target_db_name = profile.target_db if profile and profile.target_db else settings.target_db
    if isinstance(target_db_name, list):
        target_db_name = target_db_name[0]
    TDB = pool[target_db_name]

    storer_config = dict(settings.factor_storer_config)
    if profile and profile.factor_storer_config:
        storer_config.update(profile.factor_storer_config)

    table_groups: dict = {}
    for iDef, meta in def_results:
        if iDef is None or not iDef.StrategyList:
            continue
        target_table = iDef.Meta.TargetTable
        if target_table not in table_groups:
            table_groups[target_table] = {
                "defs": [],
                "table_meta": {
                    "Description": iDef.Meta.Description,
                    "IDType": iDef.Meta.IDType,
                    "Author": iDef.Meta.Author,
                    "DefScriptPath": iDef.Meta.DefScriptPath,
                },
                "signals": [],
            }
        group = table_groups[target_table]
        group["defs"].append(iDef)
        group["signals"].extend(iDef.StrategyList)

    StorerList, fwd_data, init_data = [], [], []

    for target_table, group in table_groups.items():
        signal_factors = group["signals"]
        storer_args = {"TargetFDB": TDB, "TargetTable": target_table, "TableMeta": group["table_meta"], **storer_config}
        iStorer = FactorStorer(deps=signal_factors, args=storer_args)
        StorerList.append(iStorer)
        fwd_data.append(FactorLocalContext(DTs=di.DTs, IDs=di.IDs, SectionIDs=di.SectionIDs))
        init_data.append(FactorInitData(DTRange=(di.DTs[0], di.DTs[-1]), SectionIDs=di.SectionIDs))
        Logger.info(f"  → [混合] TargetTable='{target_table}', 信号数={len(signal_factors)}")

    if settings.bt_store is not None:
        bt_db_args = dict(settings.bt_store.args)
        bt_result_db = HDF5BTResultDB(args=bt_db_args)
        for iDef, meta in def_results:
            if iDef is None or not iDef.StrategyList:
                continue
            result_key = iDef.Meta.ResultKey
            group_name = result_key if result_key else iDef.Meta.TargetTable
            metadata = {}
            for key in ("IDType", "Description", "Author", "Tags", "DefScriptPath", "TargetTable"):
                val = getattr(iDef.Meta, key, None)
                if val is not None and val != "" and val != []:
                    metadata[key] = val
            bt_storer = BTStorer(
                deps=[AccountStats(account=s, args={"AccountSection": di.SectionIDs, "Name": s.Name}) for s in iDef.StrategyList],
                args={"TargetDB": bt_result_db, "GroupName": group_name, "Metadata": metadata or None},
            )
            StorerList.append(bt_storer)
            fwd_data.append(DTLocalContext(DTs=di.DTs))
            init_data.append(DTInitData(DTRange=(di.DTs[0], di.DTs[-1])))
            Logger.info(f"  → [混合] BTStorer: GroupName='{group_name}'")

    return StorerList, fwd_data, init_data


def _build_strategy_storers(settings, pool, di, modules, profile=None, dtruler=None):
    """构建策略 FactorStorer + BTStorer 列表"""
    if dtruler is None:
        dtruler = di.DTRuler

    target_db_name = profile.target_db if profile and profile.target_db else settings.target_db
    if isinstance(target_db_name, list):
        target_db_name = target_db_name[0]
    TDB = pool[target_db_name]

    storer_config = dict(settings.factor_storer_config)
    if profile and profile.factor_storer_config:
        storer_config.update(profile.factor_storer_config)

    Logger.info("正在解析策略依赖并执行定义...")
    dep_dict, strategy_defs = build_dep_sd(modules, di)

    # 按 TargetTable 分组
    table_groups: dict = {}
    for iDef, meta in strategy_defs:
        if iDef is None:
            Logger.warning("跳过未能解析的策略模块")
            continue

        strategies = iDef.StrategyList
        if not strategies:
            continue

        target_table = iDef.Meta.TargetTable
        if target_table not in table_groups:
            table_groups[target_table] = {
                "defs": [],
                "table_meta": {
                    "Description": iDef.Meta.Description,
                    "IDType": iDef.Meta.IDType,
                    "Author": iDef.Meta.Author,
                    "DefScriptPath": iDef.Meta.DefScriptPath,
                },
                "signals": [],
            }

        group = table_groups[target_table]
        group["defs"].append(iDef)
        group["signals"].extend(strategies)

    StorerList, fwd_data, init_data = [], [], []

    for target_table, group in table_groups.items():
        signal_factors = group["signals"]
        storer_args = {"TargetFDB": TDB, "TargetTable": target_table, "TableMeta": group["table_meta"], **storer_config}
        iStorer = FactorStorer(deps=signal_factors, args=storer_args)
        StorerList.append(iStorer)
        fwd_data.append(FactorLocalContext(DTs=di.DTs, IDs=di.IDs, SectionIDs=di.SectionIDs))
        init_data.append(FactorInitData(DTRange=(di.DTs[0], di.DTs[-1]), SectionIDs=di.SectionIDs))
        Logger.info(f"  → TargetTable='{target_table}', 信号数={len(signal_factors)}")

    # 构建回测结果存储节点
    if settings.bt_store is not None:
        bt_db_args = dict(settings.bt_store.args)
        bt_result_db = HDF5BTResultDB(args=bt_db_args)
        for iDef, meta in strategy_defs:
            if iDef is None or not iDef.StrategyList:
                continue
            result_key = iDef.Meta.ResultKey
            group_name = result_key if result_key else iDef.Meta.TargetTable
            metadata = {}
            for key in ("IDType", "Description", "Author", "Tags", "DefScriptPath", "TargetTable"):
                val = getattr(iDef.Meta, key, None)
                if val is not None and val != "" and val != []:
                    metadata[key] = val
            bt_storer = BTStorer(
                deps=[AccountStats(account=s, args={"AccountSection": di.SectionIDs, "Name": s.Name}) for s in iDef.StrategyList],
                args={"TargetDB": bt_result_db, "GroupName": group_name, "Metadata": metadata or None},
            )
            StorerList.append(bt_storer)
            fwd_data.append(DTLocalContext(DTs=di.DTs))
            init_data.append(DTInitData(DTRange=(di.DTs[0], di.DTs[-1])))
            Logger.info(f"  → BTStorer: GroupName='{group_name}'")

    return StorerList, fwd_data, init_data


# ============================================================
# 执行引擎
# ============================================================

def _execute(settings, StorerList, fwd_data, init_data, dtruler):
    """统一执行引擎（合并因子缓存和策略回测存储）"""
    cache_dir = settings.cache_dir
    if cache_dir:
        task_cache_dir = os.path.join(cache_dir, __FILE_NAME__)
        os.makedirs(task_cache_dir, exist_ok=True)
    else:
        task_cache_dir = None

    workers = settings.workers
    Logger.info(f"开始执行 — workers={workers}, Storer数={len(StorerList)}")

    PIDList = [f"0-{i}" for i in range(int(workers))] if workers > 0 else ["0"]

    cache_args = {
        "DTRuler": dtruler,
        "PIDs": PIDList,
        "CacheDir": task_cache_dir,
        "StartMode": "new",
        "Suffix": ".pkl",
    }

    with FeatherFactorCache(args=cache_args) as Cache:
        with FactorContext(
            Mode=("DEBUG" if settings.debug else "PRD"),
            PIDList=PIDList,
            DTRuler=dtruler,
            SectionIDs=[],
            DataCache=Cache,
        ) as Context:
            with (ParallelEngine() if workers > 0 else Engine()) as ExecEngine:
                ExecEngine.run(
                    StorerList, Context,
                    fwd_data_list=fwd_data,
                    init_data_list=init_data,
                )


# ============================================================
# Dry-run
# ============================================================

def _dry_run(settings: DefSettings):
    Logger.info("=" * 60)
    Logger.info("DRY RUN — 仅分析配置")
    Logger.info("=" * 60)
    Logger.info(f"  DEBUG: {settings.debug}")
    Logger.info(f"  END_DT: {settings.end_dt}")
    Logger.info(f"  LOOKBACK: {settings.lookback}")
    Logger.info(f"  DT_TYPE: {settings.dt_type}")
    Logger.info(f"  DT_FREQ: {settings.dt_freq}")
    Logger.info(f"  WORKERS: {settings.workers}")
    Logger.info(f"因子库:")
    for db_def in settings.factor_databases:
        Logger.info(f"  [{db_def.role}] {db_def.name} ({db_def.class_path})")

    profiles = settings.iter_profiles()
    Logger.info(f"PROFILES ({len(profiles)} 个):")
    for i, p in enumerate(profiles):
        Logger.info(f"  Profile {i+1}: collect_mode={p.collect_mode}")
        if p.id_selection:
            Logger.info(f"    id_selection: {p.id_selection}")
        if p.section_id_list:
            Logger.info(f"    section_id_list: {p.section_id_list}")
        if p.target_db:
            Logger.info(f"    target_db: {p.target_db}")
        if p.factor_modules:
            Logger.info(f"    因子模块 ({len(p.factor_modules)}):")
            for item in p.factor_modules:
                Logger.info(f"      - {item}")
        if p.strategy_modules:
            Logger.info(f"    策略模块 ({len(p.strategy_modules)}):")
            for item in p.strategy_modules:
                Logger.info(f"      - {item}")

    Logger.info(f"输出目标 (全局): {settings.target_db}")
    if settings.bt_store:
        Logger.info(f"回测结果存储: {settings.bt_store.name} ({settings.bt_store.resolved_class_name})")
    else:
        Logger.info("回测结果存储: 未配置")


# ============================================================
# CLI
# ============================================================

def _parse_args():
    parser = argparse.ArgumentParser(
        description="QSExt 统一定义执行脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_def.py
  python run_def.py --settings settings_prod
  python run_def.py --debug --end-dt 2026-06-30
  python run_def.py --dry-run
  python run_def.py --use-proxy --register-graph
        """,
    )
    parser.add_argument("--settings", "-s", default="settings", help="配置模块名 (默认: settings)")
    parser.add_argument("--debug", "-d", action="store_true", default=None, help="调试模式")
    parser.add_argument("--dry-run", "-n", action="store_true", default=None, help="仅分析不执行")
    parser.add_argument("--end-dt", default=None, help="截止日期 (如 2026-06-30)")
    parser.add_argument("--start-dt", default=None, help="起始日期")
    parser.add_argument("--lookback", type=int, default=None, help="回溯天数")
    parser.add_argument("--dt-type", default=None, help="时点类型: 交易日 | 自然日")
    parser.add_argument("--dt-freq", default=None, help="时点频率 (如 1m, 2w)")
    parser.add_argument("--workers", "-w", type=int, default=None, help="并发 worker 数")
    parser.add_argument("--use-proxy", action="store_true", default=False, help="使用代理因子库")
    parser.add_argument("--register-graph", action="store_true", default=None, help="注册到图数据库")

    args = parser.parse_args()

    cmd_overrides = {}
    for key in ("debug", "dry_run", "end_dt", "start_dt", "lookback", "workers", "dt_type", "dt_freq", "register_graph"):
        val = getattr(args, key if key != "dry_run" else "dry_run", None)
        if val is not None:
            cmd_overrides[key] = val

    return args, cmd_overrides


if __name__ == "__main__":
    args, cmd_overrides = _parse_args()
    main(settings_path=args.settings, use_proxy=args.use_proxy, register_graph=args.register_graph, **cmd_overrides)
