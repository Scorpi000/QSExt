# -*- coding: utf-8 -*-
"""基于收益率回归的基金大类资产穿透"""
import os
import datetime as dt
from collections import OrderedDict

import numpy as np
import pandas as pd
import cvxpy as cvx

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# 大类资产分解, PanelOperation, 单时点, 全截面
# x: [基金收益率, 指数收益率, 无风险利率]
# args: {min_periods:..., index_info:...}
def asset_decompose_fun(f, idt, iid, x, args):
    NaMask = (np.sum(pd.notnull(x[0]), axis=0)<args["min_periods"])
    Y = x[0] - x[2]
    X = x[1] - np.repeat(x[2][:, :1], x[1].shape[1], axis=1)
    B = x[3] - x[2]
    Mask = np.all(pd.notnull(X), axis=1)
    Y = Y[Mask, :]
    B = B[Mask, :]
    X = np.c_[np.ones((Y.shape[0],1)), X[Mask, :]]
    Mask = pd.notnull(Y)
    Rslt = np.full(shape=(Y.shape[1], 3+X.shape[1]), fill_value=np.nan)
    for i in range(Y.shape[1]):
        iMask = Mask[:, i]
        if np.sum(iMask)<args["min_periods"]: continue
        iX = X[iMask, :]
        iY = Y[iMask, i]
        iB = B[iMask, i]
        beta = cvx.Variable(iX.shape[1])
        Prob = cvx.Problem(cvx.Minimize(cvx.norm2(iY - iX * beta)), [beta[1:]>=0, np.ones((1, iX.shape[1]-1)) * beta[1:]==1])# 全额约束
        #Prob = cvx.Problem(cvx.Minimize(cvx.norm2(iY - iX * beta)), [beta[1:]>=0, np.ones((1, iX.shape[1]-1)) * beta[1:]<=1])# 无全额约束
        try:
            Prob.solve()
        except Exception as e:
            try:
                Prob.solve(solver="SCS")
            except Exception as e:
                f.Logger.debug(str(e))
                continue
        Rslt[i, 3:] = beta.value
        Rslt[i, 0] = np.std(iY - np.dot(iX, beta.value), ddof=0)# sigma
        Rslt[i, 1] = 1 - Rslt[i, 0]**2 / np.var(iY, ddof=0)# R2
        Rslt[i, 2] = np.nanmean(np.dot(iX, beta.value) - iB)
    return pd.DataFrame(Rslt).to_records(index=False).tolist()

# args 应该包含的参数
# JYDB: 聚源因子库对象
# config_file：配置文件地址
# ND_RF：无风险利率的全年计息天数, 默认 360
def defFactor(args={}, debug=False):
    # 指标计算参数
    ND_RF = args.get("ND_RF", 360)
    
    # 大类资产配置文件
    AssetInfo = pd.read_csv(args["config_file"], index_col=0, header=0, encoding="utf-8", engine="python")
    
    Factors = []

    JYDB = args["JYDB"]

    # ############################ 基础因子 ############################################
    FT = JYDB.getTable("公募基金复权净值")
    DailyReturn = FT.getFactor("复权单位净值日增长率", args={"回溯天数": 0}) / 100
    
    # 无风险利率, 日频
    RiskFreeRateID = "600020002"# 3月期国债利率
    FT = JYDB.getTable("宏观基础指标数据", args={"回溯天数": np.inf, "忽略公告日": True, "忽略时间": True})
    PowerNum = FT.getFactor("量纲系数")
    rf = fd.disaggregate(FT.getFactor("指标数据") / 100 * 10 ** PowerNum, aggr_ids=[RiskFreeRateID])# 无风险年化收益率
    RiskFreeDailyRate = rf / ND_RF
    
    # 大类资产收益率, 日频
    FT = JYDB.getTable("指数行情", args={"回溯天数": 0})
    #AssetDailyReturn = FT.getFactor("涨跌幅") / 100
    Close = FT.getFactor("收盘价(元-点)", args={"回溯天数": np.inf})
    AssetDailyReturn = Close / fd.lag(Close, 1, 1) - 1
    
    # 基准收益率, 日频
    FT = JYDB.getTable("公募基金基准收益率", args={"回溯天数": 0})
    BenchmarkDailyReturn = FT.getFactor("本日基金基准增长率") / 100
    
    look_back_period = {'1m': 21, '3m': 63, '6m': 126, '1y': 252}  # 回溯期
    min_period = 21# 最小期数
    min_period_ratio = 0.5# 最小期数比例
    
    for iLookBack, iLookBackPeriods in look_back_period.items():
        Rslt = QS.FactorDB.PanelOperation(
            "大类资产分解结果",
            [DailyReturn, AssetDailyReturn, RiskFreeDailyRate, BenchmarkDailyReturn],
            sys_args={
                "算子": asset_decompose_fun,
                "参数": {'min_periods': max((min_period, int(iLookBackPeriods * min_period_ratio)))},
                "回溯期数": [iLookBackPeriods-1] * 4,
                "描述子截面": [None, AssetInfo.index.tolist(), None, None],
                "运算时点": "单时点",
                "输出形式": "全截面",
                "数据类型": "string"
            }
        )
        Factors.append(fd.fetch(Rslt, pos=0, factor_name=f"sigma_{iLookBack}"))
        Factors.append(fd.fetch(Rslt, pos=1, factor_name=f"r_squared_{iLookBack}"))
        Factors.append(fd.fetch(Rslt, pos=2, factor_name=f"asset_alpha_{iLookBack}"))
        Factors.append(fd.fetch(Rslt, pos=3, factor_name=f"security_alpha_{iLookBack}"))
        Descriptors = OrderedDict()
        for i, iAsset in enumerate(AssetInfo["asset2"]):
            Descriptors[iAsset] = fd.fetch(Rslt, pos=i+4, factor_name=f"{iAsset}_{iLookBack}")
            Factors.append(Descriptors[iAsset])
        for iAsset in pd.unique(AssetInfo["asset1"]):
            iMask = (AssetInfo["asset1"]==iAsset)
            if iMask.sum()==1:
                continue
            iAssetInfo = AssetInfo[iMask]
            Factors.append(fd.nansum(*[Descriptors[jSubAsset] for jSubAsset in iAssetInfo["asset2"]], factor_name=f"{iAsset}_{iLookBack}"))

    UpdateArgs = {"因子表": "mf_cn_asset_allocation_regress",
                  "默认起始日": dt.datetime(2002,1,1),
                  "最长回溯期": 365 * 5,
                  "IDs": "公募基金"}

    return (Factors, UpdateArgs)


if __name__ == "__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Factors, UpdateArgs = defFactor(args={"JYDB": JYDB, "config_file": "/home/hushuntai/Scripts/因子定义/conf/mf/mf_cn_asset_portfolio_regress_config_bond_issuer.csv"}, debug=True)

    StartDT, EndDT = dt.datetime(2020, 6, 1), dt.datetime(2020, 9, 25)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365*5), end_date=EndDT.date(), output_type="datetime")

    #IDs = sorted(pd.read_csv("/home/hushuntai/Scripts/因子定义/conf/mf/MFIDs.csv", index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
    IDs = JYDB.getMutualFundID(is_current=False)

    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTRuler)
    CFT.setID(IDs)

    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
                  factor_db=TDB, table_name=TargetTable,
                  if_exists="update", subprocess_num=20)

    TDB.disconnect()
    JYDB.disconnect()