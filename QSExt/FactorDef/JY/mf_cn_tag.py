# -*- coding: utf-8 -*-
"""公募基金标签"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize
    

def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    FT = JYDB.getTable("公募基金风格变动", args={"多重映射": False, "只填起始日": False})
    # 偏股类基金
    # 规模
    Factors.append(FT.getFactor("风格项代码", args={"风格类代码": "1013"}, new_name="size_code"))
    Factors.append(FT.getFactor("风格项名称", args={"风格类代码": "1013"}, new_name="size"))
    # 投资风格
    Factors.append(FT.getFactor("风格项代码", args={"风格类代码": "1014"}, new_name="style_code"))
    Factors.append(FT.getFactor("风格项名称", args={"风格类代码": "1014"}, new_name="style"))
    # 操作风格
    Factors.append(FT.getFactor("风格项代码", args={"风格类代码": "1015"}, new_name="operation_type_code"))
    Factors.append(FT.getFactor("风格项名称", args={"风格类代码": "1015"}, new_name="operation_type"))
    
    # 偏债类基金
    # 券种配置
    Factors.append(FT.getFactor("风格项代码", args={"风格类代码": "1110"}, new_name="bond_type_code"))
    Factors.append(FT.getFactor("风格项名称", args={"风格类代码": "1110"}, new_name="bond_type"))
    # 久期分布
    Factors.append(FT.getFactor("风格项代码", args={"风格类代码": "1111"}, new_name="duration_code"))
    Factors.append(FT.getFactor("风格项名称", args={"风格类代码": "1111"}, new_name="duration"))
    
    UpdateArgs = {
        "因子表": "mf_cn_tag",
        "因子库参数": {"检查写入值": True},
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": "公募基金"
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
    
    Args = {"JYDB": JYDB, "LDB": TDB}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
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