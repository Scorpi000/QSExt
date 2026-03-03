# coding=utf-8
"""规模因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar


def defFactor(fdi: FactorDefInput):
    Factors = []

    JYDB = fdi.FDB["JYDB"]

    # ### 财务因子 ##########################################################################
    Asset = JYDB.getTable("资产负债表_新会计准则", args={"CalcType":"最新", "ReportDate":"所有"}).getFactor("资产总计")
    Sales_TTM = JYDB.getTable("利润分配表_新会计准则", args={"CalcType":"TTM", "ReportDate":"所有"}).getFactor("营业收入")

    # ### 企业管理因子 ##########################################################################
    # EmpNum = JYDB.getTable("A股员工人数变更", args={"DTField": "公告日期", "LookBack": np.inf}).getFactor("员工人数(人)")

    # FT = JYDB.getTable("中国A股日行情估值指标")
    # FloatStkNums = FT.getFactor("当日自由流通股本")

    ### 行情因子 #############################################################################
    StockDayBarDef = defStockDayBar(fdi=fdi)
    TotalCap = StockDayBarDef.getFactor(factor_name="total_cap", def_path="...")# 单位: 万元
    FloatCap = StockDayBarDef.getFactor(factor_name="float_cap", def_path="...")# 单位: 万元
    Close = StockDayBarDef.getFactor(factor_name="close", def_path="...")

    Factors.append(TotalCap)
    Factors.append(FloatCap)
    Factors.append(rename(Asset, factor_name="asset_lr"))
    Factors.append(rename(Sales_TTM, factor_name="revenue_ttm"))
    # Factors.append(rename(EmpNum, factor_name="emp_num"))

    log = fo.Log()
    Factors.append(log(TotalCap, factor_args={"Name": "ln_market_cap"}))
    Factors.append(log(FloatCap, factor_args={"Name": "ln_float_cap"}))
    Factors.append(log(Asset, factor_args={"Name": "ln_asset"}))
    Factors.append(log(Sales_TTM, factor_args={"Name": "ln_revenue_ttm"}))

    # FreeFloatCap = rename(FloatStkNums * Close, factor_name="free_float_cap")
    # Factors.append(FreeFloatCap)
    # Factors.append(log(FreeFloatCap, factor_args={"Name": "ln_free_float_cap"}))

    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_factor_size",
        MaxLookBack=max(365, StockDayBarDef.MaxLookBack),
        IDType="A股",
        Author="麦冬"
    )
