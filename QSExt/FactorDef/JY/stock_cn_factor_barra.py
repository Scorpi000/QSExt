# coding=utf-8
"""Barra 模型因子"""
import datetime as dt

import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_factor_barra_descriptor import defFactor as defBarraDescriptor
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar
from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStockStatus


@FactorOperatorized(operator_type="Section", args={"Arity": 3, "OutputMode": "全截面", "DTMode": "单时点"})
def standardize(f, idt, iid, x, args):
    Mask = ((x[2]==1) & pd.notnull(x[0]) & pd.notnull(x[1]))
    Weight = x[1][Mask]
    Data = x[0][Mask]
    Avg = np.nansum(Data*(Weight/np.sum(Weight)))
    Std = np.nanstd(Data)
    return (x[0]-Avg)/Std

@FactorOperatorized(operator_type="Section", args={"Arity": 1, "OutputMode": "全截面", "DTMode": "单时点"})
def winsorize(f, idt, iid, x, args):
    Data = x[0]
    Max = np.nanmax(Data)
    Min = np.nanmin(Data)
    sPlus = max((0,min((1,0.5/(Max-3)))))
    sMinus = max((0,min((1,0.5/(-3-Min)))))
    Rslt = np.zeros(Data.shape)+np.nan
    Mask = (Data>3)
    Rslt[Mask] = 3*(1-sPlus)+sPlus*Data[Mask]
    Mask = (Data<-3)
    Rslt[Mask] = -3*(1-sMinus)+sMinus*Data[Mask]
    Mask = ((Data>=-3) & (Data<=3))
    Rslt[Mask] = Data[Mask]
    return Rslt

@FactorOperatorized(operator_type="Section", args={"Arity": None, "OutputMode": "全截面", "DTMode": "单时点"})
def orthogonalize(f, idt, iid, x, args):
    StdData = np.zeros(x[0].shape)+np.nan
    Y = x[0].astype('float')
    X = np.array(x[2:]).T.astype('float')
    Mask = ((x[1]==1) & (np.sum(np.isnan(X),axis=1)==0) & (~np.isnan(Y)))
    if np.sum(Mask)==0: return StdData
    Y = Y[Mask]
    X = X[Mask,:]
    X = sm.add_constant(X, prepend=True)
    Result = sm.OLS(Y,X,missing='drop').fit()
    StdData[Mask] = Result.resid
    return StdData

@FactorOperatorized(operator_type="Section", args={"Arity": 4, "OutputMode": "全截面", "DTMode": "单时点"})
def fillna(f, idt, iid, x, args):
    Mask = (x[3]==1)
    xAllData = np.log(x[1][Mask])
    ClassData = x[2][Mask]
    FactorData = x[0][Mask]
    NotNAMask = pd.notnull(FactorData)
    if FactorData.shape[0]>np.sum(NotNAMask):# 存在缺失值
        AllClasses = pd.unique(ClassData[(~NotNAMask)])
        for iClass in AllClasses:
            if pd.isnull(iClass):
                iNotNAMask = NotNAMask
                iNAMask = ((~NotNAMask) & pd.isnull(ClassData))
            else:
                iNotNAMask = ((NotNAMask) & (ClassData==iClass))
                iNAMask = ((~NotNAMask) & (ClassData==iClass))
            xData = xAllData[iNotNAMask]
            yData = FactorData[iNotNAMask]
            iMask = pd.notnull(xData)
            xData = xData[iMask]
            yData = yData[iMask]
            iNotNANum = xData.shape[0]
            if iNotNANum==0:
                continue
            xMean = np.mean(xData)
            yMean = np.mean(yData)
            Beta = (np.sum(xData*yData)-iNotNANum*xMean*yMean)/(np.sum(xData**2)-iNotNANum*xMean**2)
            Alpha = yMean-xMean*Beta
            FactorData[iNAMask] = Alpha+Beta*xAllData[iNAMask]
    Rslt = x[0].copy()
    Rslt[Mask] = FactorData
    return Rslt

def defFactor(fdi: FactorDefInput):
    # ### 描述子 ###########################################################################
    BarraDescriptorDef = defBarraDescriptor(fdi=fdi)
    DescriptorNames = ['LNCAP', 'NLSIZE', 'BETA', 'RSTR', 'DASTD', 'CMRA', 'HSIGMA', 'BTOP', 'STOM', 'STOQ', 'STOA', 'EPFWD', 'CETOP', 'ETOP', 'EGRLF', 'EGRSF', 'EGRO', 'SGRO', 'MLEV', 'BLEV', 'DTOA']
    Descriptors = {iDescriptorName: BarraDescriptorDef.getFactor(factor_name=iDescriptorName) for iDescriptorName in DescriptorNames}

    # ### 辅助因子 ###########################################################################
    ESTU = BarraDescriptorDef.getFactor("ESTU")
    Industry = BarraDescriptorDef.getFactor("barra_industry")
    
    StockDayBarDef = defStockDayBar(fdi=fdi)
    Cap = StockDayBarDef.getFactor("total_cap")# 万元
    
    StockStatusDef = defStockStatus(fdi=fdi)
    IsListed = StockStatusDef.getFactor("if_listed")

    for iDescriptorName in DescriptorNames:
        iFactor = standardize(Descriptors[iDescriptorName], Cap, ESTU)# 描述子第一次标准化
        iFactor = winsorize(iFactor)# 描述子异常值处理
        Descriptors[iDescriptorName] = standardize(iFactor, Cap, ESTU)# 描述子第二次标准化
    
    # ### 合并描述子 ##################################################################################
    Factors = {}
    Factors["Size"] = Descriptors["LNCAP"]
    Factors["Beta"] = Descriptors["BETA"]
    Factors["Momentum"] = Descriptors["RSTR"]
    Factors["ResidualVolatility"] = fo.Mean(weights=[0.74, 0.16, 0.1], ignore_nan_weight=True)(Descriptors['DASTD'], Descriptors['CMRA'], Descriptors['HSIGMA'])
    Factors["NonlinearSize"] = Descriptors["NLSIZE"]
    Factors["BookToPrice"] = Descriptors["BTOP"]
    Factors["Liquidity"] = fo.Mean(weights=[0.35, 0.35, 0.3], ignore_nan_weight=True)(Descriptors["STOM"], Descriptors["STOQ"], Descriptors["STOA"])
    Factors["EarningsYield"] = fo.Mean(weights=[0.68, 0.21, 0.11], ignore_nan_weight=True)(Descriptors['EPFWD'], Descriptors['CETOP'], Descriptors['ETOP'])
    Factors["Growth"] = fo.Mean(weights=[0.18, 0.11, 0.24, 0.47], ignore_nan_weight=True)(Descriptors['EGRLF'], Descriptors['EGRSF'], Descriptors['EGRO'], Descriptors['SGRO'])
    Factors["Leverage"] = fo.Mean(weights=[0.38, 0.35, 0.27], ignore_nan_weight=True)(Descriptors['MLEV'], Descriptors['DTOA'], Descriptors['BLEV'])

    # ### 风格因子第一次标准化 ###########################################################################
    for iFactorName, iFactor in Factors.items():
        Factors[iFactorName] = standardize(iFactor, Cap, ESTU)

    # ### 正交化 ###########################################################################
    Factors["ResidualVolatility"] = orthogonalize(Factors["ResidualVolatility"], IsListed, Factors["Beta"], Factors["Size"])
    Factors["Liquidity"] = orthogonalize(Factors["Liquidity"], IsListed, Factors["Size"])
    Factors["ResidualVolatility"] = standardize(Factors["ResidualVolatility"], Cap, ESTU)
    Factors["Liquidity"] = standardize(Factors["Liquidity"], Cap, ESTU)
    
    for iFactorName, iFactor in Factors.items():
        iFactor = fillna(iFactor, Cap, Industry, IsListed)# 缺失值填充
        Factors[iFactorName] = standardize(iFactor, Cap, ESTU, factor_args={"Name": iFactorName})# 风格因子第二次标准化
    
    Factors = [Factors[iFactor] for iFactor in sorted(Factors.keys())]

    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_factor_barra",
        MaxLookBack=max(365, BarraDescriptorDef.MaxLookBack, StockDayBarDef.MaxLookBack, StockStatusDef.MaxLookBack), 
        IDType="A股",
        Author="麦冬"
    )
