# -*- coding: utf-8 -*-
"""A股基本信息"""
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

def ifListed(f, idt, iid, x, args):
    ListDate, StatusChg = x
    Listed = np.zeros(ListDate.shape)
    DTs = np.array([idt]).T.repeat(ListDate.shape[1], axis=1).astype("datetime64")
    Listed[ListDate <= DTs] = 1
    StatusChg[StatusChg != 4] = np.nan
    StatusChg = pd.DataFrame(StatusChg).fillna(method="pad").values
    Listed[StatusChg ==4 ] = 0
    return Listed

def ListDayNumFun(f, idt, iid, x, args):
    ListDate = x[0].astype("datetime64")
    DTs = np.array([idt], dtype="datetime64").T.repeat(ListDate.shape[1], axis=1)
    ListDayNum = (DTs - ListDate).astype("timedelta64[D]") / np.timedelta64(1, "D")
    ListDayNum[ListDayNum < 0] = np.nan
    return ListDayNum + 1

def STFun(f, idt, iid, x, args):
    STType = x[0]
    ST = np.full(shape=STType.shape, fill_value=None, dtype="O")
    ST[(STType==1) | (STType==7)] = "ST"
    ST[(STType==5) | (STType==8)] = "*ST"
    ST[STType==3] = "PT"
    ST[STType==9] = "退市整理期"
    ST[STType==10] = "高风险警示"
    return ST

# args:
# JYDB: 聚源因子库对象
def defFactor(args={}):
    Factors = []
    
    JYDB = args["JYDB"]
    
    # 证券特征
    FT = JYDB.getTable("A股证券主表")
    Factors.append(FT.getFactor("中文名称", new_name="name"))
    Factors.append(FT.getFactor("证券简称", new_name="abbr"))
    Factors.append(FT.getFactor("拼音证券简称", new_name="pinyin_abbr"))
    Factors.append(FT.getFactor("上市板块_R", new_name="listed_sector"))
    ListDate = FT.getFactor("上市日期")
    Factors.append(fd.strftime(ListDate, "%Y-%m-%d", factor_name="listed_date"))
    ListDayNum = QS.FactorDB.PointOperation("listed_days", [ListDate], sys_args={"算子": ListDayNumFun, "运算时点": "多时点", "运算ID": "多ID"})
    Factors.append(ListDayNum)
    
    StatusChg = JYDB.getTable("上市状态更改").getFactor("变更类型", args={"回溯天数", np.inf})
    IfListed = QS.FactorDB.PointOperation("if_listed", [ListDate, StatusChg], sys_args={"算子": ifListed, "运算时点": "多时点", "运算ID": "多ID"})
    Factors.append(IfListed)
    
    ST = JYDB.getTable("证券特别处理").getFactor("特别处理(或撤销)类别", args={"回溯天数": np.inf})
    ST = QS.FactorDB.PointOperation("st", [ST], sys_args={"算子": STFun, "运算时点": "多时点", "运算ID": "多ID"})
    Factors.append(ST)
    
    FT = JYDB.getTable("公司概况")
    Factors.append(FT.getFactor("省份_R", new_name="province"))
    Factors.append(FT.getFactor("地区代码_R", new_name="city"))
    
    return Factors


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB()
    JYDB.connect()
    
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = JYDB.getStockID()
    
    Args = {"JYDB": JYDB}
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
    JYDB.disconnect()