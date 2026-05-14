# coding=utf-8
import datetime as dt

from QSExt.Factor.AKShareDB import AKShareDB


AKSDB = AKShareDB().connect()
print(AKSDB.TableNames)

# 交易日序列
DTs = AKSDB.getTradeDay(start_date=dt.datetime(2022, 1, 1), end_date=dt.datetime(2022, 1, 31))

# 股票证券代码
IDs = AKSDB.getStockID(is_current=False)    

#FT = AKSDB["历史行情数据-东财"]
#FT = AKSDB.getTable("历史行情数据-东财", args={"adjust": "hfq"})
FT = AKSDB.getTable("两市停复牌")

Data = FT.readData(factor_names=["停牌时间", "停牌原因"], ids=IDs, dts=[dt.datetime(2022, 10, 28), dt.datetime(2022, 10, 31)])
print(Data)

print("===")