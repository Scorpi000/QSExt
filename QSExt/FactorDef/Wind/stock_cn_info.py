# -*- coding: utf-8 -*-
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_info",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def ListDayNumFun(f, idt, iid, x, args):
    ListDate = np.vectorize(lambda x: dt.datetime.strptime(x, "%Y%m%d"))(x[0])
    DTs = np.array([idt]).T
    ListDayNum = np.vectorize(lambda x: x.days)(DTs - ListDate).astype("float")
    ListDayNum[ListDayNum<0] = np.nan
    return ListDayNum + 1

def ifListed(f, idt, iid, x, args):
    ListDate, DelistDate = x
    Listed = np.zeros_like(ListDate)
    DelistDate[pd.isnull(DelistDate)] = "99999999"
    DTs = np.array([[iDT.strftime("%Y%m%d") for iDT in idt]]).T
    Listed[(ListDate<=DTs) & (DelistDate>DTs)] = 1
    return Listed

def defFactor(args={}):
    Factors = []
    
    WDB = args["WDB"]
    
    FT = WDB.getTable("中国A股基本资料")
    ListDate = FT.getFactor("上市日期")
    Factors.append(fd.applymap(ListDate, func=lambda x: x[:4]+"-"+x[4:6]+"-"+x[6:], data_type="string", factor_name="listed_date"))
    DelistDate = FT.getFactor("退市日期")
    
    Factors.append(QS.FactorDB.PointOperation("if_listed", [ListDate, DelistDate], {"算子":ifListed, "运算时点":"多时点", "运算ID":"多ID"}))
    Factors.append(QS.FactorDB.PointOperation("listed_days", [ListDate], {"算子":ListDayNumFun, "运算时点":"多时点", "运算ID":"多ID"}))
    Factors.append(WDB.getTable("中国A股特别处理").getFactor("特别处理类型", new_name="st"))
    
    return Factors


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    WDB = QS.FactorDB.WindDB2()
    WDB.connect()
    
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = WDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = WDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = WDB.getStockID(is_current=False)
    
    Args = {"WDB": WDB}
    Factors = defFactor(args=Args)
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTs)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
        factor_db=TDB, table_name=TargetTable,
        if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    WDB.disconnect()