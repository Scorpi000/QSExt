# -*- coding: utf-8 -*-
import datetime as dt

from QSExt.Factor.TinySoftDB import TinySoftDB

FDB = TinySoftDB(args={}).connect()

# 测试时点方法
# DTs = FDB.getTradeDay(start_date=dt.datetime(2025, 1, 1), end_date=dt.datetime(2025, 12, 31))
# print(len(DTs), DTs[:10])

# 测试 ID 方法
# # 股票
# IDs = FDB.getStockID(is_current=False)
# print(len(IDs), IDs[:10])

# # 期货
# IDs = FDB.getFutureID(future_code=None, is_current=False)
# print(len(IDs), IDs[:10])

# # 期权
# IDs = FDB.getOptionID(option_code="SH510050", is_current=False)
# print(len(IDs), IDs[:10])

print(FDB._OptionID2InnerCode(["510050C2512M02500"]))

print("===")