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
from QuantStudio.BackTest.Strategy.Strategy import MakeAccount, AccountReport, MakeStrategy
from QuantStudio.BackTest.SectionFactor.Portfolio import CalcPortfolioNV, CalcMaskPortfolio
from QuantStudio.Tools.DateTimeFun import getMonthLastDateTime
from QuantStudio.Factor.HDF5DB import HDF5DB
from QuantStudio.Risk.HDF5RDB import HDF5FRDB


class MakeFilterPortfolioStrategy(MakeStrategy):

    def genSignal(self, f, idt, x, last_price, cash, position_num, args):
        ExpectedReturn, Mask, InvestableMask, BmkWeight, Industry = x[0].iloc[-1], x[1].iloc[-1], x[2].iloc[-1], x[3].iloc[-1], x[4].iloc[-1]
        
        BmkWeight = BmkWeight.fillna(0)
        Industry = Industry.where(pd.notnull(Industry), "None")
        BmkIndustryWeight = BmkWeight.groupby(Industry).sum()
        Mask = (pd.notnull(last_price) & pd.notnull(ExpectedReturn) & (Mask==1))
        InvestableMask = Mask & (InvestableMask == 1)
        ExpectedReturn, Industry = ExpectedReturn[InvestableMask], Industry[InvestableMask]

        Rank = ExpectedReturn.groupby(Industry).rank(ascending=True, pct=True)
        Portfolio = pd.Series(np.where((Rank >= args["threshold_ratio"]), 1, 0), index=Rank.index)
        Portfolio = Portfolio.groupby(Industry).apply(lambda s: s / s.sum() * BmkIndustryWeight.loc[s.name])
        Portfolio = Portfolio.droplevel(0).sort_index()
        Portfolio = Portfolio / Portfolio.sum()

        # AllIndustryList = list(Industry.unique())
        # Signal = pd.Series(0, index=BmkWeight.index)
        # for iIndustry in AllIndustryList:
        #     if pd.isnull(iIndustry): iMask = (Mask & pd.isnull(Industry))
        #     else: iMask = (Mask & (Industry == iIndustry))
        #     iBmkWeight = BmkWeight[iMask].sum()
        #     if iBmkWeight == 0: continue
        #     ExpectedReturn[iMask]

        return Portfolio



if __name__=="__main__":
    # HDB = HDF5DB(args={"MainDir": "/mnt/d/Data/HDF5DB"}).connect()
    # HRDB = HDF5FRDB(args={"MainDir": "/mnt/d/Data/HDF5RDB"}).connect()
    # if not os.path.exists(CacheDir := "/mnt/d/Data/Cache/Strategy/stock_cn_filterportfolio_strategy"): os.makedirs(CacheDir, exist_ok=True)
    HDB = HDF5DB(args={"MainDir": r"D:\Data\HDF5DB"}).connect()
    HRDB = HDF5FRDB(args={"MainDir": r"D:\Data\HDF5RDB"}).connect()
    if not os.path.exists(CacheDir := r"D:\Data\Cache\Strategy\stock_cn_filterportfolio_strategy"): os.makedirs(CacheDir, exist_ok=True)

    StartDT, EndDT = dt.datetime(2014, 1, 1), dt.datetime(2025, 7, 31)# 数据起止时间
    # TestStartDT, TestEndDT = dt.datetime(2025, 1, 27), EndDT# 测试起止时间
    TestStartDT, TestEndDT = dt.datetime(2019, 1, 31), EndDT# 测试起止时间

    FT = HDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    DTRuler = FT.getDateTime(start_dt=StartDT, end_dt=EndDT)
    TestDTs = FT.getDateTime(start_dt=TestStartDT, end_dt=TestEndDT)
    SectionIDs = IDs = FT.getID()

    # 再平衡时点序列
    BalanceDTs = getMonthLastDateTime(DTRuler)# 月末

    FT = HDB.getTable("stock_cn_day_bar_adj_backward_nafilled", args={"LookBack": np.inf})
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

    # 策略因子
    makeFilterPortfolioStrategy = MakeFilterPortfolioStrategy(
        signal_type="目标权重", init_cash=1e6, start_dt=TestDTs[0], 
        x_lookback=[0] * 5, x_section_ids=[None] * 5, 
        signal_dts=BalanceDTs,
        args={"ModelArgs": {"threshold_ratio": 0.7}}
    )
    Strategy = makeFilterPortfolioStrategy(
        ExpectedReturn, Mask, InvestableMask, BmkWeight, Industry,
        last_price=Price, #buy_limit=(~Mask), sell_limit=(~Mask), 
        factor_args={"Name": "FilterStrategy"}
    )


    ExpectedRank = fo.SectionRank(ascending=True, uniformization=True)(ExpectedReturn, mask=InvestableMask, cat_data=Industry)
    Portfolio = CalcMaskPortfolio(descriptor_ids=SectionIDs)(
        mask=(ExpectedRank >= 0.7),
        weight=None,
        cat_data=Industry,
        cat_weight=BmkWeight,
        factor_args={"CalcDTRuler": BalanceDTs, "Name": "Strategy"}
    )
    Account = MakeAccount(signal_type="目标权重", init_cash=1e6, short_allowed=False, start_dt=TestDTs[0])(
        last_price=Price, signal=Portfolio, 
        # buy_limit=(~Mask), sell_limit=(~Mask),
        factor_args={"Name": "FilterStrategy1"}
    )

    # 基准因子
    FT = HDB.getTable("index_cn_day_bar")
    BmkNV = FT.getFactor("close", args={"SectionIDs": ["000905.SH"]})

    # 策略报告
    StrategyReport = AccountReport(account=Strategy, bmk_nv=BmkNV, args={"GenReport": True})
    StrategyReport1 = AccountReport(account=Account, bmk_nv=BmkNV, args={"GenReport": True})

    NodeList = [StrategyReport, StrategyReport1]
    Report = BTReport(bt_node_list=NodeList)

    with FeatherFactorCache(args={"DTRuler": DTRuler, "CacheDir": CacheDir, "StartMode": "new"}) as Cache:
        with FactorContext(DTRuler=DTRuler, SectionIDs=SectionIDs, DataCache=Cache) as Context:
            with Engine() as ExecEngine:
                Rslt = ExecEngine.run([Report], Context, fwd_data_list=[DTLocalContext(DTs=TestDTs)], init_data_list=[DTInitData(DTRange=(TestDTs[0], TestDTs[-1]))])

    with open("Output.html", mode="w") as fp:
        fp.write(Rslt[0]["Report"])

    print("===")