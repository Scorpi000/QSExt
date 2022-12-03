# -*- coding: utf-8 -*-
"""公募基金除权"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def ExRightFun(f, idt, iid, x, args):
    ShareAdj = np.full(shape=(x[0].shape[1],), fill_value=np.nan)
    Mask = (x[0][0]!=x[0][1])
    ShareAdj[Mask] = (x[0][1] / x[0][0])[Mask]
    return ShareAdj
    
    
# args 应该包含的参数
# JYDB: 聚源因子库对象
def defFactor(args={}, debug=False):
    Factors = []

    JYDB = args["JYDB"]

    FT = JYDB.getTable("公募基金比例复权因子", args={"回溯天数": np.inf})
    AdjFactor = FT.getFactor("增长率比例复权因子")
    AdjFactor = fd.where(AdjFactor, fd.notnull(AdjFactor), 1.0)
    
    ShareAdj = QS.FactorDB.TimeOperation(
        "share_adj",
        [AdjFactor],
        sys_args={
            "算子": ExRightFun,
            "回溯期数": [1],
            "运算时点": "单时点",
            "运算ID": "多ID",
            "数据类型": "double"
        }
    )
    Factors.append(ShareAdj)
    
                     
    UpdateArgs = {
        "因子表": "mf_cn_ex_right",
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": "公募基金"
    }

    return (Factors, UpdateArgs)


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Args = {"JYDB": JYDB}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    #DTs = DTs[-1:]# 只保留最新数据
    
    #IDs = sorted(pd.read_csv("."+os.sep+"MFIDs.csv", index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
    IDs = JYDB.getMutualFundID(is_current=False)
    #IDs = ["159956.OF"]
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTRuler)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, 
                  factor_db=TDB, table_name=TargetTable, 
                  if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    JYDB.disconnect()