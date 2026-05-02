# -*- coding: utf-8 -*-
"""
调整后基金大类资产穿透

债券型基金，使用penetrated穿透结果
货币型基金，使用regress穿透结果
其他基金，
    regress中的 r_square >= 0.5，用regress穿透结果
    regress中的 r_square <  0.5，用penetrated穿透结果
"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def adjust(f, idt, iid, x, args):
    penetrated, regress, r2_type, r_squared = x
    result = np.full(penetrated.shape, np.nan)
    result = np.where(r2_type == "债券型", penetrated, result)
    result = np.where(r2_type == "货币型", regress, result)
    adjusted = np.where(r_squared >= 0.5, regress, penetrated)
    result = np.where(~((r2_type == "债券型") | (r2_type == "货币型")), adjusted, result)
    return result


def adjust_end_date(f, idt, iid, x, args):
    s, r2_type, r_squared = x
    result = np.full(s.shape, None, dtype="O")
    result = np.where(r2_type == "债券型", s, result)
    adjusted = np.where(r_squared >= 0.5, None, s)
    result = np.where(~((r2_type == "债券型") | (r2_type == "货币型")), adjusted, result)
    return result


def adjust_r_squared(f, idt, iid, x, args):
    s, r2_type = x
    result = np.full(s.shape, np.nan)
    result = np.where(r2_type == "货币型", s, result)
    adjusted = np.where(s < 0.5, np.nan, s)
    result = np.where(~((r2_type == "债券型") | (r2_type == "货币型")), adjusted, result)
    return result


def defFactor(args={}, debug=False):
    Factors = []

    LDB = args["LDB"]
    TDB = args["TDB"]

    FT = TDB.getTable("mf_cn_type")
    r2_type = FT.getFactor("r2_type_first")
    
    if args["look_ahead"]:
        FT = LDB.getTable("mf_cn_asset_portfolio_penetrated", args={"只回溯时点": True, "回溯天数": np.inf})
    else:
        FT = LDB.getTable("mf_cn_asset_portfolio_penetrated", args={"只回溯时点": True, "回溯天数": np.inf, "公告时点字段": "info_pub_date"})
    bond_weight = FT.getFactor("bond_weight", )
    cash_weight = FT.getFactor("cash_weight")
    stock_weight = FT.getFactor("stock_weight")
    report_date = fd.strftime(FT.getFactor("report_date"), "%Y-%m-%d")

    FT = TDB.getTable("mf_cn_asset_portfolio_regress")
    bond_regress = FT.getFactor("bond")
    cash_regress = FT.getFactor("cash")
    stock_regress = FT.getFactor("stock")
    r_squared = FT.getFactor("r_squared")

    bond = QS.FactorDB.PointOperation("bond", [bond_weight, bond_regress, r2_type, r_squared], {"算子": adjust, "运算时点": "多时点", "运算ID": "多ID"})
    cash = QS.FactorDB.PointOperation("cash", [cash_weight, cash_regress, r2_type, r_squared], {"算子": adjust, "运算时点": "多时点", "运算ID": "多ID"})
    stock = QS.FactorDB.PointOperation("stock", [stock_weight, stock_regress, r2_type, r_squared], {"算子": adjust, "运算时点": "多时点", "运算ID": "多ID"})
    report_date = QS.FactorDB.PointOperation("report_date", [report_date, r2_type, r_squared], {"算子": adjust_end_date, "运算时点": "多时点", "运算ID": "多ID", "数据类型": "string"})
    r_squared = QS.FactorDB.PointOperation("r_squared", [r_squared, r2_type], {"算子": adjust_r_squared, "运算时点": "多时点", "运算ID": "多ID"})

    Factors.extend([bond, cash, stock, report_date, r_squared])

    UpdateArgs = {"因子表": ("mf_cn_asset_portfolio_adjusted" if args["look_ahead"] else "mf_cn_asset_portfolio_adjusted_no_lookahead"),
                  "默认起始日": dt.datetime(2002,1,1),
                  "最长回溯期": 365 * 5,
                  "IDs": "公募基金"}

    return (Factors, UpdateArgs)


if __name__ == "__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    LDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig.json", sys_args={"数据库名": "db_fund"}, logger=Logger)
    LDB.connect()
    
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()

    Factors, UpdateArgs = defFactor(args={"JYDB": JYDB, "LDB": LDB, "TDB": TDB, "look_ahead": False}, debug=False)

    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2020, 10, 9)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365*5), end_date=EndDT.date(), output_type="datetime")

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
    LDB.disconnect()
    JYDB.disconnect()