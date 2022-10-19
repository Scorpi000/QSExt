# -*- coding: utf-8 -*-
"""交易所债券行情"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "bond_cn_exchange_day_bar",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def DayReturnFun(f, idt, iid, x, args):
    Denominator = x[1][0] + x[2][0]
    Denominator[Denominator==0] = np.nan
    Interest = x[3][0]/10
    Interest[np.isnan(Interest)] = 0
    Principal = x[4][0]/10
    Principal[np.isnan(Principal)] = 0
    Numerator = x[0][0] + x[2][1] + Interest + Principal
    return Numerator / Denominator - 1

def defFactor(args={}):
    Factors = []

    WDB = args["WDB"]

    # 市场行情因子
    FT = WDB.getTable("中国债券交易所债券行情")
    Factors.append(FT.getFactor("开盘价(元)", new_name="open"))
    Factors.append(FT.getFactor("最高价(元)", new_name="high"))
    Factors.append(FT.getFactor("最低价(元)", new_name="low"))
    Close = FT.getFactor("收盘价(元)", new_name="close")
    Factors.append(Close)
    PreClose = FT.getFactor("昨收盘价(元)", new_name="pre_close")
    Factors.append(PreClose)
    Factors.append(FT.getFactor("成交量(手)", new_name="volume"))
    Factors.append(Factorize(FT.getFactor("成交金额(千元)") * 1000, factor_name="amount"))
    Factors.append(FT.getFactor("均价(VWAP)", new_name="avg_price"))

    FT = WDB.getTable("中国债券应计利息")
    AI = FT.getFactor("应计利息")
    Factors.append(AI)
    Factors.append(FT.getFactor("已计息时间"))

    FT = WDB.getTable("中国债券付息和兑付")
    Factors.append(QS.FactorDB.Factorize(FT.getFactor("每手付息数", args={"日期字段":"债权登记日"}) / 10, factor_name="付息"))
    Factors.append(QS.FactorDB.Factorize(FT.getFactor("每手兑付本金数", args={"日期字段":"债权登记日"}) / 10, factor_name="兑付本金"))
    Factors.append(QS.FactorDB.Factorize(FT.getFactor("税后每手付息数", args={"日期字段":"债权登记日"}) / 10, factor_name="税后付息"))
    Factors.append(FT.getFactor("除息日", args={"日期字段":"债权登记日"}))
    Factors.append(FT.getFactor("付息日", args={"日期字段":"债权登记日"}))

    Interest = FT.getFactor("每手付息数", args={"日期字段":"除息日"})
    Principal = FT.getFactor("每手兑付本金数", args={"日期字段":"除息日"})
    Factors.append(QS.FactorDB.TimeOperation("日收益率", [Close, PreClose, AI, Interest, Principal], {"算子":DayReturnFun, "回溯期数":[1-1, 1-1, 2-1, 1-1, 1-1], "运算ID":"多ID"}))

    return Factors

if __name__=="__main__":
    SQLStr = "SELECT DISTINCT s_info_windcode FROM CBondDescription WHERE b_info_issuertype='财政部' AND s_info_exchmarket IN ('SSE', 'SZSE') ORDER BY s_info_windcode"
    IDs = np.array(WDB.fetchall(SQLStr)).flatten().tolist()# 所有的交易所交易国债
    #IDs = ["010303.SH"]# debug