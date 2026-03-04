# -*- coding: utf-8 -*-
"""A股增减持"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


def sum_list(x):
    if isinstance(x, list):
        return np.nansum(np.array(x, dtype=float))
    else:
        return np.nan

@FactorOperatorized(operator_type="Point", args={"Arity": 2, "IDMode": "单ID", "DTMode": "单时点", "DataType": "double"})
def apply_prod_sum(f, idt, iid, x, args):
    if isinstance(x[0], list) and isinstance(x[1], list):
        return np.nansum(np.array(x[0], dtype=float) * np.array(x[1], dtype=float))
    else:
        return np.nan

@FactorOperatorized(operator_type="Point", args={"Arity": 7, "IDMode": "单ID", "DTMode": "单时点", "DataType": "object"})
def calc_shareholder_rslt(f, idt, iid, x, args):
    if not isinstance(x[0], list): return (np.nan,) * 3
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


def defFactor(fdi: FactorDefInput):
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    apply_sum = fo.Applymap(func=sum_list, dtype="double")
    
    # 国家队增减持
    FT = JYDB.getTable("A股国家队持股统计")
    Factors.append(apply_sum(FT.getFactor("持有A股数量增减(股)"), factor_args={"Name": "national_share_chg"}))
    Factors.append(apply_sum(FT.getFactor("持有A股数量增减幅度(%)"), factor_args={"Name": "national_ratio_chg"}))
    
    # 高管增减持
    FT = JYDB.getTable("公司领导人持股变动", args={"筛选条件": "({Table}.AlternationReason IN (11, 12, 23))"})
    ShareChg = FT.getFactor("变动股数(股)")
    Factors.append(apply_sum(ShareChg, factor_args={"Name": "leader_share_chg"}))
    Factors.append(apply_sum(FT.getFactor("变动比例(%)"), factor_args={"Name": "leader_ratio_chg"}))
    TotalAmtChg = apply_prod_sum(FT.getFactor("变动均价(元-股)"), ShareChg, factor_args={"Name": "leader_amount_chg"})
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
    ShareholderRslt = calc_shareholder_rslt(SNBeforeTransfer, SNAfterTransfer, SNAfterReceive, ShareChg, ShareChgRatio, AmtChg, ChgPrice, factor_args={"Name": "shareholder_rslt"})
    Factors.append(fo.Fetch(pos=0)(ShareholderRslt, factor_args={"Name": "shareholder_share_chg"}))    
    Factors.append(fo.Fetch(pos=1)(ShareholderRslt, factor_args={"Name": "shareholder_ratio_chg"}))    
    Factors.append(fo.Fetch(pos=2)(ShareholderRslt, factor_args={"Name": "shareholder_amount_chg"}))   
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_share_chg",
        MaxLookBack=365,
        IDType="A股",
        Author="麦冬"
    )
