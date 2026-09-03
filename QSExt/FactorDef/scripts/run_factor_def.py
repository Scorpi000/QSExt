# coding=utf-8
"""
因子定义执行脚本 —— 根据配置文件运行因子定义流水线。

使用方式:
    python run_factor_def.py                                    # 默认配置，不使用代理
    python run_factor_def.py --settings settings_prod           # 指定配置
    python run_factor_def.py --use-proxy                        # 使用代理因子库（增量更新）
    python run_factor_def.py --debug --end-dt 2026-06-30        # 覆盖参数
    python run_factor_def.py --dry-run                           # 仅分析, 不执行

配置文件位于 QSExt/FactorDef/conf/ 目录，格式为 Python 模块。
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
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QuantStudio.Factor.FactorStorer import FactorStorer
from QSExt.FactorDef.FactorDefContent import FactorDefSettings, FactorDefInputBuilder, build_dep_fd
from QSExt.Tools.TraceBack import filterWarnings
filterWarnings()


__NOW__ = dt.datetime.now()
__FILE_NAME__ = os.path.splitext(os.path.basename(__file__))[0]

def main(settings_path: str = "settings", use_proxy: bool = False, **cmd_overrides):
    """根据配置文件运行因子定义流水线

    Args:
        settings_path: settings 模块路径, 如 "settings" 或 "settings_prod"
        use_proxy: 是否使用代理因子库（增量更新时复用上次计算结果）
        **cmd_overrides: 命令行覆盖参数
    """
    # 1. 加载配置
    settings = FactorDefSettings.from_module(settings_path, **cmd_overrides)
    setDefaultLogLevel(getattr(logging, settings.log_level))
    Logger.info(f"配置已加载: {settings_path} (debug={settings.debug}, workers={settings.workers})")
    Logger.info(f"因子定义流水线启动 — 进程: {os.getpid()}, 时间: {__NOW__}")

    if settings.dry_run:
        _dry_run(settings)
        return

    # 2. 初始化 Builder（创建并连接所有因子库）
    with FactorDefInputBuilder(settings) as builder:
        pool = builder._pool
        profiles = settings.iter_profiles()

        Logger.info(f"FACTOR_PROFILES: {len(profiles)} 个")
        for i, p in enumerate(profiles):
            Logger.info(f"  Profile {i+1}: modules={len(p.factor_modules)}")

        # 3. 共享时间范围
        dts, dtruler = builder.resolve_dts()

        if not dts:
            Logger.warning("计算时点为空，终止执行")
            return
        else:
            Logger.info(f"计算时点区间: {dts[0]} ~ {dts[-1]}, 共 {len(dts)} 个时点")

        # 4. 按 profile 构建各自的 Storer（不同 IDType 使用各自的 IDs）
        all_storers = []
        all_fwd = []
        all_init = []

        for profile in profiles:
            ids, section_ids = builder.resolve_ids_for(profile)
            fdi = builder.build_for_profile(profile, dts=dts, dtruler=dtruler)
            modules = builder.resolve_modules_for(profile.factor_modules)

            Logger.info(f"IDs 数量: {len(ids)}, 因子模块: {len(modules)}")
            Logger.info(f"  {_module_names(modules)}")

            if not ids:
                Logger.warning(f"IDs 为空，跳过该 profile")
                continue

            storer_list, fwd_list, init_list, dtruler = _build_storers(
                settings, pool, fdi, modules, profile=profile, dtruler=dtruler, use_proxy=use_proxy,
                proxy_tables=profile.proxy_tables,
            )
            all_storers.extend(storer_list)
            all_fwd.extend(fwd_list)
            all_init.extend(init_list)

        if not all_storers:
            Logger.warning("没有 FactorStorer 需要执行")
            return

        # 5. 一次性提交所有 Storer 执行
        _execute(settings, all_storers, all_fwd, all_init, dtruler)

    Logger.info("因子定义流水线执行完成")


def _build_storers(settings, pool, fdi, modules, profile=None, dtruler=None, use_proxy=False, proxy_tables=None):
    """构建 FactorStorer 列表和对应的 fwd_data / init_data

    Args:
        profile: FactorDefProfile，若提供则其 target_db / factor_storer_config 覆盖全局配置
        use_proxy: 是否使用代理因子库
        proxy_tables: 代理表控制，"*" 全部代理，列表指定表名，None 不代理

    Returns:
        (StorerList, fwd_data_list, init_data_list, dtruler)
    """
    if dtruler is None:
        dtruler = fdi.DTRuler

    # profile 级覆盖全局
    target_db_name = (profile.target_db if profile and profile.target_db else settings.target_db)
    if isinstance(target_db_name, list):
        target_db_name = target_db_name[0]
    TDB = pool[target_db_name]

    storer_config = dict(settings.factor_storer_config)
    if profile and profile.factor_storer_config:
        storer_config.update(profile.factor_storer_config)

    MaxLookBack = settings.max_lookback
    StorerList = []
    fwd_data = []
    init_data = []

    proxy_db = pool.get_proxy() if use_proxy else None
    proxy_table_mapping = settings.proxy_table_mapping if use_proxy else None
    effective_proxy_tables = proxy_tables if use_proxy else None

    if use_proxy:
        if proxy_db:
            Logger.info(f"代理模式已启用，代理库: {proxy_db.__class__.__name__}")
            if effective_proxy_tables == "*":
                Logger.info("代理范围: 所有表")
            elif isinstance(effective_proxy_tables, list):
                Logger.info(f"代理范围: {effective_proxy_tables}")
            else:
                Logger.info("代理范围: 无（proxy_tables 未配置）")
        else:
            Logger.warning("代理模式已启用，但未找到代理库")

    Logger.info("正在解析依赖并执行因子定义...")
    FactorDefDict, factor_defs = build_dep_fd(modules, fdi, proxy_db=proxy_db, proxy_table_mapping=proxy_table_mapping, proxy_tables=effective_proxy_tables)

    # 按 TargetTable 分组，收集同表的所有因子
    table_groups: dict = {}  # TargetTable → {factor_defs, table_meta, factors}
    for iFactorDef, factor_meta in factor_defs:
        if iFactorDef is None:
            Logger.warning("跳过未能解析的模块")
            continue

        target_table = iFactorDef.Meta.TargetTable
        if target_table not in table_groups:
            table_groups[target_table] = {
                "factor_defs": [],
                "table_meta": {
                    "Description": iFactorDef.Meta.Description,
                    "IDType": iFactorDef.Meta.IDType,
                    "Author": iFactorDef.Meta.Author,
                    "DefScriptPath": iFactorDef.Meta.DefScriptPath,
                },
                "factors": [],
                "factor_names": set(),
            }

        group = table_groups[target_table]
        group["factor_defs"].append(iFactorDef)

        # 校验因子名唯一性
        for f in iFactorDef.FactorList:
            fname = f._QSArgs.Name
            if fname in group["factor_names"]:
                raise ValueError(
                    f"因子名冲突: '{fname}' 在 TargetTable='{target_table}' 中被多个模块定义，"
                    f"请检查各因子定义模块的因子名是否唯一"
                )
            group["factor_names"].add(fname)
            group["factors"].append(f)

    for target_table, group in table_groups.items():
        iFactorDef = group["factor_defs"][0]
        factor_count = len(group["factors"])

        if len(group["factor_defs"]) > 1:
            module_names = [getattr(fd.Meta, 'DefScriptPath', '?') for fd in group["factor_defs"]]
            Logger.info(f"TargetTable='{target_table}': 合并 {len(group['factor_defs'])} 个模块 → {factor_count} 个因子 ({module_names})")

        # 动态调整 DTRuler
        if iFactorDef.Meta.MaxLookBack > MaxLookBack:
            MaxLookBack = iFactorDef.Meta.MaxLookBack
            end_dt = FactorDefInputBuilder._parse_end_dt(settings.end_dt)
            if settings.start_dt:
                start_dt = dt.datetime.strptime(settings.start_dt, "%Y-%m-%d")
            else:
                start_dt = end_dt - dt.timedelta(settings.lookback)
            dtruler_start = start_dt - dt.timedelta(MaxLookBack)
            if settings.dt_type == "自然日":
                dtruler = pd.date_range(start=dtruler_start, end=end_dt, freq='D').tolist()
            else:
                tds = settings.trading_day_source
                tds_name = tds.get("name", "JYDB")
                tds_method = tds.get("method", "getTradeDay")
                tds_method_args = tds.get("method_args", {})
                dt_source = pool[tds_name]
                method = getattr(dt_source, tds_method)
                dtruler = method(start_date=dtruler_start, end_date=end_dt, **tds_method_args)
            dtruler = FactorDefInputBuilder.apply_dt_freq(dtruler, settings.dt_freq)
            fdi.DTRuler = dtruler
            Logger.info(f"MaxLookBack 更新为 {MaxLookBack}，DTRuler 已扩展")

        # 构建 FactorStorer（使用合并后的因子列表和表元信息）
        storer_args = {
            "TargetFDB": TDB,
            "TargetTable": target_table,
            "TableMeta": group["table_meta"],
            **storer_config,
        }
        iStorer = FactorStorer(deps=group["factors"], args=storer_args)
        StorerList.append(iStorer)
        fwd_data.append(FactorLocalContext(DTs=fdi.DTs, IDs=fdi.IDs, SectionIDs=fdi.SectionIDs))
        init_data.append(FactorInitData(DTRange=(fdi.DTs[0], fdi.DTs[-1]), SectionIDs=fdi.SectionIDs))

        Logger.info(f"  → TargetTable='{target_table}', 因子数={factor_count}, MaxLookBack={iFactorDef.Meta.MaxLookBack}")

    return StorerList, fwd_data, init_data, dtruler


def _execute(settings, StorerList, fwd_data, init_data, dtruler):
    """执行引擎 — 统一的缓存/引擎执行逻辑"""
    # 缓存目录
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
                    StorerList,
                    Context,
                    fwd_data_list=fwd_data,
                    init_data_list=init_data,
                )


def _module_names(modules):
    """模块列表的简短名称"""
    return [m[0].__name__.split('.')[-1] if hasattr(m[0], '__name__') else str(m[0]) for m in modules]


def _dry_run(settings: FactorDefSettings):
    """Dry-run 模式：打印配置摘要和模块列表，不连接数据库"""
    Logger.info("=" * 60)
    Logger.info("DRY RUN — 仅分析配置")
    Logger.info("=" * 60)
    Logger.info(f"配置:")
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
    Logger.info(f"FACTOR_PROFILES ({len(profiles)} 个):")
    for i, p in enumerate(profiles):
        Logger.info(f"  Profile {i+1}: id_selection={p.id_selection}, section_id_list={p.section_id_list}")
        if p.target_db:
            Logger.info(f"    target_db: {p.target_db} (覆盖全局)")
        if p.factor_storer_config:
            Logger.info(f"    factor_storer_config: {p.factor_storer_config} (覆盖全局)")
        Logger.info(f"    因子模块 ({len(p.factor_modules)}):")
        for item in p.factor_modules:
            name = item[0].__name__ if isinstance(item, tuple) and hasattr(item[0], "__name__") else str(item)
            Logger.info(f"    - {name}")

    Logger.info(f"输出目标 (全局): {settings.target_db}")
    Logger.info(f"缓存目录: {settings.cache_dir}")


def _parse_args():
    """解析命令行参数，返回 (parsed_args, cmd_overrides)"""
    parser = argparse.ArgumentParser(
        description="QSExt 因子定义执行脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_factor_def.py
  python run_factor_def.py --settings settings_prod
  python run_factor_def.py --debug --end-dt 2026-06-30
  python run_factor_def.py --dry-run
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
    parser.add_argument("--register-graph", action="store_true", default=None, help="注册到图数据库")
    parser.add_argument("--use-proxy", action="store_true", default=False, help="使用代理因子库（增量更新时复用上次计算结果）")

    args = parser.parse_args()

    # 构建命令行覆盖（仅传递非 None 的参数）
    cmd_overrides = {}
    if args.debug is not None:
        cmd_overrides["debug"] = args.debug
    if args.dry_run is not None:
        cmd_overrides["dry_run"] = args.dry_run
    if args.end_dt is not None:
        cmd_overrides["end_dt"] = args.end_dt
    if args.start_dt is not None:
        cmd_overrides["start_dt"] = args.start_dt
    if args.lookback is not None:
        cmd_overrides["lookback"] = args.lookback
    if args.workers is not None:
        cmd_overrides["workers"] = args.workers
    if args.dt_type is not None:
        cmd_overrides["dt_type"] = args.dt_type
    if args.dt_freq is not None:
        cmd_overrides["dt_freq"] = args.dt_freq
    if args.register_graph is not None:
        cmd_overrides["register_graph"] = args.register_graph

    return args, cmd_overrides


if __name__ == "__main__":
    args, cmd_overrides = _parse_args()
    main(settings_path=args.settings, use_proxy=args.use_proxy, **cmd_overrides)
