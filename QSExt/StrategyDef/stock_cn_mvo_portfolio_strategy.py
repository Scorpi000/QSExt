# -*- coding: utf-8 -*-
"""均值方差优化投资组合策略"""
import os
import datetime as dt

import numpy as np
import pandas as pd
import cvxpy as cvx
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
from QuantStudio.BackTest.SectionFactor.Portfolio import CalcPortfolioNV
from QuantStudio.Tools.DateTimeFun import getMonthLastDateTime
from QuantStudio.Factor.HDF5DB import HDF5DB
from QuantStudio.Risk.HDF5RDB import HDF5FRDB


class MakeMVOPortfolioStrategy(MakeStrategy):
    def genSignal(self, f, idt, x, last_price, cash, position_num, args):
        ExpectedReturn, Mask, BmkWeight, CovMatrix = x[0].iloc[-1], x[1].iloc[-1], x[2].iloc[-1], x[3].loc[idt]
        
        BmkWeight = BmkWeight.fillna(0)
        BmkMask = (BmkWeight > 0)
        Mask = (pd.notnull(last_price) & pd.notnull(ExpectedReturn) & (~ CovMatrix.isnull().all()) & Mask)
        
        ProblemMask = Mask | BmkMask
        ExpectedReturn, BmkWeight, CovMatrix = ExpectedReturn[ProblemMask], BmkWeight[ProblemMask], CovMatrix.loc[ProblemMask, ProblemMask]
        ExpectedReturn = ExpectedReturn.fillna(0)
        NullMask = (CovMatrix.isnull().all() | ExpectedReturn.isnull())
        CovMatrix = CovMatrix.values.copy()
        Diag = np.diag(CovMatrix)
        np.fill_diagonal(CovMatrix, np.where(pd.notnull(Diag), Diag, 1))
        CovMatrix = np.where(pd.notnull(CovMatrix), CovMatrix, 0)
        
        w = cvx.Variable(shape=(ExpectedReturn.shape[0],))
        Obj = ExpectedReturn.values @ w
        Constraints = [
            w >= 0,
            w <= 1,
            w[NullMask] == 0,
            cvx.quad_form(w - BmkWeight.values, CovMatrix, assume_PSD=True) <= args["sigma"]**2 / 12
        ]
        Problem = cvx.Problem(cvx.Maximize(Obj), Constraints)
        Problem.solve(verbose=True)
        Portfolio = pd.Series(w.value, index=ExpectedReturn.index)
        Portfolio[Portfolio.abs() < 1e-6] = 0
        return Portfolio


if __name__=="__main__":
    HDB = HDF5DB(args={"MainDir": "/mnt/d/Data/HDF5DB"}).connect()
    HRDB = HDF5FRDB(args={"MainDir": "/mnt/d/Data/HDF5RDB"}).connect()
    if not os.path.exists(CacheDir := "/mnt/d/Data/Cache/Strategy/stock_cn_mvo_portfolio_strategy"): os.makedirs(CacheDir, exist_ok=True)

    StartDT, EndDT = dt.datetime(2014, 1, 1), dt.datetime(2026, 2, 28)# 数据起止时间
    TestStartDT, TestEndDT = dt.datetime(2025, 1, 1), EndDT# 测试起止时间

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
    Mask = ((IfListed == 1) & (IfTrading == 1) & (~ fo.NotNull()(ST)))

    # 基准权重
    FT = HDB.getTable("stock_cn_index_component")
    BmkWeight = FT.getFactor("zz500_weight")

    # 预期收益因子 
    FT = HDB.getTable("stock_cn_multi_factor_simple")
    ExpectedReturn = FT.getFactor("score_ew")

    RT = HRDB.getTable("stock_cn_barra_risk_model")

    # 策略因子
    makeMVOPortfolioStrategy = MakeMVOPortfolioStrategy(signal_type="目标权重", init_cash=1e6, start_dt=TestDTs[0], x_lookback=[0]*3, x_section_ids=[None]*3, args={"ModelArgs": {"sigma": 0.03}})
    Strategy = makeMVOPortfolioStrategy(
        ExpectedReturn, Mask, BmkWeight, 
        last_price=Price, buy_limit=(~Mask), sell_limit=(~Mask), 
        extra_deps=[RT], extra_section_ids=[None], extra_lookback=[0], 
        factor_args={"Name": "MVOStrategy", "CalcDTRuler": BalanceDTs}
    )

    # 基准因子
    FT = HDB.getTable("index_cn_day_bar")
    BmkNV = FT.getFactor("close", args={"SectionIDs": ["000905.SH"]})

    # 策略报告
    StrategyReport = AccountReport(account=Strategy, bmk_nv=BmkNV, args={"GenReport": True})

    NodeList = [StrategyReport]
    Report = BTReport(bt_node_list=NodeList)

    with FeatherFactorCache(args={"DTRuler": DTRuler, "CacheDir": CacheDir, "StartMode": "new"}) as Cache:
        with FactorContext(DTRuler=DTRuler, SectionIDs=SectionIDs, DataCache=Cache) as Context:
            with Engine() as ExecEngine:
                Rslt = ExecEngine.run([Report], Context, fwd_data_list=[DTLocalContext(DTs=TestDTs)], init_data_list=[DTInitData(DTRange=(TestDTs[0], TestDTs[-1]))])

