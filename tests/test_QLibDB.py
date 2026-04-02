# coding=utf-8
import re
import time
import datetime as dt

import numpy as np
import pandas as pd
import qlib

from QSExt.Factor.QLibDB import QLibDB

# 测试 init 时间
# StartT = time.perf_counter()
# qlib.init(provider_uri='~/.qlib/qlib_data/cn_data')
# print(time.perf_counter() - StartT)

# StartT = time.perf_counter()
# qlib.init(provider_uri='~/.qlib/qlib_data/cn_data')
# print(time.perf_counter() - StartT)

if __name__=="__main__":
    FDB = QLibDB().connect()
    print(FDB.Args)
    print(FDB.TableNames)

    FT = FDB.getTable("cn_data")
    print(FT.FactorNames)

    # DataType = FT.getFactorMetaData(key="DataType")

    DTs = FT.getDateTime(start_dt=dt.datetime(2026, 3, 1), end_dt=dt.datetime(2026, 3, 15))
    print(DTs)

    IDs = FT.getID(idt=dt.datetime(2026, 3, 31))
    print(IDs[:5])

    IDs = ["000001.SZ", "600000.SH"]
    DTs = [dt.datetime(2026, 3, 31), dt.datetime(2026, 4, 1)]
    Data = FT.readData(factor_names=["$close"], ids=IDs, dts=DTs)
    print(Data.iloc[0])

    F = FT.getFactor(ifactor_name="($open - $close) / $close")
    IDs = ["000001.SZ", "600000.SH"]
    DTs = [dt.datetime(2026, 3, 31), dt.datetime(2026, 4, 1)]
    Data = F.readData(ids=IDs, dts=DTs)
    print(Data)

    df = pd.DataFrame(
        [(None, "aha"), ("中文", "aaa")],
        index=[dt.datetime(2022, 1, 1), dt.datetime(2022, 1, 2)],
        columns=["000001.SZ", "000002.SZ"],
        dtype="O"
    )
    FDB.writeFactorData(df, "test_table", "factor1", data_type="string")

    # FT = FDB.getTable("test_table")
    FT = FDB["test_table"]
    # Data = FT.readData(FT.FactorNames, ids=None, dts=None)
    F = FT["factor1"]
    print(F)
    Data = FT[FT.FactorNames]
    print(Data)
    Data = FT[FT.FactorNames, [dt.datetime(2022, 1, 1)]]
    print(Data)
    Data = FT[FT.FactorNames, dt.datetime(2022, 1, 1)]
    print(Data)

    Data = F[[dt.datetime(2022, 1, 1)]]
    print(Data)
    Data = F[:, "000001.SZ"]
    print(Data)
    Data = F[dt.datetime(2022, 1, 1), "000002.SZ"]
    print(Data)

    FDB.deleteTable("test_table")


    print("===")