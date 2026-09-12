# -*- coding: utf-8 -*-
"""示例因子模块 —— 演示 DefModule 框架的完整用法

本文件是一个独立可运行的因子定义示例，展示了：

1. __FACTOR_META__ 元信息声明
2. 自定义算子（@FactorOperatorized 装饰器）
3. 从 FactorDB 读取数据
4. 依赖因子声明与注入（FactorDeps）
5. defFactor 标准签名与返回

注意：本示例依赖 BaoStock 因子库（BSDB）中的具体表名和字段名，
实际使用时请根据数据源调整。
"""
from typing import List

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.BasicOperator import rename
from QSExt.DefModule.DefContent import DefInput


# ============================================================
# __FACTOR_META__ — 模块元信息（唯一真相源）
# ============================================================
__FACTOR_META__ = {
    # ---- 必填 ----
    "TargetTable": "stock_cn_factor_example1",   # 输出因子表名
    "IDType": "A股",                             # 证券类型
    "Description": "示例因子：演示 DefModule 框架用法，含行情因子",

    # ---- 可选 ----
    "Author": "示例作者",
    "MaxLookBack": 365 * 2,                      # 最大回溯天数
    "Tags": ["示例", "教学", "行情"],

    # ---- 依赖声明 ----
    # FactorDeps: 声明需要哪些表的哪些因子，框架自动注入到 fdi.Factors
    "FactorDeps": {},

    # DBDeps: 声明直接访问的因子库，框架校验存在性
    "DBDeps": {"BSDB": "基于 BaoStock 的因子库，提供行情和基本信息等数据"},

    "DefScriptPath": __file__,
}


# ============================================================
# defFactor — 因子定义入口
# ============================================================
def defFactor(fdi: DefInput) -> List[Factor]:
    """标准签名：接收 DefInput，返回 List[Factor]

    框架在调用前已完成:
    1. 递归解析 FactorDeps 依赖链
    2. 将依赖因子注入到 fdi.Factors
    3. 校验 DBDeps 中声明的库是否在 fdi.FDB 中存在
    """
    Factors = []

    # ---- 获取数据库连接 ----
    BSDB = fdi.FDB["BSDB"]

    # ============================================================
    # 示例 1：简单因子 —— 从单表读取 + 重命名
    # ============================================================
    FT = BSDB.getTable("A股K线数据", args={"LookBack": 0})
    Factors.append(FT.getFactor("close"))
    Factors.append(FT.getFactor("open"))
    Factors.append(FT.getFactor("high"))
    Factors.append(FT.getFactor("low"))
    Factors.append(rename(FT.getFactor("preclose"), factor_name="pre_close"))

    return Factors
