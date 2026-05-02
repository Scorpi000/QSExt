# coding=utf-8
"""更新A股数据"""
import os
import logging
import datetime as dt
from typing import Optional, Literal

import pandas as pd

from QuantStudio.Core import setDefaultLogLevel
setDefaultLogLevel(logging.DEBUG)
from QuantStudio.Core import __QS_Logger__ as Logger
from QuantStudio.Factor.JYDB import JYDB
from QuantStudio.Factor.HDF5DB import HDF5DB
from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Core.ParallelEngine import ParallelEngine
from QuantStudio.Factor.Factor import FactorContext, FactorLocalContext, FactorInitData
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QuantStudio.Factor.FactorStorer import FactorStorer
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY import stock_cn_info, stock_cn_status, stock_cn_industry, stock_cn_index_component, stock_cn_day_bar_nafilled,\
stock_cn_day_bar_adj_backward_nafilled, stock_cn_consensus_expectation, stock_cn_factor_value, stock_cn_factor_growth, stock_cn_factor_quality,\
stock_cn_factor_momentum, stock_cn_factor_sentiment, stock_cn_factor_size, stock_cn_factor_liquidity, stock_cn_factor_volatility, stock_cn_factor_alternative,\
stock_cn_factor_barra_descriptor, stock_cn_factor_barra, stock_cn_margin_trading, stock_cn_factor_money_flow
from QSExt.FactorDef.Local import stock_cn_factor_qlib_alpha158
from QSExt.Tools.TraceBack import traceCrush, filterWarnings
filterWarnings()


__NOW__ = dt.datetime.now()
__FILE_NAME__ = '.'.join(os.path.split(__file__)[-1].split('.')[:-1])
__LOG_DIR__ = "./log"
traceCrush(os.path.join(__LOG_DIR__, f"{__FILE_NAME__}_crash_log_{__NOW__.strftime('%Y%m%dT%H%M%S')}_{os.getpid()}.txt"))


def main(
    end_dt:Literal["today", "yesterday", "last_friday", "last_month_end"] | str="last_friday", 
    start_dt:Optional[str]=None, 
    lookback:int=15, 
    workers:int=8,
    cache_dir:Optional[str]=None
):
    """更新A股数据

    Args:
        end_dt: 数据更新的截止时点
        start_dt: 数据更新的起始时点，如果为 None 则用 end_dt 减去 lookback 指定的回溯天数得到
        lookback: 从 end_dt 开始的回溯天数，在 start_dt 为 None 时用于计算起始时点
        workers: 并发数量
    """
    Logger.info(f"开始更新A股数据..., 主进程: {os.getpid()}, 启动时间: {__NOW__}")
    if cache_dir:
        if not os.path.exists(CacheDir := os.path.join(cache_dir, __FILE_NAME__)): os.makedirs(CacheDir, exist_ok=True)
    else:
        CacheDir = None

    SDB = JYDB(args={"FTArgs": {"PreFilterID": False}}).connect()
    TDB = HDF5DB().connect()

    if end_dt == "today":
        EndDT = dt.datetime.combine(dt.date.today(), dt.time(0))
    elif end_dt == "yesterday":
        EndDT = dt.datetime.combine(dt.date.today(), dt.time(0)) - dt.timedelta(1)
    elif end_dt == "last_friday":
        EndDT = dt.datetime.combine(dt.date.today(), dt.time(0)) - dt.timedelta(dt.date.today().weekday() + 3)
    elif end_dt=="last_month_end":
        EndDT = dt.datetime.combine(dt.date.today(), dt.time(0)) - dt.timedelta(dt.date.today().day)
    else:
        EndDT = pd.to_datetime(end_dt)

    if start_dt is not None:
        StartDT = pd.to_datetime(start_dt)
    else:
        StartDT = EndDT - dt.timedelta(int(lookback))
    Logger.info(f"数据更新的起始时点: {StartDT.date()}, 终止时点: {EndDT.date()}")
    
    DTs = SDB.getTradeDay(start_date=StartDT, end_date=EndDT)
    MaxLookBack = 365 * 10
    DTRuler = SDB.getTradeDay(start_date=StartDT - dt.timedelta(MaxLookBack), end_date=EndDT)
    Logger.info(f"数据更新的时点数量: {len(DTs)}")
    if not DTs: return
    
    IDs = SectionIDs = SDB.getStockID(is_current=False)
    Logger.info(f"数据更新的证券数量: {len(IDs)}")
    if not IDs: return

    with pd.ExcelFile("../conf/config.xlsx", engine="openpyxl") as xlsFile:
        IndexList = pd.read_excel(xlsFile, sheet_name="常用指数", index_col=None, header=0)
    
    FDI = FactorDefInput(FDB={"JYDB": SDB}, DTs=DTs, IDs=IDs, SectionIDs=SectionIDs, DTRuler=DTRuler)# 不使用数据代理
    # FDI = FactorDefInput(FDB={"JYDB": SDB}, DTs=DTs, IDs=IDs, SectionIDs=SectionIDs, DTRuler=DTRuler, ProxyDB=TDB)# 使用数据代理
    ModuleList = [
        (stock_cn_info, {}, None),
        (stock_cn_status, {}, None),
        (stock_cn_industry, {}, None),
        (stock_cn_index_component, {"constituent_index_list": IndexList, "weight_index_list": IndexList}, None),
        (stock_cn_day_bar_nafilled, {}, None),
        (stock_cn_day_bar_adj_backward_nafilled, {}, None),
        (stock_cn_consensus_expectation, {}, None),
        (stock_cn_factor_value, {}, None),
        (stock_cn_factor_growth, {}, None),
        (stock_cn_factor_quality, {}, None),
        (stock_cn_factor_momentum, {}, None),
        (stock_cn_factor_sentiment, {}, None),
        (stock_cn_factor_size, {}, None),
        (stock_cn_factor_liquidity, {}, None),
        (stock_cn_factor_volatility, {}, None),
        (stock_cn_factor_alternative, {}, None),
        (stock_cn_factor_barra_descriptor, {}, None),
        (stock_cn_factor_barra, {}, None),
        (stock_cn_margin_trading, {}, None),
        (stock_cn_factor_money_flow, {}, None),
        # (stock_cn_factor_qlib_alpha158, {}, None),
    ]
    StorerList, FactorDefDict = [], {}
    for iModule, iModelArgs in ModuleList:
        FDI.ModelArgs = iModelArgs
        iFactorDef: FactorDef = iModule.defFactor(fdi=FDI, dep_fd=FactorDefDict)
        FactorDefDict[iFactorDef.TargetTable] = iFactorDef
        if iFactorDef.MaxLookBack > MaxLookBack:
            MaxLookBack = iFactorDef.MaxLookBack
            FDI.DTRuler = DTRuler = SDB.getTradeDay(start_date=StartDT - dt.timedelta(MaxLookBack), end_date=EndDT)
        iTableMeta = {"Description": iFactorDef.Description, "IDType": iFactorDef.IDType, "Author": iFactorDef.Author, "DefScriptPath": iFactorDef.DefScriptPath}
        iStorer = FactorStorer(deps=iFactorDef.FactorList, args={"TargetFDB": TDB, "TargetTable": iFactorDef.TargetTable, "IfExists": "update", "TableMeta": iTableMeta, "UpdateMeta": True})
        StorerList.append(iStorer)

    Logger.info(f"并发数量: {workers}")
    PIDList = [f"0-{i}" for i in range(int(workers))] if workers > 0 else ["0"]
    with FeatherFactorCache(args={"DTRuler": DTRuler, "PIDs": PIDList, "CacheDir": CacheDir, "StartMode": "new", "Suffix": ".pkl"}) as Cache:
        with FactorContext(Mode="DEBUG", PIDList=PIDList, DTRuler=DTRuler, SectionIDs=SectionIDs, DataCache=Cache) as Context:
            with (ParallelEngine() if workers > 0 else Engine()) as ExecEngine:
                LocalContext = FactorLocalContext(DTs=DTs, IDs=IDs)
                InitData = FactorInitData(DTRange=(DTs[0], DTs[-1]), SectionIDs=SectionIDs)
                ExecEngine.run(StorerList, Context, fwd_data_list=[LocalContext] * len(StorerList), init_data_list=[InitData] * len(StorerList))
    
    TDB.disconnect()
    SDB.disconnect()
    Logger.info("数据更新完成")

if __name__=="__main__":
    main(end_dt="2019-12-31", start_dt="2014-01-01", workers=8)
    # main()