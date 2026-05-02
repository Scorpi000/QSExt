# -*- coding: utf-8 -*-
"""公募基金风格稳定性因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def industry_sds_hb(f, idt, iid, x, args):
    IndustryWeight = pd.DataFrame(x[:3], index=["standard", "code", "weight"]).T
    IndustryWeight_L1 = pd.DataFrame(x[3:], index=["standard", "code", "weight"]).T
    IndustryWeight = IndustryWeight[pd.notnull(IndustryWeight["standard"])]
    IndustryWeight_L1 = IndustryWeight_L1[pd.notnull(IndustryWeight_L1["standard"])]
    Standards = set(IndustryWeight["standard"].values).intersection(set(IndustryWeight_L1["standard"].values))
    IndustryWeight = IndustryWeight[IndustryWeight["standard"].isin(Standards)]
    IndustryWeight_L1 = IndustryWeight_L1[IndustryWeight_L1["standard"].isin(Standards)]
    if (IndustryWeight.shape[0]==0) or (IndustryWeight_L1.shape[0]==0):
        return np.nan
    IndustryWeight = pd.merge(IndustryWeight, IndustryWeight_L1, how="outer", left_on=["standard", "code"], right_on=["standard", "code"], suffixes=("", "_l1"))
    TotalWeight = IndustryWeight["weight"].sum()
    if TotalWeight<=0: return np.nan
    IndustryWeight["weight"] = IndustryWeight["weight"] / TotalWeight
    TotalWeight = IndustryWeight["weight_l1"].sum()
    if TotalWeight<=0: return np.nan
    IndustryWeight["weight_l1"] = IndustryWeight["weight_l1"] / TotalWeight
    SDS = ((IndustryWeight["weight"].fillna(0) - IndustryWeight["weight_l1"].fillna(0))**2).sum() ** 0.5
    return SDS

def sds_rb(f, idt, iid, x, args):
    for ix in x:
        if not isinstance(ix, list):
            return np.nan
    IndustryWeight = pd.DataFrame(x[:2], index=["code", "weight"]).T
    IndustryWeight_L1 = pd.DataFrame(x[2:], index=["code", "weight"]).T
    IndustryWeight = IndustryWeight[pd.notnull(IndustryWeight["code"]) & (~IndustryWeight["code"].isin(("alpha", "bond", "cash", "sigma", "r2")))]
    IndustryWeight_L1 = IndustryWeight_L1[pd.notnull(IndustryWeight_L1["code"]) & (~IndustryWeight_L1["code"].isin(("alpha", "bond", "cash", "sigma", "r2")))]
    if (IndustryWeight.shape[0]==0) or (IndustryWeight_L1.shape[0]==0):
        return np.nan
    IndustryWeight = pd.merge(IndustryWeight, IndustryWeight_L1, how="outer", left_on=["code"], right_on=["code"], suffixes=("", "_l1"))
    TotalWeight = IndustryWeight["weight"].sum()
    if TotalWeight<=0: return np.nan
    IndustryWeight["weight"] = IndustryWeight["weight"] / TotalWeight
    TotalWeight = IndustryWeight["weight_l1"].sum()
    if TotalWeight<=0: return np.nan
    IndustryWeight["weight_l1"] = IndustryWeight["weight_l1"] / TotalWeight
    SDS = ((IndustryWeight["weight"].fillna(0) - IndustryWeight["weight_l1"].fillna(0))**2).sum() ** 0.5
    return SDS

def asset_sds(f, idt, iid, x, args):
    Weight = np.array(x[:3])
    Weight_L1 = np.array(x[3:])
    Mask = (np.all(pd.isnull(Weight), axis=0) | np.all(pd.isnull(Weight_L1), axis=0))
    Weight[pd.isnull(Weight)] = 0
    Weight_L1[pd.isnull(Weight_L1)] = 0
    SDS = (np.sum((Weight - Weight_L1) ** 2, axis=0) + (np.sum(Weight, axis=0) - np.sum(Weight_L1, axis=0)) ** 2) ** 0.5
    SDS[Mask] = np.nan
    return SDS

def defFactor(args={}, debug=False):
    Factors = []
    
    LSQLDB = args["LSQLDB"]
    LHDF5DB = args["LHDF5DB"]
    
    # 基于持仓的资产配置 SDS
    FT = LDB.getTable("mf_cn_asset_portfolio", args={"公告时点字段": "info_pub_date", "回溯天数": 0, "多重映射": False, "截止日期递增": True})
    StockWeight = FT.getFactor("stock_weight", args={"回溯期数": 0, "原始值回溯天数": 365*5})
    BondWeight = FT.getFactor("bond_weight", args={"回溯期数": 0, "原始值回溯天数": 365*5})
    CashWeight = FT.getFactor("cash_weight", args={"回溯期数": 0, "原始值回溯天数": 365*5})
    StockWeight_l1 = FT.getFactor("stock_weight", args={"回溯期数": 1, "原始值回溯天数": 365*5})
    BondWeight_l1 = FT.getFactor("bond_weight", args={"回溯期数": 1, "原始值回溯天数": 365*5})
    CashWeight_l1 = FT.getFactor("cash_weight", args={"回溯期数": 1, "原始值回溯天数": 365*5})
    AssetSDS = QS.FactorDB.PointOperation(
        "asset_sds",
        [StockWeight, BondWeight, CashWeight, StockWeight_l1, BondWeight_l1, CashWeight_l1],
        sys_args={
            "算子": asset_sds,
            "运算时点": "多时点",
            "运算ID": "多ID"
        }
    )
    Factors.append(fd.fillna(AssetSDS, lookback=366, factor_name="asset_sds_hb"))
    
    # 基于持仓的行业配置 SDS
    FT = LSQLDB.getTable("mf_cn_industry_component", args={"公告时点字段": "info_pub_date", "回溯天数": 0, "多重映射": False, "截止日期递增": True, "排序字段": [("industry_standard", "ASC"), ("component_code", "ASC")], "筛选条件": "{Table}.component_name<>'行业投资合计'"})
    IndustryStandard = FT.getFactor("industry_standard", args={"回溯期数": 0, "原始值回溯天数": 365*5})
    IndustryComponentID = FT.getFactor("component_code", args={"回溯期数": 0, "原始值回溯天数": 365*5})
    IndustryWeight = FT.getFactor("weight_in_nv", args={"回溯期数": 0, "原始值回溯天数": 365*5})
    IndustryStandard_L1 = FT.getFactor("industry_standard", args={"回溯期数": 1, "原始值回溯天数": 365*5})
    IndustryComponentID_L1 = FT.getFactor("component_code", args={"回溯期数": 1, "原始值回溯天数": 365*5})
    IndustryWeight_L1 = FT.getFactor("weight_in_nv", args={"回溯期数": 1, "原始值回溯天数": 365*5})
    IndustrySDS = QS.FactorDB.PointOperation(
        "industry_sds",
        [IndustryStandard, IndustryComponentID, IndustryWeight, IndustryStandard_L1, IndustryComponentID_L1, IndustryWeight_L1],
        sys_args={
            "算子": industry_sds_hb,
            "运算时点": "单时点",
            "运算ID": "单ID"
        }
    )
    Factors.append(fd.fillna(IndustrySDS, lookback=366, factor_name="industry_sds_hb"))
    
    # 基于收益的资产配置 SDS
    FT = LHDF5DB.getTable("mf_cn_asset_portfolio_regress")
    StockWeight = FT.getFactor("stock")
    BondWeight = FT.getFactor("bond")
    CashWeight = FT.getFactor("cash")
    StockWeight_l1 = fd.lag(StockWeight, 20, 20)
    BondWeight_l1 = fd.lag(BondWeight, 20, 20)
    CashWeight_l1 = fd.lag(CashWeight, 20, 20)
    AssetSDS = QS.FactorDB.PointOperation(
        "asset_sds",
        [StockWeight, BondWeight, CashWeight, StockWeight_l1, BondWeight_l1, CashWeight_l1],
        sys_args={
            "算子": asset_sds,
            "运算时点": "多时点",
            "运算ID": "多ID"
        }
    )
    Factors.append(fd.fillna(AssetSDS, lookback=366, factor_name="asset_sds_20d"))
    
    # 基于收益的行业配置 SDS
    FT = LHDF5DB.getTable("mf_cn_industry_sw_allocation_sharpe_model", args={"公告时点字段": None, "回溯天数": 0, "多重映射": False})
    IndustryComponentID = FT.getFactor("component_code")
    IndustryWeight = FT.getFactor("weight_3m")
    IndustryComponentID_L1 = fd.lag(IndustryComponentID, 20, 20)
    IndustryWeight_L1 = fd.lag(IndustryWeight, 20, 20)
    IndustrySDS = QS.FactorDB.PointOperation(
        "industry_sw_sds_20d",
        [IndustryComponentID, IndustryWeight, IndustryComponentID_L1, IndustryWeight_L1],
        sys_args={
            "算子": sds_rb,
            "运算时点": "单时点",
            "运算ID": "单ID"
        }
    )
    Factors.append(IndustrySDS)
    
    # 基于收益的风格配置 SDS
    FT = LHDF5DB.getTable("mf_cn_style_citic_allocation_sharpe_model", args={"射": False})
    StyleComponentID = FT.getFactor("component_code")
    StyleWeight = FT.getFactor("weight_3m")
    StyleComponentID_L1 = fd.lag(StyleComponentID, 20, 20)
    StyleWeight_L1 = fd.lag(StyleWeight, 20, 20)
    StyleSDS = QS.FactorDB.PointOperation(
        "style_citic_sds_20d",
        [StyleComponentID, StyleWeight, StyleComponentID_L1, StyleWeight_L1],
        sys_args={
            "算子": sds_rb,
            "运算时点": "单时点",
            "运算ID": "单ID"
        }
    )
    Factors.append(StyleSDS)    
    
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_style_stability",
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
    
    LSQLDB = QS.FactorDB.SQLDB(logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Args = {"LSQLDB": LSQLDB, "LHDF5DB": TDB}
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
    
    LSQLDB.disconnect()
    TDB.disconnect()
    JYDB.disconnect()