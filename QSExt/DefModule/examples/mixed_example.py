# -*- coding: utf-8 -*-
"""混合定义示例 —— 在同一个脚本中同时定义因子和策略。

本文件演示 DefModule 统一框架的核心能力：
    1. 使用 __FACTOR_META__ 声明元信息
    2. defNode 入口函数同时返回因子和策略实例
    3. 框架根据算子类型自动归类：
       - 普通因子 → FactorList
       - MakeAccount 策略 → StrategyList

策略逻辑：基于 MA5 和 MA20 均线交叉，上穿等权买入，下穿清仓。
"""
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor import FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.BackTest.Strategy.Strategy import MakeAccount
from QSExt.DefModule.DefContent import DefInput


# ============================================================
# __FACTOR_META__ — 模块元信息
# ============================================================
__FACTOR_META__ = {
    "TargetTable": "stock_cn_mixed_example",
    "IDType": "A股",
    "Description": "混合定义示例：同时产出行情因子和均线交叉策略",
    "Author": "示例作者",
    "MaxLookBack": 365 * 2,
    "Tags": ["示例", "混合", "均线"],
    "FactorDeps": {},
    "DBDeps": {"BSDB": "基于 BaoStock 的因子库"},
    "DefScriptPath": __file__,
}


# ============================================================
# defNode — 统一入口（同时返回因子和策略）
# ============================================================
def defNode(fdi: DefInput) -> list:
    """统一入口函数，返回的列表中可同时包含因子和策略。

    框架根据对象的算子类型自动归类：
    - 算子为 MakeAccount 实例 → StrategyList
    - 其他 → FactorList
    """
    items = []

    BSDB = fdi.FDB["BSDB"]

    # ============================================================
    # 因子部分 —— 行情因子
    # ============================================================
    FT = BSDB.getTable("A股K线数据", args={"LookBack": 0})
    close = FT.getFactor("close")
    items.append(FT.getFactor("open"))
    items.append(FT.getFactor("high"))
    items.append(FT.getFactor("low"))
    items.append(rename(FT.getFactor("preclose"), factor_name="pre_close"))

    # ============================================================
    # 策略部分 —— 均线交叉策略
    # ============================================================
    ma_short = fo.RollingMean(window=5, min_periods=5)(close)
    ma_long = fo.RollingMean(window=20, min_periods=20)(close)

    # 信号：MA5 >= MA20 买入，否则卖出
    Signal = fo.Where()(1, ma_short >= ma_long, 0)
    Signal = Signal / fo.Aggregate(aggr_func=np.nansum)(Signal)

    # 构造策略实例（MakeAccount 算子，框架自动识别为策略）
    makeAccount = MakeAccount(
        signal_type="目标权重",
        init_cash=1e6,
        short_allowed=False,
        start_dt=dt.datetime(2024, 6, 5),
    )
    strategy = makeAccount(last_price=close, signal=Signal, factor_args={"Name": "ma_cross_strategy"})
    items.append(strategy)

    return items
