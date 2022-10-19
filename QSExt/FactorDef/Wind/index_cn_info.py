# coding=utf-8
"""指数基本信息"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "index_cn_info",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "指数"
}

def NameFun(f, idt, iid, x, args):
    Data = pd.DataFrame(x[0])
    Data = Data.applymap(lambda x:str.replace(x,'指数','') if pd.notnull(x) else None)
    return Data.values

def defFactor(args={}):
    Factors = []

    WDB = args["WDB"]

    RawName = WDB.getTable("中国A股指数基本资料").getFactor("证券简称")
    Factors.append(QS.FactorDB.PointOperation("指数名称", [RawName], {"算子":NameFun, "运算ID":"多ID", "运算时点":"多时点", "数据类型":"string"}))

    return Factors

if __name__=="__main__":
    pass