# coding=utf-8
"""资金流因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar


def defFactor(fdi: FactorDefInput):
    Factors = []

    JYDB = fdi.FDB["JYDB"]
    
    StockDayBarDef = defStockDayBar(fdi=fdi)
    Volume = StockDayBarDef.getFactor(factor_name="volume")# 股

    # ### Level1 指标因子 #############################################################################
    FT = JYDB.getTable("股票交易资金流向", args={"AdditionalCondition": {"行情类别": "1"}, "MultiMapping": True, "Operator": sum, "OperatorDataType": "double"})
    ActiveBuyAmount = FT.getFactor("流入金额(元)")
    ActiveSellAmount = FT.getFactor("流出金额(元)")
    ActiveBuyVolume = FT.getFactor("流入量(股)")
    ActiveSellVolume = FT.getFactor("流出量(股)")
    
    # BS, 升序, 参考《银河量化十周年专题之五：选股因子及因子择时新视角》, 银河证券, 20140909
    Factors.append(fo.RollingApply(func=np.nansum, window=5)(ActiveBuyAmount - ActiveSellAmount, factor_args={"Name": "buy_minus_sell_5d_amt"}))
    Factors.append(fo.RollingApply(func=np.nansum, window=5)(ActiveBuyVolume - ActiveSellVolume, factor_args={"Name": "buy_minus_sell_5d_vol"}))
    
    # ### 散户量差
    FT = JYDB.getTable("股票交易资金流向", args={"AdditionalCondition": {"行情类别": "1", "单笔成交金额区间": "1,2"}, "MultiMapping": True, "Operator": sum, "OperatorDataType": "double"})
    SmallActiveBuyVolume = FT.getFactor("流入量(股)")
    SmallActiveSellVolume = FT.getFactor("流出量(股)")    
    
    Factors.append(rename((SmallActiveBuyVolume - SmallActiveSellVolume) / Volume, factor_name="small_trade_flow_1d"))

    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_factor_money_flow",
        MaxLookBack=max(365, StockDayBarDef.MaxLookBack),
        IDType="A股",
        Author="麦冬"
    )
