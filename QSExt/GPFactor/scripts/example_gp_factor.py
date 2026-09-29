# -*- coding: utf-8 -*-
"""
遗传规划因子挖掘示例脚本 —— 演示如何使用 GPLearner 自动生成因子。

实现逻辑:
    1. 创建随机数因子作为终端因子（使用 DataFactor 包装）
    2. 配置算子列表（加减乘除、取负、绝对值、对数等）
    3. 使用 ICFitnessEvaluator 作为适应度评估器（基于 CalcIC 算子）
    4. 初始化 GPLearner 并执行进化
    5. 输出 Hall of Fame 中的最优因子及其表达式

使用方式:
    # 直接运行（小种群快速演示）
    python QSExt/GPFactor/scripts/example_gp_factor.py

    # 使用配置文件（支持 JSON 和 YAML 格式）
    python QSExt/GPFactor/scripts/example_gp_factor.py --config QSExt/GPFactor/conf/gp_config.yaml

    # 自定义参数
    python QSExt/GPFactor/scripts/example_gp_factor.py --stock-num 50

依赖:
    - QuantStudio
    - QSExt.GPFactor.GPLearn
    - QSExt.GPFactor.fitness
"""

import argparse
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Factor.Factor import DataFactor, FactorContext
from QuantStudio.Factor.BasicOperator import Add, Sub, Mul, Div, Neg, Abs
from QuantStudio.Factor.FactorOperator import Lag, Log
from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Core.ParallelEngine import ParallelEngine
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QSExt.GPFactor.GPLearn import GPLearner, toExprStr, calcDepth
from QSExt.GPFactor.fitness import ICFitnessEvaluator


# ============================================================
#  创建随机数因子
# ============================================================

def create_random_factors(
    n_factors: int = 5,
    stock_ids: list = None,
    dtruler: list = None,
    seed: int = 42,
) -> list:
    """创建随机数因子作为终端因子。

    使用 DataFactor 包装随机生成的 DataFrame 数据。

    Args:
        n_factors: 因子数量
        stock_ids: 股票 ID 列表
        dtruler: 时点标尺
        seed: 随机种子

    Returns:
        DataFactor 对象列表
    """
    np.random.seed(seed)

    if stock_ids is None:
        stock_ids = [f"Stock_{i:03d}" for i in range(50)]
    if dtruler is None:
        dtruler = [dt.datetime(2024, 1, 1) + dt.timedelta(days=i) for i in range(100)]

    factors = []

    digit_num = int(np.log10(n_factors)) + 1
    for i in range(n_factors):
        # 生成随机数据 DataFrame (index=时间, columns=股票)
        data = pd.DataFrame(
            np.random.randn(len(dtruler), len(stock_ids)),
            index=dtruler,
            columns=stock_ids,
        )
        # 创建 DataFactor
        name = "Seed_" + str(i).zfill(digit_num)
        factor = DataFactor(data=data, args={"Name": name})
        factors.append(factor)

    return factors


# ============================================================
#  进度回调
# ============================================================

def progress_callback(gen_idx: int, fitness_history: list, hall_of_fame: list):
    """逐代输出进化进度。"""
    best_fitness = fitness_history[-1].max()
    avg_fitness = fitness_history[-1].mean()
    print(f"  Gen {gen_idx + 1}: best_IC={best_fitness:.6f}, avg_IC={avg_fitness:.6f}")
    if hall_of_fame:
        best_factor = hall_of_fame[0][1][0]
        expr_str = toExprStr(best_factor)
        depth = calcDepth(best_factor)
        print(f"    Best: IC={hall_of_fame[0][0]:.6f}, depth={depth}, expr={expr_str}")


# ============================================================
#  主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="遗传规划因子挖掘示例")
    parser.add_argument(
        "--config", type=str, default=None,
        help="GP 配置文件路径（支持 JSON 和 YAML 格式，默认使用内置参数）",
    )
    parser.add_argument(
        "--stock-num", type=int, default=50,
        help="股票数量（默认 50）",
    )
    parser.add_argument(
        "--days", type=int, default=365,
        help="模拟天数（默认 100）",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="随机种子（默认 42）",
    )
    parser.add_argument(
        "--cache-dir", type=str, default=None,
        help="缓存目录（默认使用系统临时目录）",
    )
    parser.add_argument(
        "--workers", type=int, default=0,
        help="并发数量",
    )
    args = parser.parse_args()

    # ----------------------------------------------------------
    #  1. 加载配置
    # ----------------------------------------------------------
    if args.config:
        # 从配置文件加载（支持 JSON 和 YAML）
        learner_config = {"config_file": args.config}
        print(f"已加载配置: {args.config}")
    else:
        # 使用小种群快速演示
        learner_config = {
            "args": {
                "PopulationSize": 50,
                "TournamentSize": 5,
                "InitDepthMin": 2,
                "InitDepthMax": 4,
                "PCrossover": 0.7,
                "PSubtreeMutation": 0.1,
                "PHoistMutation": 0.05,
                "PPointMutation": 0.1,
                "ConstRangeEnabled": True,
                "ConstRangeMin": -0.5,
                "ConstRangeMax": 0.5,
                "NGenerations": 3,
                "Verbose": 1,
            },
        }
        print("使用内置默认配置（小种群快速演示）")

    # ----------------------------------------------------------
    #  2. 创建随机数因子作为终端因子
    # ----------------------------------------------------------
    print("\n创建随机数因子...")

    # 生成股票 ID 列表
    stock_ids = [f"Stock_{i:03d}" for i in range(args.stock_num)]

    # 生成时点标尺（包含回溯期）
    total_days = args.days
    dtruler = [dt.datetime(2024, 1, 1) + dt.timedelta(days=i) for i in range(total_days)]

    # 计算时点序列（去掉回溯期）
    dts = dtruler[120:]

    # 创建终端因子
    terminal_factors = create_random_factors(
        n_factors=5,
        stock_ids=stock_ids,
        dtruler=dtruler,
        seed=args.seed,
    )
    print(f"终端因子: {[f.Name for f in terminal_factors]}")
    print(f"股票数量: {len(stock_ids)}")
    print(f"交易日: {len(dts)} 天")

    # ----------------------------------------------------------
    #  3. 配置算子列表
    # ----------------------------------------------------------
    operator_list = [
        Add(),          # 加法: arity=2
        Sub(),          # 减法: arity=2
        Mul(),          # 乘法: arity=2
        Div(),          # 除法: arity=2
        Neg(),          # 取负: arity=1
        Abs(),          # 绝对值: arity=1
        Log(),          # 对数: arity=1
        Lag(offset=1),  # 滞后 1 期: arity=1
    ]
    print(f"算子列表: {[op.Name for op in operator_list]}")

    # ----------------------------------------------------------
    #  4. 创建适应度评估器
    # ----------------------------------------------------------
    print("\n创建适应度评估器...")

    # 价格因子（用于计算收益率）
    price_factor = create_random_factors(n_factors=1, stock_ids=stock_ids, dtruler=dtruler, seed=args.seed)[0]

    fitness_evaluator = ICFitnessEvaluator(
        price_factor=price_factor,
        section_ids=stock_ids,
        dtruler=dtruler,
        dts=dts
    )

    # ----------------------------------------------------------
    #  5. 初始化 GPLearner 并执行进化
    # ----------------------------------------------------------
    learner = GPLearner(
        operator_list=operator_list,
        terminal_factors=terminal_factors,
        fitness_fun=fitness_evaluator,
        **learner_config,
    )

    n_generations = learner.Args.NGenerations
    verbose = learner.Args.Verbose
    print(f"\n种群大小: {learner.Args.PopulationSize}, 进化代数: {n_generations}")

    print("\n开始遗传规划进化...")
    PIDList = ["0"] if args.workers <= 0 else [f"0-{i}" for i in range(args.workers)]
    with FeatherFactorCache(args={"CacheDir": args.cache_dir, "DTRuler": dtruler, "StartMode": "continue"}) as Cache:
        with FactorContext(PIDList=PIDList, DTRuler=dtruler, SectionIDs=[], DataCache=Cache) as Context:
            with (ParallelEngine() if args.workers > 0 else Engine()) as ExecEngine:
                populations, fitness_history, ancestry = learner.evolve(
                    n_generations=n_generations,
                    verbose=verbose,
                    progress_callback=progress_callback,
                )

    # ----------------------------------------------------------
    #  6. 输出结果
    # ----------------------------------------------------------
    print("\n" + "=" * 60)
    print("Hall of Fame（最优因子 Top-5）")
    print("=" * 60)

    for rank, (ic, pn_expr) in enumerate(learner.hall_of_fame[:5], 1):
        factor = pn_expr[0]
        expr_str = toExprStr(factor)
        depth = calcDepth(factor)
        node_count = len(pn_expr)
        print(f"\n  #{rank}:")
        print(f"    IC       = {ic:.6f}")
        print(f"    深度     = {depth}")
        print(f"    节点数   = {node_count}")
        print(f"    表达式   = {expr_str}")

    print("\n" + "=" * 60)
    print("完成！")
    return learner


if __name__ == "__main__":
    learner = main()
