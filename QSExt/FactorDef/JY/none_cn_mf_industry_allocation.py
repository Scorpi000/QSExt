# -*- coding: utf-8 -*-
"""公募基金行业配置"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def calc_alloc(f, idt, iid, x, args):
    fund_type, fund_size, fund_status, component, weight, stock_industry = x
    fund_ids, stock_ids, target_types = args["fund_ids"], args["stock_ids"], args["target_types"]
    stock_industry = pd.DataFrame(stock_industry, index=idt, columns=stock_ids)
    fund_type = pd.DataFrame(fund_type, index=idt, columns=fund_ids)
    fund_size = pd.DataFrame(fund_size, index=idt, columns=fund_ids)
    fund_status = pd.DataFrame(fund_status, index=idt, columns=fund_ids)
    component = pd.DataFrame(component, index=idt, columns=fund_ids)
    weight = pd.DataFrame(weight, index=idt, columns=fund_ids)
    mask = ((fund_status==1) & pd.notnull(fund_size) & pd.notnull(fund_type) & pd.notnull(component))
    temp = pd.DataFrame(index=fund_ids, columns=["component_code", "weight"])
    rslt = pd.DataFrame(index=idt, columns=iid)
    for i, iDT in enumerate(idt):
        iSize = fund_size.iloc[i]
        iType = fund_type.iloc[i]
        temp["component_code"] = component.iloc[i]
        temp["weight"] = weight.iloc[i]
        iMask = mask.iloc[i]
        for jTargetType in target_types.keys():
            if target_types[jTargetType] is not None:
                ijMask = (iMask & (iType.isin(target_types[jTargetType])))
            else:
                ijMask = iMask
            ijTemp = temp[ijMask].copy()
            ijTemp["size"] = iSize[ijMask]
            ijTemp = pd.Series(
                ijTemp.apply(lambda s: (np.array(s["weight"], dtype=float) * s["size"]).tolist(), axis=1).sum(),
                index = ijTemp["component_code"].sum() or []
            )
            ijTemp = pd.DataFrame(ijTemp.groupby(level=0).sum(), columns=["amount"])
            ijTemp["industry"] = stock_industry.iloc[i].loc[ijTemp.index]
            ijAlloc = ijTemp.groupby(by=["industry"]).sum()["amount"] / ijTemp["amount"].sum()
            rslt.loc[iDT, jTargetType] = ijAlloc[pd.notnull(ijAlloc.index)].to_list()
    return rslt.to_numpy()
    
def get_code(f, idt, iid, x, args):
    mf_type = x[0]
    industry_index_ids = args["industry_index_ids"]
    res = np.full((x[0].shape[0], 3), None, dtype="O")
    res[:] = [[industry_index_ids] * 3] * mf_type.shape[0]
    return res


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    industry_index_ids = args["industry_index_ids"]
    target_types = args["target_types"]
    
    StockIDs = JYDB.getStockID(is_current=False)
    FundIDs = JYDB.getMutualFundID(is_current=False)
    
    FT = LDB.getTable("stock_cn_industry", args={"回溯天数": np.inf})
    stock_industry = FT.getFactor("citic_industry")
    
    fund_type = LDB.getTable("mf_cn_type", args={"回溯天数": np.inf}).getFactor("jy_type_second")
    fund_status = LDB.getTable("mf_cn_status", args={"回溯天数": np.inf}).getFactor("if_exist")
    fund_size = LDB.getTable("mf_cn_net_value_nafilled", args={"回溯天数": np.inf}).getFactor("net_value")
    
    FT = LDB.getTable("mf_cn_stock_component_penetrated", args={"多重映射": True})
    component = FT.getFactor("component_code")
    weight = FT.getFactor("weight")
    
    industry_code = QS.FactorDB.SectionOperation(
        "industry_code",
        [fund_type],
        sys_args={
            "算子": get_code,
            "参数": {"industry_index_ids": industry_index_ids},
            "描述子截面": [FundIDs],
            "运算时点": "多时点",
            "输出形式": "全截面",
            "数据类型": "object"
        }
    )
    Factors.append(industry_code)
    
    industry_alloc = QS.FactorDB.SectionOperation(
        "weight",
        [fund_type, fund_size, fund_status, component, weight, stock_industry],
        sys_args={
            "算子": calc_alloc,
            "参数": {
                "industry_index_ids": industry_index_ids,
                "target_types": target_types,
                "fund_ids": FundIDs,
                "stock_ids": StockIDs
            },
            "描述子截面": [FundIDs, FundIDs, FundIDs, FundIDs, FundIDs, StockIDs],
            "运算时点": "多时点",
            "输出形式": "全截面",
            "数据类型": "object"
        }
    )
    Factors.append(industry_alloc)
    
    UpdateArgs = {
        "因子表": "none_cn_mf_industry_allocation",
        "因子库参数": {"检查写入值": True},
        "默认起始日": dt.datetime(2005,1,1),
        "最长回溯期": 3650,
        "IDs": ["偏股主动型", "混合型", "所有"],
        "时点类型": "自然日",
        "更新频率": "季度"
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
    
    Args = {
        "JYDB": JYDB, 
        "LDB": TDB,
        "industry_index_ids": sorted(pd.read_csv("../conf/citic_industry.csv", index_col=0, header=0, encoding="utf-8", engine="python")["index_code"]),
        "target_types": {
            "偏股主动型": ["标准股票型", "偏股混合型"],
            "混合型": ["灵活配置型", "偏债平衡型"],
            "所有": None
        }
    }
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
                  if_exists="update", subprocess_num=3)
    
    TDB.disconnect()
    JYDB.disconnect()