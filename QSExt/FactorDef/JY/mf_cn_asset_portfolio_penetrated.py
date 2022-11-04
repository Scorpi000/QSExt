# -*- coding: utf-8 -*-
"""公募基金资产配置穿透"""
import os
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


# deprecated: 资产穿透, 返回: (Cash, Stock, Bond, Fund, Metal, Derivative, AssetBacked, ReturnSale, CashWeight, StockWeight, BondWeight, FundWeight, MetalWeight, DerivativeWeight, AssetBackedWeight, ReturnSaleWeight)
def penetrate_deprecated(f, idt, iid, x, args):
    Rslt = np.array(x[:16]).T
    TotalAsset = x[-3]
    FundComponentID, FundPositionAmt = x[-2], x[-1]
    Mask = pd.notnull(FundComponentID)
    if np.sum(Mask)==0: return pd.DataFrame(Rslt).to_records(index=False).tolist()
    Idx = np.arange(0, Mask.shape[0])[Mask]
    IDs = np.array(iid)
    for i in Idx:
        iRslt = Rslt[i, :]
        iMask = pd.isnull(iRslt)
        iRslt[iMask] = 0
        for j, jID in enumerate(FundComponentID[i]):
            jMask = (IDs==jID)
            jRslt = Rslt[jMask, :]
            if jRslt.shape[0]==0:
                continue
            if isinstance(FundComponentID[jMask][0], list) and (len(FundComponentID[jMask][0])>0):
                raise Exception("'%s' 持有的基金 '%s' 也持有基金!" % (iid[i], jID))
            jRslt = jRslt[0, :]
            jRslt[pd.isnull(jRslt)] = 0
            iRslt[3] -= float(FundPositionAmt[i][j])
            iRslt[0:8] += float(FundPositionAmt[i][j]) * jRslt[8:16]
        iRslt[8:16] = iRslt[0:8] / float(TotalAsset[i])
        iRslt[iMask & (iRslt==0)] = np.nan
        Rslt[i, :] = iRslt
    return pd.DataFrame(Rslt).to_records(index=False).tolist()

# 递归方式穿透单个基金
def _penetrate_single_fund(idx, mf_ids, total_asset, asset_portfolio, component_fund_ids, component_fund_amount, logger):
    AssetPortfolio = np.copy(asset_portfolio[idx])
    iComponentFundIDs = component_fund_ids[idx]
    if isinstance(iComponentFundIDs, list) and (len(iComponentFundIDs)>0):# 该基金持有基金, 继续穿透
        iMask = pd.isnull(AssetPortfolio)
        AssetPortfolio[iMask] = 0
        for j, jID in enumerate(iComponentFundIDs):
            jIdx = mf_ids.searchsorted(jID)
            if (jIdx<mf_ids.shape[0]) and (mf_ids[jIdx]==jID):
                try:
                    jAssetPorfolio = _penetrate_single_fund(jIdx, mf_ids, total_asset, asset_portfolio, component_fund_ids, component_fund_amount, logger)
                except RecursionError as e:
                    Logger.error(e)
                    Logger.debug(jID)
                    Logger.debug(component_fund_ids)
                    continue
                if np.nansum(jAssetPorfolio[8:]) > float(total_asset[jIdx]):
                    logger.error("'%s' 持有的成份总价值超过资产总值!" % (mf_ids[jIdx], ))
                jAssetPorfolio[pd.isnull(jAssetPorfolio)] = 0
                AssetPortfolio[3] -= float(component_fund_amount[idx][j])
                AssetPortfolio[0:8] += float(component_fund_amount[idx][j]) * (jAssetPorfolio[0:8] / float(total_asset[jIdx]))
            else:
                logger.warning("'%s' 持有的基金 '%s' 不在基金列表里!" % (mf_ids[idx], jID))
        AssetPortfolio[8:16] = AssetPortfolio[0:8] / float(total_asset[idx])
        AssetPortfolio[iMask & (AssetPortfolio==0)] = np.nan
    return AssetPortfolio
# 资产穿透, 返回: (ComponentID, PositionAmount, PositionWeight)
def penetrate(f, idt, iid, x, args):
    AssetPortfolio = np.array(x[:16]).T
    TotalAsset = x[-3]
    FundComponentID, FundPositionAmt = x[-2], x[-1]
    Mask = pd.notnull(FundComponentID)
    if np.sum(Mask)==0: return pd.DataFrame(AssetPortfolio).to_records(index=False).tolist()
    Idx = np.arange(0, Mask.shape[0])[Mask]
    IDs = np.array(iid)
    Rslt = np.copy(AssetPortfolio)
    for i in Idx:
        Rslt[i, :] = _penetrate_single_fund(i, IDs, TotalAsset, AssetPortfolio, FundComponentID, FundPositionAmt, f.Logger)
    return pd.DataFrame(Rslt).to_records(index=False).tolist()


def defFactor(args={}, debug=False):
    Factors = []

    LDB = args["LDB"]
    #FT = LDB.getTable("mf_cn_asset_portfolio", args={"时间转字符串":True})
    FT = LDB.getTable("mf_cn_asset_portfolio")
    TotalAsset = FT.getFactor("total_asset")
    ReportDate = FT.getFactor("report_date")
    InfoPublDate = FT.getFactor("info_pub_date")

    Cash = FT.getFactor("cash")
    Stock = FT.getFactor("stock")
    Bond = FT.getFactor("bond")
    Fund = FT.getFactor("fund")
    Metal = FT.getFactor("precious_metal")
    Derivative = FT.getFactor("derivative")
    AssetBacked = FT.getFactor("asset_backed")
    ReturnSale = FT.getFactor("return_sale")

    CashWeight = FT.getFactor("cash_weight")
    StockWeight = FT.getFactor("stock_weight")
    BondWeight = FT.getFactor("bond_weight")
    FundWeight = FT.getFactor("fund_weight")
    MetalWeight = FT.getFactor("precious_metal_weight")
    DerivativeWeight = FT.getFactor("derivative_weight")
    AssetBackedWeight = FT.getFactor("asset_backed_weight")
    ReturnSaleWeight = FT.getFactor("return_sale_weight")

    #FT = LDB.getTable("mf_cn_fund_component", args={"因子值类型":"list"})
    FT = LDB.getTable("mf_cn_fund_component", args={"多重映射": True})
    FundComponentID = FT.getFactor("component_code")
    FundPositionAmt = FT.getFactor("amount")

    PenetrateRslt = QS.FactorDB.SectionOperation("PenetrateRslt", [Cash, Stock, Bond, Fund, Metal, Derivative, AssetBacked, ReturnSale,
                                                                   CashWeight, StockWeight, BondWeight, FundWeight, MetalWeight, DerivativeWeight, AssetBackedWeight, ReturnSaleWeight,
                                                                   TotalAsset, FundComponentID, FundPositionAmt], sys_args={"算子":penetrate, "数据类型":"string"})

    Factors.append(fd.strftime(ReportDate, "%Y-%m-%d", factor_name="report_date"))
    Factors.append(fd.strftime(InfoPublDate, "%Y-%m-%d", factor_name="info_pub_date"))
    Factors.append(TotalAsset)
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 0), "cash"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 1), "stock"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 2), "bond"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 3), "fund"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 4), "precious_metal"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 5), "derivative"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 6), "asset_backed"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 7), "return_sale"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 8), "cash_weight"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 9), "stock_weight"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 10), "bond_weight"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 11), "fund_weight"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 12), "precious_metal_weight"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 13), "derivative_weight"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 14), "asset_backed_weight"))
    Factors.append(Factorize(fd.fetch(PenetrateRslt, 15), "return_sale_weight"))


    UpdateArgs = {"因子表": "mf_cn_asset_portfolio_penetrated",
                  "默认起始日": dt.datetime(2002,1,1),
                  "最长回溯期": 365 * 10,
                  "IDs": "公募基金",
                  "时点类型": "自然日"}

    return (Factors, UpdateArgs)


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB()
    JYDB.connect()
    
    #TDB = QS.FactorDB.HDF5DB()
    TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB.connect()
    
    Args = {"LDB": TDB}
    Factors, UpdateArgs = defFactor(Args)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2020, 10, 9)
    #DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTs = QS.Tools.DateTime.getDateTimeSeries(StartDT, EndDT, timedelta=dt.timedelta(1))# 自然日
    #DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    DTRuler = QS.Tools.DateTime.getDateTimeSeries(StartDT-dt.timedelta(365), EndDT, timedelta=dt.timedelta(1))# 自然日
    #DTs = DTs[-1:]# 只保留最新数据
    
    #IDs = sorted(pd.read_csv("../conf/mf/MFIDs.csv", index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
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