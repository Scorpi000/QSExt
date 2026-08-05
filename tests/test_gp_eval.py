"""
GP 因子挖掘独立测试脚本。

在 HDF5DB 的数据上运行遗传规划挖掘，验证:
1. FeatherFactorCache + FactorContext + Engine 的正确使用
2. fitness_fun 跨代正常执行

用法：C:/Users/hst/Project/PythonEnv/QS/Scripts/python.exe scripts/test_gp_eval.py
"""
import datetime as dt
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import warnings
from pandas.errors import PerformanceWarning
warnings.filterwarnings('ignore', category=PerformanceWarning)

# --- 1. 数据准备 ---

from QuantStudio.Factor.HDF5DB import HDF5DB
from QuantStudio import __QS_MainPath__

hdf5_main_dir = "D:/Data/HDF5DB"
FDB = HDF5DB(args={"MainDir": str(hdf5_main_dir)}).connect()

StartDT, EndDT = dt.datetime(2025, 1, 1), dt.datetime(2025, 6, 30)
TestStartDT, TestEndDT = dt.datetime(2025, 3, 31), EndDT

FT = FDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
DTRuler = FT.getDateTime(start_dt=StartDT, end_dt=EndDT)
TestDTs = FT.getDateTime(start_dt=TestStartDT, end_dt=TestEndDT)
SectionIDs = FT.getID()

Price = FT.getFactor("close")
Open = FT.getFactor("open")
Avg = FT.getFactor("avg")
High = FT.getFactor("high")
Low = FT.getFactor("low")

print(f"DTRuler: {len(DTRuler)} dts, TestDTs: {len(TestDTs)} dts, SectionIDs: {len(SectionIDs)} ids")

# --- 2. 回测评估函数 ---

from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Core.Node import DTInitData, DTLocalContext
from QuantStudio.Factor.Factor import FactorContext
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QuantStudio.BackTest.SectionFactor.IC import CalcIC, IC


def make_fitness_fun(dtruler, dts, section_ids, price, cache_dir, start_mode="new"):
    """构建 fitness 函数: cache 和 context 都复用."""
    cache = FeatherFactorCache(args={
        "DTRuler": dtruler,
        "PIDs": ["0"],
        "CacheDir": cache_dir,
        "StartMode": start_mode,
    })
    cache.start()

    context = FactorContext(
        PID="0", PIDList=["0"], DTRuler=dtruler,
        SectionIDs=section_ids, DataCache=cache,
    )

    def fitness_fun(factors):
        if not factors:
            return np.array([])
        try:
            calc_ic = CalcIC(
                descriptor_ids=section_ids,
                lookback=31,
                period_lookback=1,
                corr_method="spearman",
            )(*factors, price=price, factor_args={})
            ic_node = IC(calc_ic, args={"RollingAvgPeriod": 12, "GenReport": False})
            with Engine() as engine:
                output, = engine.run(
                    [ic_node], context,
                    fwd_data_list=[DTLocalContext(DTs=dts)],
                    init_data_list=[DTInitData(DTRange=(dts[0], dts[-1]))],
                )
            stats = output.get("统计数据", output) if isinstance(output, dict) else output
            if isinstance(stats, pd.DataFrame) and "IC_IR" in stats.columns:
                ic_ir = pd.to_numeric(stats["IC_IR"], errors="coerce").fillna(0.0).values
                return np.abs(ic_ir)
            return np.full(len(factors), 0.0)
        except Exception as e:
            logger.warning(f"fitness 评估失败: {e}")
            import traceback
            traceback.print_exc()
            return np.full(len(factors), np.nan)

    return fitness_fun

logger = logging.getLogger(__name__)

# --- 3. 手动因子测试 ---

from QuantStudio.Factor.BasicOperator import sub, div, add, mul, qs_abs, neg
from QSExt.GPFactor.GPLearn import toExprStr

manual_factors = [
    sub(Price, Avg),                     # close - avg
    sub(High, Low),                      # high - low
    sub(Open, Price),                    # open - close
    sub(div(add(High, Low), Avg), Avg),  # (high+low)/2 - avg
]

cache_dir = Path(__QS_MainPath__).parent / "docs/data/Cache"
cache_dir.mkdir(parents=True, exist_ok=True)

fitness_fun = make_fitness_fun(DTRuler, TestDTs, SectionIDs, Price, str(cache_dir), start_mode="new")

print("\n--- 手动因子 fitness ---")
result = fitness_fun(manual_factors)
for i, f in enumerate(manual_factors):
    print(f"  {toExprStr(f)}: fitness={result[i]:.6f}")

# --- 4. GP 挖掘 ---

from QSExt.GPFactor.GPLearn import GPLearner, GPConfig

operators = [add, sub, mul, div]
terminals = [Price, Open, Avg]

fitness_fun2 = make_fitness_fun(DTRuler, TestDTs, SectionIDs, Price, str(cache_dir), start_mode="continue")

config = GPConfig(
    population_size=20,
    tournament_size=5,
    init_depth=(2, 4),
    init_method="half and half",
    const_range=None,
    p_crossover=0.9,
    p_subtree_mutation=0.01,
    p_hoist_mutation=0.01,
    p_point_mutation=0.01,
    p_point_replace=0.05,
    parsimony_coefficient=0.0,
)

learner = GPLearner(
    operator_list=operators,
    terminal_factors=terminals,
    fitness_fun=fitness_fun2,
    config=config,
)

print("\n--- GP 进化 (3 代) ---")
populations, fitness_history, ancestry = learner.evolve(n_generations=3)

for i, arr in enumerate(fitness_history):
    best = float(arr.max()) if not np.all(np.isnan(arr)) else 0.0
    avg = float(arr[~np.isnan(arr)].mean()) if not np.all(np.isnan(arr)) else 0.0
    print(f"  第{i}代 best={best:.6f} avg={avg:.6f}  fitness=[{', '.join(f'{v:.4f}' for v in arr[:5])}{'...' if len(arr) > 5 else ''}]")

print("\n--- Hall of Fame ---")
for i, (fit_val, expr) in enumerate(learner.hall_of_fame[:5]):
    print(f"  {i+1}: fitness={float(fit_val):.6f}  expr={toExprStr(expr[0])}")

print("\ndone")
