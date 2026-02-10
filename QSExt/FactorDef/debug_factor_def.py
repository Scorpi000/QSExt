import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Core.JYDB import JYDB
from QuantStudio.Core.BaoStockDB import BaoStockDB
from QuantStudio.Core.HDF5DB import HDF5DB
from QuantStudio.Core.CalcEngine import Engine, ParallelEngine
from QuantStudio.Core.Factor import DataFactor, FactorContext, FactorLocalContext
from QuantStudio.Core.BasicOperator import rename
from QuantStudio.Core.FactorCache import HDF5Cache, FeatherCache
from QuantStudio.Core.FactorOperation import SectionOperation, PanelOperation, makeFactorOperator
import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.FactorStorer import FactorStorer
from QSExt.FactorDef.FactorDefContent import FactorDefInput

# from QSExt.FactorDef.BaoStock.stock_cn_day_bar_adj_backward import defFactor
# from QSExt.FactorDef.JY.stock_cn_info import defFactor
# from QSExt.FactorDef.JY.stock_cn_industry import defFactor
# from QSExt.FactorDef.JY.stock_cn_status import defFactor
# from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor
# from QSExt.FactorDef.JY.stock_cn_day_bar_adj_backward_nafilled import defFactor
from QSExt.FactorDef.JY.stock_cn_factor_value import defFactor


if __name__=="__main__1":
    import logging
    Logger = logging.getLogger()
    
    #SDB = JYDB(logger=Logger).connect()
    SDB =  BaoStockDB(logger=Logger).connect()
    TDB = HDF5DB(logger=Logger).connect()

    FactorDef = defFactor(FactorDefInput(FDB={"BSDB": SDB}))
    print(FactorDef)
    
    iFactor = FactorDef.getFactor(factor_name="listed_date")
    print(iFactor)
    print("===")

if __name__=="__main__1":
    HDB = HDF5DB().connect()
    print(HDB.TableNames)

    FT = HDB.getTable("stock_cn_factor_value")
    DTs = FT.getDateTime()
    Data = FT.readData(FT.FactorNames, ids=None, dts=DTs[-1:])
    print(Data.iloc[:, 0])
    print("===")

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    SDB = JYDB(logger=Logger).connect()
    # SDB = BaoStockDB(logger=Logger).connect()
    TDB = HDF5DB(logger=Logger).connect()

    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = SDB.getTradeDay(start_date=StartDT, end_date=EndDT)
    DTRuler = SDB.getTradeDay(start_date=StartDT - dt.timedelta(365), end_date=EndDT)
    
    # SectionIDs = SDB.getStockID(is_current=False)
    # IDs = SectionIDs
    # DEBUG
    SectionIDs = IDs = ["000001.SZ", "000003.SZ", "301111.SZ", "600519.SH", "688981.SH", "920726.BJ"]
    
    FactorDef = defFactor(fdi=FactorDefInput(FDB={"JYDB": SDB}, DTs=DTs, IDs=IDs, SectionIDs=SectionIDs, DTRuler=DTRuler))
    
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
    Rslt = ExecEngine.run([Storer], Context, fwd_data_list=[LocalContext], init_data_list=[{"dt_range": (DTs[0], DTs[-1]), "section_ids": SectionIDs}])
    print(Rslt)
    
    TDB.disconnect()
    SDB.disconnect()
    
    print("===")
    