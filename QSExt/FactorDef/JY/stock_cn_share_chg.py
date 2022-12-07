# -*- coding: utf-8 -*-
"""A股增减持"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

def apply_sum(x):
    if isinstance(x, list):
        return np.nansum(np.array(x, dtype=float))
    else:
        return np.nan

def apply_prod_sum(x):
    if isinstance(x[0], list) and isinstance(x[1], list):
        return np.nansum(np.array(x[0], dtype=float) * np.array(x[1], dtype=float))
    else:
        return np.nan

def calc_shareholder_rslt(f, idt, iid, x, args):
    if not isinstance(x[0], list): return (np.nan,)*3
    Transfer = np.array(x[0], dtype="O")
    Transfer = np.where(pd.notnull(Transfer), Transfer, np.array(x[1], dtype="O"))
    Receiver = np.array(x[2], dtype="O")
    ShareChg, ShareChgRatio, AmtChg, ChgPrice = np.array(x[3], dtype=float), np.array(x[4], dtype=float), np.array(x[5], dtype=float), np.array(x[6], dtype=float)
    IncMask = (pd.isnull(Transfer) & pd.notnull(Receiver))
    DecMask = (pd.notnull(Transfer) & pd.isnull(Receiver))
    ShareNetInc = np.nansum(ShareChg[IncMask]) - np.nansum(ShareChg[DecMask])
    ShareRatioNetInc = np.nansum(ShareChgRatio[IncMask]) - np.nansum(ShareChgRatio[DecMask])
    AmtChg = np.where(pd.notnull(AmtChg), AmtChg, ChgPrice * ShareChg)
    AmtNetInc = np.nansum(AmtChg[IncMask]) - np.nansum(AmtChg[DecMask])
    return (ShareNetInc, ShareRatioNetInc, AmtNetInc)


# args:
# JYDB: 聚源因子库对象
# LDB: 本地因子库对象
def defFactor(args={}):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    
    # 国家队增减持
    FT = JYDB.getTable("A股国家队持股统计")
    Factors.append(fd.applymap(FT.getFactor("持有A股数量增减(股)"), apply_sum, factor_name="national_share_chg"))
    Factors.append(fd.applymap(FT.getFactor("持有A股数量增减幅度(%)"), apply_sum, factor_name="national_ratio_chg"))
    
    # 高管增减持
    FT = JYDB.getTable("公司领导人持股变动", args={"筛选条件": "({Table}.AlternationReason IN (11, 12, 23))"})
    ShareChg = FT.getFactor("变动股数(股)")
    Factors.append(fd.applymap(ShareChg, apply_sum, factor_name="leader_share_chg"))
    Factors.append(fd.applymap(FT.getFactor("变动比例(%)"), apply_sum, factor_name="leader_ratio_chg"))
    TotalAmtChg = QS.FactorDB.PointOperation(
        "leader_amount_chg",
        [FT.getFactor("变动均价(元-股)"), ShareChg],
        sys_args={
            "算子": apply_prod_sum,
            "参数": {},
            "运算时点": "单时点",
            "运算ID": "单ID",
            "数据类型": "double"
        }
    )
    Factors.append(TotalAmtChg)
    
    # 股东增减持
    FT = JYDB.getTable("股东股权变动", args={"筛选条件": "((({Table}.SNBeforeTran IS NOT NULL OR {Table}.SNAfterTran IS NOT NULL) AND {Table}.SNAfterRece IS NULL) OR ({Table}.SNBeforeTran IS NULL AND {Table}.SNAfterTran IS NULL AND {Table}.SNAfterRece IS NOT NULL))"})
    SNBeforeTransfer = FT.getFactor("出让前股东序号")
    SNAfterTransfer = FT.getFactor("出让后股东序号")
    SNAfterReceive = FT.getFactor("受让后股东序号")
    ShareChg = FT.getFactor("涉及股数(股)")
    ShareChgRatio = FT.getFactor("占总股本比例")
    AmtChg = FT.getFactor("交易金额(元)")
    ChgPrice = FT.getFactor("交易价格(元-股)")
    ShareholderRslt = QS.FactorDB.PointOperation(
        "shareholder_rslt",
        [SNBeforeTransfer, SNAfterTransfer, SNAfterReceive, ShareChg, ShareChgRatio, AmtChg, ChgPrice],
        sys_args={
            "算子": calc_shareholder_rslt,
            "参数": {},
            "运算时点": "单时点",
            "运算ID": "单ID",
            "数据类型": "object"
        }
    )
    Factors.append(fd.fetch(ShareholderRslt, 0, factor_name="shareholder_share_chg"))    
    Factors.append(fd.fetch(ShareholderRslt, 1, factor_name="shareholder_ratio_chg"))    
    Factors.append(fd.fetch(ShareholderRslt, 2, factor_name="shareholder_amount_chg"))    
    
    UpdateArgs = {
        "因子表": "stock_cn_share_chg",
        "默认起始日": dt.datetime(2005, 1, 1),
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