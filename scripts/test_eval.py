"""
测试因子挖掘评估链路：用真实数据跑一次 IC 评估，验证 _build_fitness_fun_sync + fitness_fun 是否正常工作。

用法：C:/Users/hst/Project/PythonEnv/QS/Scripts/python.exe scripts/test_eval.py
"""
import sys
sys.path.insert(0, r"C:/Users/hst/Project/QSExt/QSWeb/backend")

import datetime as dt
import numpy as np
from app.services.mining_service import mining_service
from app.models.mining import GPRunConfig, EvalConfig, EvalModuleConfig, TerminalFactorRef, PriceRef
from app.services.connection_service import connection_service
from app.services.factor_service import factor_service

mining_service._factor_service = factor_service

# HDF5DB 连接
conns = connection_service.list_connections()
hdf5_conn = [c for c in conns if c.name == 'HDF5DB'][0]
conn_id = hdf5_conn.qsid
table_name = "stock_cn_day_bar_adj_backward_nafilled"
factor_name = "close"
print(f"Using conn_id={conn_id}, table={table_name}, factor={factor_name}")

# 构建配置
config = GPRunConfig(
    operators=["add", "sub"],
    terminal_factors=[
        TerminalFactorRef(conn_id=conn_id, table_name=table_name, factor_name=factor_name),
    ],
    n_generations=1,
    population_size=10,
    start_date="2025-01-01",
    end_date="2025-06-30",
    eval=EvalConfig(
        modules=[
            EvalModuleConfig(
                module="ic",
                instance_label="",
                params={"corr_method": "spearman", "period_lookback": 1, "lookback": 31},
                section_mode="auto",
                price_ref=PriceRef(
                    conn_id=conn_id, table_name=table_name, factor_name=factor_name,
                ),
            )
        ],
        transform="abs_ic_ir",
        sign="greater",
    ),
)

# 解析终端因子
terminal_factors = mining_service._resolve_terminals_sync(config.terminal_factors)
print(f"terminal_factors: {len(terminal_factors)}")
for tf in terminal_factors:
    print(f"  {tf.Name}")

# 获取评估上下文
dtruler, dts, section_ids = mining_service._get_eval_context_sync(terminal_factors, config)
print(f"dtruler: {len(dtruler)} dts, dts: {len(dts)} dts, section_ids: {len(section_ids)} ids")
if dts:
    print(f"dts range: {dts[0]} ~ {dts[-1]}")

# 构建适应度函数
fitness_fun, sign = mining_service._build_fitness_fun_sync(
    config.eval, dtruler, dts, section_ids
)
print(f"fitness_fun built, sign={sign}")

# 模拟几个因子
from QuantStudio.Factor.BasicOperator import add
factors = [add(terminal_factors[0], terminal_factors[0]) for _ in range(10)]
print(f"simulated {len(factors)} factors")

# 执行评估（跑两次模拟多代）
import traceback
print("=== run 1 ===")
try:
    result = fitness_fun(factors)
    print(f"fitness: {result}")
except Exception as e:
    traceback.print_exc()
print("=== run 2 ===")
try:
    result = fitness_fun(factors)
    print(f"fitness: {result}")
except Exception as e:
    traceback.print_exc()
print("done")
