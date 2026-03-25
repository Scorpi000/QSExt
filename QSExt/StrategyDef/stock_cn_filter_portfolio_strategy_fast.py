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


if __name__=="__main__":
    # HDB = HDF5DB(args={"MainDir": "/mnt/d/Data/HDF5DB"}).connect()
    # HRDB = HDF5FRDB(args={"MainDir": "/mnt/d/Data/HDF5RDB"}).connect()
    # if not os.path.exists(CacheDir := "/mnt/d/Data/Cache/Strategy/stock_cn_filter_portfolio_strategy_fast"): os.makedirs(CacheDir, exist_ok=True)
    HDB = HDF5DB(args={"MainDir": r"D:\Data\HDF5DB"}).connect()
    HRDB = HDF5FRDB(args={"MainDir": r"D:\Data\HDF5RDB"}).connect()
    if not os.path.exists(CacheDir := r"D:\Data\Cache\Strategy\stock_cn_filter_portfolio_strategy_fast"): os.makedirs(CacheDir, exist_ok=True)

    StartDT, EndDT = dt.datetime(2014, 1, 1), dt.datetime(2025, 7, 31)# 数据起止时间
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

    # 基准权重
    FT = HDB.getTable("stock_cn_index_component")
    BmkWeight = FT.getFactor("zz500_weight")
    # ZZ500Constituent = FT.getFactor("zz500")
    ZZ800Constituent = FT.getFactor("zz800")
    ZZ1000Constituent = FT.getFactor("zz1000")

    InvestableMask = ((ZZ800Constituent == 1) | (ZZ1000Constituent == 1) & (~ fo.NotNull()(ST)))

    # 预期收益因子 
    # FT = HDB.getTable("stock_cn_multi_factor_simple")
    # ExpectedReturn = FT.getFactor("score_ew_o")
    FT = HDB.getTable("stock_cn_multi_factor_ml")
    ExpectedReturn = FT.getFactor("adaboost_loss_1y")
    ExpectedRank = fo.SectionRank(ascending=True, uniformization=True)(ExpectedReturn, mask=InvestableMask, cat_data=Industry)

    # 基准因子
    FT = HDB.getTable("index_cn_day_bar")
    BmkNV = FT.getFactor("close", args={"SectionIDs": ["000905.SH"]})

    Portfolio = CalcMaskPortfolio(descriptor_ids=SectionIDs)(
        mask=(ExpectedRank >= 0.7),
        weight=None,
        cat_data=Industry,
        cat_weight=BmkWeight,
        factor_args={"CalcDTRuler": BalanceDTs, "Name": "Strategy"}
    )
    PortfolioNV = CalcPortfolioNV(descriptor_ids=SectionIDs, start_dt=TestDTs[0])(Portfolio, price=Price, init_nv=1, factor_args={"Name": "Strategy"})

    PortfolioBTNode = MultiPortfolio(
        nv=PortfolioNV, portfolio_list=[Portfolio], 
        bmk_nv=BmkNV, bmk_portfolio=BmkWeight, 
        args={"RebalanceDTs": BalanceDTs, "GenReport": True, "Name": "策略回测"}
    )

    NodeList = [PortfolioBTNode]
    Report = BTReport(bt_node_list=NodeList)

    with FeatherFactorCache(args={"DTRuler": DTRuler, "CacheDir": CacheDir, "StartMode": "new"}) as Cache:
        with FactorContext(DTRuler=DTRuler, DefaultSectionIDs=SectionIDs, FactorDataCache=Cache) as Context:
            with Engine() as ExecEngine:
                Rslt = ExecEngine.run([Report], Context, fwd_data_list=[DTLocalContext(DTs=TestDTs)], init_data_list=[DTInitData(DTRange=(TestDTs[0], TestDTs[-1]))])

    with open("FastOutput.html", mode="w") as fp:
        fp.write(Rslt[0]["Report"])

    print("===")