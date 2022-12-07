# -*- coding: utf-8 -*-
"""公募基金股票整体仓位测算"""
import datetime as dt

import numpy as np
import pandas as pd
import cvxpy as cvx

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

POSITION_LIMIT = {
    "标准股票型": (0.8, 0.95),
    "偏股型": (0.6, 0.95),
    "灵活配置型": (0, 0.95),
}

P_LAMBDA = {
    "标准股票型": 2.5e-6,
    "偏股型": 1.5e-6,
    "灵活配置型": 4e-6,
}

def get_position(f, idt, iid, x, args):
    mf_position, mf_type, mf_nv = x
    category = (args["category"] if "category" in args else None)
    if category:
        mask = (mf_type==category)
        position_limit = POSITION_LIMIT[category]
        mf_position = mf_position[mask].clip(min=position_limit[0], max=position_limit[1])
        mf_nv = mf_nv[mask]
    m = (~(np.isnan(mf_position) | np.isnan(mf_nv)))
    Rslt = (mf_position[m] * mf_nv[m]).sum() / mf_nv[m].sum()
    return Rslt


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"].connect()
    LDB = args["LDB"]
    
    FundIDs = JYDB.getMutualFundID(is_current=False)
    
    FT = LDB.getTable("mf_cn_type")
    MFType = FT.getFactor("jy_type_second")
    
    FT = LDB.getTable("mf_cn_position_stock", args={"筛选条件": "{Table}.industry_code='ALL'"})
    MFPosition = FT.getFactor("position")    
    
    FT = LDB.getTable("mf_cn_net_value_nafilled")
    MFNV = FT.getFactor("unit_net_value_adj")
    
    position_stock_std = QS.FactorDB.SectionOperation(
        "标准股票型",
        [MFPosition, MFType, MFNV],
        sys_args={
            "算子": get_position,
            "参数": {"category": "标准股票型"},
            "描述子截面": [FundIDs, FundIDs, FundIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "object"
        }
    )
    
    position_stock_part = QS.FactorDB.SectionOperation(
        "偏股型",
        [MFPosition, MFType, MFNV],
        sys_args={
            "算子": get_position,
            "参数": {"category": "偏股型"},
            "描述子截面": [FundIDs, FundIDs, FundIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "object"
        }
    )
    
    position_free = QS.FactorDB.SectionOperation(
        "灵活配置型",
        [MFPosition, MFType, MFNV],
        sys_args={
            "算子": get_position,
            "参数": {"category": "灵活配置型"},
            "描述子截面": [FundIDs, FundIDs, FundIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "object"
        }
    )
    
    position_total = QS.FactorDB.SectionOperation(
        "TOTAL",
        [MFPosition, MFType, MFNV],
        sys_args={
            "算子": get_position,
            "参数": {},
            "描述子截面": [FundIDs, FundIDs, FundIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "object"
        }
    )
    
    TargetFactors = [position_stock_std, position_stock_part, position_free, position_total]
    TargetIDs = [[iFactor.Name] for iFactor in TargetFactors]
    
    # 合并因子
    Factors.append(fd.merge(TargetFactors, TargetIDs, factor_name="position", data_type="double"))
    
    UpdateArgs = {
        "因子表": "none_cn_mf_position_stock",
        "因子库参数": {"检查写入值": True},
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": sum(TargetIDs, [])
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