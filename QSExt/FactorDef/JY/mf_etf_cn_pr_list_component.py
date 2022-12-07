# -*- coding: utf-8 -*-
"""ETF 申赎清单成份明细"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"].connect()
    
    SQLStr = "SELECT CONCAT(t.SecuCode, '.OF') AS ID, t1.MS AS Market FROM secumain t LEFT JOIN ct_systemconst t1 ON (t.SecuMarket=t1.DM AND t1.LB=201) WHERE t.InnerCode IN (SELECT DISTINCT InnerCode FROM mf_etfprlist) ORDER BY ID"
    IDInfo = pd.read_sql(SQLStr, JYDB.Connection, index_col=["ID"]).iloc[:, 0]
    
    FT = JYDB.getTable("公募基金ETF申购赎回成份股信息(公募基金ID)")
    Factors.append(FT.getFactor("成份股内部编码_R", new_name="component_code"))
    Factors.append(FT.getFactor("股票数量(股)", new_name="volume"))
    Factors.append(FT.getFactor("现金替代标志_R", new_name="cash_substitute"))
    Factors.append(FT.getFactor("固定替代金额(元)", new_name="substitute_fixed"))
    
    UpdateArgs = {
        "因子表": "mf_etf_cn_pr_list_component",
        "因子库参数": {"检查写入值": True, "检查缺失容许": True},
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": sorted(IDInfo.index)
    }
    return Factors, UpdateArgs

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Args = {"JYDB": JYDB, "LDB": TDB, "industry_index_ids": sorted(pd.read_csv("../conf/citic_industry.csv", index_col=0, header=0, encoding="utf-8", encoding="python")["index_code"])}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
    IDs = UpdateArgs["IDs"]
    
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