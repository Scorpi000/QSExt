# -*- coding: utf-8 -*-
"""基于收益率回归的基金大类资产穿透(TODO)"""
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
# x: [基金收益率, 指数收益率, 无风险利率, 基准收益率, 基金类型]
# args: {min_periods:..., index_info:...}
def asset_decompose_fun(f, idt, iid, x, args):
    NaMask = (np.sum(pd.notnull(x[0]), axis=0)<args["min_periods"])
    Y = (x[0] - x[2]) * 10000
    X = (x[1] - np.repeat(x[2][:, :1], x[1].shape[1], axis=1))  * 10000
    B = x[3] - x[2]
    Type = x[4][0]
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
        if Type[i]=="货币型":
            beta = np.zeros((iX.shape[1],))
            beta[args["cash_idx"]] = 1
            iResid = iY - np.dot(iX[:, 1:], beta)
            Rslt[i, 3] = np.mean(iResid) / 10000
            Rslt[i, 4:] = beta
            Rslt[i, 0] = np.std(iResid) / 10000# sigma
            Rslt[i, 1] = 1 - np.var(iResid) / np.var(iY, ddof=0)# R2
            Rslt[i, 2] = np.nanmean(np.dot(iX, beta) / 10000 + Rslt[i, 3] - iB)
            continue
        beta = cvx.Variable(iX.shape[1])
        Obj = cvx.Minimize(cvx.norm2(iY - iX * beta))
        Constraints = [beta[1:]>=0, np.sum(beta[1:])==1, beta[args["cash_idx"]+1]>=0.05]
        if Type[i] in ("标准股票型","指数股票型","其他股票型"):
            if idt[-1]>=dt.datetime(2015, 8, 8):
                Constraints.append(beta>=0.6)# TODO
        Prob = cvx.Problem(Obj, Constraints)
        try:
            Prob.solve()
        except:
            try:
                Prob.solve(solver="SCS")
            except Exception as e:
                f.Logger.warning(e)
                continue
        Rslt[i, 3] = beta.value[0] / 10000
        Rslt[i, 4:] = np.clip(beta.value[1:], 0, 1)
        Rslt[i, 0] = np.std(iY - np.dot(iX, beta.value)) / 10000# sigma
        Rslt[i, 1] = 1 - np.var(iY - np.dot(iX, beta.value)) / np.var(iY, ddof=0)# R2
        Rslt[i, 2] = np.nanmean(np.dot(iX, beta.value) / 10000 - iB)
    return pd.DataFrame(Rslt).to_records(index=False).tolist()


# args 应该包含的参数
# window：窗口长度，默认 252
# min_periods：可以计算指标的最小样本量要求，默认 126
# config_file：配置文件地址
# ND_RF：无风险利率的全年计息天数, 默认 360
def defFactor(args={}, debug=False):
    # 指标计算参数
    window = args.get("window", 252)
    min_periods = args.get("min_periods", 126)
    ND_RF = args.get("ND_RF", 360)
    
    # 大类资产配置文件
    AssetInfo = pd.read_csv(args["config_file"], index_col=0, header=0, encoding="utf-8", engine="python")
    
    Factors = []

    JYDB = args["JYDB"]

    # ############################ 基础因子 ############################################
    FT = JYDB.getTable("公募基金复权净值")
    DailyReturn = FT.getFactor("复权单位净值日增长率", args={"回溯天数": 0}) / 100
    
    FT = JYDB.getTable("公募基金聚源分类")
    Type = FT.getFactor("二级分类名称")# 基金分类
    
    # 无风险利率, 日频
    RiskFreeRateID = "600020002"  # 3月期国债利率
    FT = JYDB.getTable("宏观基础指标数据", args={"回溯天数": np.inf, "忽略公告日": True, "忽略时间": True})
    PowerNum = FT.getFactor("量纲系数")
    rf = fd.disaggregate(FT.getFactor("指标数据") / 100 * 10 ** PowerNum, aggr_ids=[RiskFreeRateID])# 无风险年化收益率
    RiskFreeDailyRate = rf / ND_RF
    
    # 大类资产收益率, 日频
    FT = JYDB.getTable("指数行情", args={"回溯天数": 0})
    AssetDailyReturn = FT.getFactor("涨跌幅") / 100
    
    # 基准收益率, 日频
    FT = JYDB.getTable("公募基金基准收益率", args={"回溯天数": 0})
    BenchmarkDailyReturn = FT.getFactor("本日基金基准增长率") / 100

    Rslt = QS.FactorDB.PanelOperation(
        "大类资产分解结果",
        [DailyReturn, AssetDailyReturn, RiskFreeDailyRate, BenchmarkDailyReturn, Type],
        sys_args={
            "算子": asset_decompose_fun,
            "参数": {'min_periods': min_periods, 'cash_idx': AssetInfo.index.tolist().index("H11025")},
            "回溯期数": [window-1] * 4 + [1-1],
            "描述子截面": [None, AssetInfo.index.tolist(), None, None],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "string"
        }
    )
    Factors.append(fd.fetch(Rslt, pos=0, factor_name="sigma"))
    Factors.append(fd.fetch(Rslt, pos=1, factor_name="r_squared"))
    Factors.append(fd.fetch(Rslt, pos=2, factor_name="asset_alpha"))
    Factors.append(fd.fetch(Rslt, pos=3, factor_name="security_alpha"))
    Descriptors = OrderedDict()
    for i, iAsset in enumerate(AssetInfo["asset2"]):
        Descriptors[iAsset] = fd.fetch(Rslt, pos=i+4, factor_name=iAsset)
        Factors.append(Descriptors[iAsset])
    for iAsset in pd.unique(AssetInfo["asset1"]):
        iMask = (AssetInfo["asset1"]==iAsset)
        if iMask.sum()==1:
            continue
        iAssetInfo = AssetInfo[iMask]
        Factors.append(fd.nansum(*[Descriptors[jSubAsset] for jSubAsset in iAssetInfo["asset2"]], factor_name=iAsset))

    UpdateArgs = {"因子表": "mf_cn_asset_portfolio_regress",
                  "默认起始日": dt.datetime(2002,1,1),
                  "最长回溯期": 365 * 5,
                  "IDs": "公募基金"}

    return (Factors, UpdateArgs)


if __name__ == "__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB()
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    #Factors, UpdateArgs = defFactor(args={"JYDB": JYDB, "window": 252, "min_periods": 126, "config_file": "/home/hushuntai/Scripts/因子定义/conf/mf/mf_cn_asset_portfolio_regress_config.csv"}, debug=True)
    Factors, UpdateArgs = defFactor(args={"JYDB": JYDB, "window": 126, "min_periods": 63, "config_file": "/home/hushuntai/Scripts/因子定义/conf/mf/mf_cn_asset_portfolio_regress_config.csv"}, debug=True)
    #Factors, UpdateArgs = defFactor(args={"JYDB": JYDB, "window": 63, "min_periods": 30, "config_file": "/home/hushuntai/Scripts/因子定义/conf/mf/mf_cn_asset_portfolio_regress_config.csv"}, debug=True)

    StartDT, EndDT = dt.datetime(2020, 3, 1), dt.datetime(2020, 5, 31)
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