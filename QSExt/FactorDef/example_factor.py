# -*- coding: utf-8 -*-
"""示例因子模块 —— 演示 FactorDef 框架的完整用法

本文件是一个独立可运行的因子定义示例，展示了：

1. __FACTOR_META__ 元信息声明
2. 自定义算子（@FactorOperatorized 装饰器）
3. 从 FactorDB 读取数据并变换（主板 + 科创板双表合并）
4. 依赖因子声明与注入（FactorDeps）
5. defFactor 标准签名与返回

注意：本示例依赖聚源数据库（JYDB）中的具体表名和字段名，
实际使用时请根据数据源调整。

"""
from typing import List

import numpy as np

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor import FactorOperator as fo
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput


# ============================================================
# __FACTOR_META__ — 模块元信息（唯一真相源）
# ============================================================
__FACTOR_META__ = {
    # ---- 必填 ----
    "TargetTable": "stock_cn_factor_example",   # 输出因子表名
    "IDType": "A股",                             # 证券类型
    "Description": "示例因子：演示 FactorDef 框架用法，含动量因子和简单变换因子",

    # ---- 可选 ----
    "Author": "示例作者",
    "MaxLookBack": 365 * 2,                      # 最大回溯天数
    "Tags": ["示例", "动量", "教学"],

    # ---- 依赖声明 ----
    # FactorDeps: 声明需要哪些表的哪些因子，框架自动注入到 fdi.Factors
    "FactorDeps": {
        "stock_cn_status": ["if_listed"],          # 依赖：上市状态
        "stock_cn_day_bar_nafilled": ["close"],     # 依赖：收盘价（前复权）
    },

    # DBDeps: 声明直接访问的因子库，框架校验存在性
    "DBDeps": {"JYDB": "聚源数据库，提供行情和财务数据"},

    "DefScriptPath": __file__,
}


# ============================================================
# 自定义算子
# ============================================================

@FactorOperatorized(
    operator_type="Time",
    args={
        "Arity": 1,
        "DTMode": "多时点",
        "IDMode": "单ID",
        "DataType": "double",
        "LookBack": [20],              # 回溯 20 个时点（长度与 Arity 一致）
    },
)
def calcMomentum(f, idt, iid, x, args):
    """计算过去 N 日动量（收益率）

    算子类型为 Time（时序算子），对单个 ID 跨时间操作。
    LookBack = [20] 表示回溯 20 个时点，框架自动为每次调用填充
    长度为 21 的窗口（当前值 + 20 个历史值）。
    """
    Prices = x[0]
    Returns = (Prices[-1] - Prices[0]) / Prices[0]  # (最新价 - 最早价) / 最早价
    return Returns


@FactorOperatorized(
    operator_type="Section",
    args={
        "Arity": 1,
        "DTMode": "单时点",
        "DataType": "double",
    },
)
def calcZScore(f, idt, iid, x, args):
    """截面标准化（Z-Score）

    算子类型为 Section（截面算子），在单个时点上跨所有 ID 操作。
    将原始值减去截面均值后除以截面标准差，缺失值原样保留。
    """
    Raw = np.array(x[0], dtype=float)
    Mask = np.isfinite(Raw)
    Result = np.full(Raw.shape, np.nan)
    if Mask.sum() > 1:
        Mean = np.mean(Raw[Mask])
        Std = np.std(Raw[Mask])
        if Std > 0:
            Result[Mask] = (Raw[Mask] - Mean) / Std
    return Result


# ============================================================
# defFactor — 因子定义入口
# ============================================================
def defFactor(fdi: FactorDefInput) -> List[Factor]:
    """标准签名：接收 FactorDefInput，返回 List[Factor]

    框架在调用前已完成:
    1. 递归解析 FactorDeps 依赖链
    2. 将依赖因子注入到 fdi.Factors
    3. 校验 DBDeps 中声明的库是否在 fdi.FDB 中存在
    """
    Factors = []

    # ---- 获取数据库连接 ----
    JYDB = fdi.FDB["JYDB"]

    # ---- 获取依赖因子（由框架根据 FactorDeps 预注入）----
    IsListed = fdi.Factors["if_listed"]
    Close = fdi.Factors["close"]

    # ---- 常用算子 ----
    notnull = fo.NotNull()

    # ============================================================
    # 示例 1：简单因子 —— 从单表读取 + 重命名
    # ============================================================
    # 从主板读取
    FT = JYDB.getTable("日行情表", args={"LookBack": 0})
    Turnover = FT.getFactor("换手率(%)")

    # 从科创板读取，用 where 合并
    FT_STAR = JYDB.getTable("科创板日行情", args={"LookBack": 0})
    Turnover_STAR = FT_STAR.getFactor("换手率(%)")
    Turnover = fo.Where(dtype="double")(Turnover, notnull(Turnover), Turnover_STAR)

    # 重命名并添加描述
    TurnoverFactor = rename(
        Turnover,
        factor_name="turnover",
        factor_args={"Meta": {"Description": "日换手率(%)，主板+科创板合并"}},
    )
    Factors.append(TurnoverFactor)

    # ============================================================
    # 示例 2：自定义算子 —— 动量因子
    # ============================================================
    MomentumRaw = calcMomentum(
        Close,
        factor_args={
            "Name": "momentum_20d",
            "Meta": {"Description": "20日动量(收益率)，基于前复权收盘价计算"},
        },
    )

    # 过滤未上市或停牌样本
    MomentumFiltered = fo.Where(dtype="double")(MomentumRaw, IsListed == 1, np.nan)

    Factors.append(MomentumFiltered)

    # ============================================================
    # 示例 3：算子组合 —— 动量 Z-Score
    # ============================================================
    MomentumZ = calcZScore(
        MomentumRaw,
        factor_args={
            "Name": "momentum_20d_zscore",
            "Meta": {"Description": "20日动量截面Z-Score，去均值除标准差"},
        },
    )
    Factors.append(MomentumZ)

    return Factors
