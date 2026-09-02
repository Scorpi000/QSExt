# -*- coding: utf-8 -*-
"""示例策略模块 —— 演示 StrategyDef 框架的完整用法

本文件展示了一个基于均线交叉的简单交易策略：

1. __STRATEGY_META__ 元信息声明
2. MakeStrategy 子类 —— 重写 genSignal()
3. defStrategy 标准签名 —— 从 sdi 获取依赖并构造策略实例

策略逻辑：当短期均线上穿长期均线时买入（信号=1），下穿时卖出（信号=-1）。

"""
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Factor import FactorOperator as fo
from QuantStudio.BackTest.Strategy.Strategy import MakeStrategy, MakeAccount
from QSExt.StrategyDef.StrategyDefContent import StrategyDefInput


# ============================================================
# __STRATEGY_META__ — 模块元信息
# ============================================================
__STRATEGY_META__ = {
    # ---- 必填 ----
    "TargetTable": "stock_cn_strategy_example",
    "IDType": "A股",
    "Description": "均线交叉策略示例：短期均线上穿长期均线买入，下穿卖出",

    # ---- 算子默认配置 ----
    "OperatorConfig": {
        "SignalType": "目标权重",
        "InitCash": 1e6,
        "ShortAllowed": False,
        "StartDT": dt.datetime(2024, 6, 5)
    },

    # ---- 依赖声明 ----
    # FactorDeps: key=依赖因子的模块路径, value=[{Name: 因子名, Alias: 别名}]
    # "FactorDeps": {
    #     "stock_cn_day_bar_nafilled": [{"Name": "close", "Alias": "price"}],
    # },
    # StrategyDeps: key=依赖策略的模块路径, value=[{Name: 信号名, Alias: 别名}]
    # "StrategyDeps": {
    #     "grid_trading": [{"Name": "grid_signal", "Alias": "gs"}],
    # },
    "DBDeps": {"BSDB": "基于 BaoStock 的因子库，提供行情和基本信息等数据"},

    # ---- 可调参数 ----
    "ModelArgs": {
        "short_window": "短期均线窗口",
        "long_window": "长期均线窗口",
    },

    "Author": "示例作者",
    "Tags": ["示例", "均线", "趋势跟踪"],
    "MaxLookBack": 120,
    "DefScriptPath": __file__,

    # ---- 回测结果存储（可选） ----
    # "ResultKey": "{IDType}/{TargetTable}/{StrategyName}",  # 控制 BTStorer 的 GroupName 格式
}


# ============================================================
# MakeStrategy 子类
# ============================================================

class MACrossStrategy(MakeStrategy):
    """均线交叉策略

    信号逻辑：
      - ma_short >= ma_long → 买入
      - ma_short < ma_long → 卖出
    
    等权配置所有买入的标的
    """

    def genSignal(self, f, idt, x, last_price, cash, position_num, args):
        """生成交易信号

        Args:
            f: 当前策略因子
            idt: 当前时点
            x: 输入的因子数据列表，x[0]=short_ma, x[1]=long_ma
            last_price: 最新价格
            cash: 现金
            position_num: 当前持仓数量
            args: 策略参数

        Returns:
            pd.Series: 信号值，索引为证券ID
        """
        short_ma = x[0].iloc[0]
        long_ma = x[1].iloc[0]
        
        signal = pd.Series(np.nan, index=short_ma.index)
        signal[short_ma >= long_ma] = 1
        signal[short_ma < long_ma] = 0
        signal = signal / signal.sum()
        return signal


# ============================================================
# defStrategy — 策略定义入口
# ============================================================

def defStrategy(sdi: StrategyDefInput) -> list:
    """标准签名：接收 StrategyDefInput，返回策略实例列表

    框架在调用前已完成:
    1. 递归解析 FactorDeps 和 StrategyDeps 依赖链
    2. 将依赖因子注入到 sdi.Factors
    3. 将依赖策略注入到 sdi.Strategies

    Returns:
        List[Factor]: 策略实例列表，一个模块可定义多个策略，框架统一包装为 StrategyDef
    """
    StrategyList = []

    # ---- 获取数据库连接 ----
    BSDB = sdi.FDB["BSDB"]

    # ============================================================
    # 示例 1：简单因子 —— 从单表读取 + 重命名
    # ============================================================
    FT = BSDB.getTable("A股K线数据", args={"LookBack": 0})
    close = FT.getFactor("close")

    # 从 ModelArgs 读取参数，使用默认值兜底
    short_window = int(sdi.ModelArgs.get("short_window", 5))
    long_window = int(sdi.ModelArgs.get("long_window", 20))

    # 从 OperatorConfig 读取算子配置
    op_config = __STRATEGY_META__["OperatorConfig"]
    signal_type = sdi.ModelArgs.get("signal_type", op_config["SignalType"])
    init_cash = float(sdi.ModelArgs.get("init_cash", op_config["InitCash"]))
    short_allowed = sdi.ModelArgs.get("short_allowed", op_config["ShortAllowed"])
    start_dt = sdi.ModelArgs.get("start_dt", op_config["StartDT"])

    # 计算短期和长期均线
    ma_short = fo.RollingMean(window=short_window, min_periods=short_window)(close)
    ma_long = fo.RollingMean(window=long_window, min_periods=long_window)(close)

    # 计算信号
    Signal = fo.Where()(1, ma_short >= ma_long, 0)
    Signal = Signal / fo.Aggregate(aggr_func=np.nansum)(Signal)

    # 根据信号构造策略
    makeAccount = MakeAccount(
        signal_type=signal_type,
        init_cash=init_cash,
        short_allowed=short_allowed,
        start_dt=start_dt
    )
    Strategy = makeAccount(last_price=close, signal=Signal, factor_args={"Name": "strategy_from_signal"})
    StrategyList.append(Strategy)

    # 通过自定义算子构造策略实例
    makeStrategy = MACrossStrategy(
        signal_type=signal_type,
        init_cash=init_cash,
        short_allowed=short_allowed,
        start_dt=start_dt,
        x_lookback=[0, 0],# x_lookback 指定每个依赖因子的回溯期数
        x_section_ids=[None, None],# x_section_ids 指定每个依赖因子的截面
    )
    Strategy = makeStrategy(ma_short, ma_long, last_price=close, factor_args={"Name": "strategy_from_custom_class"})
    StrategyList.append(Strategy)
    
    return StrategyList
