# coding=utf-8
"""RV 因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

UpdateArgs = {
    "因子表": "stock_cn_multi_factor_rv",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def defFactor(args={}):
    Factors = []

    WDB = args["WDB"]
    LDB = args["LDB"]

    FT = LDB.getTable("stock_cn_info")
    IsListed = FT.getFactor("if_listed")
    FT = LDB.getTable("stock_cn_industry")
    ZXIndustry = FT.getFactor("citic_level1")
    FT = LDB.getTable("stock_cn_day_bar_adj_backward_")
    AdjClose = FT.getFactor("close")

    Beta = LDB.getTable("stock_cn_factor_barra").getFactor("Beta")
    LnFloatCap = LDB.getTable("stock_cn_factor_size").getFactor("FloatCap_Ln")
    Rating = LDB.getTable("stock_cn_factor_sentiment").getFactor("Rating")
    EP_Fwd12M = LDB.getTable("stock_cn_factor_value").getFactor("EP_Fwd12M")

    Mask = (IsListed==1) & (fd.notnull(ZXIndustry)) & (fd.notnull(AdjClose))

    BetaStd = fd.standardizeQuantile(f=Beta, mask=Mask)
    LnFloatCapStd = fd.standardizeQuantile(f=LnFloatCap, mask=Mask)
    RatingStd = fd.standardizeQuantile(f=Rating, mask=Mask, ascending=False)
    EP_Fwd12MStd = fd.standardizeQuantile(f=EP_Fwd12M, mask=Mask)

    Rating_adj = fd.orthogonalize(Y=RatingStd, X=[BetaStd,LnFloatCapStd], mask=Mask, dummy_data=ZXIndustry)
    Factors.append(Factorize(Rating_adj, "Rating_adj"))
    EP_Fwd12M_adj = fd.orthogonalize(Y=EP_Fwd12MStd, X=[BetaStd,LnFloatCapStd], mask=Mask, dummy_data=ZXIndustry)
    Factors.append(Factorize(EP_Fwd12M_adj,"EP_Fwd12M_adj"))
    Factors.append(Factorize((0.5*Rating_adj + 0.5*EP_Fwd12M_adj), "RV"))

    return Factors


if __name__ == "__main__":
    pass