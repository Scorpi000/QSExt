# coding=utf-8
import re
import time
import datetime as dt

import numpy as np
import pandas as pd
import qlib

from QuantStudio.Core.QSObject import Panel
from QSExt.Factor.QLibDB import QLibDB

# 测试 init 时间
# StartT = time.perf_counter()
# qlib.init(provider_uri='~/.qlib/qlib_data/cn_data')
# print(time.perf_counter() - StartT)

# StartT = time.perf_counter()
# qlib.init(provider_uri='~/.qlib/qlib_data/cn_data')
# print(time.perf_counter() - StartT)

# 查看原始数据
# with open(r"D:\Data\QLib\cn_data\features\bj430017\close.day.bin", mode="rb") as fp:
#     a = np.fromfile(fp, dtype="<f")
#     dt_start_idx, a = int(a[0]), a[1:]
# print(dt_start_idx)
# print(a.shape)

if __name__=="__main__":
    FDB = QLibDB().connect()
    print(FDB.Args)
    print(FDB.TableNames)

    FT = FDB.getTable("cn_data")
    print(FT.FactorNames)

    DataType = FT.getFactorMetaData(key="DataType")
    print(DataType)
    
    # DTs = FT.getDateTime(start_dt=dt.datetime(2026, 3, 1), end_dt=dt.datetime(2026, 3, 15))
    # print(DTs)

    # IDs = FT.getID(idt=dt.datetime(2026, 3, 31))
    # print(IDs[:5])

    # # 因子表数据读取
    # IDs = ["000001.SZ", "600000.SH"]
    # DTs = [dt.datetime(2026, 3, 31), dt.datetime(2026, 4, 1)]
    # Data = FT.readData(factor_names=["$close"], ids=IDs, dts=DTs)
    # print(Data.iloc[0])

    # # 因子数据读取
    # F = FT.getFactor(ifactor_name="($open - $close) / $close")
    # IDs = ["000001.SZ", "600000.SH"]
    # DTs = [dt.datetime(2026, 3, 31), dt.datetime(2026, 4, 1)]
    # Data = F.readData(ids=IDs, dts=DTs)
    # print(Data)

    # # 数据写入
    # np.random.seed(0)
    # nDT, nID = 5, 2
    # DTs = [dt.datetime(2025, 1, 1) + dt.timedelta(i) for i in range(nDT)]
    # IDs = [str(i).zfill(6)+".SZ" for i in range(1, nID+1)]
    # Data = Panel({
    #     "$close": pd.DataFrame(np.random.randn(5, 2), index=DTs, columns=IDs),
    #     "$open": pd.DataFrame(np.random.randn(5, 2), index=DTs, columns=IDs)
    # })
    # print(Data["$close"])
    # FDB.writeData(data=Data, table_name="test_table", if_exists="update")
    # FT = FDB.getTable("test_table")
    # Data = FT.readData(factor_names=["$close"], ids=IDs, dts=DTs)
    # print(Data.iloc[0])

    # # 数据更新
    # NewDTs = DTs[1:] + [dt.datetime(2025, 1, 1) + dt.timedelta(nDT)]
    # NewIDs = IDs[1:] + [str(nID+1).zfill(6)+".SZ"]
    # Data = Panel({
    #     "$close": pd.DataFrame(np.random.randn(5, 2), index=NewDTs, columns=NewIDs),
    #     "$open": pd.DataFrame(np.random.randn(5, 2), index=NewDTs, columns=NewIDs)
    # })
    # print(Data["$close"])
    # FDB.writeData(data=Data, table_name="test_table", if_exists="update")

    # FT = FDB.getTable("test_table")
    # Data = FT.readData(factor_names=["$close"], ids=sorted(set(IDs + NewIDs)), dts=sorted(set(DTs + NewDTs)))
    # print(Data.iloc[0])

    FDB.deleteTable("test_table")

    print("===")