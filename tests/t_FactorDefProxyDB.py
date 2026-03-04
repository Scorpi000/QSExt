# coding=utf-8
"""测试在因子定义中使用代理因子库"""
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Factor.JYDB import JYDB
from QuantStudio.Factor.HDF5DB import HDF5DB
from QuantStudio.Core.CalcEngine import Engine, ParallelEngine
from QuantStudio.Factor.Factor import FactorContext, FactorLocalContext, FactorInitData
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QuantStudio.Factor.FactorStorer import FactorStorer
from QSExt.FactorDef.FactorDefContent import FactorDefInput
from QSExt.FactorDef.JY.stock_cn_info import defFactor

SDB = JYDB().connect()
TDB = HDF5DB().connect()

EndDT = dt.datetime.combine(dt.date.today(), dt.time(0)) - dt.timedelta(1)
StartDT = EndDT - dt.timedelta(15)
DTs = SDB.getTradeDay(start_date=StartDT, end_date=EndDT)
MaxLookBack = 365 * 10
DTRuler = SDB.getTradeDay(start_date=StartDT - dt.timedelta(MaxLookBack), end_date=EndDT)

SectionIDs = IDs = ["000001.SZ", "000003.SZ", "301111.SZ", "600519.SH", "688981.SH", "920726.BJ"]# DEBUG

# FT = TDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
# Meta = FT.getFactorMetaData(key="SourceFactorID")
# print(Meta)

# 不使用代理
FDI = FactorDefInput(FDB={"JYDB": SDB}, DTs=DTs, IDs=IDs, SectionIDs=SectionIDs, DTRuler=DTRuler)
FactorDef = defFactor(fdi=FDI)
TargetF = FactorDef.getFactor("name")
print(TargetF.QSID)
print(TargetF.Descriptors)

# 使用代理
FDI = FactorDefInput(FDB={"JYDB": SDB}, DTs=DTs, IDs=IDs, SectionIDs=SectionIDs, DTRuler=DTRuler, ProxyDB=TDB)
FactorDef = defFactor(fdi=FDI)
TargetF = FactorDef.getFactor("name")
print(TargetF.QSID)
print(TargetF.Descriptors)

print("===")