# -*- coding: utf-8 -*-
"""公募基金基金持仓"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# 同一个报告期, 如果有中报或者年报, 取中报或年报, 否则取季报
def filterReportType(f, idt, iid, x, args):
    if (not isinstance(x[0], list)) or (len(x[0])==0): return None
    ReportType = np.array(x[0])
    Mask = (ReportType==np.nanmin(ReportType))
    return Mask.tolist()

# 同一个报告期, 如果有中报或者年报, 取中报或年报, 否则取季报
def mask(f, idt, iid, x, args):
    if not isinstance(x[1], list): return x[0]
    return np.array(x[0])[np.array(x[1], dtype=bool)].tolist()

def adjustDT(f, idt, iid, x, args):
    if isinstance(x[0], list):
        return [iDT.strftime("%Y-%m-%d") for iDT in x[0]]
    else:
        return x[0]

# 聚合同一只成份证券的数据
def _uniqueID(z):
    if not isinstance(z, list): return None
    z = np.array(z)
    return list(set(z[pd.notnull(z) & (z!="")]))

def uniqueID(f, idt, iid, x, args):
    return pd.DataFrame(x[0]).applymap(_uniqueID).values

def reshapeData(f, idt, iid, x, args):
    if not isinstance(x[1], list): return None
    if len(x[1])==0: return []
    return [x[0][0]] * len(x[1])

def aggrData(f, idt, iid, x, args):
    if not isinstance(x[0], list): return None
    return pd.Series(x[1], index=x[0]).groupby(axis=0, level=[0]).sum().loc[x[2]].tolist()

# 计算持仓占资产净值的权重的单位
def adjustWeight(f, idt, iid, x, args):
    if isinstance(x[0], list):
        return (np.array(x[0]) / 100).tolist()
    else:
        return x[0]

# 计算持仓占资产总值的权重
def genWeight(f, idt, iid, x, args):
    if (not isinstance(x[0], list)) or pd.isnull(x[1]): return None
    Amt = np.array(x[0], dtype=float)
    TotalAsset = float(x[1])
    if TotalAsset<=0:
        f.Logger.error(f"公募基金 '{iid}' 在报告期 '{idt}' 的基金资产总值 {TotalAsset} 小于等于 0, 将填充 NaN!")
        return [None] * Amt.shape[0]
    if np.nansum(Amt)>TotalAsset*(1+0.001):
        f.Logger.error(f"公募基金 '{iid}' 在报告期 '{idt}' 的基金持仓总金额为 {np.nansum(Amt)}, 超过了基金资产总值 {TotalAsset}, 将填充 NaN!")
        return [None] * Amt.shape[0]
    return (Amt / TotalAsset).tolist()

# 将持仓数据缺失的基金填充主代码对应的持仓
def mapMainCode(f, idt, iid, x, args):
    Data, MainCode = x[0], x[1]
    ids = np.array(iid, dtype="O")
    for iCode in pd.unique(MainCode[pd.notnull(Data)]):
        iMask = (ids==iCode)
        if np.sum(iMask)==0: continue
        iFillMask = (MainCode==iCode)
        Data[iFillMask] = Data[iMask].repeat(np.sum(iFillMask))
    return Data

def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    FT = JYDB.getTable("公募基金概况")
    MainCode = FT.getFactor("基金主代码_R")
    
    FT = JYDB.getTable("公募基金投资基金明细(公募基金ID)", args={"公告时点字段": None, "忽略时间": True, "信息来源": ""})
    ReportDate = FT.getFactor("报告期")
    InfoPublDate = FT.getFactor("信息发布日期")
    FundReportType = FT.getFactor("信息来源")
    ComponentID = FT.getFactor("投资基金内部编码_R")
    PositionVolume = FT.getFactor("持有数量(份)")
    PositionAmount = FT.getFactor("公允价值(元)")
    PositionWeightInNV = FT.getFactor("占资产净值比例(%)")
    
    FT = LDB.getTable("mf_cn_asset_portfolio")
    TotalAsset = FT.getFactor("total_asset")
    
    Mask = fd.notnull(TotalAsset)
    ReportDate = fd.where(ReportDate, Mask, None, data_type="object")
    InfoPublDate = fd.where(InfoPublDate, Mask, None, data_type="object")
    FundReportType = fd.where(FundReportType, Mask, None, data_type="object")    
    ComponentID = fd.where(ComponentID, Mask, None, data_type="object")
    PositionVolume = fd.where(PositionVolume, Mask, None, data_type="object")
    PositionAmount = fd.where(PositionAmount, Mask, None, data_type="object")
    PositionWeightInNV = fd.where(PositionWeightInNV, Mask, None, data_type="object")
    
    ReportMask = QS.FactorDB.PointOperation("ReportMask", [FundReportType], sys_args={"算子": filterReportType, "数据类型": "object"})
    ReportDate = QS.FactorDB.PointOperation("ReportDate", [ReportDate, ReportMask], sys_args={"算子": mask, "数据类型": "object"})
    InfoPublDate = QS.FactorDB.PointOperation("InfoPublDate", [InfoPublDate, ReportMask], sys_args={"算子": mask, "数据类型": "object"})
    ComponentID = QS.FactorDB.PointOperation("ComponentID", [ComponentID, ReportMask], sys_args={"算子": mask, "数据类型": "object"})
    PositionVolume = QS.FactorDB.PointOperation("PositionVolume", [PositionVolume, ReportMask], sys_args={"算子": mask, "数据类型": "object"})
    PositionAmount = QS.FactorDB.PointOperation("PositionAmount", [PositionAmount, ReportMask], sys_args={"算子": mask, "数据类型": "object"})
    PositionWeightInNV = QS.FactorDB.PointOperation("PositionWeightInNV", [PositionWeightInNV, ReportMask], sys_args={"算子": mask, "数据类型": "object"})
    
    ReportDate = QS.FactorDB.PointOperation(ReportDate.Name, [ReportDate], sys_args={"算子": adjustDT, "数据类型": "object"})
    InfoPublDate = QS.FactorDB.PointOperation(InfoPublDate.Name, [InfoPublDate], sys_args={"算子": adjustDT, "数据类型": "object"})
    
    UniComponentID = QS.FactorDB.PointOperation(
        "唯一成份代码", 
        [ComponentID], 
        sys_args={
            "算子": uniqueID,
            "参数": {},
            "运算时点": "多时点",
            "运算ID": "多ID",
            "数据类型": "object"
        }
    )
    
    ReportDate = QS.FactorDB.PointOperation("报告期", [ReportDate, UniComponentID], sys_args={"算子": reshapeData, "数据类型": "object"})
    InfoPublDate = QS.FactorDB.PointOperation("信息发布日期", [InfoPublDate, UniComponentID], sys_args={"算子": reshapeData, "数据类型": "object"})
    PositionVolume = QS.FactorDB.PointOperation("持仓数量", [ComponentID, PositionVolume, UniComponentID], sys_args={"算子": aggrData, "数据类型": "object"})
    PositionAmount = QS.FactorDB.PointOperation("持仓估值", [ComponentID, PositionAmount, UniComponentID], sys_args={"算子": aggrData, "数据类型": "object"})
    PositionWeightInNV = QS.FactorDB.PointOperation("占资产净值比例", [ComponentID, PositionWeightInNV, UniComponentID], sys_args={"算子": aggrData, "数据类型": "object"})
    PositionWeightInNV = QS.FactorDB.PointOperation(PositionWeightInNV.Name, [PositionWeightInNV], sys_args={"算子": adjustWeight, "数据类型": "object"})
    
    PositionWeight = QS.FactorDB.PointOperation("PositionWeight", [PositionAmount, TotalAsset], sys_args={"算子": genWeight, "数据类型": "object"})
    
    ReportDate = QS.FactorDB.SectionOperation("report_date", [ReportDate, MainCode], sys_args={"算子": mapMainCode, "数据类型": "object"})
    InfoPublDate = QS.FactorDB.SectionOperation("info_pub_date", [InfoPublDate, MainCode], sys_args={"算子": mapMainCode, "数据类型": "object"})
    UniComponentID = QS.FactorDB.SectionOperation("component_code", [UniComponentID, MainCode], sys_args={"算子": mapMainCode, "数据类型": "object"})
    PositionVolume = QS.FactorDB.SectionOperation("volume", [PositionVolume, MainCode], sys_args={"算子": mapMainCode, "数据类型": "object"})
    PositionAmount = QS.FactorDB.SectionOperation("amount", [PositionAmount, MainCode], sys_args={"算子": mapMainCode, "数据类型": "object"})
    PositionWeightInNV = QS.FactorDB.SectionOperation("weight_in_nv", [PositionWeightInNV, MainCode], sys_args={"算子": mapMainCode, "数据类型": "object"})
    PositionWeight = QS.FactorDB.SectionOperation("weight", [PositionWeight, MainCode], sys_args={"算子": mapMainCode, "数据类型": "object"})
    
    Factors += [ReportDate, InfoPublDate, UniComponentID, PositionVolume, PositionAmount, PositionWeightInNV, PositionWeight]
    
    UpdateArgs = {
        "因子表": "mf_cn_fund_component",
        "因子库参数": {"检查写入值": True},
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": "公募基金",
        "时点类型": "自然日"
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
    #DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTs = QS.Tools.DateTime.getDateTimeSeries(StartDT, EndDT, timedelta=dt.timedelta(1))
    #DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    DTRuler = QS.Tools.DateTime.getDateTimeSeries(StartDT-dt.timedelta(365), EndDT, timedelta=dt.timedelta(1))

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