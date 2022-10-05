# coding=utf-8
"""指数成份及其权重因子"""
import datetime as dt
import UpdateDate
import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize

WDB = QS.FactorDB.WindDB2()
WDB.connect()

Factors = []# 因子列表

# 指数成份
FT = WDB.getTable("中国A股指数成份股")
Factors.append(FT.getFactor("000016.SH", new_name="上证50"))
Factors.append(FT.getFactor("399330.SZ", new_name="深证100"))
Factors.append(FT.getFactor("000903.SH", new_name="中证100"))
Factors.append(FT.getFactor("000300.SH", new_name="沪深300"))
Factors.append(FT.getFactor("000905.SH", new_name="中证500"))
Factors.append(FT.getFactor("000906.SH", new_name="中证800"))
Factors.append(FT.getFactor("000852.SH", new_name="中证1000"))
Factors.append(FT.getFactor("399311.SZ", new_name="国证1000"))
Factors.append(FT.getFactor("399303.SZ", new_name="国证2000"))
Factors.append(FT.getFactor("399313.SZ", new_name="巨潮100"))

# 指数成份权重
FT = WDB.getTable("沪深300免费指数权重")
sz50 = Factorize(FT.getFactor("权重", args={"指数Wind代码":"000016.SH"})/100,factor_name="上证50成份权重")
sz100 = Factorize(FT.getFactor("权重", args={"指数Wind代码":"399330.SZ"})/100,factor_name="深证100成份权重")
zz100 = Factorize(FT.getFactor("权重", args={"指数Wind代码":"000903.SH"})/100,factor_name="中证100成份权重")
zz500 = Factorize(FT.getFactor("权重", args={"指数Wind代码":"000905.SH"})/100,factor_name="中证500成份权重")
zz800 = Factorize(FT.getFactor("权重", args={"指数Wind代码":"000906.SH"})/100,factor_name="中证800成份权重")
zz1000 = Factorize(FT.getFactor("权重", args={"指数Wind代码":"000852.SH"})/100,factor_name="中证1000成份权重")
gz1000 = Factorize(FT.getFactor("权重", args={"指数Wind代码":"399311.SZ"})/100,factor_name="国证1000成份权重")
hs300 = Factorize(FT.getFactor("权重", args={"指数Wind代码":"399300.SZ"})/100,factor_name="沪深300成份权重")
Factors.append(sz50)
Factors.append(sz100)
Factors.append(zz100)
Factors.append(zz500)
Factors.append(zz800)
Factors.append(gz1000)
Factors.append(hs300)


if __name__=="__main__":
    HDB = QS.FactorDB.HDF5DB()
    HDB.connect()
    
    CFT = QS.FactorDB.CustomFT("IndexConstituentFactor")
    CFT.addFactors(factor_list=Factors)
    
    IDs = WDB.getStockID(index_id="全体A股", is_current=False)
    #IDs = ["000001.SZ", "000003.SZ", "603297.SH"]# debug
    
    #if CFT.Name not in HDB.TableNames: StartDT = dt.datetime(2018, 8, 31, 23, 59, 59, 999999)
    #else: StartDT = HDB.getTable(CFT.Name).getDateTime()[-1] + dt.timedelta(1)
    #EndDT = dt.datetime(2018, 10, 31, 23, 59, 59, 999999)
    StartDT, EndDT = UpdateDate.StartDT, UpdateDate.EndDT
    #StartDT, EndDT = dt.datetime(2000,1,1), dt.datetime(2018,11,9)
    
    DTs = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT, end_dt=EndDT)
    DTRuler = WDB.getTable("中国A股交易日历").getDateTime(start_dt=StartDT-dt.timedelta(365), end_dt=EndDT)
    
    #from WindPy import w
    #w.start()
    #Data = {}
    #for iDT in DTs:
        #iData = w.wset("indexconstituent",("date=%s;windcode=000300.SH;field=wind_code,i_weight" % (iDT.strftime("%Y-%m-%d"), )))
        #if iData.Data: Data[iDT] = pd.Series(iData.Data[1], index=iData.Data[0])
    #if Data: Data = pd.DataFrame(Data).T.loc[DTs]
    #else: Data = pd.DataFrame(index=DTs, columns=IDs)
    #CFT.addFactors(factor_list=[QS.FactorDB.DataFactor("沪深300成份权重", Data)])
    
    TargetTable = "IndexConstituentFactor"
    #TargetTable = QS.Tools.genAvailableName("TestTable", HDB.TableNames)# debug
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=HDB, table_name=TargetTable, if_exists="update", dt_ruler=DTRuler)
    
    HDB.disconnect()
    WDB.disconnect()