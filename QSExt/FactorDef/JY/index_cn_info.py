# -*- coding: utf-8 -*-
"""指数特征因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# args 应该包含的参数
# JYDB: 聚源因子库对象
# id_info_file: ID 配置信息文件地址
def defFactor(args={}, debug=False):
    Factors = []
    JYDB = args["JYDB"]
    
    FT = JYDB.getTable("指数证券主表")
    Factors.append(FT.getFactor("中文名称", new_name="name"))
    Factors.append(FT.getFactor("证券简称", new_name="abbr"))
    #Factors.append(FT.getFactor("拼音证券简称", new_name="pinyin_abbr"))
    
    FT = JYDB.getTable("指数基本情况")
    Factors.append(FT.getFactor("指数类别_R", new_name="index_type"))
    Factors.append(fd.strftime(FT.getFactor("基日"), "%Y-%m-%d", factor_name="base_date"))
    Factors.append(FT.getFactor("基点(点)", new_name="base_point"))
    Factors.append(FT.getFactor("成份证券类别_R", new_name="component_type"))
    Factors.append(FT.getFactor("成份证券市场_R", new_name="component_market"))
    Factors.append(FT.getFactor("成份证券数量", new_name="component_num"))
    Factors.append(FT.getFactor("成份证券调整周期_R", new_name="component_adj_period"))
    Factors.append(FT.getFactor("指数计算类别_R", new_name="index_price_type"))
    Factors.append(FT.getFactor("指数设计类别_R", new_name="design_type"))
    Factors.append(FT.getFactor("对应主指数内码_R", new_name="main_code"))
    Factors.append(FT.getFactor("与主指数关系_R", new_name="main_relationship"))
    Factors.append(FT.getFactor("行业标准_R", new_name="industry_standard"))
    Factors.append(FT.getFactor("加权方式_R", new_name="weight_method"))
    
    # 生成指数 ID
    if isinstance(args["id_info_file"], str):
        IDs = sorted(pd.read_csv(args["id_info_file"], index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
    else:
        IDs = []
        for iInfoFile in args["id_info_file"]:
            IDs += pd.read_csv(iInfoFile, index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0].tolist()
        IDs = sorted(set(IDs))
    
    UpdateArgs = {"因子表": "index_cn_info",
                  "默认起始日": dt.datetime(2002,1,1),
                  "最长回溯期": 3650,
                  "IDs": IDs}
    return Factors, UpdateArgs

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_FactorTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Args = {"JYDB": JYDB, "id_info_file": [r"../conf/index/IndexIDs_cn.csv", r"../conf/index/IndexIDs_IndexMF.csv", r"../conf/index/IndexIDs_ETF.csv"]}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)

    StartDT, EndDT = dt.datetime(2000, 1, 1), dt.datetime(2000, 1, 1)
    #StartDT, EndDT = dt.datetime(2021, 7, 1), dt.datetime(2021, 7, 10)
    #DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTs = QS.Tools.DateTime.getDateTimeSeries(StartDT, EndDT, timedelta=dt.timedelta(1))# 自然日
    #DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    DTRuler = QS.Tools.DateTime.getDateTimeSeries(StartDT-dt.timedelta(365), EndDT, timedelta=dt.timedelta(1))# 自然日
    DTs = DTs[-1:]
    
    IDs = UpdateArgs["IDs"]

    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTRuler)
    CFT.setID(IDs)

    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
                  factor_db=TDB, table_name=TargetTable,
                  if_exists="update", subprocess_num=0)

    TDB.disconnect()
    JYDB.disconnect()