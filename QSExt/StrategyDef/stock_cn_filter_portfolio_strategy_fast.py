# -*- coding: utf-8 -*-
"""打分筛选投资组合策略"""
import faulthandler
faulthandler.enable()
import os
import datetime as dt

import numpy as np
import pandas as pd
pd.set_option("future.infer_string", False)  # 禁用 PyArrow 字符串后端
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei']# 指定默认字体为微软雅黑
plt.rcParams['axes.unicode_minus'] = False# 正确显示负号

from QuantStudio.Core.CalcEngine import Engine, ParallelEngine
from QuantStudio.Core.Node import DTLocalContext, DTInitData
from QuantStudio.Factor.Factor import DataFactor, FactorContext, FactorLocalContext, FactorInitData
from QuantStudio.Factor.FactorCache import FeatherFactorCache
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.BackTest.BackTestModel import BTReport
from QuantStudio.BackTest.SectionFactor.Portfolio import CalcPortfolioNV, CalcMaskPortfolio, MultiPortfolio
from QuantStudio.Tools.DateTimeFun import getMonthLastDateTime
from QuantStudio.Factor.HDF5DB import HDF5DB
from QuantStudio.Risk.HDF5RDB import HDF5FRDB
from QSExt.Factor.FactorOperator import QuantileStandardization


if __name__=="__main__":
    # HDB = HDF5DB(args={"MainDir": "/mnt/d/Data/HDF5DB"}).connect()
    # HRDB = HDF5FRDB(args={"MainDir": "/mnt/d/Data/HDF5RDB"}).connect()
    # if not os.path.exists(CacheDir := "/mnt/d/Data/Cache/Strategy/stock_cn_filter_portfolio_strategy_fast"): os.makedirs(CacheDir, exist_ok=True)
    HDB = HDF5DB(args={"MainDir": r"D:\Data\HDF5DB"}).connect()
    HRDB = HDF5FRDB(args={"MainDir": r"D:\Data\HDF5RDB"}).connect()
    if not os.path.exists(CacheDir := r"D:\Data\Cache\Strategy\stock_cn_filter_portfolio_strategy_fast"): os.makedirs(CacheDir, exist_ok=True)

    StartDT, EndDT = dt.datetime(2014, 1, 1), dt.datetime(2025, 7, 31)# 数据起止时间
    # StartDT, EndDT = dt.datetime(2014, 1, 1), dt.datetime(2026, 2, 27)# 数据起止时间
    # TestStartDT, TestEndDT = dt.datetime(2025, 1, 27), EndDT# 测试起止时间
    TestStartDT, TestEndDT = dt.datetime(2019, 1, 31), EndDT# 测试起止时间

    FT = HDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    DTRuler = FT.getDateTime(start_dt=StartDT, end_dt=EndDT)
    TestDTs = FT.getDateTime(start_dt=TestStartDT, end_dt=TestEndDT)
    SectionIDs = IDs = FT.getID()

    # 再平衡时点序列
    BalanceDTs = getMonthLastDateTime(DTRuler)# 月末

    FT = HDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    Price = FT.getFactor("close")

    # 可交易的证券
    FT = HDB.getTable("stock_cn_status")
    IfListed = FT.getFactor("if_listed")
    IfTrading = FT.getFactor("if_trading")
    ST = FT.getFactor("st")
    Mask = ((IfListed == 1) & (IfTrading == 1))

    # 行业
    FT = HDB.getTable("stock_cn_industry")
    Industry = FT.getFactor("citic2019_level1")

    # 基准权重和净值
    FT = HDB.getTable("stock_cn_index_component")
    # BmkWeight = FT.getFactor("zz500_weight")
    # BmkNV = HDB.getTable("index_cn_day_bar").getFactor("close", args={"SectionIDs": ["000852.SH"]})
    BmkWeight = FT.getFactor("zz1000_weight")
    BmkNV = HDB.getTable("index_cn_day_bar").getFactor("close", args={"SectionIDs": ["000852.SH"]})
    # ZZ500Constituent = FT.getFactor("zz500")
    ZZ800Constituent = FT.getFactor("zz800")
    ZZ1000Constituent = FT.getFactor("zz1000")

    # InvestableMask = ((ZZ800Constituent == 1) | (ZZ1000Constituent == 1) & (~ fo.NotNull()(ST)) & Mask)
    InvestableMask = ((~ fo.NotNull()(ST)) & Mask)

    # 预期收益因子
    standardize = QuantileStandardization(ascending=True)
    StdMask = (IfListed == 1)

    FT = HDB.getTable("stock_cn_multi_factor_simple")
    Liquidity = standardize(FT.getFactor("liquidity"), mask=StdMask, cat_data=None, factor_args={"Name": "Liquidity"})
    Growth = standardize(FT.getFactor("growth"), mask=StdMask, cat_data=None, factor_args={"Name": "Growth"})
    Value = standardize(FT.getFactor("value"), mask=StdMask, cat_data=None, factor_args={"Name": "Value"})
    Alternative = standardize(FT.getFactor("alternative"), mask=StdMask, cat_data=None, factor_args={"Name": "Alternative"})

    FT = HDB.getTable("stock_cn_factor_barra")
    BarraLiquidity = standardize(- FT.getFactor("Liquidity"), mask=StdMask, cat_data=None, factor_args={"Name": "Barra_Liquidity"})
    Volatility = standardize(- FT.getFactor("ResidualVolatility"), mask=StdMask, cat_data=None, factor_args={"Name": "ResidualVolatility"})
    NonlinearSize = standardize(- FT.getFactor("NonlinearSize"), mask=StdMask, cat_data=None, factor_args={"Name": "NonlinearSize"})
    Momentum = standardize(FT.getFactor("Momentum"), mask=StdMask, cat_data=None, factor_args={"Name": "Momentum"})

    ExpectedReturn = fo.Mean(weights=None, ignore_nan_weight=False)(Growth, Liquidity, factor_args={"Name": "multi_factor"})
    # ExpectedReturn = fo.Mean(weights=None, ignore_nan_weight=False)(Growth, Liquidity, BarraLiquidity, factor_args={"Name": "multi_factor"})
    
    PortfolioList = []
    for iFactor in [ExpectedReturn]:
        ExpectedRank = fo.SectionRank(ascending=True, uniformization=True)(iFactor, mask=InvestableMask, cat_data=Industry)
        Portfolio = CalcMaskPortfolio(descriptor_ids=SectionIDs)(
            mask=(ExpectedRank >= 0.9),
            weight=None,
            cat_data=Industry,
            cat_weight=BmkWeight,
            factor_args={"CalcDTRuler": BalanceDTs, "Name": iFactor.Name}
        )
        PortfolioList.append(Portfolio)
    PortfolioNV = CalcPortfolioNV(descriptor_ids=SectionIDs, start_dt=TestDTs[0])(*PortfolioList, price=Price, init_nv=1, factor_args={"Name": "Strategy"})

    PortfolioBTNode = MultiPortfolio(
        nv=PortfolioNV, portfolio_list=PortfolioList, 
        bmk_nv=BmkNV, bmk_portfolio=BmkWeight, 
        args={"RebalanceDTs": BalanceDTs, "GenReport": True, "Name": "策略回测"}
    )

    NodeList = [PortfolioBTNode]
    Report = BTReport(bt_node_list=NodeList)

    PIDList = ["0"]
    with FeatherFactorCache(args={"DTRuler": DTRuler, "CacheDir": CacheDir, "StartMode": "new", "PIDs": PIDList}) as Cache:
        with FactorContext(PID="0", PIDList=PIDList, DTRuler=DTRuler, DefaultSectionIDs=SectionIDs, FactorDataCache=Cache) as Context:
            with Engine() as ExecEngine:
            # with ParallelEngine(args={"IOConcurrentNum": 4}) as ExecEngine:
                Rslt = ExecEngine.run([Report], Context, fwd_data_list=[DTLocalContext(DTs=TestDTs)], init_data_list=[DTInitData(DTRange=(TestDTs[0], TestDTs[-1]))])

    with open("FastOutput.html", mode="w") as fp:
        fp.write(Rslt[0]["Report"])

    # NodeList = [Price, Portfolio]
    # with FeatherFactorCache(args={"DTRuler": DTRuler, "CacheDir": CacheDir, "StartMode": "new"}) as Cache:
    #     with FactorContext(DTRuler=DTRuler, DefaultSectionIDs=SectionIDs, FactorDataCache=Cache) as Context:
    #         with Engine() as ExecEngine:
    #             Rslt = ExecEngine.run(
    #                 NodeList, Context, 
    #                 fwd_data_list=[FactorLocalContext(DTs=TestDTs, IDs=SectionIDs)] * len(NodeList), 
    #                 init_data_list=[FactorInitData(DTRange=(TestDTs[0], TestDTs[-1]), SectionIDs=SectionIDs)] * len(NodeList)
    #             )

    # with pd.ExcelWriter(r"D:\HST\Data.xlsx", engine="openpyxl") as xlsFile:
    #     Rslt[0].to_excel(xlsFile, sheet_name="Price", index=True, header=True)
    #     Rslt[1].to_excel(xlsFile, sheet_name="Portfolio", index=True, header=True)

    print("===")