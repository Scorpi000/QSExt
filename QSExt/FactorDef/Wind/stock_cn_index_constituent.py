# coding=utf-8
"""指数成份及其权重因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_index_constituent",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def defFactor(args={}):
    Factors = []

    WDB = args["WDB"]

    # 指数成份
    FT = WDB.getTable("中国A股指数成份股")
    Factors.append(FT.getFactor("000016.SH", new_name="sh50"))
    Factors.append(FT.getFactor("399330.SZ", new_name="sz100"))
    Factors.append(FT.getFactor("000903.SH", new_name="zz100"))
    Factors.append(FT.getFactor("000300.SH", new_name="hs300"))
    Factors.append(FT.getFactor("000905.SH", new_name="zz500"))
    Factors.append(FT.getFactor("000906.SH", new_name="zz800"))
    Factors.append(FT.getFactor("000852.SH", new_name="zz1000"))
    Factors.append(FT.getFactor("399311.SZ", new_name="gz1000"))
    Factors.append(FT.getFactor("399303.SZ", new_name="gz2000"))
    Factors.append(FT.getFactor("399313.SZ", new_name="jc100"))

    # 指数成份权重
    FT = WDB.getTable("沪深300免费指数权重")
    Factors.append(Factorize(FT.getFactor("权重", args={"指数Wind代码":"000016.SH"}) / 100, factor_name="sh50_weight"))
    Factors.append(Factorize(FT.getFactor("权重", args={"指数Wind代码":"399330.SZ"}) / 100, factor_name="sz100_weight"))
    Factors.append(Factorize(FT.getFactor("权重", args={"指数Wind代码":"000903.SH"}) / 100, factor_name="zz100_weight"))
    Factors.append(Factorize(FT.getFactor("权重", args={"指数Wind代码":"000905.SH"}) / 100, factor_name="zz500_weight"))
    Factors.append(Factorize(FT.getFactor("权重", args={"指数Wind代码":"000906.SH"}) / 100, factor_name="zz800_weight"))
    Factors.append(Factorize(FT.getFactor("权重", args={"指数Wind代码":"000852.SH"}) / 100, factor_name="zz1000_weight"))
    Factors.append(Factorize(FT.getFactor("权重", args={"指数Wind代码":"399311.SZ"}) / 100, factor_name="gz1000_weight"))
    Factors.append(Factorize(FT.getFactor("权重", args={"指数Wind代码":"399300.SZ"}) / 100, factor_name="hs300_weight"))

    return Factors
    
if __name__=="__main__":
    pass