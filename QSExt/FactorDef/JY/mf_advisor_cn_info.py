# -*- coding: utf-8 -*-
"""基金公司基本信息"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


# args 应该包含的参数
# JYDB: 聚源因子库对象
def defFactor(args={}, debug=False):
    Factors = []

    JYDB = args["JYDB"]

    FT = JYDB.getTable("公募基金管理人概况")
    Factors.append(FT.getFactor("基金管理人名称", new_name="name"))
    Factors.append(FT.getFactor("基金管理人简称", new_name="abbr"))
    Factors.append(fd.strftime(FT.getFactor("成立日期"), "%Y-%m-%d", factor_name="establishment_date"))
    Factors.append(fd.strftime(FT.getFactor("存续截至日"), "%Y-%m-%d", factor_name="maturity_date"))
    Factors.append(FT.getFactor("总经理", new_name="ceo"))
    Factors.append(FT.getFactor("组织形式_R", new_name="organization_form"))
    Factors.append(FT.getFactor("注册资本(元)", new_name="registered_capital"))
    Factors.append(FT.getFactor("注册地址", new_name="registered_address"))
    Factors.append(FT.getFactor("所属地区_R", new_name="region"))
    Factors.append(FT.getFactor("注册登记代码", new_name="ta_code"))
    Factors.append(FT.getFactor("证监会标识码", new_name="csrc_code"))
    Factors.append(FT.getFactor("公司网址", new_name="web_site"))
    Factors.append(FT.getFactor("背景介绍", new_name="background"))
    
    IDs = FT.getID()
    
    UpdateArgs = {
        "因子表": "mf_advisor_cn_info",
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": IDs
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