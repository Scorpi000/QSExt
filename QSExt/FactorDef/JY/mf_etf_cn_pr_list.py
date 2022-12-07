# -*- coding: utf-8 -*-
"""ETF 申赎清单"""
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
    
    FT = JYDB.getTable("公募基金ETF申购赎回清单信息")
    Factors.append(FT.getFactor("一级市场基金代码", new_name="primary_market_code"))
    Factors.append(FT.getFactor("标的指数内部编码_R", new_name="target_index"))
    Factors.append(FT.getFactor("上一交易日期", new_name="pre_trading_day"))
    Factors.append(FT.getFactor("现金差额(元)", new_name="cash_balance"))
    Factors.append(FT.getFactor("最小申赎单位资产净值(元)", new_name="least_unit_nv"))
    Factors.append(FT.getFactor("基金份额净值(元)", new_name="share_nv"))
    Factors.append(FT.getFactor("IOPV收盘价", new_name="iopv"))
    Factors.append(FT.getFactor("预估现金部分(元)", new_name="cash_forecasted"))
    
    UpdateArgs = {
        "因子表": "mf_etf_cn_pr_list",
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