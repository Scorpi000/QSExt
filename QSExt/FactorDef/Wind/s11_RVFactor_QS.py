#!/usr/bin/env python
# coding: utf-8


"""RV因子定义"""
import datetime as dt
import UpdateDate
import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

Factors = []

WDB = QS.FactorDB.WindDB2()
HDB = QS.FactorDB.HDF5DB()
HDB.connect()

FT = HDB.getTable("ElementaryFactor")


IsListed = FT.getFactor("是否在市")
ZXIndustry = FT.getFactor("中信行业")
AdjClose = FT.getFactor("复权收盘价")

Beta = HDB.getTable("BarraFactor").getFactor("Beta")
LnFloatCap = HDB.getTable("StyleAlternativeFactor").getFactor("FloatCap_Ln")
Rating = HDB.getTable("StyleSentimentFactor").getFactor("Rating")
EP_Fwd12M = HDB.getTable("StyleValueFactor").getFactor("EP_Fwd12M")


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


if __name__ == "__main__":
    WDB.connect()
    CFT = QS.FactorDB.CustomFT("RVFactor")
    CFT.addFactors(factor_list=Factors)

    IDs = WDB.getStockID(index_id="全体A股", is_current=False)
    # IDs = ["000001.SZ", "000003.SZ", "603297.SH"]# debug

    # if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2018, 8, 31, 23, 59, 59, 999999)
    # else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    # EndDT = dt.datetime(2018, 10, 31, 23, 59, 59, 999999)
    StartDT, EndDT = UpdateDate.StartDT, UpdateDate.EndDT

    DTs = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT - dt.timedelta(365000), end_dt=EndDT)

    TargetTable = "RVFactor"
    # TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable,
                  if_exists="update", dt_ruler=DTRuler)

    HDB.disconnect()
    WDB.disconnect()





