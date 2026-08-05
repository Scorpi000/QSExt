# coding=utf-8
"""
策略定义执行脚本 —— 根据配置文件运行策略定义流水线。

使用方式:
    python run_strategy_def.py                                    # 默认配置
    python run_strategy_def.py --settings settings_prod           # 指定配置
    python run_strategy_def.py --debug --end-dt 2026-06-30        # 覆盖参数
    python run_strategy_def.py --dry-run                           # 仅分析, 不执行
    python run_strategy_def.py --register-graph                    # 同时注册到图数据库

配置文件位于 QSExt/StrategyDef/conf/ 目录，格式为 Python 模块。

策略定义流水线的执行步骤:
    1. 加载 settings 配置
    2. 创建并连接因子库（StrategyDBPool）
    3. 解析时间范围和 ID 列表
    4. 解析策略模块依赖链（build_dep_sd）
    5. 调用 defStrategy(sdi) 获取策略实例
    6. 将策略信号因子写入 HDF5 目标表
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
from QuantStudio.Factor.FactorStorer import FactorStorer
from QSExt.StrategyDef.StrategyDefContent import StrategyDefSettings, StrategyDefInputBuilder, build_dep_sd


__NOW__ = dt.datetime.now()
__FILE_NAME__ = os.path.splitext(os.path.basename(__file__))[0]


def main(settings_path: str = "settings", register_graph: bool = False, **cmd_overrides):
    """根据配置文件运行策略定义流水线

    Args:
        settings_path: settings 模块路径
        register_graph: 是否同时注册到图数据库
        **cmd_overrides: 命令行覆盖参数
    """
    # 1. 加载配置
    settings = StrategyDefSettings.from_module(settings_path, **cmd_overrides)
    setDefaultLogLevel(getattr(logging, settings.log_level))
    Logger.info(f"配置已加载: {settings_path} (debug={settings.debug}, workers={settings.workers})")
    Logger.info(f"策略定义流水线启动 — 进程: {os.getpid()}, 时间: {__NOW__}")

    if settings.dry_run:
        _dry_run(settings)
        return

    # 2. 初始化 Builder
    with StrategyDefInputBuilder(settings) as builder:
        pool = builder._pool
        profiles = settings.iter_profiles()

        Logger.info(f"ID_PROFILES: {len(profiles)} 个")
        for i, p in enumerate(profiles):
            Logger.info(f"  Profile {i+1}: id_type={p.id_type}, modules={len(p.strategy_modules)}")

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
            sdi = builder.build_for_profile(profile, dts=dts, dtruler=dtruler)
            modules = builder._resolve_modules_for(profile.strategy_modules)

            Logger.info(f"[{profile.id_type}] IDs 数量: {len(ids)}, 策略模块: {len(modules)}")

            if not ids:
                Logger.warning(f"[{profile.id_type}] IDs 为空，跳过该 profile")
                continue

            storer_list, fwd_list, init_list = _build_storers(
                settings, pool, sdi, modules, dtruler=dtruler,
            )
            all_storers.extend(storer_list)
            all_fwd.extend(fwd_list)
            all_init.extend(init_list)

        if not all_storers:
            Logger.warning("没有 FactorStorer 需要执行")
            return

        # 5. 执行
        _execute(settings, all_storers, all_fwd, all_init, dtruler)

    # 6. 可选：注册到图数据库
    if register_graph:
        _register_to_graph(settings)

    Logger.info("策略定义流水线执行完成")


def _build_storers(settings, pool, sdi, modules, dtruler=None):
    """构建 FactorStorer 列表"""
    if dtruler is None:
        dtruler = sdi.DTRuler

    target_db_name = settings.target_db
    if isinstance(target_db_name, list):
        target_db_name = target_db_name[0]
    TDB = pool[target_db_name]

    StorerList = []
    fwd_data = []
    init_data = []

    Logger.info("正在解析依赖并执行策略定义...")
    StrategyDefDict, strategy_defs = build_dep_sd(modules, sdi)

    for iStrategyDef, strategy_meta in strategy_defs:
        if iStrategyDef is None:
            Logger.warning("跳过未能解析的策略模块")
            continue

        target_table = iStrategyDef.Meta.TargetTable
        table_meta = {
            "Description": iStrategyDef.Meta.Description,
            "IDType": iStrategyDef.Meta.IDType,
            "Author": iStrategyDef.Meta.Author,
            "DefScriptPath": iStrategyDef.Meta.DefScriptPath,
        }

        # 策略输出的信号因子列表
        signal_factors = [iStrategyDef.StrategyInstance]

        storer_args = {
            "TargetFDB": TDB,
            "TargetTable": target_table,
            "TableMeta": table_meta,
        }
        iStorer = FactorStorer(deps=signal_factors, args=storer_args)
        StorerList.append(iStorer)
        fwd_data.append(FactorLocalContext(DTs=sdi.DTs, IDs=sdi.IDs))
        init_data.append(FactorInitData(DTRange=(sdi.DTs[0], sdi.DTs[-1]), SectionIDs=sdi.SectionIDs))

        Logger.info(f"  → TargetTable='{target_table}', 信号数={len(signal_factors)}, MaxLookBack={iStrategyDef.Meta.MaxLookBack}")

    return StorerList, fwd_data, init_data


def _execute(settings, StorerList, fwd_data, init_data, dtruler):
    """执行引擎"""
    workers = settings.workers
    Logger.info(f"开始执行 — workers={workers}, Storer数={len(StorerList)}")

    PIDList = [f"0-{i}" for i in range(int(workers))] if workers > 0 else ["0"]

    with FactorContext(
        Mode=("DEBUG" if settings.debug else "PRD"),
        PIDList=PIDList,
        DTRuler=dtruler,
        SectionIDs=[],
    ) as Context:
        with (ParallelEngine() if workers > 0 else Engine()) as ExecEngine:
            ExecEngine.run(
                StorerList,
                Context,
                fwd_data_list=fwd_data,
                init_data_list=init_data,
            )


def _register_to_graph(settings):
    """注册策略到图数据库"""
    Logger.info("注册策略到图数据库...")
    try:
        from QSExt.StrategyDef.scripts.register_strategies_to_graphdb import main as register_main
        register_main(settings_path="settings", skip_embedding=settings.skip_embedding)
    except Exception as e:
        Logger.warning(f"图数据库注册失败: {e}")


def _dry_run(settings: StrategyDefSettings):
    """Dry-run 模式"""
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
    Logger.info(f"ID_PROFILES ({len(profiles)} 个):")
    for i, p in enumerate(profiles):
        Logger.info(f"  Profile {i+1}: id_type={p.id_type}")
        Logger.info(f"    策略模块 ({len(p.strategy_modules)}):")
        for item in p.strategy_modules:
            Logger.info(f"    - {item}")
    Logger.info(f"输出目标: {settings.target_db}")


def _parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="QSExt 策略定义执行脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_strategy_def.py
  python run_strategy_def.py --settings settings_prod
  python run_strategy_def.py --debug --end-dt 2026-06-30
  python run_strategy_def.py --dry-run
  python run_strategy_def.py --register-graph
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

    args = parser.parse_args()

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
    main(settings_path=args.settings, register_graph=args.register_graph, **cmd_overrides)
