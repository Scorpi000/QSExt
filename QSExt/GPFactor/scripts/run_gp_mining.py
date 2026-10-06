# -*- coding: utf-8 -*-
"""
GPFactor 因子挖掘脚本 —— 以 settings.py 中配置的因子定义作为初始因子池进行遗传规划挖掘。

实现逻辑:
    1. 加载 DefSettings（默认为 settings 模块），取第 1 个含 factor_modules 的 Profile
    2. 用 DefInputBuilder 解析 DTs / DTRuler / IDs / FDB，并按因子定义的 MaxLookBack 扩展 DTRuler
    3. 用 build_dep_fd 执行各模块的 defFactor，收集其产出的因子作为「初始因子池」
    4. 遍历池中每棵因子树，提取：
         - 「默认算子集」：所有 DerivativeFactor 节点的 Operator，按 QSID 去重
         - 「默认叶子因子」：所有无 Descriptors 的因子表因子，按 QSID 去重（常数节点不计入）
    5. 打印三集合摘要；指定 --evolve 时以池因子作为初始种群执行完整 GP 进化

使用方式:
    # 仅构建并打印三集合（不执行进化）
    python -m QSExt.GPFactor.scripts.run_gp_mining --settings ~/QuantStudioConfig/settings.py

    # 执行完整进化（需指定适应度计算所用的价格因子）
    python -m QSExt.GPFactor.scripts.run_gp_mining --evolve \\
        --price-db JYDB --price-table stock_cn_day_bar_adj_backward_nafilled --price-factor close

    # 覆盖 settings 配置项
    python -m QSExt.GPFactor.scripts.run_gp_mining --end-dt 2026-06-30 --lookback 252 --workers 4

依赖:
    - QuantStudio
    - QSExt.DefModule.DefContent
    - QSExt.GPFactor.GPLearn / QSExt.GPFactor.fitness
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
from QuantStudio.Factor.Factor import DataFactor, FactorContext
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QuantStudio.Factor.FactorOperation import DerivativeFactor
from QSExt.DefModule.DefContent import DefSettings, DefInputBuilder, build_dep_fd
from QSExt.GPFactor.GPLearn import GPLearner, flattenFactor2PN, toExprStr, calcDepth
from QSExt.GPFactor.fitness import ICFitnessEvaluator


# 默认 GP 参数配置文件
__DEFAULT_GP_CONFIG__ = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "conf", "gp_config.yaml"
)


# ============================================================
#  因子树遍历工具
# ============================================================

def isConstantFactor(factor) -> bool:
    """判断因子对象是否为常数节点。

    判定规则与 ``QSExt.GPFactor.GPLearn.toExprStr`` 一致：直接持有标量数据的
    DataFactor 即为常数节点。

    Args:
        factor: 因子对象

    Returns:
        True 表示常数节点
    """
    return (isinstance(factor, DataFactor)
            and (factor._DataContent == "Value")
            and (factor._QSArgs.DataType in ("double", "string")))


def collectOperators(factor, result: dict) -> None:
    """递归收集因子树中出现的算子。

    Args:
        factor: 因子树的根节点
        result: 收集容器 ``{算子 QSID: 算子实例}``，由调用方传入以便多次调用间去重
    """
    if isinstance(factor, DerivativeFactor):
        result.setdefault(factor.Operator.QSID, factor.Operator)
    for iFactor in factor.Descriptors:
        collectOperators(iFactor, result)


def collectTerminals(factor, result: dict) -> None:
    """递归收集因子树中的叶子因子（因子表因子），常数节点不计入。

    Args:
        factor: 因子树的根节点
        result: 收集容器 ``{因子 QSID: 因子实例}``，由调用方传入以便多次调用间去重
    """
    Descriptors = factor.Descriptors
    if not Descriptors:
        if not isConstantFactor(factor):
            result.setdefault(factor.QSID, factor)
        return
    for iFactor in Descriptors:
        collectTerminals(iFactor, result)


def extractFromPool(pool_factors: list) -> tuple:
    """从初始因子池中提取默认算子集和默认叶子因子集。

    Args:
        pool_factors: 初始因子池中的因子列表

    Returns:
        ``(operators, terminals)``，分别为去重后的算子列表和叶子因子列表
    """
    Operators, Terminals = {}, {}
    for iFactor in pool_factors:
        collectOperators(iFactor, Operators)
        collectTerminals(iFactor, Terminals)
    return list(Operators.values()), list(Terminals.values())


def _factorLabel(factor) -> str:
    """因子的可读标签：属于因子表时显示为 ``表名.因子名``。"""
    FactorTable = factor.FactorTable
    return f"{FactorTable.Name}.{factor.Name}" if FactorTable is not None else factor.Name


# ============================================================
#  初始因子池构建
# ============================================================

def resolveProfile(settings: DefSettings):
    """取出 settings 中第 1 个包含因子模块的 Profile。

    Args:
        settings: 统一运行时配置

    Returns:
        DefProfile 对象
    """
    Profiles = [p for p in settings.iter_profiles()
                if p.factor_modules and p.collect_mode in ("factor", "both")]
    if not Profiles:
        raise ValueError("settings 中没有任何包含 factor_modules 的 Profile")
    if len(Profiles) > 1:
        Logger.warning(f"settings 中有 {len(Profiles)} 个含因子模块的 Profile，仅使用第 1 个")
    return Profiles[0]


def buildPool(settings: DefSettings, builder: DefInputBuilder, profile) -> tuple:
    """解析 Profile 中的因子定义模块，收集其产出因子作为初始因子池。

    Args:
        settings: 统一运行时配置
        builder: 已初始化的 DefInputBuilder（数据库连接池保持连接）
        profile: 待解析的 DefProfile

    Returns:
        ``(pool_factors, di)``，di 为解析因子定义时使用的 DefInput（含 DTs / IDs / DTRuler / FDB）
    """
    dts, dtruler = builder.resolve_dts()
    if not dts:
        raise ValueError("配置的计算时点为空，请检查 END_DT / LOOKBACK 配置")
    di = builder.build_for_profile(profile, dts=dts, dtruler=dtruler)

    modules = builder.resolve_modules_for(profile.factor_modules, kind="factor")
    if not modules:
        raise ValueError("Profile 中未解析出任何因子定义模块")
    Logger.info(f"解析 {len(modules)} 个因子定义模块: "
                f"{[getattr(iMod, '__name__', str(iMod)) for iMod, _, _ in modules]}")

    dep_fd, factor_defs = build_dep_fd(modules, di)

    # 因子树可能比 settings 配置的回溯期更深，按定义声明的 MaxLookBack 扩展 DTRuler
    MaxLookBack = max([settings.max_lookback] + [iDef.Meta.MaxLookBack for iDef in dep_fd.values()])
    if MaxLookBack > settings.max_lookback:
        end_dt = DefInputBuilder._parse_end_dt(settings.end_dt)
        start_dt = pd.to_datetime(settings.start_dt) if settings.start_dt else end_dt - dt.timedelta(settings.lookback)
        dtruler = DefInputBuilder.apply_dt_freq(
            builder._fetch_dates(start_date=start_dt - dt.timedelta(MaxLookBack), end_date=end_dt),
            settings.dt_freq,
        )
        di.DTRuler = dtruler
        Logger.info(f"MaxLookBack={MaxLookBack} > 配置的 {settings.max_lookback}，"
                    f"DTRuler 已扩展至 {len(dtruler)} 个时点")

    Pool = {}
    for iDef, meta in factor_defs:
        if iDef is None:
            Logger.warning("跳过未能解析的因子定义模块")
            continue
        for iFactor in iDef.FactorList:
            Pool.setdefault(iFactor.QSID, iFactor)
    return list(Pool.values()), di


def printSummary(pool_factors: list, operators: list, terminals: list) -> None:
    """打印初始因子池、默认算子集和默认叶子因子的摘要。"""
    Logger.info("=" * 60)
    Logger.info(f"初始因子池（{len(pool_factors)} 个因子）:")
    for iFactor in pool_factors:
        Logger.info(f"  {_factorLabel(iFactor):<40} 深度={calcDepth(iFactor)}  表达式={toExprStr(iFactor)}")
    Logger.info(f"默认算子集（{len(operators)} 个算子）:")
    for iOperator in operators:
        Logger.info(f"  {iOperator.Name:<20} Arity={iOperator._QSArgs.Arity}")
    Logger.info(f"默认叶子因子（{len(terminals)} 个因子表因子）:")
    for iFactor in terminals:
        Logger.info(f"  {_factorLabel(iFactor)}")
    Logger.info("=" * 60)


# ============================================================
#  进化
# ============================================================

def _progressCallback(gen_idx: int, fitness_history: list, hall_of_fame: list) -> None:
    """逐代输出进化进度（GPLearner.evolve 的 progress_callback）。"""
    Logger.info(f"Gen {gen_idx + 1}: best_IC={fitness_history[-1].max():.6f}, "
                f"avg_IC={fitness_history[-1].mean():.6f}")
    if hall_of_fame:
        Logger.info(f"  当前最优: IC={hall_of_fame[0][0]:.6f}, 表达式={toExprStr(hall_of_fame[0][1][0])}")


def runEvolve(settings: DefSettings, di, pool_factors: list, operators: list, terminals: list,
              gp_config: str, price_db: str, price_table: str, price_factor: str) -> GPLearner:
    """以初始因子池为初始种群执行 GP 进化。

    Args:
        settings: 统一运行时配置
        di: 解析因子定义时使用的 DefInput
        pool_factors: 初始因子池
        operators: 默认算子集
        terminals: 默认叶子因子集
        gp_config: GPLearner 配置文件路径
        price_db: 适应度计算所用价格因子的因子库名
        price_table: 适应度计算所用价格因子的因子表名
        price_factor: 适应度计算所用价格因子名

    Returns:
        执行完进化的 GPLearner 实例
    """
    if not operators:
        raise ValueError("因子池中未出现任何算子，无法执行进化（池中因子均为因子表因子）")
    if price_db not in di.FDB:
        raise KeyError(f"因子库 '{price_db}' 不存在，可用: {list(di.FDB.keys())}")
    Price = di.FDB[price_db].getTable(price_table).getFactor(price_factor)

    evaluator = ICFitnessEvaluator(
        price_factor=Price, section_ids=di.SectionIDs, dtruler=di.DTRuler, dts=di.DTs,
    )
    learner = GPLearner(
        operator_list=operators, terminal_factors=terminals,
        fitness_fun=evaluator, config_file=gp_config,
    )
    parents = [flattenFactor2PN(iFactor) for iFactor in pool_factors]

    workers = int(settings.workers)
    PIDList = [f"0-{i}" for i in range(workers)] if workers > 0 else ["0"]
    Logger.info(f"开始进化: 初始种群={len(parents)}, 算子数={len(operators)}, "
                f"叶子数={len(terminals)}, workers={workers}")

    cache_args = {
        "DTRuler": di.DTRuler, "PIDs": PIDList, "CacheDir": settings.cache_dir or None,
        "StartMode": "new", "Suffix": ".pkl",
    }
    with FeatherFactorCache(args=cache_args) as Cache:
        with FactorContext(
            Mode=("DEBUG" if settings.debug else "PRD"),
            PIDList=PIDList, DTRuler=di.DTRuler, SectionIDs=[], DataCache=Cache,
        ) as Context:
            with (ParallelEngine() if workers > 0 else Engine()) as ExecEngine:
                learner.evolve(parents=parents, progress_callback=_progressCallback)

    Logger.info("Hall of Fame (Top-5):")
    for i, (iFitness, iExpr) in enumerate(learner.hall_of_fame[:5], 1):
        Logger.info(f"  #{i}: IC={iFitness:.6f}, 深度={calcDepth(iExpr[0])}, "
                    f"节点数={len(iExpr)}, 表达式={toExprStr(iExpr[0])}")
    return learner


# ============================================================
#  入口
# ============================================================

def main(settings_path: str = "settings", gp_config: str = __DEFAULT_GP_CONFIG__,
         evolve: bool = False, price_db: str = None, price_table: str = None,
         price_factor: str = None, **cmd_overrides):
    """脚本入口：构建初始因子池，可选执行 GP 进化。

    Args:
        settings_path: settings 模块路径
        gp_config: GPLearner 配置文件路径
        evolve: True 则执行完整 GP 进化
        price_db: 适应度计算所用价格因子的因子库名
        price_table: 适应度计算所用价格因子的因子表名
        price_factor: 适应度计算所用价格因子名
        **cmd_overrides: 覆盖 settings 的命令行参数

    Returns:
        evolve=True 时返回 GPLearner 实例，否则返回 None
    """
    if evolve and not all([price_db, price_table, price_factor]):
        raise ValueError("--evolve 需要同时指定 --price-db / --price-table / --price-factor")

    settings = DefSettings.from_module(settings_path, **cmd_overrides)
    setDefaultLogLevel(getattr(logging, settings.log_level))
    Logger.info(f"配置已加载: {settings_path} (workers={settings.workers})")

    with DefInputBuilder(settings) as builder:
        profile = resolveProfile(settings)
        pool_factors, di = buildPool(settings, builder, profile)
        if not pool_factors:
            raise ValueError("初始因子池为空，请检查 Profile 中的因子定义模块")
        operators, terminals = extractFromPool(pool_factors)
        printSummary(pool_factors, operators, terminals)

        if not evolve:
            return None
        return runEvolve(
            settings=settings, di=di, pool_factors=pool_factors, operators=operators,
            terminals=terminals, gp_config=gp_config,
            price_db=price_db, price_table=price_table, price_factor=price_factor,
        )


def _parse_args():
    parser = argparse.ArgumentParser(
        description="GPFactor 因子挖掘脚本 —— 以 settings.py 配置的因子定义作为初始因子池",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m QSExt.GPFactor.scripts.run_gp_mining
  python -m QSExt.GPFactor.scripts.run_gp_mining --settings ~/QuantStudioConfig/settings.py
  python -m QSExt.GPFactor.scripts.run_gp_mining --evolve --price-db JYDB \\
      --price-table stock_cn_day_bar_adj_backward_nafilled --price-factor close
        """,
    )
    parser.add_argument("--settings", "-s", default="settings", help="配置模块名或路径 (默认: settings)")
    parser.add_argument("--gp-config", default=__DEFAULT_GP_CONFIG__, help="GPLearner 配置文件路径")
    parser.add_argument("--evolve", action="store_true", default=False,
                        help="执行完整 GP 进化 (需同时指定 --price-db / --price-table / --price-factor)")
    parser.add_argument("--price-db", default=None, help="适应度计算所用价格因子的因子库名")
    parser.add_argument("--price-table", default=None, help="适应度计算所用价格因子的因子表名")
    parser.add_argument("--price-factor", default=None, help="适应度计算所用价格因子名")
    parser.add_argument("--debug", "-d", action="store_true", default=None, help="调试模式")
    parser.add_argument("--end-dt", default=None, help="截止日期 (如 2026-06-30)")
    parser.add_argument("--start-dt", default=None, help="起始日期")
    parser.add_argument("--lookback", type=int, default=None, help="回溯天数")
    parser.add_argument("--workers", "-w", type=int, default=None, help="并发 worker 数")

    args = parser.parse_args()
    cmd_overrides = {}
    for key in ("debug", "end_dt", "start_dt", "lookback", "workers"):
        val = getattr(args, key, None)
        if val is not None:
            cmd_overrides[key] = val
    return args, cmd_overrides


if __name__ == "__main__":
    args, cmd_overrides = _parse_args()
    main(
        settings_path=args.settings, gp_config=args.gp_config, evolve=args.evolve,
        price_db=args.price_db, price_table=args.price_table, price_factor=args.price_factor,
        **cmd_overrides,
    )
