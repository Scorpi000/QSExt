# -*- coding: utf-8 -*-
"""基金经理管理基准组合净值"""
import datetime as dt
from collections import OrderedDict

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize
from .mf_manager_cn_net_value import gen_equal_weight, fill_daily_return, filter_fund, portfolio_return_d_fun, portfolio_return_m_fun

def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"].connect()
    LDB = args["LDB"]
    
    IDs = JYDB.getTable("公募基金经理(转型)(基金经理ID)", args={"多重映射": True}).getID()
    MFIDs = JYDB.getMutualFundID(is_current=False)
    
    FT = JYDB.getTable("公募基金经理(转型)(基金经理ID)", args={"多重映射": True})
    FundCode = FT.getFactor("基金内部编码_R", args={"只填起始日": False})
    FundCodeAdj = FT.getFactor("基金内部编码_R", args={"只填起始日": True})
    
    FT = LDB.getTable("mf_cn_status")
    Mask = (FT.getFactor("if_exist")==1)
    
    # 将基金经理管理的基金中 if_exist==0 的基金剔除
    FundCode = QS.FactorDB.SectionOperation("FundCode", [FundCode, Mask], sys_args={
        "算子": filter_fund,
        "运算时点": "单时点",
        "输出形式": "全截面",
        "描述子截面": [None, MFIDs],
        "数据类型": "object"
    })
    FundCodeAdj = QS.FactorDB.SectionOperation("FundCodeAdj", [FundCodeAdj, Mask], sys_args={
        "算子": filter_fund,
        "运算时点": "单时点",
        "输出形式": "全截面",
        "描述子截面": [None, MFIDs],
        "数据类型": "object"
    })
    
    FT = LDB.getTable("mf_cn_info")
    MainCode = FT.getFactor("main_code")
    MainCode = fd.where(MainCode, fd.notnull(MainCode), QS.FactorDB.DataFactor("Code", pd.Series(MFIDs, index=MFIDs)), data_type="string")
    EqualWeight = QS.FactorDB.SectionOperation("equal_weight", [MainCode, Mask], sys_args={
        "算子": gen_equal_weight,
        "运算时点": "单时点",
        "输出形式": "全截面",
        "数据类型": "double"
    })
    
    # 基准收益
    FT = JYDB.getTable("公募基金基准收益率(转型)", args={"回溯天数": 0})
    MFDailyReturn = fd.where(FT.getFactor("本日基金基准增长率") / 100, Mask, np.nan)
    MFDailyReturn = QS.FactorDB.SectionOperation("benchmark_daily_return",
        [MFDailyReturn, MainCode, Mask],
        sys_args={
            "算子": fill_daily_return,
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
    })
    
    FT = LDB.getTable("mf_cn_net_value_nafilled")
    Size = FT.getFactor("net_value")
    
    FT = LDB.getTable("mf_cn_type")
    MFType = FT.getFactor(args["MFType"])
    
    Return_d_ew = OrderedDict()# 每日再平衡等权合成
    Return_m_ew = OrderedDict()# 每月末再平衡等权合成
    Return_d_sw = OrderedDict()# 每日再平衡规模加权合成
    Return_m_sw = OrderedDict()# 每月末再平衡规模加权合成
    for iType in ["All"]+args["MFAllTypes"]:
        if iType=="All":
            iMask = Mask
        else:
            iMask = (Mask & (MFType==iType))
        iFactorName = f"daily_return_d_ew_{iType}"
        Return_d_ew[iFactorName] = QS.FactorDB.PanelOperation(iFactorName,
            [FundCode, MFDailyReturn, EqualWeight, iMask],
            sys_args={
                "算子": portfolio_return_d_fun,
                "参数": {},
                "回溯期数": [2-1, 1-1, 2-1, 2-1],
                "运算时点": "单时点",
                "输出形式": "全截面",
                "描述子截面": [None, MFIDs, MFIDs, MFIDs],
                "数据类型": "double"
        })
        
        iFactorName = f"daily_return_m_ew_{iType}"
        Return_m_ew[iFactorName] = QS.FactorDB.PanelOperation(iFactorName,
            [FundCode, FundCodeAdj, MFDailyReturn, EqualWeight, iMask],
            sys_args={
                "算子": portfolio_return_m_fun,
                "参数": {},
                "回溯期数": [32-1, 32-1, 32-1, 32-1, 32-1],
                "运算时点": "单时点",
                "输出形式": "全截面",
                "描述子截面": [None, None, MFIDs, MFIDs, MFIDs],
                "数据类型": "double"
        })
        
        iFactorName = f"daily_return_d_sw_{iType}"
        Return_d_sw[iFactorName] = QS.FactorDB.PanelOperation(iFactorName,
            [FundCode, MFDailyReturn, Size, iMask],
            sys_args={
                "算子": portfolio_return_d_fun,
                "参数": {},
                "回溯期数": [2-1, 1-1, 2-1, 2-1],
                "运算时点": "单时点",
                "输出形式": "全截面",
                "描述子截面": [None, MFIDs, MFIDs, MFIDs],
                "数据类型": "double"
        })
        
        iFactorName = f"daily_return_m_sw_{iType}"
        Return_m_sw[iFactorName] = QS.FactorDB.PanelOperation(iFactorName,
            [FundCode, FundCodeAdj, MFDailyReturn, Size, iMask],
            sys_args={
                "算子": portfolio_return_m_fun,
                "参数": {},
                "回溯期数": [32-1, 32-1, 32-1, 32-1, 32-1],
                "运算时点": "单时点",
                "输出形式": "全截面",
                "描述子截面": [None, None, MFIDs, MFIDs, MFIDs],
                "数据类型": "double"
        })        
    
    if args.get("TableType", "Wide")=="Wide":
        Factors = list(Return_d_ew.values()) + list(Return_m_ew.values()) + list(Return_d_sw.values()) + list(Return_m_sw.values())
    elif args["TableType"]=="Narrow":
        TypeFactors = []
        for iType in ["All"]+args["MFAllTypes"]:
            iMask = (fd.isnull(Return_d_ew[f"daily_return_d_ew_{iType}"]) & fd.isnull(Return_m_ew[f"daily_return_m_ew_{iType}"]) & fd.isnull(Return_d_sw[f"daily_return_d_sw_{iType}"]) & fd.isnull(Return_m_sw[f"daily_return_m_sw_{iType}"]))
            iTypeFactor = fd.where(None, iMask, QS.FactorDB.DataFactor(f"type_{iType}", data=iType, sys_args={"数据类型": "string"}))
            TypeFactors.append(iTypeFactor)
        Factors.append(fd.tolist(*TypeFactors, factor_name="type"))
        Factors.append(fd.tolist(*Return_d_ew.values(), factor_name="daily_return_d_ew"))
        Factors.append(fd.tolist(*Return_m_ew.values(), factor_name="daily_return_m_ew"))
        Factors.append(fd.tolist(*Return_d_sw.values(), factor_name="daily_return_d_sw"))
        Factors.append(fd.tolist(*Return_m_sw.values(), factor_name="daily_return_m_sw"))
    else:
        raise Exception(f"不支持的表类型: {args['TableType']}")
        
    UpdateArgs = {
        "因子表": "mf_manager_cn_benchmark_net_value",
        "因子库参数": {"检查写入值": True, "检查缺失容许": True},
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
    
    SQLStr = "SELECT FundTypeName FROM mf_fundtype WHERE Standard=75 AND StandardLevel=2 ORDER BY DisclosureCode"
    MFAllTypes = [iType[0] for iType in JYDB.fetchall(SQLStr) if iType[0].find("其他")==-1]
    
    Args = {"JYDB": JYDB, "MFAllTypes": MFAllTypes, "MFType": "jy_type_second", "TableType": "Wide"}
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