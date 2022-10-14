# -*- coding: utf-8 -*-
"""股指期货连续合约因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS

def FeatureFun(f, idt, iid, x, args):
    ContractMapping = x[0]
    if f.DataType=="string": Data = np.full(shape=ContractMapping.shape, fill_value=None, dtype="O")
    else: Data = np.full(shape=ContractMapping.shape, fill_value=np.nan, dtype="float")
    for iID in pd.unique(ContractMapping.flatten()):
        if iID not in args["FutureInfo"].index: continue
        Data[ContractMapping==iID] = args["FutureInfo"].loc[iID, args["Field"]]
    return Data

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

def MonthReturnFun(f, idt, iid, x, args):
    CurDate = idt[-1].strftime("%Y%m%d")
    for i in range(1, 31):
        iDT = idt[-i-1]
        if iDT is None: return np.full(shape=(x[0].shape[1],), fill_value=np.nan)
        iPreDate = iDT.strftime("%Y%m%d")
        if (iPreDate[:6]!=CurDate[:6]): break
    DayReturns = x[0][-i:]
    return np.nanprod(1+DayReturns, axis=0) - 1

if __name__=="__main__":
    Factors = []

    WDB = QS.FactorDB.WindDB2()
    WDB.connect()
    
    # 市场行情因子
    FT = WDB.getTable("中国股指期货日行情")
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

    # 获取合约信息
    StandardIDs = ["IF", "IH", "IC"]
    FutureInfo = WDB.getTable("中国期货基本资料").readData(factor_names=["合约类型", "标准合约代码", "交易所", "上市日期", "挂牌基准价", "最后交易日期", "交割月份", "最后交割日"], ids=WDB.getTable("中国期货基本资料").getID(), dts=[dt.datetime.today()]).iloc[:, 0]
    Mask = pd.Series(False, index=FutureInfo.index)
    for iID in StandardIDs: Mask = (Mask | (FutureInfo["标准合约代码"]==iID))
    Mask = (Mask & (FutureInfo["合约类型"]==1) & (FutureInfo["交易所"]=="CFFEX"))# 合约类型: 1: 月合约, 2: 连续合约
    FutureInfo = FutureInfo[Mask].loc[:, ["上市日期", "挂牌基准价", "最后交易日期", "交割月份", "最后交割日"]]
    FutureInfo = pd.merge(FutureInfo, WDB.getTable("中国期货标准合约属性").readData(factor_names=["合约乘数"], ids=FutureInfo.index.tolist(), dts=[dt.datetime.today()]).iloc[:, 0], left_index=True, right_index=True)

    Factors.append(QS.FactorDB.PointOperation("合约乘数", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"合约乘数"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"double"}))
    Factors.append(QS.FactorDB.PointOperation("上市日期", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"上市日期"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"string"}))
    Factors.append(QS.FactorDB.PointOperation("挂牌基准价", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"挂牌基准价"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"double"}))
    Factors.append(QS.FactorDB.PointOperation("最后交易日期", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"最后交易日期"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"string"}))
    Factors.append(QS.FactorDB.PointOperation("交割月份", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"交割月份"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"string"}))
    Factors.append(QS.FactorDB.PointOperation("最后交割日", [ContractMapping], {"算子":FeatureFun, "参数":{"FutureInfo":FutureInfo, "Field":"最后交割日"}, "运算时点":"多时点", "运算ID":"多ID", "数据类型":"string"}))

    # 收益率因子
    DayReturn = QS.FactorDB.Factorize(Settlement / PreSettlement - 1, factor_name="日收益率")
    Factors.append(DayReturn)
    Factors.append(QS.FactorDB.TimeOperation("周收益率", [DayReturn], {"算子":WeekReturnFun, "回溯期数":[8-1], "运算ID":"多ID"}))
    Factors.append(QS.FactorDB.TimeOperation("月收益率", [DayReturn], {"算子":MonthReturnFun, "回溯期数":[31-1], "运算ID":"多ID"}))
    
    CFT = QS.FactorDB.CustomFT("IndexFutureContinuousContractFactor")
    CFT.addFactors(factor_list=Factors)
    
    HDB = QS.FactorDB.HDF5DB()
    HDB.connect()
    
    # 设置 ID 序列
    IDs = ["IF.CFE", "IF_S.CFE", "IF00.CFE", "IF01.CFE", "IF02.CFE", "IF03.CFE"]# 沪深 300 股指期货, 主力合约, 次主力合约, 当月合约, 下月合约, 第一季月, 第二季月
    IDs += ["IH.CFE", "IH_S.CFE", "IH00.CFE", "IH01.CFE", "IH02.CFE", "IH03.CFE"]# 上证 50 股指期货, 主力合约, 次主力合约, 当月合约, 下月合约, 第一季月, 第二季月
    IDs += ["IC.CFE", "IC_S.CFE", "IC00.CFE", "IC01.CFE", "IC02.CFE", "IC03.CFE"]# 中证 500 股指期货, 主力合约, 次主力合约, 当月合约, 下月合约, 第一季月, 第二季月
    
    InitPrice = PreSettlement.readData(dts=[dt.datetime(2010, 4, 16)], ids=IDs[:6])
    InitPrice = pd.DataFrame(np.c_[InitPrice.values, PreSettlement.readData(dts=[dt.datetime(2015,4,16)], ids=IDs[6:]).values], columns=IDs, index=[dt.datetime(2010, 4, 15)])
    
    # 设置时间序列
    #StartDT = dt.datetime(2010, 5, 1)# debug
    if CFT.Name not in HDB.TableNames:
        StartDT = dt.datetime(2010, 4, 16)
    else:
        StartDT = HDB.getTable(CFT.Name).getDateTime()[-1]
        AdjPrice = HDB.getTable(CFT.Name).readData(factor_names=["连续结算价"], dts=[StartDT], ids=IDs).iloc[0]
        InitPrice = AdjPrice.where(pd.notnull(AdjPrice), InitPrice.values)
        StartDT += dt.timedelta(1)
    #EndDT = dt.datetime(2010, 5, 31)# debug
    EndDT = dt.datetime.today()
    DTs = WDB.getTable("中国期货交易日历").getDateTime(iid="CFFEX", start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国期货交易日历").getDateTime(iid="CFFEX", start_dt=max(dt.datetime(2010, 4, 16), StartDT-dt.timedelta(40)), end_dt=EndDT)

    AdjPrice = QS.FactorDB.FactorTools.nav(DayReturn, init=InitPrice, factor_name="连续结算价")
    CFT.addFactors(factor_list=[AdjPrice])
    
    TargetTable = CFT.Name
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler, subprocess_num=0)
    
    HDB.disconnect()
    WDB.disconnect()