# coding=utf-8
import datetime as dt

from QSExt.Factor.DuckDB import DuckDB


PDDB = DuckDB(args={"ParquetDir": r"D:\Data\QSData\DataScrapy\Parquet"}).connect()
print(PDDB.TableNames)

FT = PDDB.getTable("stock_cn_minute_bar")
print(FT.FactorNames)

DTs = FT.getDateTime(start_dt=dt.datetime(2026, 6, 3), end_dt=dt.datetime(2026, 6, 5))
Data = FT.readData(factor_names=["close", "open"], ids=["000001.SZ"], dts=DTs)
print(Data.iloc[:, :, 0])