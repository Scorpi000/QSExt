# coding=utf-8
"""Barra 模型因子(TODO)"""
import datetime as dt
import UpdateDate
import numpy as np
import pandas as pd
import statsmodels.api as sm

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

HDB = QS.FactorDB.HDF5DB()
HDB.connect()


# ### 描述子 ###########################################################################
DescriptorNames = ['LNCAP', 'NLSIZE', 'BETA', 'RSTR', 'DASTD', 'CMRA', 'HSIGMA', 'BTOP', 'STOM', 'STOQ', 'STOA', 'EPFWD', 'CETOP', 'ETOP', 'EGRLF', 'EGRSF', 'EGRO', 'SGRO', 'MLEV', 'BLEV', 'DTOA']
FT = HDB.getTable("BarraDescriptor")
Descriptors = {iDescriptorName:FT.getFactor(iDescriptorName) for iDescriptorName in DescriptorNames}


# ### 辅助因子 ###########################################################################
ESTU = FT.getFactor("ESTU")
Industry = FT.getFactor("Industry")

FT = HDB.getTable("ElementaryFactor")
Cap = FT.getFactor("总市值")
IsListed = FT.getFactor("是否在市")


# ### 描述子第一次标准化 ###########################################################################
def StandardizeFun(f, idt, iid, x, args):
    Mask = ((x[2]==1) & pd.notnull(x[0]) & pd.notnull(x[1]))
    Weight = x[1][Mask]
    Data = x[0][Mask]
    Avg = np.nansum(Data*(Weight/np.sum(Weight)))
    Std = np.nanstd(Data)
    return (x[0]-Avg)/Std
for iDescriptorName in DescriptorNames:
    Descriptors[iDescriptorName] = QS.FactorDB.SectionOperation(iDescriptorName, [Descriptors[iDescriptorName], Cap, ESTU], {"算子":StandardizeFun})


# ### 描述子异常值处理 ###########################################################################
def WinsorizeFun(f, idt, iid, x, args):
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
for iDescriptorName in DescriptorNames:
    Descriptors[iDescriptorName] = QS.FactorDB.SectionOperation(iDescriptorName, [Descriptors[iDescriptorName]], {"算子":WinsorizeFun})


# ### 描述子第二次标准化 ###########################################################################
for iDescriptorName in DescriptorNames:
    Descriptors[iDescriptorName] = QS.FactorDB.SectionOperation(iDescriptorName, [Descriptors[iDescriptorName], Cap, ESTU], {"算子":StandardizeFun})


# ### 合并描述子 ##################################################################################
Factors = {}
Factors["Size"] = Descriptors["LNCAP"]
Factors["Beta"] = Descriptors["BETA"]
Factors["Momentum"] = Descriptors["RSTR"]
Factors["ResidualVolatility"] = fd.nanmean(Descriptors['DASTD'], Descriptors['CMRA'], Descriptors['HSIGMA'], weights=[0.74,0.16,0.1], ignore_nan_weight=True)
Factors["NonlinearSize"] = Descriptors["NLSIZE"]
Factors["BookToPrice"] = Descriptors["BTOP"]
Factors["Liquidity"] = fd.nanmean(Descriptors["STOM"], Descriptors["STOQ"], Descriptors["STOA"], weights=[0.35,0.35,0.3], ignore_nan_weight=True)
Factors["EarningsYield"] = fd.nanmean(Descriptors['EPFWD'], Descriptors['CETOP'], Descriptors['ETOP'], weights=[0.68,0.21,0.11], ignore_nan_weight=True)
Factors["Growth"] = fd.nanmean(Descriptors['EGRLF'], Descriptors['EGRSF'], Descriptors['EGRO'], Descriptors['SGRO'], weights=[0.18,0.11,0.24,0.47], ignore_nan_weight=True)
Factors["Leverage"] = fd.nanmean(Descriptors['MLEV'], Descriptors['DTOA'], Descriptors['BLEV'], weights=[0.38,0.35,0.27], ignore_nan_weight=True)


# ### 风格因子第一次标准化 ###########################################################################
for iFactorName, iFactor in Factors.items():
    Factors[iFactorName] = QS.FactorDB.SectionOperation(iFactorName, [iFactor,Cap,ESTU], {"算子":StandardizeFun})


# ### 正交化 ###########################################################################
def OrthogonalizeFun(f, idt, iid, x, args):
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
Factors["ResidualVolatility"] = QS.FactorDB.SectionOperation("ResidualVolatility", [Factors["ResidualVolatility"],IsListed,Factors["Beta"],Factors["Size"]],{"算子":OrthogonalizeFun,"输出形式":"全截面"})
Factors["Liquidity"] = QS.FactorDB.SectionOperation("Liquidity",[Factors["Liquidity"],IsListed,Factors["Size"]],{"算子":OrthogonalizeFun,"输出形式":"全截面"})
Factors["ResidualVolatility"] = QS.FactorDB.SectionOperation("ResidualVolatility",[Factors["ResidualVolatility"],Cap,ESTU],{"算子":StandardizeFun})
Factors["Liquidity"] = QS.FactorDB.SectionOperation("Liquidity",[Factors["Liquidity"],Cap,ESTU],{"算子":StandardizeFun})


# ### 缺失值填充 ###########################################################################
def FillNaFun(f, idt, iid, x, args):
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
    Rslt = x[0]
    Rslt[Mask] = FactorData
    return Rslt
for iFactorName, iFactor in Factors.items():
    Factors[iFactorName] = QS.FactorDB.SectionOperation(iFactorName, [iFactor,Cap,Industry,IsListed], {"算子":FillNaFun})

# ### 风格因子第二次标准化 ###########################################################################
for iFactorName, iFactor in Factors.items():
    Factors[iFactorName] = QS.FactorDB.SectionOperation(iFactorName, [iFactor,Cap,ESTU], {"算子":StandardizeFun})

Factors = [Factors[iFactor] for iFactor in sorted(Factors.keys())]

if __name__=="__main__":
    WDB = QS.FactorDB.WindDB2()
    WDB.connect()
    
    CFT = QS.FactorDB.CustomFT("BarraFactor")
    CFT.addFactors(factor_list=Factors)
    
    IDs = WDB.getStockID(index_id="全体A股", is_current=False)
    #IDs = ["000001.SZ", "000003.SZ", "603297.SH"]# debug
    
    #if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2018, 8, 31, 23, 59, 59, 999999)
    #else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    #EndDT = dt.datetime(2018, 10, 31, 23, 59, 59, 999999)
    StartDT, EndDT = UpdateDate.StartDT, UpdateDate.EndDT
    
    DTs = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT-dt.timedelta(365), end_dt=EndDT)

    TargetTable = "BarraFactor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler)
    
    HDB.disconnect()
    WDB.disconnect()