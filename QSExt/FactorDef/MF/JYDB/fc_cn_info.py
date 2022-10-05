# -*- coding: utf-8 -*-
"""基金公司信息因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

Factors = []

JYDB = QS.FactorDB.JYDB()

FT = JYDB.getTable("公募基金管理人概况")
Factors.append(FT.getFactor("基金管理人名称", new_name="name"))
Factors.append(FT.getFactor("基金管理人简称", new_name="abbr"))
Factors.append(fd.strftime(FT.getFactor("成立日期"), "%Y-%m-%d", factor_name="establishment_date"))
Factors.append(FT.getFactor("总经理", new_name="ceo"))
Factors.append(FT.getFactor("公司网址", new_name="web_site"))
Factors.append(FT.getFactor("背景介绍", new_name="background"))


if __name__=="__main__":
    TDB = QS.FactorDB.SQLDB()
    TDB.connect()
    JYDB.connect()
    
    CFT = QS.FactorDB.CustomFT("fc_cn_info")
    CFT.addFactors(factor_list=Factors)
    
    IDs = FT.getID()
    
    StartDT, EndDT = dt.datetime(2019,9,1), dt.datetime(2019,9,30)
    
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=TDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler)
    
    TDB.disconnect()
    JYDB.disconnect()