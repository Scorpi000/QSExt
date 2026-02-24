import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Core.JYDB import JYDB
from QuantStudio.Core.BaoStockDB import BaoStockDB
from QuantStudio.Core.HDF5DB import HDF5DB
from QuantStudio.Core.CalcEngine import Engine, ParallelEngine
from QuantStudio.Core.Factor import DataFactor, FactorContext, FactorLocalContext, FactorInitData
from QuantStudio.Core.BasicOperator import rename
from QuantStudio.Core.FactorCache import HDF5Cache, FeatherCache
from QuantStudio.Core.FactorOperation import SectionOperation, PanelOperation, makeFactorOperator
import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.FactorStorer import FactorStorer
from QSExt.FactorDef.FactorDefContent import FactorDefInput

# from QSExt.FactorDef.JY.stock_cn_info import defFactor
# from QSExt.FactorDef.JY.stock_cn_industry import defFactor
# from QSExt.FactorDef.JY.stock_cn_status import defFactor
# from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor
# from QSExt.FactorDef.JY.stock_cn_day_bar_adj_backward_nafilled import defFactor
# from QSExt.FactorDef.JY.stock_cn_factor_value import defFactor
# from QSExt.FactorDef.JY.stock_cn_factor_momentum import defFactor
# from QSExt.FactorDef.JY.stock_cn_factor_growth import defFactor# TODEBUG
from QSExt.FactorDef.JY.stock_cn_factor_quality import defFactor# TODEBUG
# from QSExt.FactorDef.JY.stock_cn_consensus_expectation import defFactor
# from QSExt.FactorDef.JY.stock_cn_factor_size import defFactor
# from QSExt.FactorDef.JY.stock_cn_factor_liquidity import defFactor
# from QSExt.FactorDef.JY.stock_cn_factor_sentiment import defFactor
# from QSExt.FactorDef.JY.stock_cn_factor_money_flow import defFactor
# from QSExt.FactorDef.JY.stock_cn_factor_volatility import defFactor# TODEBUG
# from QSExt.FactorDef.JY.stock_cn_factor_alternative import defFactor
# from QSExt.FactorDef.JY.stock_cn_factor_barra_descriptor import defFactor
# from QSExt.FactorDef.JY.stock_cn_factor_barra import defFactor
# from QSExt.FactorDef.JY.stock_cn_margin_trading import defFactor
# from QSExt.FactorDef.JY.stock_cn_index_component import defFactor

# from QSExt.FactorDef.JY import stock_cn_status
# from QSExt.FactorDef.JY import stock_cn_day_bar_adj_backward_nafilled
# from QSExt.FactorDef.JY import stock_cn_factor_momentum


if __name__=="__main__1":
    #SDB = JYDB().connect()
    SDB =  BaoStockDB().connect()
    TDB = HDF5DB().connect()

    FactorDef = defFactor(FactorDefInput(FDB={"BSDB": SDB}))
    print(FactorDef)
    
    iFactor = FactorDef.getFactor(factor_name="listed_date")
    print(iFactor)
    print("===")

if __name__=="__main__":
    SDB = JYDB().connect()
    TDB = HDF5DB().connect()
    print(TDB.TableNames)

    FactorDef = defFactor(fdi=FactorDefInput(FDB={"JYDB": SDB}, DTs=[], IDs=[], SectionIDs=[], DTRuler=[]))
    FT = TDB.getTable(FactorDef.TargetTable)
    DTs = FT.getDateTime()
    Data = FT.readData(FT.FactorNames, ids=None, dts=DTs[-1:])
    print(Data.iloc[:, 0].T)

    TDB.disconnect()
    SDB.disconnect()
    print("===")

# 单定义
if __name__=="__main__1":
    SDB = JYDB().connect()
    # SDB = BaoStockDB().connect()
    TDB = HDF5DB().connect()

    SDB.Logger.info("开始因子计算...")
    StartDT, EndDT = dt.datetime(2021, 7, 1), dt.datetime(2021, 7, 15)
    DTs = SDB.getTradeDay(start_date=StartDT, end_date=EndDT)
    DTRuler = SDB.getTradeDay(start_date=StartDT - dt.timedelta(365), end_date=EndDT)
    
    # SectionIDs = SDB.getStockID(is_current=False)
    # IDs = SectionIDs
    SectionIDs = IDs = ["000001.SZ", "000003.SZ", "301111.SZ", "600519.SH", "688981.SH", "920726.BJ"]# DEBUG
    
    FactorDef = defFactor(fdi=FactorDefInput(FDB={"JYDB": SDB}, DTs=DTs, IDs=IDs, SectionIDs=SectionIDs, DTRuler=DTRuler))
    if FactorDef.MaxLookBack > 365: DTRuler = SDB.getTradeDay(start_date=StartDT - dt.timedelta(FactorDef.MaxLookBack), end_date=EndDT)
    
    ExecEngine = Engine()
    PIDList = ["0"]
    # ExecEngine = ParallelEngine(args={"IOConcurrentNum": 3})
    # PIDList = [f"0-{i}" for i in range(3)]
    Cache = FeatherCache(args={"DTRuler": DTRuler, "MinDTUnit": dt.timedelta(1), "PIDs": PIDList})
    Cache.start()
    Context = FactorContext(
        PID="0",
        PIDList=PIDList,
        DTRuler=DTRuler,
        DefaultSectionIDs=SectionIDs,
        SplitType="连续切分",
        FactorDataCache=Cache
    )
    LocalContext = FactorLocalContext(DTs=DTs, IDs=IDs)
    Storer = FactorStorer(deps=FactorDef.FactorList, args={"TargetFDB": TDB, "TargetTable": FactorDef.TargetTable, "IfExists": "update"})
    Rslt = ExecEngine.run([Storer], Context, fwd_data_list=[LocalContext], init_data_list=[FactorInitData(DTRange=(DTs[0], DTs[-1]), SectionIDs=SectionIDs)])
    print(Rslt)
    
    TDB.disconnect()
    SDB.disconnect()
    
    print("===")

# 多定义
if __name__=="__main__1":
    SDB = JYDB().connect()
    # SDB = BaoStockDB().connect()
    TDB = HDF5DB().connect()

    SDB.Logger.info("开始因子计算...")
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = SDB.getTradeDay(start_date=StartDT, end_date=EndDT)
    DTRuler = SDB.getTradeDay(start_date=StartDT - dt.timedelta(365), end_date=EndDT)
    
    # SectionIDs = SDB.getStockID(is_current=False)
    # IDs = SectionIDs
    SectionIDs = IDs = ["000001.SZ", "000003.SZ", "301111.SZ", "600519.SH", "688981.SH", "920726.BJ"]# DEBUG
    
    FDI = FactorDefInput(FDB={"JYDB": SDB}, DTs=DTs, IDs=IDs, SectionIDs=SectionIDs, DTRuler=DTRuler)
    MaxLookBack = 365
    StorerList = []
    for iModule in [stock_cn_status, stock_cn_day_bar_adj_backward_nafilled, stock_cn_factor_momentum]:
        iFactorDef = iModule.defFactor(fdi=FDI)
        if iFactorDef.MaxLookBack > MaxLookBack:
            MaxLookBack = iFactorDef.MaxLookBack
            FDI.DTRuler = DTRuler = SDB.getTradeDay(start_date=StartDT - dt.timedelta(MaxLookBack), end_date=EndDT)
        iStorer = FactorStorer(deps=iFactorDef.FactorList, args={"TargetFDB": TDB, "TargetTable": iFactorDef.TargetTable, "IfExists": "update"})
        StorerList.append(iStorer)

    ExecEngine = Engine()
    PIDList = ["0"]
    # ExecEngine = ParallelEngine(args={"IOConcurrentNum": 3})
    # PIDList = [f"0-{i}" for i in range(3)]
    Cache = FeatherCache(args={"DTRuler": DTRuler, "MinDTUnit": dt.timedelta(1), "PIDs": PIDList})
    Cache.start()
    Context = FactorContext(
        PID="0",
        PIDList=PIDList,
        DTRuler=DTRuler,
        DefaultSectionIDs=SectionIDs,
        SplitType="连续切分",
        FactorDataCache=Cache
    )
    LocalContext = FactorLocalContext(DTs=DTs, IDs=IDs)
    Rslt = ExecEngine.run(StorerList, Context, fwd_data_list=[LocalContext] * len(StorerList), init_data_list=[{"dt_range": (DTs[0], DTs[-1]), "section_ids": SectionIDs}] * len(StorerList))
    print(Rslt)
    
    TDB.disconnect()
    SDB.disconnect()
    
    print("===")