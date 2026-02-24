# coding=utf-8
"""动量因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.BasicOperator import rename
from QuantStudio.Core.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_day_bar_adj_backward_nafilled import defFactor as defStockAdjDayBar
from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStockStatus


@FactorOperatorized(operator_type="Time", args={"Arity": 2, "ModelArgs": {"非空率": 0.8}, "LookBack":[2-1, 2-1], "IDMode": "多ID", "DTMode": "单时点"})
def calcMomentum(f, idt, iid, x, args):
    FirstClose = x[0][0,:]
    LastClose = x[0][-1,:]
    IfTrading = x[1]
    Len = IfTrading.shape[0]
    Mask = (np.sum(IfTrading==1, axis=0) / Len < args['非空率'])
    return LastClose / np.where((FirstClose==0) | Mask, np.nan, FirstClose) - 1

def defFactor(fdi: FactorDefInput):
    Factors = []

    # ### 日行情因子 #############################################################################
    StockAdjDayBarDef = defStockAdjDayBar(fdi=fdi)
    AdjClose = StockAdjDayBarDef.getFactor(factor_name="close", def_path="...")
    StockStatusDef = defStockStatus(fdi=fdi)
    IfTrading = StockStatusDef.getFactor(factor_name="if_trading", def_path="...")
    IfListed = StockStatusDef.getFactor(factor_name="if_listed", def_path="...")
    Mask = ((IfListed==1) & (IfTrading==1))

    # 计算RTN_1D
    RTN_1D = calcMomentum(AdjClose, Mask, factor_args={"Name": "rtn_1d"})
    Factors.append(RTN_1D)
    
    # 计算RTN_5D
    RTN_5D = calcMomentum.new(args={"LookBack": [6-1, 6-1]})(AdjClose, Mask, factor_args={"Name": "rtn_5d"})
    Factors.append(RTN_5D)
    
    # 计算RTN_20D
    RTN_20D = calcMomentum.new(args={"LookBack": [21-1, 21-1]})(AdjClose, Mask, factor_args={"Name": "rtn_20d"})
    Factors.append(RTN_20D)

    # 计算RTN_60D
    RTN_60D = calcMomentum.new(args={"LookBack": [61-1, 61-1]})(AdjClose, Mask, factor_args={"Name": "rtn_60d"})
    Factors.append(RTN_60D)
    
    # 计算RTN_120D
    RTN_120D = calcMomentum.new(args={"LookBack": [121-1, 121-1]})(AdjClose, Mask, factor_args={"Name": "rtn_120d"})
    Factors.append(RTN_120D)
    
    # 计算RTN_180D
    RTN_180D = calcMomentum.new(args={"LookBack": [181-1, 181-1]})(AdjClose, Mask, factor_args={"Name": "rtn_180d"})
    Factors.append(RTN_180D)
    
    #计算RTN_240D
    RTN_240D = calcMomentum.new(args={"LookBack": [241-1, 241-1]})(AdjClose, Mask, factor_args={"Name": "rtn_240d"})
    Factors.append(RTN_240D)

    #计算RTN_720D
    RTN_720D = calcMomentum.new(args={"LookBack": [721-1, 721-1]})(AdjClose, Mask, factor_args={"Name": "rtn_720d"})
    Factors.append(RTN_720D)
    
    #计算RTN_1200D
    RTN_1200D = calcMomentum.new(args={"LookBack": [1201-1, 1201-1]})(AdjClose, Mask, factor_args={"Name": "rtn_1200d"})
    Factors.append(RTN_1200D)
    
    return FactorDef(
        FactorList=Factors,
        TargetTable="stock_cn_factor_momentum",
        MaxLookBack=max(365 * 6, StockAdjDayBarDef.MaxLookBack, StockStatusDef.MaxLookBack), 
        IDType="A股",
        Author="麦冬"
    )
