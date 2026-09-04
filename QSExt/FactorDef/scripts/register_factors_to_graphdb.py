# coding=utf-8
"""
因子图数据库注册脚本 —— 根据配置文件加载因子模块并注册到 QSGraphDB

与 run_factor_def.py 共享同一套 settings 配置体系，区别是不写 HDF5 数据，
而是将因子元信息和拓扑关系注册到 Neo4j 图数据库。

使用方式:
    python register_factors_to_graphdb.py
    python register_factors_to_graphdb.py --settings settings_prod
    python register_factors_to_graphdb.py --debug --dry-run
    python register_factors_to_graphdb.py --modules QSExt.FactorDef.stock_cn_factor_example1
    python register_factors_to_graphdb.py --tags 动量 实验因子
    python register_factors_to_graphdb.py --skip-embedding
    python register_factors_to_graphdb.py --no-clean  # 不删除脚本关联的旧因子

配置文件位于 QSExt/FactorDef/conf/ 目录。

行为说明:
    默认情况下，注册脚本节点时会删除该脚本关联的所有旧因子，然后重新写入。
    使用 --no-clean 参数可以跳过清理步骤，保留旧因子。
"""
import os
import argparse
import logging
import datetime as dt
from typing import List, Optional

from QuantStudio.Core import setDefaultLogLevel
setDefaultLogLevel(logging.DEBUG)
from QuantStudio.Core import __QS_Logger__ as Logger
from QuantStudio.Factor.FactorStorer import FactorStorer
from QSExt.QSRegistry.api import QSGraphDB
from QSExt.QSRegistry.utils import init_graphdb
from QSExt.FactorDef.FactorDefContent import FactorDef, FactorDefSettings, FactorDefInputBuilder, build_dep_fd


__NOW__ = dt.datetime.now()

# ---- 主逻辑 --------------------------------------------------------------------

def main(settings_path: str = "settings", **cmd_overrides):
    """根据配置文件加载因子模块并注册到图数据库"""
    Logger.info(f"因子图数据库注册启动 — 进程: {os.getpid()}, 时间: {__NOW__}")

    # 分离 _ 前缀的非 settings 参数
    extra_args = {k: v for k, v in cmd_overrides.items() if k.startswith("_")}
    user_id = cmd_overrides.pop("user_id", None)
    no_clean = extra_args.get("_no_clean", False)
    settings_overrides = {k: v for k, v in cmd_overrides.items() if not k.startswith("_")}

    # 1. 加载配置
    settings = FactorDefSettings.from_module(settings_path, **settings_overrides)
    Logger.info(f"配置已加载: {settings_path} (debug={settings.debug})")

    if settings.dry_run:
        _dry_run(settings)
        return

    # 2. 初始化 Builder
    with FactorDefInputBuilder(settings) as builder:
        fdi = builder.build()
        modules = builder.resolve_modules()
        pool = builder._pool

        Logger.info(f"数据源: {pool.source_names}, DTs 数量: {len(fdi.DTs)}, IDs 数量: {len(fdi.IDs)}")
        Logger.info(f"因子模块 ({len(modules)}): {[m[0].__name__.split('.')[-1] if hasattr(m[0], '__name__') else str(m[0]) for m in modules]}")

        if not fdi.IDs:
            Logger.warning("IDs 为空，终止执行")
            return

        if not modules:
            Logger.warning("没有因子模块需要处理")
            return

        # 3. 运行因子定义（含依赖自动解析，不需要代理）
        Logger.info("正在解析依赖并执行因子定义...")
        FactorDefDict, factor_defs = build_dep_fd(modules, fdi)

        all_factor_defs: List[FactorDef] = [fd for fd, _ in factor_defs if fd is not None]

        for iFactorDef in all_factor_defs:
            Logger.info(f"  → TargetTable='{iFactorDef.Meta.TargetTable}', "
                        f"因子数={len(iFactorDef.FactorList)}, "
                        f"MaxLookBack={iFactorDef.Meta.MaxLookBack}")

        total_factors = sum(len(fd.FactorList) for fd in all_factor_defs)
        Logger.info(f"共 {len(all_factor_defs)} 个模块, {total_factors} 个因子")

        if total_factors == 0:
            Logger.warning("没有因子需要注册")
            return

        # 4. 初始化 QSGraphDB
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

            # 5. 收集所有因子并构建标签映射，批量注册
            all_factors = []
            tags_map = {}

            for factor_def in all_factor_defs:
                base_tags = (extra_tags +
                            [factor_def.Meta.TargetTable,
                             factor_def.Meta.IDType,
                             factor_def.Meta.Author] +
                            list(factor_def.Meta.Tags))

                for factor in factor_def.FactorList:
                    all_factors.append(factor)
                    tags_map[factor.QSID] = base_tags

            Logger.info(f"开始批量注册 {total_factors} 个因子到图数据库 ...")
            try:
                qsids = fgdb.storeFactors(all_factors, tags=tags_map, user_id=user_id)
                success_count = len(qsids)
                for i, (factor, qsid) in enumerate(zip(all_factors, qsids), 1):
                    Logger.info(f"  [{i:>3}/{total_factors}] ✓ {factor._QSArgs.Name} "
                                f"(QSID: {qsid[:16]}…)")
            except Exception as e:
                Logger.error(f"批量注册失败: {e}")
                success_count = 0

            Logger.info(f"注册完成: {success_count}/{total_factors} 成功")

            # 5a. 注册脚本节点并建立 因子-[:定义于]->脚本 关系
            Logger.info("开始注册脚本节点...")
            script_count = 0
            for factor_def in all_factor_defs:
                script_path = factor_def.Meta.DefScriptPath
                if not script_path or not os.path.isfile(script_path):
                    Logger.debug(f"  跳过脚本注册: {factor_def.Meta.TargetTable} (无有效脚本路径)")
                    continue

                try:
                    result = fgdb.storeFactorDef(
                        factor_def,
                        user_id=user_id,
                        clean_old=not no_clean,
                    )
                    script_count += 1
                    Logger.info(
                        f"  ✓ 脚本注册成功: {os.path.basename(script_path)} "
                        f"(QSID: {result['script_qsid'][:16]}…, 因子: {result['factor_count']})"
                    )
                except Exception as e:
                    Logger.warning(f"  ✗ 脚本注册失败 ({factor_def.Meta.TargetTable}): {e}")

            Logger.info(f"脚本注册完成: {script_count} 个")

            # 5b. 构建并注册 FactorStorer
            target_db_name = settings.target_db
            if isinstance(target_db_name, list):
                target_db_name = target_db_name[0]

            try:
                TDB = pool[target_db_name]
                # 确保目标因子库已在图中注册
                fgdb.registerFactorDB(TDB)
            except KeyError:
                Logger.warning(f"目标因子库 '{target_db_name}' 未在 pool 中找到，跳过 FactorStorer 注册")
                TDB = None

            if TDB is not None:
                # 按 TargetTable 分组合并因子
                table_groups: dict = {}
                for iFactorDef, factor_meta in factor_defs:
                    if iFactorDef is None:
                        continue
                    tt = iFactorDef.Meta.TargetTable
                    if tt not in table_groups:
                        table_groups[tt] = {"factor_defs": [], "factors": [], "factor_names": set()}
                    group = table_groups[tt]
                    group["factor_defs"].append(iFactorDef)
                    for f in iFactorDef.FactorList:
                        fname = f._QSArgs.Name
                        if fname in group["factor_names"]:
                            raise ValueError(
                                f"因子名冲突: '{fname}' 在 TargetTable='{tt}' 中被多个模块定义"
                            )
                        group["factor_names"].add(fname)
                        group["factors"].append(f)

                storer_count = 0
                for target_table, group in table_groups.items():
                    iFactorDef = group["factor_defs"][0]

                    if len(group["factor_defs"]) > 1:
                        module_names = [getattr(fd.Meta, 'DefScriptPath', '?') for fd in group["factor_defs"]]
                        Logger.info(f"TargetTable='{target_table}': 合并 {len(group['factor_defs'])} 个模块 → {len(group['factors'])} 个因子 ({module_names})")

                    try:
                        table_meta = {
                            "Description": iFactorDef.Meta.Description,
                            "IDType": iFactorDef.Meta.IDType,
                            "Author": iFactorDef.Meta.Author,
                            "DefScriptPath": iFactorDef.Meta.DefScriptPath,
                        }
                        storer_args = {
                            "TargetFDB": TDB,
                            "TargetTable": target_table,
                            "TableMeta": table_meta,
                            **settings.factor_storer_config,
                        }
                        iStorer = FactorStorer(deps=group["factors"], args=storer_args)
                        storer_qsid = fgdb.storeFactorStorer(iStorer, tags=extra_tags or None, user_id=user_id)
                        storer_count += 1
                        Logger.info(f"  ✓ FactorStorer '{iStorer._QSArgs.Name}' → {target_db_name}/{target_table} (QSID: {storer_qsid[:16]}…)")
                    except Exception as e:
                        Logger.warning(f"FactorStorer 注册失败 ({target_table}): {e}")

                Logger.info(f"FactorStorer 注册完成: {storer_count} 个")

            # 6. 图统计
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

    Logger.info("因子图数据库注册完成")


def _dry_run(settings: FactorDefSettings):
    """Dry-run 模式：打印配置摘要，不连接数据库"""
    Logger.info("=" * 60)
    Logger.info("DRY RUN — 仅分析配置")
    Logger.info("=" * 60)
    Logger.info(f"  DEBUG: {settings.debug}")
    Logger.info(f"  END_DT: {settings.end_dt}")
    Logger.info(f"因子库:")
    for db_def in settings.factor_databases:
        Logger.info(f"  [{db_def.role}] {db_def.name} ({db_def.class_path})")
    Logger.info(f"FACTOR_PROFILES:")
    for i, p in enumerate(settings.iter_profiles()):
        Logger.info(f"  Profile {i+1}: modules={len(p.factor_modules)}")
        for item in p.factor_modules:
            Logger.info(f"    - {item}")
    Logger.info(f"Neo4j 配置: {settings.neo4j_config_path}")
    Logger.info(f"嵌入模型: {settings.embedding_model} (dim={settings.embedding_dim})")
    Logger.info(f"跳过嵌入: {settings.skip_embedding}")


def _read_id_type(module_path: str) -> Optional[str]:
    """从模块的 __FACTOR_META__ 中读取 IDType

    同时支持文件路径 (/path/to/module.py) 和 Python 模块路径 (pkg.module)。
    加载失败或未声明时返回 None。
    """
    try:
        import importlib
        module = None

        # 优先按 Python 模块路径导入
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            pass

        # 回退：按文件路径加载
        if module is None and os.path.isfile(module_path):
            import importlib.util
            modname = os.path.splitext(os.path.basename(module_path))[0]
            spec = importlib.util.spec_from_file_location(modname, module_path)
            if spec is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

        if module is None:
            return None

        meta = getattr(module, "__FACTOR_META__", None)
        if isinstance(meta, dict) and meta.get("IDType"):
            Logger.debug(f"  自动检测 IDType: {module_path} → {meta['IDType']}")
            return meta["IDType"]
    except Exception as e:
        Logger.debug(f"  无法读取模块 {module_path} 的 IDType: {e}")
    return None


def _build_profiles_from_modules(module_paths: list) -> list:
    """将模块列表构建为单个 profile

    Args:
        module_paths: 模块路径列表

    Returns:
        [{"factor_modules": [...]}]
    """
    Logger.info(f"  构建 profile: {len(module_paths)} 个模块")
    return [{"factor_modules": module_paths}]


def _parse_args():
    """解析命令行参数，返回 (parsed_args, cmd_overrides)"""
    parser = argparse.ArgumentParser(
        description="QSExt 因子图数据库注册脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python register_factors_to_graphdb.py
  python register_factors_to_graphdb.py --settings settings_prod
  python register_factors_to_graphdb.py --debug --dry-run
  python register_factors_to_graphdb.py --modules QSExt.FactorDef.stock_cn_factor_example1
  python register_factors_to_graphdb.py --tags 动量 实验因子
  python register_factors_to_graphdb.py --skip-embedding
        """,
    )
    parser.add_argument("--settings", "-s", default="settings", help="配置模块名 (默认: settings)")
    parser.add_argument("--debug", "-d", action="store_true", default=None, help="调试模式")
    parser.add_argument("--dry-run", "-n", action="store_true", default=None, help="仅分析不执行")
    parser.add_argument("--end-dt", default=None, help="截止日期 (如 2026-06-30)")
    parser.add_argument("--start-dt", default=None, help="起始日期")
    parser.add_argument("--lookback", type=int, default=None, help="回溯天数")
    parser.add_argument("--modules", nargs="*", default=None, help="指定运行的模块名")
    parser.add_argument("--id-type", default="A股", help="模块未声明 IDType 时的回退值 (默认: A股)")
    parser.add_argument("--tags", "-t", nargs="*", default=None, help="附加标签")
    parser.add_argument("--skip-embedding", action="store_true", default=None, help="跳过向量嵌入")
    parser.add_argument("--no-vector-demo", action="store_true", default=None, help="跳过向量检索演示")
    parser.add_argument(
        "--no-clean", action="store_true", default=None,
        help="不删除脚本关联的旧因子（默认会删除后重新写入）"
    )

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
    if args.modules is not None:
        cmd_overrides["factor_profiles"] = _build_profiles_from_modules(args.modules)
    if args.skip_embedding is not None:
        cmd_overrides["skip_embedding"] = args.skip_embedding

    # 非 settings 字段通过 _ 前缀传递
    if args.tags is not None:
        cmd_overrides["_graph_tags"] = args.tags
    if args.no_vector_demo is not None:
        cmd_overrides["_no_vector_demo"] = args.no_vector_demo
    if args.no_clean is not None:
        cmd_overrides["_no_clean"] = args.no_clean

    return args, cmd_overrides


if __name__ == "__main__":
    args, cmd_overrides = _parse_args()
    main(settings_path=args.settings, **cmd_overrides)
