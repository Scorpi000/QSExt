# -*- coding: utf-8 -*-
"""A 股基本因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize

Factors = []
import UpdateDate
WDB = QS.FactorDB.WindDB2()

# ### 证券特征 #########################################################################
FT = WDB.getTable("中国A股基本资料")
ListDate = FT.getFactor("上市日期")
DelistDate = FT.getFactor("退市日期")
def ListDayNumFun(f, idt, iid, x, args):
    ListDate = np.vectorize(lambda x: dt.datetime.strptime(x, "%Y%m%d"))(x[0])
    DTs = np.array([idt]).T
    ListDayNum = np.vectorize(lambda x: x.days)(DTs - ListDate).astype("float")
    ListDayNum[ListDayNum<0] = np.nan
    return ListDayNum + 1
ListDayNum = QS.FactorDB.PointOperation("上市天数", [ListDate], {"算子":ListDayNumFun, "运算时点":"多时点", "运算ID":"多ID"})
Factors.append(ListDayNum)
ST = WDB.getTable("中国A股特别处理").getFactor("特别处理类型", new_name="特殊处理")
Factors.append(ST)
def isListed(f, idt, iid, x, args):
    ListDate, DelistDate = x
    Listed = np.zeros_like(ListDate)
    DelistDate[pd.isnull(DelistDate)] = "99999999"
    DTs = np.array([[iDT.strftime("%Y%m%d") for iDT in idt]]).T
    Listed[(ListDate<=DTs) & (DelistDate>DTs)] = 1
    return Listed
Factors.append(QS.FactorDB.PointOperation("是否在市", [ListDate, DelistDate], {"算子":isListed, "运算时点":"多时点", "运算ID":"多ID"}))

# ### 行业分类 #########################################################################
Factors.append(WDB.getTable("中国A股Wind行业分类").getFactor("行业名称", args={"分类级别":1}, new_name="Wind行业"))
Factors.append(WDB.getTable("中国A股中信行业分类").getFactor("行业名称", args={"分类级别":1}, new_name="中信行业"))

# ### 市场行情 #########################################################################
FT = WDB.getTable("中国A股日行情估值指标")
Factors.extend([FT.getFactor("换手率"), FT.getFactor("当日总市值", new_name="总市值"), FT.getFactor("当日流通市值", new_name="流通市值"), FT.getFactor("涨跌停状态", new_name="涨跌停")])
FT = WDB.getTable("中国A股日行情")
PreClose, Open, High = FT.getFactor("昨收盘价(元)", new_name="昨收盘价"), FT.getFactor("开盘价(元)", new_name="开盘价"), FT.getFactor("最高价(元)", new_name="最高价")
Low, Close, VWAP, AdjFactor = FT.getFactor("最低价(元)", new_name="最低价"), FT.getFactor("收盘价(元)", new_name="收盘价"), FT.getFactor("均价(VWAP)", new_name="均价"), FT.getFactor("复权因子")
# 由于数据库中的复权价皆保留了两位有效数字, 这里用复权因子乘以相应价格重新计算复权价
AdjPreClose = Factorize(AdjFactor * PreClose, factor_name="复权昨收盘价")
AdjClose = Factorize(AdjFactor * Close, factor_name="复权收盘价")
Factors.extend([PreClose, Open, High, Low, Close, FT.getFactor("成交量(手)", new_name="成交量"), FT.getFactor("成交金额(千元)", new_name="成交金额"), VWAP, 
                AdjFactor, AdjPreClose, Factorize(AdjFactor * Open, factor_name="复权开盘价"), Factorize(AdjFactor * High, factor_name="复权最高价"), Factorize(AdjFactor * Low, factor_name="复权最低价"), 
                AdjClose, Factorize(AdjFactor * VWAP, factor_name="复权均价"), FT.getFactor("交易状态")])
Factors.append(Factorize(Close / PreClose - 1, "日收益率"))
def WeekRetFun(f, idt, iid, x, args):
    CurDate = idt[-1].date()
    CurWeekDay = CurDate.weekday()
    for i in range(1, 8):
        iDT = idt[-i-1]
        if iDT is None: return np.full(shape=(x[0].shape[1],), fill_value=np.nan)
        iPreDate = iDT.date()
        iPreWeekDay = iPreDate.weekday()
        if (CurWeekDay-iPreWeekDay)!=(CurDate-iPreDate).days: break
    Denominator = x[1][-i]
    Denominator[Denominator==0] = np.nan
    return x[0][0] / Denominator - 1
Factors.append(QS.FactorDB.TimeOperation('周收益率', [AdjClose, AdjPreClose], {"算子":WeekRetFun, "回溯期数":[1-1, 8-1], "运算ID":"多ID"}))
def MonthRetFun(f, idt, iid, x, args):
    CurDate = idt[-1].strftime("%Y%m%d")
    for i in range(1, 31):
        iDT = idt[-i-1]
        if iDT is None: return np.full(shape=(x[0].shape[1],), fill_value=np.nan)
        iPreDate = iDT.strftime("%Y%m%d")
        if (iPreDate[:6]!=CurDate[:6]): break
    Denominator = x[1][-i]
    Denominator[Denominator==0] = np.nan
    return x[0][0] / Denominator - 1
Factors.append(QS.FactorDB.TimeOperation('月收益率', [AdjClose, AdjPreClose], {"算子":MonthRetFun, "回溯期数":[1-1, 31-1], "运算ID":"多ID"}))


if __name__=="__main__":
    HDB = QS.FactorDB.HDF5DB()
    HDB.connect()
    WDB.connect()
    
    CFT = QS.FactorDB.CustomFT("ElementaryFactor")
    CFT.addFactors(factor_list=Factors)
    
    IDs = WDB.getStockID(index_id="全体A股", is_current=False)
    #IDs = ["000001.SZ", "000003.SZ", "603297.SH"]# debug
    
    #if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2018, 8, 31, 23, 59, 59, 999999)
    #else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    #EndDT = dt.datetime(2018, 10, 31, 23, 59, 59, 999999)
    StartDT, EndDT = UpdateDate.StartDT, UpdateDate.EndDT
    
    DTs = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT-dt.timedelta(183), end_dt=EndDT)
    
    TargetTable = "ElementaryFactor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler)
    
    HDB.disconnect()
    WDB.disconnect()