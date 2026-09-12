# coding=utf-8
"""
统一图数据库注册脚本 —— 根据配置文件加载因子和策略模块并注册到 QSGraphDB。

使用方式:
    python register_to_graphdb.py
    python register_to_graphdb.py --settings settings_prod
    python register_to_graphdb.py --debug --dry-run
    python register_to_graphdb.py --skip-embedding

该脚本根据 PROFILE 配置自动区分因子和策略模块进行注册。
"""
import os
import argparse
import logging
import datetime as dt
from typing import List

from QuantStudio.Core import setDefaultLogLevel
setDefaultLogLevel(logging.DEBUG)
from QuantStudio.Core import __QS_Logger__ as Logger
from QuantStudio.Factor.FactorStorer import FactorStorer
from QSExt.QSRegistry.api import QSGraphDB
from QSExt.QSRegistry.utils import init_graphdb
from QSExt.DefModule.DefContent import (
    DefSettings, DefInputBuilder, Def,
    build_dep_fd, build_dep_sd, make_def_key,
)
from QuantStudio.BackTest.BTResultDB import HDF5BTResultDB


__NOW__ = dt.datetime.now()


def main(settings_path: str = "settings", **cmd_overrides):
    """根据配置文件加载模块并注册到图数据库"""
    Logger.info(f"统一图数据库注册启动 — 进程: {os.getpid()}, 时间: {__NOW__}")

    extra_args = {k: v for k, v in cmd_overrides.items() if k.startswith("_")}
    user_id = cmd_overrides.pop("user_id", None)
    no_clean = extra_args.get("_no_clean", False)
    settings_overrides = {k: v for k, v in cmd_overrides.items() if not k.startswith("_")}

    settings = DefSettings.from_module(settings_path, **settings_overrides)
    Logger.info(f"配置已加载: {settings_path} (debug={settings.debug})")

    if settings.dry_run:
        _dry_run(settings)
        return

    with DefInputBuilder(settings) as builder:
        fdi = builder.build_for_profile(settings.iter_profiles()[0])
        pool = builder._pool

        # 收集所有模块
        all_factor_modules = []
        all_strategy_modules = []
        for profile in settings.iter_profiles():
            if profile.factor_modules:
                all_factor_modules.extend(builder.resolve_modules_for(profile.factor_modules, kind="factor"))
            if profile.strategy_modules:
                all_strategy_modules.extend(builder.resolve_modules_for(profile.strategy_modules, kind="strategy"))

        Logger.info(f"因子模块: {len(all_factor_modules)}, 策略模块: {len(all_strategy_modules)}")

        # 初始化 QSGraphDB
        extra_tags = list(extra_args.get("_graph_tags", []))
        fgdb = init_graphdb(
            neo4j_config_path=settings.neo4j_config_path,
            skip_embedding=settings.skip_embedding,
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
        )
        if fgdb is None:
            Logger.error("QSGraphDB 初始化失败，无法注册")
            return

        try:
            # 注册数据源因子库
            for src_name in pool.source_names:
                fgdb.registerFactorDB(pool[src_name])

            # 解析因子依赖
            if all_factor_modules:
                Logger.info("解析因子依赖...")
                dep_fd, factor_results = build_dep_fd(all_factor_modules, fdi)
                _register_factor_defs(fgdb, factor_results, extra_tags, user_id, no_clean, settings, pool)

            # 解析策略依赖
            if all_strategy_modules:
                Logger.info("解析策略依赖...")
                dep_sd, strategy_results = build_dep_sd(all_strategy_modules, fdi)
                _register_strategy_defs(fgdb, strategy_results, extra_tags, user_id, no_clean, settings, pool)

            # 图统计
            try:
                stats = fgdb.getGraphStats()
                Logger.info("QSGraphDB 图统计:")
                for key, val in stats.items():
                    Logger.info(f"  {key}: {val}")
            except Exception as e:
                Logger.warning(f"获取图统计失败: {e}")

        finally:
            fgdb.disconnect()
            Logger.info("QSGraphDB 已断开")

    Logger.info("统一图数据库注册完成")


def _register_factor_defs(fgdb, results, extra_tags, user_id, no_clean, settings, pool):
    """注册因子/策略定义到图数据库"""
    all_defs = [d for d, _ in results if d is not None]

    # 收集所有因子（合并 FactorList 和 StrategyList）
    all_factors = []
    tags_map = {}
    for iDef in all_defs:
        items = iDef.FactorList + iDef.StrategyList
        base_tags = (extra_tags + [iDef.Meta.TargetTable, iDef.Meta.IDType, iDef.Meta.Author] + list(iDef.Meta.Tags))
        for f in items:
            all_factors.append(f)
            tags_map[f.QSID] = base_tags

    if not all_factors:
        Logger.warning("没有因子/策略需要注册")
        return

    Logger.info(f"批量注册 {len(all_factors)} 个对象...")
    try:
        qsids = fgdb.storeFactors(all_factors, tags=tags_map, user_id=user_id)
        Logger.info(f"注册完成: {len(qsids)}/{len(all_factors)} 成功")
    except Exception as e:
        Logger.error(f"批量注册失败: {e}")

    # 注册脚本节点
    for iDef in all_defs:
        script_path = iDef.Meta.DefScriptPath
        if not script_path or not os.path.isfile(script_path):
            continue
        try:
            result = fgdb.storeDef(iDef, user_id=user_id, clean_old=not no_clean)
            Logger.info(f"  ✓ 脚本注册: {os.path.basename(script_path)} (因子: {result['factor_count']})")
        except Exception as e:
            Logger.warning(f"  ✗ 脚本注册失败 ({iDef.Meta.TargetTable}): {e}")


def _generate_group_name(def_obj: Def, strategy_instance) -> str:
    """为策略实例生成回测结果集 GroupName。"""
    meta = def_obj.Meta
    result_key = meta.ResultKey
    if result_key:
        return f"{result_key}/{strategy_instance.Name}"
    return f"{meta.TargetTable}/{strategy_instance.Name}"


def _register_strategy_defs(fgdb, results, extra_tags, user_id, no_clean, settings, pool):
    """注册策略定义到图数据库（包含策略特有逻辑）"""
    all_defs = [d for d, _ in results if d is not None]
    strategy_defs_with_meta = [(d, m) for d, m in results if d is not None and d.StrategyList]

    if not all_defs:
        Logger.warning("没有策略需要注册")
        return

    # 批量注册策略
    all_strategies = []
    tags_map = {}
    for iDef in all_defs:
        base_tags = (extra_tags + [iDef.Meta.TargetTable, iDef.Meta.IDType, iDef.Meta.Author] + list(iDef.Meta.Tags))
        all_strategies.append(iDef)
        for s in iDef.StrategyList:
            tags_map[s.QSID] = base_tags

    Logger.info(f"开始批量注册 {len(all_strategies)} 个策略到图数据库...")
    try:
        success_count = fgdb.storeStrategies(all_strategies, tags=tags_map, user_id=user_id)
        Logger.info(f"注册完成: {success_count}/{len(all_strategies)} 成功")
    except Exception as e:
        Logger.error(f"批量注册失败: {e}")

    # 注册脚本节点
    for iDef in all_defs:
        script_path = iDef.Meta.DefScriptPath
        if not script_path or not os.path.isfile(script_path):
            continue
        try:
            result = fgdb.storeDef(iDef, user_id=user_id, clean_old=not no_clean)
            Logger.info(f"  ✓ 脚本注册: {os.path.basename(script_path)} (因子: {result['factor_count']})")
        except Exception as e:
            Logger.warning(f"  ✗ 脚本注册失败 ({iDef.Meta.TargetTable}): {e}")

    # 补建 (因子表)-[:属于因子库]->(因子库) 关系
    target_db_name = settings.target_db
    if isinstance(target_db_name, list):
        target_db_name = target_db_name[0]
    if target_db_name and target_db_name in pool:
        target_fdb = pool[target_db_name]
        fgdb.registerFactorDB(target_fdb)
        target_tables = {d.Meta.TargetTable for d in all_defs if d.Meta.TargetTable}
        for table_name in target_tables:
            try:
                fgdb._runCypher(
                    """
                    MATCH (t:`因子表` {Name: $table_name})
                    MATCH (d:`因子库` {Name: $fdb_name})
                    MERGE (t)-[:`属于因子库`]->(d)
                    """,
                    {"table_name": table_name, "fdb_name": target_fdb.Name}
                )
                Logger.info(f"已关联因子表: {table_name} → {target_fdb.Name}")
            except Exception as e:
                Logger.warning(f"关联因子表失败 ({table_name}): {e}")

    # 注册回测结果集 / 回测结果库
    if settings.bt_store:
        resultset_count = 0
        try:
            bt_result_db = HDF5BTResultDB(args=dict(settings.bt_store.args))
            fgdb.storeBTResultDB(bt_result_db, user_id=user_id)

            for iDef in all_defs:
                base_tags = (extra_tags + [iDef.Meta.TargetTable, iDef.Meta.IDType, iDef.Meta.Author] + list(iDef.Meta.Tags))
                for s in iDef.StrategyList:
                    group_name = _generate_group_name(iDef, s)
                    fgdb.storeBTResultSet(
                        group_name=group_name,
                        bt_result_db_name=bt_result_db.Name,
                        strategy_qsid=s.QSID,
                        tags=base_tags,
                        user_id=user_id,
                    )
                    resultset_count += 1
            Logger.info(f"回测结果集注册完成: {resultset_count} 个")
        except Exception as e:
            Logger.error(f"回测结果集注册失败: {e}")


def _dry_run(settings: DefSettings):
    Logger.info("=" * 60)
    Logger.info("DRY RUN — 仅分析配置")
    Logger.info("=" * 60)
    profiles = settings.iter_profiles()
    Logger.info(f"PROFILES ({len(profiles)} 个):")
    for i, p in enumerate(profiles):
        Logger.info(f"  Profile {i+1}: collect_mode={p.collect_mode}")
        if p.factor_modules:
            Logger.info(f"    因子模块 ({len(p.factor_modules)}): {p.factor_modules}")
        if p.strategy_modules:
            Logger.info(f"    策略模块 ({len(p.strategy_modules)}): {p.strategy_modules}")
    Logger.info(f"Neo4j: {settings.neo4j_config_path}")
    Logger.info(f"嵌入: {settings.embedding_model} (skip={settings.skip_embedding})")


def _parse_args():
    parser = argparse.ArgumentParser(description="QSExt 统一图数据库注册脚本")
    parser.add_argument("--settings", "-s", default="settings", help="配置模块名")
    parser.add_argument("--debug", "-d", action="store_true", default=None)
    parser.add_argument("--dry-run", "-n", action="store_true", default=None)
    parser.add_argument("--skip-embedding", action="store_true", default=None)
    parser.add_argument("--tags", "-t", nargs="*", default=None, help="附加标签")
    parser.add_argument("--no-clean", action="store_true", default=None)
    args = parser.parse_args()

    cmd_overrides = {}
    if args.debug is not None:
        cmd_overrides["debug"] = args.debug
    if args.dry_run is not None:
        cmd_overrides["dry_run"] = args.dry_run
    if args.skip_embedding is not None:
        cmd_overrides["skip_embedding"] = args.skip_embedding
    if args.tags is not None:
        cmd_overrides["_graph_tags"] = args.tags
    if args.no_clean is not None:
        cmd_overrides["_no_clean"] = args.no_clean

    return args, cmd_overrides


if __name__ == "__main__":
    args, cmd_overrides = _parse_args()
    main(settings_path=args.settings, **cmd_overrides)
