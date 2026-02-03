import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Core.JYDB import JYDB
from QuantStudio.Core.HDF5DB import HDF5DB
from QuantStudio.Core.CalcEngine import Engine, ParallelEngine
from QuantStudio.Core.Factor import DataFactor, FactorContext, FactorLocalContext
from QuantStudio.Core.BasicOperator import Factorize
from QuantStudio.Core.FactorCache import HDF5Cache, FeatherCache
from QuantStudio.Core.FactorOperation import SectionOperation, PanelOperation, makeFactorOperator, FactorOperatorized
import QuantStudio.Core.FactorOperator as fo
from QuantStudio.Core.FactorStorer import FactorStorer
from QSExt.FactorDef.JY.stock_cn_info import defFactor


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = JYDB(logger=Logger).connect()
    TDB = HDF5DB(logger=Logger).connect()

    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    SectionIDs = JYDB.getStockID(is_current=False)
    IDs = SectionIDs#[:5]# DEBUG
    
    Args = {"JYDB": JYDB}
    Factors, UpdateArgs = defFactor(args=Args)
    
    # ExecEngine = Engine()
    # PIDList = ["0"]
    ExecEngine = ParallelEngine(args={"IOConcurrentNum": 3})
    PIDList = [f"0-{i}" for i in range(3)]
    Cache = FeatherCache(args={"DTRuler": DTRuler, "MinDTUnit": dt.timedelta(1), "CacheDir": r"D:\Data\FactorCache", "PIDs": PIDList, "ClearStart": True})
    Cache.start()
    Context = FactorContext(
        PID="0",
        PIDList=PIDList,
        DTRuler=DTRuler,
        DefaultSectionIDs=SectionIDs,
        IDSplit="连续切分",
        FactorDataCache=Cache
    )
    LocalContext = FactorLocalContext(DTs=DTs, IDs=IDs)
    Storer = FactorStorer(deps=Factors, args={"TargetFDB": TDB, "TargetTable": UpdateArgs["因子表"], "IfExists": "update"})
    Rslt = ExecEngine.run([Storer], Context, fwd_data_list=[LocalContext], init_data_list=[{"dt_range": (DTs[0], DTs[-1]), "section_ids": SectionIDs}])
    print(Rslt)
    
    TDB.disconnect()
    JYDB.disconnect()

    print("===")
    