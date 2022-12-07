# coding=utf-8
"""规模因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_factor_size",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def defFactor(args={}):
    Factors = []

    JYDB = args["JYDB"]
    LDB = args["LDB"]

    # ### 财务因子 ##########################################################################
    Asset = JYDB.getTable("资产负债表_新会计准则").getFactor("资产总计", args={"计算方法":"最新", "报告期":"所有"})
    Sales_TTM = JYDB.getTable("利润分配表_新会计准则").getFactor("营业收入", args={"计算方法":"TTM", "报告期":"所有"})

    # ### 企业管理因子 ##########################################################################
    #Num_Emp = JYDB.getTable("A股员工人数变更").getFactor("员工人数(人)", args={"时点字段":"公告日期", "回溯天数":np.inf})

    #FT = JYDB.getTable("中国A股日行情估值指标")
    #Float_Stk_Nums = FT.getFactor("当日自由流通股本", new_name="自由流通股本")

    # ### 行情因子 #############################################################################
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    FloatCap = FT.getFactor("float_cap")# 万元
    TotalCap = FT.getFactor("total_cap")# 万元
    Close = FT.getFactor("close")

    Factors.append(TotalCap)
    Factors.append(FloatCap)
    Factors.append(Factorize(Asset, "asset_lr"))
    Factors.append(Factorize(Sales_TTM, "revenue_ttm"))
    #Factors.append(Factorize(Num_Emp,"Num_Emp"))

    Factors.append(fd.log(TotalCap, factor_name="ln_market_cap"))
    Factors.append(fd.log(FloatCap, factor_name="ln_float_cap"))
    Factors.append(fd.log(Asset, factor_name="ln_asset"))
    Factors.append(fd.log(Sales_TTM, factor_name="ln_revenue_ttm"))

    #Free_FloatCap = Factorize(Float_Stk_Nums * Close, "Free_FloatCap")
    #FreeFloatCap_Ln = fd.log(Free_FloatCap, factor_name="FreeFloatCap_Ln")
    #Factors.append(Free_FloatCap)
    #Factors.append(FreeFloatCap_Ln)

    return Factors

if __name__=="__main__":
    pass