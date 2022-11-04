# coding=utf-8
"""股票指数估值"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

def calc_index_value(f, idt, iid, x, args):
    Value, ComponentID, ComponentWeight = x
    Value = pd.Series(Value, index=f.DescriptorSection[0])
    Rslt = np.full_like(ComponentID, np.nan)
    for i, iIDs in enumerate(ComponentID):
        if isinstance(iIDs, list):
            iWeight = np.array(ComponentWeight[i])
            if Value.index.intersection(iIDs).shape[0]>0:
                iValue = Value.loc[iIDs].values
                iMask = (pd.notnull(iValue) & pd.notnull(iWeight))
                iWeightSum = np.sum(iWeight[iMask])
                if iWeightSum>0:
                    Rslt[i] = np.sum((iValue * iWeight)[iMask]) / iWeightSum
    return Rslt

def IndexAvgFun(f, idt, iid, x, args):
    Value, ComponentID = x
    Value = pd.Series(Value, index=f.DescriptorSection[0])
    Rslt = np.full_like(ComponentID, np.nan)
    for i, iIDs in enumerate(ComponentID):
        if isinstance(iIDs, list):
            if Value.index.intersection(iIDs).shape[0]>0:
                Rslt[i] = Value.loc[iIDs].mean()
    return Rslt

def IndexMedianFun(f, idt, iid, x, args):
    Value, ComponentID = x
    Value = pd.Series(Value, index=f.DescriptorSection[0])
    Rslt = np.full_like(ComponentID, np.nan)
    for i, iIDs in enumerate(ComponentID):
        if isinstance(iIDs, list):
            if Value.index.intersection(iIDs).shape[0]>0:
                Rslt[i] = Value.loc[iIDs].median()
    return Rslt

# args 应该包含的参数
# JYDB: 聚源因子库对象
# LDB: 本地因子库对象
# id_info_file: ID 信息配置文件路径
def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    StockIDs = JYDB.getStockID(is_current=False)
    if isinstance(args["id_info_file"], str):
        IDs = sorted(pd.read_csv(args["id_info_file"], index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
    else:
        IDs = []
        for iInfoFile in args["id_info_file"]:
            IDs += pd.read_csv(iInfoFile, index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0].tolist()
        IDs = sorted(set(IDs))
    
    # 指数成份
    FT = LDB.getTable("index_cn_stock_component")
    ComponentID = fd.fillna(FT.getFactor("component_code"), lookback=63)
    ComponentWeight = fd.fillna(FT.getFactor("weight"), lookback=63)
    
    # 股票估值，聚源计算
    StockFT = LDB.getTable("stock_cn_valuation_jy")
    TargetFactors = ["dp_lyr", "dp_ltm", "pe_ttm", "pe_lyr", "pb_lr", 'pcf_lyr', "pcf_ttm", "pcfs_lyr", "pcfs_ttm", "ps_lyr", "ps_ttm", "pe_ttm_m", "pb_m"]
    for iFactorName in TargetFactors:
        iFactor = StockFT.getFactor(iFactorName)
        Factors.append(QS.FactorDB.SectionOperation(iFactorName+"_jy", [iFactor, ComponentID, ComponentWeight], sys_args={
            "算子": calc_index_value, 
            "参数": {},
            "计算时点": "单时点", 
            "输出形式": "全截面",
            "描述子截面": [StockIDs, None, None]}))
        Factors.append(QS.FactorDB.SectionOperation(iFactorName+"_avg_jy", [iFactor, ComponentID], sys_args={
            "算子": IndexAvgFun, 
            "参数": {},
            "计算时点": "单时点", 
            "输出形式": "全截面",
            "描述子截面": [StockIDs, None]}))
        Factors.append(QS.FactorDB.SectionOperation(iFactorName+"_median_jy", [iFactor, ComponentID], sys_args={
            "算子": IndexMedianFun, 
            "参数": {},
            "计算时点": "单时点", 
            "输出形式": "全截面",
            "描述子截面": [StockIDs, None]}))
    
    # 股票估值，自己计算
    StockFT = LDB.getTable("stock_cn_style_value")
    TargetFactors = StockFT.FactorNames
    for iFactorName in TargetFactors:
        iFactor = StockFT.getFactor(iFactorName)
        Factors.append(QS.FactorDB.SectionOperation(iFactorName, [iFactor, ComponentID, ComponentWeight], sys_args={
            "算子": calc_index_value, 
            "参数": {},
            "计算时点": "单时点", 
            "输出形式": "全截面",
            "描述子截面": [StockIDs, None, None]}))
        Factors.append(QS.FactorDB.SectionOperation(iFactorName+"_avg", [iFactor, ComponentID], sys_args={
            "算子": IndexAvgFun, 
            "参数": {},
            "计算时点": "单时点", 
            "输出形式": "全截面",
            "描述子截面": [StockIDs, None]}))
        Factors.append(QS.FactorDB.SectionOperation(iFactorName+"_median", [iFactor, ComponentID], sys_args={
            "算子": IndexMedianFun, 
            "参数": {},
            "计算时点": "单时点",
            "输出形式": "全截面",
            "描述子截面": [StockIDs, None]}))
    
    UpdateArgs = {"因子表": "index_cn_stock_valuation",
                  "默认起始日": dt.datetime(2002, 1, 1),
                  "最长回溯期": 365,
                  "IDs": IDs}
    
    return (Factors, UpdateArgs)

if __name__ == "__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_FactorTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()

    Args = {"JYDB": JYDB, "LDB": TDB, "id_info_file": [r"../conf/index/IndexIDs_StockWeight.csv", r"../conf/index/IndexIDs_IndexMF.csv", r"../conf/index/IndexIDs_ETF.csv"]}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2005, 1, 1), dt.datetime(2021, 1, 31)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")

    IDs = UpdateArgs["IDs"]
    IDs = ["000985"]

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