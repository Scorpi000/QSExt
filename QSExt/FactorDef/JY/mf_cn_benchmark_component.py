# -*- coding: utf-8 -*-
"""公募基金基准成份"""
import os
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


# 将日期因子转换成字符串
def adjustDT(f, idt, iid, x, args):
    if isinstance(x[0], list):
        return [iDT.strftime("%Y-%m-%d") for iDT in x[0]]
    else:
        return x[0]

def calc_weight(f, idt, iid, x, args):
    if isinstance(x[0], list) and isinstance(x[1], list):
        return np.nanmean(np.array(x, dtype=np.float), axis=0).tolist()
    else:
        return None

    # args 应该包含的参数
    # JYDB: 聚源因子库对象
def defFactor(args={}, debug=False):
    Factors = []

    JYDB = args["JYDB"]

    FT = JYDB.getTable("公募基金投资目标比例", args={"投资标的": "90", "只填起始日": False, "多重映射": True})
    ComponentIDs = FT.getFactor("参照基准指数内部编码_R", new_name="component_code")
    ComponentInnerCode = FT.getFactor("参照基准指数内部编码", new_name="component_inner_code")
    ExecuteDate = FT.getFactor("执行日期", new_name="execute_date")
    InfoPublDate = FT.getFactor("信息发布日期", new_name="info_pub_date")
    
    if args.get("adjust_dt", True):
        ExecuteDate = QS.FactorDB.PointOperation("execute_date", [ExecuteDate], sys_args={"算子":adjustDT, "数据类型":"object"})
        InfoPublDate = QS.FactorDB.PointOperation("info_pub_date", [InfoPublDate], sys_args={"算子":adjustDT, "数据类型":"object"})

    MaxWeight = FT.getFactor("投资比例最高值", new_name="max_weight")
    MinWeight = FT.getFactor("投资比例最低值", new_name="min_weight")
    Weight = QS.FactorDB.PointOperation("weight", [MaxWeight, MinWeight], sys_args={"算子":calc_weight, "数据类型":"object"})
    
    Factors += [ComponentInnerCode, ComponentIDs, ExecuteDate, InfoPublDate, MaxWeight, MinWeight, Weight]

    UpdateArgs = {"因子表": "mf_cn_benchmark_component",
                  "因子库参数": {"检查写入值": True},
                  "默认起始日": dt.datetime(2002,1,1),
                  "最长回溯期": 365*10,
                  "外部因子库": JYDB,
                  "IDs": "公募基金"}

    return (Factors, UpdateArgs)


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_Test.json", sys_args={"检查写入值": True}, logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()

    Args = {"JYDB": JYDB, "LDB": TDB, "adjust_dt": False}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 4, 30)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    #DTs = QS.Tools.DateTime.getDateTimeSeries(StartDT, EndDT, timedelta=dt.timedelta(1))# 自然日
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    #DTRuler = QS.Tools.DateTime.getDateTimeSeries(StartDT-dt.timedelta(365), EndDT, timedelta=dt.timedelta(1))# 自然日
    #DTs = DTs[-1:]# 只保留最新数据
    
    IDs = JYDB.getMutualFundID(is_current=False)
    #IDs = ["002943.OF", "090020.OF"]
    
    CFT = QS.FactorDB.CustomFT("mf_cn_benchmark_component")
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTRuler)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, 
                  factor_db=TDB, table_name=TargetTable, 
                  if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    JYDB.disconnect()