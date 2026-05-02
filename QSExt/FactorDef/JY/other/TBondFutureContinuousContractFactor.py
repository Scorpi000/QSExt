# -*- coding: utf-8 -*-
"""国债期货连续合约因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS

Factors = []

WDB = QS.FactorDB.WindDB2()
WDB.connect()

# 市场行情因子
FT = WDB.getTable("中国国债期货交易日行情")
Factors.append(FT.getFactor("开盘价(元)", new_name="开盘价"))
Factors.append(FT.getFactor("最高价(元)", new_name="最高价"))
Factors.append(FT.getFactor("最低价(元)", new_name="最低价"))
Factors.append(FT.getFactor("收盘价(元)", new_name="收盘价"))
Settlement = FT.getFactor("结算价(元)", new_name="结算价")
Factors.append(Settlement)
PreSettlement = FT.getFactor("前结算价(元)", new_name="前结算价")
Factors.append(PreSettlement)
Factors.append(FT.getFactor("成交量(手)", new_name="成交量"))
Factors.append(QS.FactorDB.Factorize(FT.getFactor("成交金额(万元)") * 10000, factor_name="成交金额"))
Factors.append(FT.getFactor("持仓量(手)", new_name="持仓量"))

# 证券特征
ContractMapping = WDB.getTable("中国期货连续(主力)合约和月合约映射表").getFactor("映射月合约Wind代码", new_name="月合约")
Factors.append(ContractMapping)
StandardIDs = ["T", "TF", "TS"]
FutureInfo = WDB.getTable("中国期货基本资料").readData(factor_names=["合约类型", "标准合约代码", "交易所", "上市日期", "挂牌基准价", "最后交易日期", "交割月份", "最后交割日"], ids=WDB.getTable("中国期货基本资料").getID(), dts=[dt.datetime.today()]).iloc[:, 0]
Mask = pd.Series(False, index=FutureInfo.index)
for iID in StandardIDs: Mask = (Mask | (FutureInfo["标准合约代码"]==iID))
Mask = (Mask & (FutureInfo["合约类型"]==1) & (FutureInfo["交易所"]=="CFFEX"))
FutureInfo = FutureInfo[Mask].loc[:, ["上市日期", "挂牌基准价", "最后交易日期", "交割月份", "最后交割日"]]
FutureInfo = pd.merge(FutureInfo, WDB.getTable("中国期货标准合约属性").readData(factor_names=["合约乘数"], ids=FutureInfo.index.tolist(), dts=[dt.datetime.today()]).iloc[:, 0], left_index=True, right_index=True)
def FeatureFun(f, idt, iid, x, args):
    ContractMapping = x[0]
    if f.DataType=="string": Data = np.full(shape=ContractMapping.shape, fill_value=None, dtype="O")
    else: Data = np.full(shape=ContractMapping.shape, fill_value=np.nan, dtype="float")
    for iID in pd.unique(ContractMapping.flatten()):
        if iID not in args["FutureInfo"].index: continue
        Data[ContractMapping==iID] = args["FutureInfo"].loc[iID, args["Field"]]
    return Data
Factors.append(QS.FactorDB.PointOperation("合约乘数", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"合约乘数"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"double"}))
Factors.append(QS.FactorDB.PointOperation("上市日期", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"上市日期"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"string"}))
Factors.append(QS.FactorDB.PointOperation("挂牌基准价", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"挂牌基准价"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"double"}))
Factors.append(QS.FactorDB.PointOperation("最后交易日期", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"最后交易日期"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"string"}))
Factors.append(QS.FactorDB.PointOperation("交割月份", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"交割月份"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"string"}))
Factors.append(QS.FactorDB.PointOperation("最后交割日", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"最后交割日"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"string"}))


# 收益率因子
def DayReturnFun(f, idt, iid, x, args):
    PreSettlement = pd.Series(x[1][0], index=x[2][0]).loc[x[2][1]]
    return x[0][0] / PreSettlement.values
DayReturn = QS.FactorDB.TimeOperation("日收益率", [Settlement, PreSettlement, ContractMapping], {"算子":DayReturnFun, "回溯期数":[1-1, 1-1, 2-1], "运算ID":"多ID"})
Factors.append(DayReturn)

def WeekReturnFun(f, idt, iid, x, args):
    CurDate = idt[-1].date()
    CurWeekDay = CurDate.weekday()
    for i in range(1, 8):
        iDT = idt[-i-1]
        if iDT is None: return np.full(shape=(x[0].shape[1],), fill_value=np.nan)
        iPreDate = iDT.date()
        iPreWeekDay = iPreDate.weekday()
        if (CurWeekDay-iPreWeekDay)!=(CurDate-iPreDate).days: break
    DayReturns = x[0][-i:]
    return np.nanprod(1+DayReturns, axis=0) - 1
Factors.append(QS.FactorDB.TimeOperation("周收益率", [DayReturn], {"算子":WeekReturnFun, "回溯期数":[8-1], "运算ID":"多ID"}))

def MonthReturnFun(f, idt, iid, x, args):
    CurDate = idt[-1].strftime("%Y%m%d")
    for i in range(1, 31):
        iDT = idt[-i-1]
        if iDT is None: return np.full(shape=(x[0].shape[1],), fill_value=np.nan)
        iPreDate = iDT.strftime("%Y%m%d")
        if (iPreDate[:6]!=CurDate[:6]): break
    DayReturns = x[0][-i:]
    return np.nanprod(1+DayReturns, axis=0) - 1
Factors.append(QS.FactorDB.TimeOperation("月收益率", [DayReturn], {"算子":MonthReturnFun, "回溯期数":[31-1], "运算ID":"多ID"}))

if __name__=="__main__":
    HDB = QS.FactorDB.HDF5DB()
    HDB.connect()
    WDB.connect()
    
    CFT = QS.FactorDB.CustomFT("TBondFutureContinuousContractFactor")
    CFT.addFactors(factor_list=Factors)

    IDs = ["T.CFE", "T_S.CFE", "T00.CFE", "T01.CFE", "T02.CFE"]# 10 年期国债期货
    IDs += ["TF.CFE", "TF_S.CFE", "TF00.CFE", "TF01.CFE", "TF02.CFE"]# 5 年期国债期货
    IDs += ["TS.CFE", "TS_S.CFE", "TS00.CFE", "TS01.CFE", "TS02.CFE"]# 2 年期国债期货
    
    if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2013, 9, 6)
    else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    EndDT = dt.datetime.today()
    #StartDT, EndDT = dt.datetime(2018, 9, 1), dt.datetime(2018, 9, 30)# debug
    
    DTs = WDB.getTable("中国期货交易日历").getDateTime(iid="CFFEX", start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国期货交易日历").getDateTime(iid="CFFEX", start_dt=StartDT-dt.timedelta(40), end_dt=EndDT)

    TargetTable = "TBondFutureContinuousContractFactor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler)
    
    HDB.disconnect()
    WDB.disconnect()