# -*- coding: utf-8 -*-
"""新策略 —— 策略模板

本文件是策略定义的空白模板，展示 StrategyDef 框架的基本结构：

1. __STRATEGY_META__ — 模块元信息声明
2. MakeStrategy 子类 —— 重写 genSignal() 实现交易信号逻辑
3. defStrategy — 标准入口函数，从 sdi 获取依赖因子并构造策略实例

使用方法：
  1. 复制此文件，重命名为你的策略名
  2. 填写 __STRATEGY_META__ 中的元信息
  3. 实现 MyStrategy.genSignal() 中的信号逻辑
  4. 在 defStrategy 中配置依赖因子并返回策略实例列表
"""
import pandas as pd

from QuantStudio.BackTest.Strategy.Strategy import MakeStrategy
from QSExt.StrategyDef.StrategyDefContent import StrategyDefInput


# ============================================================
# __STRATEGY_META__ — 模块元信息
# ============================================================
__STRATEGY_META__ = {
    # ---- 必填 ----
    "TargetTable": "my_strategy_signals",
    "IDType": "A股",
    "Description": "",

    # ---- 算子默认配置 ----
    "OperatorConfig": {
        "SignalType": "目标权重",
        "InitCash": 1e6,
        "ShortAllowed": False,
    },

    # ---- 依赖声明 ----
    "FactorDeps": {},
    # StrategyDeps: key=依赖策略的模块路径, value=[{Name: 信号名, Alias: 别名}]
    # "StrategyDeps": {},
    "DBDeps": {},

    # ---- 可调参数 ----
    "ModelArgs": {},

    "Author": "",
    "Tags": [],
    "MaxLookBack": 365,
    "DefScriptPath": __file__,
}


# ============================================================
# MakeStrategy 子类
# ============================================================

class MyStrategy(MakeStrategy):
    """自定义策略"""

    def genSignal(self, f, idt, x, last_price, cash, position_num, args):
        """生成交易信号

        Args:
            f: 当前策略因子
            idt: 当前时点
            x: 输入的依赖因子数据列表
            last_price: 最新价格
            cash: 现金
            position_num: 当前持仓数量
            args: 策略参数

        Returns:
            pd.Series: 信号值，索引为证券 ID
        """
        # TODO: 在此编写你的交易信号逻辑
        return None


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
        List[Factor]: 策略实例列表，一个模块可定义多个策略
    """
    op_config = __STRATEGY_META__["OperatorConfig"]

    op = MyStrategy(
        signal_type=sdi.ModelArgs.get("signal_type", op_config["SignalType"]),
        init_cash=sdi.ModelArgs.get("init_cash", op_config["InitCash"]),
        short_allowed=sdi.ModelArgs.get("short_allowed", op_config["ShortAllowed"]),
    )

    # 从 sdi.Factors 取依赖因子，传给 op()
    # 示例: return [op(factor1, factor2, last_price=sdi.Factors.get("close"))]
    return [op()]
