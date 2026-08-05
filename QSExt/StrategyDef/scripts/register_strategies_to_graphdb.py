# coding=utf-8
"""
策略图数据库注册脚本 —— 根据配置文件加载策略模块并注册到 QSGraphDB

与 run_strategy_def.py 共享同一套 settings 配置体系，区别是不写 HDF5 数据，
而是将策略元信息和拓扑关系注册到 Neo4j 图数据库。

使用方式:
    python register_strategies_to_graphdb.py
    python register_strategies_to_graphdb.py --settings settings_prod
    python register_strategies_to_graphdb.py --debug --dry-run
    python register_strategies_to_graphdb.py --modules QSExt.StrategyDef.example_strategy
    python register_strategies_to_graphdb.py --tags 趋势跟踪 实验策略
    python register_strategies_to_graphdb.py --skip-embedding

配置文件位于 QSExt/StrategyDef/conf/ 目录。
"""
import os
import json
import re
import argparse
import logging
import datetime as dt
from typing import List, Optional

from dotenv import load_dotenv

from QuantStudio.Core import setDefaultLogLevel
setDefaultLogLevel(logging.DEBUG)
from QuantStudio.Core import __QS_Logger__ as Logger
from QSExt.QSRegistry.api import QSGraphDB
from QSExt.StrategyDef.StrategyDefContent import (
    StrategyDef, StrategyDefSettings, StrategyDefInputBuilder, build_dep_sd,
)
from QSExt import __QS_MainPath__


__NOW__ = dt.datetime.now()


# ---- Neo4j 配置 ----------------------------------------------------------------

def _load_neo4j_config(config_path: Optional[str] = None) -> dict | None:
    """加载 Neo4j 连接配置，失败返回 None"""
    if config_path is None:
        config_path = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
    else:
        config_path = os.path.expanduser(config_path)

    if not os.path.exists(config_path):
        Logger.warning(f"Neo4j 配置文件不存在: {config_path}")
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r",\s*([}\]])", r"\1", content)
        neo4j_cfg = json.loads(content)
        return {
            "IPAddr": neo4j_cfg["IPAddr"],
            "Port": neo4j_cfg["Port"],
            "User": neo4j_cfg["User"],
            "Pwd": neo4j_cfg["Pwd"],
            "DBName": neo4j_cfg.get("DBName", "neo4j"),
        }
    except Exception as e:
        Logger.warning(f"加载 Neo4j 配置失败: {e}")
        return None


def _init_graphdb(
    neo4j_config_path: Optional[str] = None,
    skip_embedding: bool = False,
    embedding_model: str = "bge-m3",
    embedding_dim: int = 1024,
) -> Optional[QSGraphDB]:
    """初始化并连接 QSGraphDB"""
    neo4j_args = _load_neo4j_config(neo4j_config_path)
    if neo4j_args is None:
        return None

    if not skip_embedding:
        load_dotenv(__QS_MainPath__ + "/config/.env")
        neo4j_args["OllamaBaseURL"] = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        neo4j_args["OllamaAPIKey"] = os.getenv("OLLAMA_API_KEY", "ollama")
        neo4j_args["EmbeddingModel"] = os.getenv("EMBEDDING_MODEL", embedding_model)
        neo4j_args["EmbeddingDim"] = int(os.getenv("EMBEDDING_DIM", str(embedding_dim)))

    try:
        fgdb = QSGraphDB(args=neo4j_args)
        fgdb.connect()
        Logger.info(f"QSGraphDB 已连接 → {neo4j_args['IPAddr']}:{neo4j_args['Port']}")
        return fgdb
    except Exception as e:
        Logger.warning(f"QSGraphDB 连接失败: {e}")
        return None


# ---- 主逻辑 --------------------------------------------------------------------

def main(settings_path: str = "settings", **cmd_overrides):
    """根据配置文件加载策略模块并注册到图数据库"""
    Logger.info(f"策略图数据库注册启动 — 进程: {os.getpid()}, 时间: {__NOW__}")

    extra_args = {k: v for k, v in cmd_overrides.items() if k.startswith("_")}
    settings_overrides = {k: v for k, v in cmd_overrides.items() if not k.startswith("_")}

    # 1. 加载配置
    settings = StrategyDefSettings.from_module(settings_path, **settings_overrides)
    Logger.info(f"配置已加载: {settings_path} (debug={settings.debug})")

    if settings.dry_run:
        _dry_run(settings)
        return

    # 2. 初始化 Builder
    with StrategyDefInputBuilder(settings) as builder:
        sdi = builder.build()
        modules = builder.resolve_modules()
        pool = builder._pool

        Logger.info(f"数据源: {pool.source_names}, DTs 数量: {len(sdi.DTs)}, IDs 数量: {len(sdi.IDs)}")
        Logger.info(f"策略模块 ({len(modules)}): {[m[0].__name__.split('.')[-1] if hasattr(m[0], '__name__') else str(m[0]) for m in modules]}")

        if not sdi.IDs:
            Logger.warning("IDs 为空，终止执行")
            return
        if not modules:
            Logger.warning("没有策略模块需要处理")
            return

        # 3. 运行策略定义
        Logger.info("正在解析依赖并执行策略定义...")
        StrategyDefDict, strategy_defs = build_dep_sd(modules, sdi)

        all_strategy_defs: List[StrategyDef] = [sd for sd, _ in strategy_defs if sd is not None]

        for iStrategyDef in all_strategy_defs:
            Logger.info(f"  → TargetTable='{iStrategyDef.Meta.TargetTable}', "
                        f"策略数={len(iStrategyDef.StrategyList)}, "
                        f"MaxLookBack={iStrategyDef.Meta.MaxLookBack}")

        if not all_strategy_defs:
            Logger.warning("没有策略需要注册")
            return

        # 4. 初始化 QSGraphDB
        extra_tags = list(extra_args.get("_graph_tags", []))
        fgdb = _init_graphdb(
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

            # 5. 收集所有策略并构建标签映射，批量注册
            all_strategies = []
            tags_map = {}

            for strategy_def in all_strategy_defs:
                base_tags = (extra_tags +
                            [strategy_def.Meta.TargetTable,
                             strategy_def.Meta.IDType,
                             strategy_def.Meta.Author] +
                            list(strategy_def.Meta.Tags))

                all_strategies.append(strategy_def)
                tags_map[strategy_def.StrategyInstance.QSID] = base_tags

            Logger.info(f"开始批量注册 {len(all_strategies)} 个策略到图数据库 ...")
            try:
                success_count = fgdb.storeStrategies(all_strategies, tags=tags_map)
                Logger.info(f"注册完成: {success_count}/{len(all_strategies)} 成功")
            except Exception as e:
                Logger.error(f"批量注册失败: {e}")
                success_count = 0

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

    Logger.info("策略图数据库注册完成")


def _dry_run(settings: StrategyDefSettings):
    """Dry-run 模式"""
    Logger.info("=" * 60)
    Logger.info("DRY RUN — 仅分析配置")
    Logger.info("=" * 60)
    Logger.info(f"  DEBUG: {settings.debug}")
    Logger.info(f"  END_DT: {settings.end_dt}")
    Logger.info(f"因子库:")
    for db_def in settings.factor_databases:
        Logger.info(f"  [{db_def.role}] {db_def.name} ({db_def.class_path})")
    Logger.info(f"ID_PROFILES:")
    for i, p in enumerate(settings.iter_profiles()):
        Logger.info(f"  Profile {i+1}: id_type={p.id_type}, modules={len(p.strategy_modules)}")
        for item in p.strategy_modules:
            Logger.info(f"    - {item}")
    Logger.info(f"Neo4j 配置: {settings.neo4j_config_path}")
    Logger.info(f"嵌入模型: {settings.embedding_model} (dim={settings.embedding_dim})")
    Logger.info(f"跳过嵌入: {settings.skip_embedding}")


def _parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="QSExt 策略图数据库注册脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python register_strategies_to_graphdb.py
  python register_strategies_to_graphdb.py --settings settings_prod
  python register_strategies_to_graphdb.py --debug --dry-run
  python register_strategies_to_graphdb.py --modules QSExt.StrategyDef.example_strategy
  python register_strategies_to_graphdb.py --tags 趋势跟踪 实验策略
  python register_strategies_to_graphdb.py --skip-embedding
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
        cmd_overrides["id_profiles"] = _build_profiles_from_modules(
            args.modules, default_id_type=args.id_type
        )
    if args.skip_embedding is not None:
        cmd_overrides["skip_embedding"] = args.skip_embedding

    if args.tags is not None:
        cmd_overrides["_graph_tags"] = args.tags

    return args, cmd_overrides


def _build_profiles_from_modules(module_paths: list, default_id_type: str = "A股") -> list:
    """按 IDType 分组模块"""
    groups: dict = {}
    for m in module_paths:
        id_type = _read_id_type(m) or default_id_type
        groups.setdefault(id_type, []).append(m)

    profiles = []
    for idt, mods in groups.items():
        profiles.append({
            "id_type": idt,
            "strategy_modules": mods,
        })
        Logger.info(f"  Profile [{idt}]: {len(mods)} 个模块")
    return profiles


def _read_id_type(module_path: str) -> Optional[str]:
    """从模块的 __STRATEGY_META__ 中读取 IDType"""
    try:
        import importlib
        module = None
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            pass
        if module is None and os.path.isfile(module_path):
            import importlib.util
            modname = os.path.splitext(os.path.basename(module_path))[0]
            spec = importlib.util.spec_from_file_location(modname, module_path)
            if spec is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
        if module is None:
            return None
        meta = getattr(module, "__STRATEGY_META__", None)
        if isinstance(meta, dict) and meta.get("IDType"):
            return meta["IDType"]
    except Exception:
        pass
    return None


if __name__ == "__main__":
    args, cmd_overrides = _parse_args()
    main(settings_path=args.settings, **cmd_overrides)
