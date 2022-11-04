# -*- coding: utf-8 -*-
"""公募基金资产配置因子"""
import os
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def adjustDT(f, idt, iid, x, args):
    if pd.notnull(x[0]):
        return pd.Timestamp(x[0]).strftime("%Y-%m-%d")
    else:
        return None


# 将持仓数据缺失的基金填充主代码对应的持仓
def mapMainCode(f, idt, iid, x, args):
    Data = x[0]
    MainCode = x[1]
    ids = np.array(iid, dtype="O")
    for iCode in pd.unique(MainCode[pd.notnull(Data)]):
        iMask = (ids==iCode)
        if np.sum(iMask)==0: continue
        iFillMask = (MainCode==iCode)
        Data[iFillMask] = Data[iMask].repeat(np.sum(iFillMask))
    return Data


def TotalAssetFun(f, idt, iid, x, args):
    Amt = np.array(x[:8])
    Weight = np.array(x[8:16])
    Mask = (pd.isnull(Amt) | (Amt<0) | pd.isnull(Weight) | (Weight<=0))
    Amt[Mask] = np.nan
    Weight[Mask] = np.nan
    TotalAmt = np.nansum(Amt, axis=0)
    TotalWeight = np.nansum(Weight, axis=0)
    NaMask = (pd.notnull(Amt) | pd.notnull(Weight))
    NaMask = (np.sum(NaMask, axis=0)>0)
    Mask = ((TotalWeight<=0) & NaMask)
    if np.sum(Mask)>0:
        Msg = "公募基金 '%s' 在日期 '%s' 的持仓现金, 股票, 债券, 基金, 贵金属, 衍生品, 资产支持证券, 买入返售证券的总权重 %f 小于等于 0!"
        RowIdx = np.arange(Mask.shape[0]).reshape((Mask.shape[0], 1)).repeat(Mask.shape[1], axis=1)[Mask]
        ColIdx = np.arange(Mask.shape[1]).reshape((1, Mask.shape[1])).repeat(Mask.shape[0], axis=0)[Mask]
        for i, iWeight in enumerate(TotalWeight[Mask]):
            f.Logger.error(Msg % (iid[ColIdx[i]], idt[RowIdx[i]].strftime("%Y-%m-%d"), iWeight))
    TotalWeight[TotalWeight<=0] = np.nan
    return TotalAmt / TotalWeight


def defFactor(args={}, debug=False):
    Factors = []

    JYDB = args["JYDB"]
    FT = JYDB.getTable("公募基金概况")
    MainCode = FT.getFactor("基金主代码_R")

    FT = JYDB.getTable("公募基金资产配置(新)", args={"公告时点字段":None, "忽略时间":True})
    ReportDate = FT.getFactor("报告期")
    InfoPublDate = FT.getFactor("信息发布日期")
    NV = FT.getFactor("资产净值")

    Cash = FT.getFactor("货币资金资产市值(元)")
    Stock = FT.getFactor("股票投资合计资产市值(元)")
    Bond = FT.getFactor("债券投资合计资产市值(元)")
    AssetBacked = FT.getFactor("资产支持证券资产市值(元)")
    Fund = FT.getFactor("基金投资合计资产市值(元)")
    Metal = FT.getFactor("贵金属投资合计资产市值(元)")
    Derivative = FT.getFactor("金融衍生品投资资产市值(元)")
    ReturnSale = FT.getFactor("买入返售证券资产市值(元)")
    
    CashWeight = FT.getFactor("货币资金占资产总值比例")
    StockWeight = FT.getFactor("股票投资合计占资产总值比例")
    BondWeight = FT.getFactor("债券投资合计占资产总值比例")
    AssetBackedWeight = FT.getFactor("资产支持证券占资产总值比例")
    FundWeight = FT.getFactor("基金投资合计占资产总值比例")
    MetalWeight = FT.getFactor("贵金属投资合计占资产总值比例")
    DerivativeWeight = FT.getFactor("金融衍生品投资占资产总值比例")
    ReturnSaleWeight = FT.getFactor("买入返售证券占资产总值比例")
    
    ReportDate = QS.FactorDB.PointOperation(ReportDate.Name, [ReportDate], sys_args={"算子":adjustDT, "数据类型":"string"})
    InfoPublDate = QS.FactorDB.PointOperation(InfoPublDate.Name, [InfoPublDate], sys_args={"算子":adjustDT, "数据类型":"string"})
    
    Factors.append(QS.FactorDB.SectionOperation("report_date", [ReportDate, MainCode], sys_args={"算子":mapMainCode, "数据类型":"string"}))
    Factors.append(QS.FactorDB.SectionOperation("info_pub_date", [InfoPublDate, MainCode], sys_args={"算子":mapMainCode, "数据类型":"string"}))
    
    NV = QS.FactorDB.SectionOperation("net_asset", [NV, MainCode], sys_args={"算子":mapMainCode})
    Cash = QS.FactorDB.SectionOperation("cash", [Cash, MainCode], sys_args={"算子":mapMainCode})
    Stock = QS.FactorDB.SectionOperation("stock", [Stock, MainCode], sys_args={"算子":mapMainCode})
    Bond = QS.FactorDB.SectionOperation("bond", [Bond, MainCode], sys_args={"算子":mapMainCode})
    AssetBacked = QS.FactorDB.SectionOperation("asset_backed", [AssetBacked, MainCode], sys_args={"算子":mapMainCode})
    Fund = QS.FactorDB.SectionOperation("fund", [Fund, MainCode], sys_args={"算子":mapMainCode})
    Metal = QS.FactorDB.SectionOperation("precious_metal", [Metal, MainCode], sys_args={"算子":mapMainCode})
    Derivative = QS.FactorDB.SectionOperation("derivative", [Derivative, MainCode], sys_args={"算子":mapMainCode})
    ReturnSale = QS.FactorDB.SectionOperation("return_sale", [ReturnSale, MainCode], sys_args={"算子":mapMainCode})

    Factors += [NV, Cash, Stock, Bond, AssetBacked, Fund, Metal, Derivative, ReturnSale]

    CashWeight = QS.FactorDB.SectionOperation("cash_weight", [CashWeight, MainCode], sys_args={"算子":mapMainCode})
    StockWeight = QS.FactorDB.SectionOperation("stock_weight", [StockWeight, MainCode], sys_args={"算子":mapMainCode})
    BondWeight = QS.FactorDB.SectionOperation("bond_weight", [BondWeight, MainCode], sys_args={"算子":mapMainCode})
    AssetBackedWeight = QS.FactorDB.SectionOperation("asset_backed_weight", [AssetBackedWeight, MainCode], sys_args={"算子":mapMainCode})
    FundWeight = QS.FactorDB.SectionOperation("fund_weight", [FundWeight, MainCode], sys_args={"算子":mapMainCode})
    MetalWeight = QS.FactorDB.SectionOperation("precious_metal_weight", [MetalWeight, MainCode], sys_args={"算子":mapMainCode})
    DerivativeWeight = QS.FactorDB.SectionOperation("derivative_weight", [DerivativeWeight, MainCode], sys_args={"算子":mapMainCode})
    ReturnSaleWeight = QS.FactorDB.SectionOperation("return_sale_weight", [ReturnSaleWeight, MainCode], sys_args={"算子":mapMainCode})
    
    Factors += [CashWeight, StockWeight, BondWeight, AssetBackedWeight, FundWeight, MetalWeight, DerivativeWeight, ReturnSaleWeight]
    
    TotalAsset = QS.FactorDB.PointOperation("total_asset", [Cash, Stock, Bond, Fund, Metal, Derivative, AssetBacked, ReturnSale,
                                                            CashWeight, StockWeight, BondWeight, FundWeight, MetalWeight, DerivativeWeight, AssetBackedWeight, ReturnSaleWeight],
                                            sys_args={"算子":TotalAssetFun, "运算时点": "多时点", "运算ID": "多ID"})
    Factors.append(TotalAsset)

    UpdateArgs = {"因子表": "mf_cn_asset_portfolio",
                  "默认起始日": dt.datetime(2002,1,1),
                  "最长回溯期": 365 * 10,
                  "IDs": "公募基金",
                  "时点类型": "自然日"}
    
    return (Factors, UpdateArgs)


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    Args = {"JYDB": JYDB}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2016, 1, 1), dt.datetime(2021, 7, 12)
    #DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTs = QS.Tools.DateTime.getDateTimeSeries(StartDT, EndDT, timedelta=dt.timedelta(1))# 自然日
    #DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    DTRuler = QS.Tools.DateTime.getDateTimeSeries(StartDT-dt.timedelta(365), EndDT, timedelta=dt.timedelta(1))# 自然日
    #DTs = DTs[-1:]# 只保留最新数据
    
    #IDs = sorted(pd.read_csv("."+os.sep+"MFIDs.csv", index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
    IDs = JYDB.getMutualFundID(is_current=False)
    
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