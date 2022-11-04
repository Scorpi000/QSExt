# coding=utf-8
"""股票指数成长性"""
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

# args 应该包含的参数
# JYDB: 聚源因子库对象
# LDB: 本地因子库对象
# id_info_file: ID 信息配置文件路径
def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    StockIDs = JYDB.getStockID(is_current=False)
    IDs = sorted(pd.read_csv(args["id_info_file"], index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
    
    # 指数成份
    FT = LDB.getTable("index_cn_stock_component")
    ComponentID = fd.fillna(FT.getFactor("component_code"), lookback=63)
    ComponentWeight = fd.fillna(FT.getFactor("weight"), lookback=63)
    
    # ### 利润表因子 #############################################################################
    FT = JYDB.getTable("利润分配表_新会计准则")
    Sales_TTM = FT.getFactor("营业收入", args={"计算方法":"TTM"})
    Sales_TTM_L1 = FT.getFactor("营业收入", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})
    Sales_SQ = FT.getFactor("营业收入", args={"计算方法":"单季度"})
    Sales_SQ_L1 = FT.getFactor("营业收入", args={"计算方法":"单季度", "报告期":"所有", "回溯年数":1})
    NetProfit_TTM = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"TTM"})
    NetProfit_TTM_L1 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"TTM", "报告期":"所有", "回溯年数":1})
    NetProfit_SQ = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度"})
    NetProfit_SQ_L1 = FT.getFactor("归属于母公司所有者的净利润", args={"计算方法":"单季度", "报告期":"所有", "回溯年数":1})
    
    iFactor = QS.FactorDB.SectionOperation(Sales_TTM.Name, [Sales_TTM, ComponentID, ComponentWeight], sys_args={
        "算子": calc_index_value, 
        "计算时点": "单时点", 
        "输出形式": "全截面",
        "描述子截面": [StockIDs, None, None]})
    iFactor_L1 = QS.FactorDB.SectionOperation(Sales_TTM.Name+"_L1", [Sales_TTM_L1, ComponentID, ComponentWeight], sys_args={
        "算子": calc_index_value, 
        "计算时点": "单时点", 
        "输出形式": "全截面",
        "描述子截面": [StockIDs, None, None]})
    Factors.append(Factorize((iFactor - iFactor_L1) / abs(iFactor_L1), factor_name="revenue_ttm_yoy"))
    
    iFactor = QS.FactorDB.SectionOperation(Sales_SQ.Name, [Sales_SQ, ComponentID, ComponentWeight], sys_args={
        "算子": calc_index_value, 
        "计算时点": "单时点", 
        "输出形式": "全截面",
        "描述子截面": [StockIDs, None, None]})
    iFactor_L1 = QS.FactorDB.SectionOperation(Sales_SQ.Name+"_L1", [Sales_SQ_L1, ComponentID, ComponentWeight], sys_args={
        "算子": calc_index_value, 
        "计算时点": "单时点", 
        "输出形式": "全截面",
        "描述子截面": [StockIDs, None, None]})
    Factors.append(Factorize((iFactor - iFactor_L1) / abs(iFactor_L1), factor_name="revenue_sq_yoy"))
    
    iFactor = QS.FactorDB.SectionOperation(NetProfit_TTM.Name, [NetProfit_TTM, ComponentID, ComponentWeight], sys_args={
        "算子": calc_index_value, 
        "计算时点": "单时点", 
        "输出形式": "全截面",
        "描述子截面": [StockIDs, None, None]})
    iFactor_L1 = QS.FactorDB.SectionOperation(NetProfit_TTM.Name+"_L1", [NetProfit_TTM_L1, ComponentID, ComponentWeight], sys_args={
        "算子": calc_index_value, 
        "计算时点": "单时点", 
        "输出形式": "全截面",
        "描述子截面": [StockIDs, None, None]})
    Factors.append(Factorize((iFactor - iFactor_L1) / abs(iFactor_L1), factor_name="net_profit_ttm_yoy"))
    
    iFactor = QS.FactorDB.SectionOperation(NetProfit_SQ.Name, [NetProfit_SQ, ComponentID, ComponentWeight], sys_args={
        "算子": calc_index_value, 
        "计算时点": "单时点", 
        "输出形式": "全截面",
        "描述子截面": [StockIDs, None, None]})
    iFactor_L1 = QS.FactorDB.SectionOperation(NetProfit_SQ.Name+"_L1", [NetProfit_SQ_L1, ComponentID, ComponentWeight], sys_args={
        "算子": calc_index_value, 
        "计算时点": "单时点", 
        "输出形式"    : "全截面",
        "描述子截面": [StockIDs, None, None]})
    Factors.append(Factorize((iFactor - iFactor_L1) / abs(iFactor_L1), factor_name="net_profit_sq_yoy"))
    
    UpdateArgs = {"因子表": "index_cn_stock_indicator",
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

    Args = {"JYDB": JYDB, "LDB": TDB, "id_info_file": r"../conf/index/IndexIDs_StockWeight.csv"}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2005, 1, 1), dt.datetime(2020, 5, 31)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")

    IDs = UpdateArgs["IDs"]

    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTRuler)
    CFT.setID(IDs)

    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
                      factor_db=TDB, table_name=TargetTable,
                  if_exists="update", subprocess_num=10)

    TDB.disconnect()
    JYDB.disconnect()