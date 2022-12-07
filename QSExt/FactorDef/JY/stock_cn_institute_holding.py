# -*- coding: utf-8 -*-
"""A股机构投资者"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools


def sum_list(x):
    if isinstance(x, list):
        return np.nansum(np.array(x, dtype=float))
    else:
        return np.nan

def defFactor(args={}):
    Factors = []
    
    JYDB = args["JYDB"]
    
    # 机构持股
    FT = JYDB.getTable("股东持股统计", args={"公告时点字段": None, "忽略时间": True})
    InstituteHolding_A = FT.getFactor("机构持有A股数量合计(股)", new_name="institute_holding_num_a")
    InstituteHoldingRatio_A = Factorize(FT.getFactor("机构持有A股比例合计(%)") / 100, factor_name="institute_holding_ratio_a")
    Factors += [InstituteHolding_A, InstituteHoldingRatio_A]
    
    InstituteHolding_AUnrestricted = FT.getFactor("机构持有无限售流通A股数量合计(股)", new_name="institute_holding_num_a_unrestricted")
    InstituteHoldingRatio_AUnrestricted = Factorize(FT.getFactor("机构持有无限售流通A股比例合计(%)") / 100, factor_name="institute_holding_ratio_a_unrestricted")
    Factors += [InstituteHolding_AUnrestricted, InstituteHoldingRatio_AUnrestricted]
        
    InstituteHolding = FT.getFactor("机构持股数量合计(股)", new_name="institute_holding_num")
    InstituteHoldingRatio = Factorize(FT.getFactor("机构持股比例合计(%)") / 100, factor_name="institute_holding_ratio")
    Factors += [InstituteHolding, InstituteHoldingRatio]
    
    # 国家队持股
    FT = JYDB.getTable("A股国家队持股统计", args={"公告时点字段": None, "忽略时间": True})
    NationalHolding = fd.applymap(FT.getFactor("持有A股总数(股)"), sum_list, data_type="double", factor_name="national_holding_num_a")
    NationalHoldingRatio = Factorize(fd.applymap(FT.getFactor("占总股本比例(%)"), sum_list, data_type="double") / 100, factor_name="institute_holding_ratio_a")
    Factors += [NationalHolding, NationalHoldingRatio]
    
    NationalHolding_AUnrestricted = fd.applymap(FT.getFactor("其中-无限售A股数(股)"), sum_list, data_type="double", factor_name="national_holding_num_a_unrestricted")
    NationalHoldingRatio_AUnrestricted = Factorize(NationalHolding_AUnrestricted / NationalHolding * NationalHoldingRatio, factor_name="institute_holding_ratio_a_unrestricted")
    Factors += [NationalHolding_AUnrestricted, NationalHoldingRatio_AUnrestricted]    
        
    
    UpdateArgs = {
        "因子表": "stock_cn_institute_holding",
        "默认起始日": dt.datetime(2002, 1, 1),
        "最长回溯期": 365,
        "IDs": "股票",
        "时点类型": "自然日"
    }    
    
    return Factors, UpdateArgs


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB()
    JYDB.connect()
    
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = JYDB.getStockID()
    
    Args = {"JYDB": JYDB, "LDB": TDB}
    Factors, UpdateArgs = defFactor(args=Args)
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTs)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
        factor_db=TDB, table_name=TargetTable,
        if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    JYDB.disconnect()