# -*- coding: utf-8 -*-
"""ETF 基金行情"""
import datetime as dt

import numpy as np
import pandas as pd
import cvxpy as cvx

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"].connect()
    
    FT = JYDB.getTable("公募基金ETF申购赎回清单信息")
    Factors.append(FT.getFactor("一级市场基金代码", new_name="primary_market_code"))
    TargetIndex = FT.getFactor("标的指数内部编码")
    Factors.append(FT.getFactor("标的指数内部编码_R", new_name="target_index"))
    Factors.append(FT.getFactor("IOPV收盘价", new_name="iopv"))
        
    FT = JYDB.getTable("公募基金日行情表")
    PreClose = FT.getFactor("昨收盘(元)", new_name="pre_close")
    Factors.append(PreClose)
    Factors.append(FT.getFactor("今开盘(元)", new_name="open"))
    Factors.append(FT.getFactor("最高价(元)", new_name="high"))
    Factors.append(FT.getFactor("最低价(元)", new_name="low"))
    Close = FT.getFactor("收盘价(元)", new_name="close")
    Factors.append(Close)
    Amount, Volume = FT.getFactor("成交金额(元)", new_name="amount"), FT.getFactor("成交量(股)")
    Factors.append(Factorize(Volume / 10000, factor_name="volume"))
    Factors.append(Amount)
    Factors.append(Factorize(Amount / Volume, factor_name="avg"))
    Factors.append(Factorize(Close / PreClose - 1, factor_name="chg"))
    
    FT = JYDB.getTable("公募基金行情历史表现")# 数据不全
    Factors.append(Factorize(FT.getFactor("换手率(%)") / 100, factor_name="turnover_rate"))
    Factors.append(FT.getFactor("贴水(元)", new_name="discount"))
    Factors.append(Factorize(FT.getFactor("贴水率(%)") / 100, factor_name="discount_ratio"))
    
    FT = JYDB.getTable("公募基金份额变动", args={"统计区间": "996"})
    Factors.append(FT.getFactor("期末份额(份)", new_name="total_shares"))
    Factors.append(FT.getFactor("流通份额(份)", new_name="float_shares"))
    
    # ETF 所属市场
    SQLStr = "SELECT CONCAT(t.SecuCode, '.OF') AS ID, t1.MS AS Market FROM secumain t LEFT JOIN ct_systemconst t1 ON (t.SecuMarket=t1.DM AND t1.LB=201) WHERE t.InnerCode IN (SELECT DISTINCT InnerCode FROM mf_etfprlist) ORDER BY ID"
    IDInfo = pd.read_sql(SQLStr, JYDB.Connection, index_col=["ID"]).iloc[:, 0]
    Factors.append(QS.FactorDB.DataFactor(name="market", data=IDInfo))
    
    # ETF 成份所属市场
    SQLStr = "SELECT t.IndexCode AS ID, t1.MS AS Market FROM lc_indexbasicinfo t LEFT JOIN ct_systemconst t1 ON (t.SecuMarket=t1.DM AND t1.LB=2015) WHERE t.IndexCode IN (SELECT DISTINCT TargetIndexInnerCode FROM mf_etfprlist WHERE TargetIndexInnerCode IS NOT NULL)"
    IndexInfo = pd.read_sql(SQLStr, JYDB.Connection, index_col=["ID"]).iloc[:, 0]
    Factors.append(fd.map_value(TargetIndex, IndexInfo, data_type="string", factor_name="component_market"))
    
    UpdateArgs = {
        "因子表": "mf_etf_cn_day_bar",
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