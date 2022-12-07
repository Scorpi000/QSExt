# -*- coding: utf-8 -*-
"""指数择时因子"""
import datetime as dt

import datetime as dt
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

def LeadingTrendFun(f, idt, iid, x, args):
    ComponentID, StockReturn, StockRtn_20D, StockRollingAmt = x
    StockReturn = pd.Series(StockReturn, index=f.Args.DescriptorSection[1])
    StockRtn_20D = pd.Series(StockRtn_20D, index=f.Args.DescriptorSection[2])
    StockRollingAmt = pd.Series(StockRollingAmt, index=f.Args.DescriptorSection[3])
    Rslt = np.full(shape=ComponentID.shape, fill_value=np.nan)
    for i, iID in enumerate(iid):
        iComponentIDs = ComponentID[i]
        if isinstance(iComponentIDs, list) and (StockRtn_20D.index.intersection(iComponentIDs).shape[0]>0):
            iScore = (StockRtn_20D[iComponentIDs].rank() + StockRollingAmt[iComponentIDs].rank()).sort_values(ascending=False)
            Rslt[i] = StockReturn.loc[iScore.iloc[:int(np.ceil(len(iComponentIDs) * args["Threshold"]))].index].mean()
    return Rslt

def ActivityFun(f, idt, iid, x, args):
    ComponentID, StockTurnover, StockAvgTurnover = x
    Mask = pd.Series(StockTurnover>=StockAvgTurnover*args["Threshold"], index=f.Args.DescriptorSection[1])
    Rslt = np.full(shape=ComponentID.shape, fill_value=np.nan)
    for i, iID in enumerate(iid):
        iComponentIDs = ComponentID[i]
        if isinstance(iComponentIDs, list) and (Mask.index.intersection(iComponentIDs).shape[0]>0):
            Rslt[i] = Mask[iComponentIDs].sum() / len(iComponentIDs)
    return Rslt

def PriceLimitFun(f, idt, iid, x, args):
    ComponentID, ComponentWeight, LimitUp, LimitDown, Amount = x
    Rslt = np.full(shape=ComponentID.shape, fill_value=np.nan)
    LimitUp = pd.Series(LimitUp, index=f.Args.DescriptorSection[2])
    LimitDown = pd.Series(LimitDown, index=f.Args.DescriptorSection[3])
    Amount = pd.Series(Amount, index=f.Args.DescriptorSection[4])
    for i, iID in enumerate(iid):
        iComponentIDs = ComponentID[i]
        if isinstance(iComponentIDs, list):
            iComponentWeight = np.array(ComponentWeight[i])
            iLimitUp = LimitUp.reindex(iComponentIDs).values
            iLimitDown = LimitDown.reindex(iComponentIDs).values
            iAmount = Amount.reindex(iComponentIDs).values
            Rslt[i] = np.nansum(iLimitUp * iAmount * iComponentWeight) - np.nansum(iLimitDown * iAmount * iComponentWeight)
    return Rslt

def HighLowFun(f, idt, iid, x, args):
    ComponentID, High, Low, Close = x
    Rslt = np.full(shape=ComponentID.shape, fill_value=np.nan)
    High = pd.Series(High, index=f.Args.DescriptorSection[1])
    Low = pd.Series(Low, index=f.Args.DescriptorSection[2])
    Close = pd.Series(Close, index=f.Args.DescriptorSection[3])
    for i, iID in enumerate(iid):
        iComponentIDs = ComponentID[i]
        if isinstance(iComponentIDs, list):
            iHigh = High.reindex(iComponentIDs).values
            iLow = Low.reindex(iComponentIDs).values
            iClose = Close.reindex(iComponentIDs).values
            Rslt[i] = (np.sum(iClose>=iHigh) - np.sum(iClose<=iLow)) / len(iComponentIDs)
    return Rslt    
            
def IndexSumFun(f, idt, iid, x, args):
    Value, ComponentID, ComponentWeight = x
    Rslt = np.full(shape=ComponentID.shape, fill_value=np.nan)
    Value = pd.Series(Value, index=f.Args.DescriptorSection[0])
    for i, iIDs in enumerate(ComponentID):
        if isinstance(iIDs, list):
            iComponentWeight = np.array(ComponentWeight[i], dtype=float)
            iValue = Value.reindex(iIDs).values
            if not np.all(np.isnan(iValue)):
                Rslt[i] = np.nansum(iValue * iComponentWeight)
    return Rslt

def IndexSumFun_WithoutWeight(f, idt, iid, x, args):
    Value, ComponentID = x
    Rslt = np.full(shape=ComponentID.shape, fill_value=np.nan)
    Value = pd.Series(Value, index=f.Args.DescriptorSection[0])
    for i, iIDs in enumerate(ComponentID):
        if isinstance(iIDs, list):
            iValue = Value.reindex(iIDs).values
            if not np.all(np.isnan(iValue)):
                Rslt[i] = np.nansum(iValue)
    return Rslt

# args 应该包含的参数
# JYDB: 聚源因子库对象
# id_info_file: ID 配置信息文件地址
def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"].connect()
    IndexDB = args["IndexDB"]
    StockDB = args["StockDB"]
    MacroDB = args["MacroDB"]
    
    StockIDs = JYDB.getStockID(is_current=False)
    
    FT = IndexDB.getTable("index_cn_quote")
    Close = FT.getFactor("close")
    High = FT.getFactor("high")
    Low = FT.getFactor("low")
    Return = FT.getFactor("chg")
                
    FT = IndexDB.getTable("index_cn_stock_component")
    ComponentID = fd.fillna(FT.getFactor("component_code"), lookback=60)
    ComponentWeight = fd.fillna(FT.getFactor("weight"), lookback=60)
    
    FT = StockDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    StockAmount = FT.getFactor("amount")
    StockAdjClose = FT.getFactor("close")
    StockReturn = FT.getFactor("chg")
    StockTurnover = FT.getFactor("turnover_rate")
    
    MacroFT = MacroDB.getTable("macro_cn_indicator_data", args={"回溯天数": np.inf})
        
    # 货币市场
    # Shibor 1M: 反向
    # Shibor 3M: 反向
    Factors.append(fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["601280004"], factor_name="Shibor_1M"))
    Factors.append(fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["601280005"], factor_name="Shibor_3M"))
    # 回购利率 FR007: 反向
    Factors.append(fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["601250002"], factor_name="FR007"))
    
    # 债券市场
    # 国债收益率
    TBondYield_10Y = fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["600020013"], factor_name="TBondYield_10Y")
    TBondYield_3Y = fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["600020007"], factor_name="TBondYield_3Y")
    TBondYield_1Y = fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["600020005"], factor_name="TBondYield_1Y")
    TBondYield_3M = fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["600020002"], factor_name="TBondYield_3M")
    Factors += [TBondYield_10Y, TBondYield_3Y, TBondYield_1Y, TBondYield_3M]
    # 期限利差: 正向
    Factors.append(Factorize(TBondYield_10Y - TBondYield_1Y, factor_name="TBondSpread_10Y_1Y"))
    Factors.append(Factorize(TBondYield_10Y - TBondYield_3M, factor_name="TBondSpread_10Y_3M"))
    # 信用利差
    RiskYield = fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["600100304"])# 三年期AA级企业债收益率
    Factors.append(Factorize(RiskYield - TBondYield_3Y, factor_name="CreditSpread_3Y"))
    
    # 汇率市场
    # 在岸人民币兑美元汇率: 反向
    Factors.append(fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["110253785"], factor_name="USDCNY"))
    # 离岸人民币兑美元汇率: 反向
    Factors.append(fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["110253784"], factor_name="USDCNH"))
    # 美元指数
    Factors.append(fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["190901135"], factor_name="USDX"))
    
    # 大宗市场
    # 金油比: 反向
    OilPrice = fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["1080010001"], factor_name="OilPrice")# WTI 原油期货价格
    GoldPrice = fd.disaggregate(MacroFT.getFactor("value"), aggr_ids=["1330021181"], factor_name="GoldPrice")# COMEX 黄金期货价格
    GoldOilRatio = Factorize(GoldPrice / OilPrice, factor_name="GoldOilRatio")
    Factors += [OilPrice, GoldPrice, GoldOilRatio]
    
    # 全球股市
    # 标普 500: 正向
    FT = JYDB.getTable("指数行情", args={"回溯天数": np.inf})
    Factors.append(fd.disaggregate(FT.getFactor("收盘价(元-点)"), aggr_ids=[".GSPC.NYSE"], factor_name="SP500"))
    
    # 估值水平
    FT = IndexDB.getTable("index_cn_stock_valuation")
    EP = FT.getFactor("ep_ttm", new_name="EP")
    BP = FT.getFactor("bp_lr", new_name="BP")
    DP = FT.getFactor("dp_ttm_jy", new_name="DP")
    RFR = fd.disaggregate(MacroFT.getFactor("value") / 100, aggr_ids=["600020002"], factor_name="RFR")# 无风险利率: 三月期国债收益率
    ERP = Factorize(EP - RFR, factor_name="ERP")
    ERP_Bond = Factorize(EP - TBondYield_10Y, factor_name="ERP_Bond")
    DRP = Factorize(DP - RFR, factor_name="DRP")
    Factors += [EP, BP, DP, ERP, DRP, ERP_Bond]
    
    # 破净占比
    FT = StockDB.getTable("stock_cn_factor_value")
    StockBrokenNet = (FT.getFactor("bp_lr")>1)
    WeightedBrokenNetRatio = QS.FactorDB.SectionOperation(
        "WeightedBrokenNetRatio",
        [StockBrokenNet, ComponentID, ComponentWeight],
        sys_args={
            "算子": IndexSumFun,
            "参数": {},
            "描述子截面": [StockIDs, None, None],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    BrokenNetRatio = QS.FactorDB.SectionOperation(
        "BrokenNetRatio",
        [StockBrokenNet, ComponentID],
        sys_args={
            "算子": IndexSumFun_WithoutWeight,
            "参数": {},
            "描述子截面": [StockIDs, None],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors += [WeightedBrokenNetRatio, BrokenNetRatio]
    
    # 动量指标
    Mom_1M = Factorize(Close / fd.lag(Close, 20, 20) - 1, factor_name="Mom_1M")
    Mom_3M = Factorize(Close / fd.lag(Close, 60, 60) - 1, factor_name="Mom_3M")
    Mom_1Y = Factorize(Close / fd.lag(Close, 240, 240) - 1, factor_name="Mom_1Y")
    Factors += [Mom_1M, Mom_3M, Mom_1Y]
    
    # 防御性行业(食品饮料, 医药)超额收益
    FT = IndexDB.getTable("index_sw_industry_cn_quote")
    FoodBeverageIndustryClose = fd.disaggregate(FT.getFactor("close"), aggr_ids=["801120.SH"])
    HealthCareIndustryClose = fd.disaggregate(FT.getFactor("close"), aggr_ids=["801150.SH"])
    Factors.append(Factorize(FoodBeverageIndustryClose / fd.lag(FoodBeverageIndustryClose, 20, 20) - 1 - Mom_1M, factor_name="FoodBeverageExcessReturn_1M"))
    Factors.append(Factorize(HealthCareIndustryClose / fd.lag(HealthCareIndustryClose, 20, 20) - 1 - Mom_1M, factor_name="HealthCareExcessReturn_1M"))
    
    # 股票涨跌停板: 正向
    FT = StockDB.getTable("stock_cn_quote_special")
    LimitUp = FT.getFactor("if_limit_up")
    LimitDown = FT.getFactor("if_limit_down")
    PriceLimit = QS.FactorDB.SectionOperation(
        "PriceLimit",
        [ComponentID, ComponentWeight, LimitUp, LimitDown, StockAmount],
        sys_args={
            "算子": PriceLimitFun,
            "参数": {},
            "描述子截面": [None, None, StockIDs, StockIDs, StockIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    
    # 龙头股趋势: 正向
    StockRtn_20D = StockAdjClose / fd.lag(StockAdjClose, 20, 20) - 1
    StockRollingAmt = fd.rolling_sum(StockAmount, 20)
    LeadingTrend = QS.FactorDB.SectionOperation(
        "LeadingTrend",
        [ComponentID, StockReturn, StockRtn_20D, StockRollingAmt],
        sys_args={
            "算子": LeadingTrendFun,
            "参数": {"Threshold": 0.03},
            "描述子截面": [None, StockIDs, StockIDs, StockIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    
    # 市场强弱指标: 正向
    StockHigh = fd.rolling_max(StockAdjClose, window=60, min_periods=40)
    StockLow = fd.rolling_min(StockAdjClose, window=60, min_periods=40)
    HighLow = QS.FactorDB.SectionOperation(
        "HighLow",
        [ComponentID, StockHigh, StockLow, StockAdjClose],
        sys_args={
            "算子": HighLowFun,
            "参数": {},
            "描述子截面": [None, StockIDs, StockIDs, StockIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors.append(HighLow)
    
    # 市场活跃度: 正向
    StockAvgTurnover_5D = fd.rolling_mean(fd.where(StockTurnover, StockTurnover!=0, np.nan), window=5, min_periods=1)
    Activity = QS.FactorDB.SectionOperation(
        "Activity",
        [ComponentID, StockTurnover, fd.lag(StockAvgTurnover_5D, 1, 1)],
        sys_args={
            "算子": ActivityFun,
            "参数": {"Threshold": 1.5},
            "描述子截面": [None, StockIDs, StockIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors.append(Activity)
    
    # RSRS
    N, M = 18, 600
    RSRS = Factorize(fd.rolling_cov(Low, High, window=N, min_periods=N, ddof=0) / fd.rolling_var(Low, window=N, min_periods=N, ddof=0), factor_name="RSRS")
    RSRS_zscore = Factorize((RSRS - fd.rolling_mean(RSRS, M, M)) / fd.rolling_std(RSRS, M, M, ddof=1), factor_name="RSRS_zscore")
    R = fd.rolling_corr(Low, High, window=N, min_periods=N, ddof=0)
    RSRS_Adj = Factorize(RSRS_zscore * R ** 2, factor_name="RSRS_Adj")
    RSRS_RShewed = Factorize(RSRS_zscore * R ** 2 * RSRS, factor_name="RSRS_Shewed")
    RSRS_Passivation = Factorize(RSRS_zscore * R ** (4 * fd.rolling_rank(fd.rolling_std(Return, N, N), M, M) / M), factor_name="RSRS_Passivation")
    Factors += [RSRS, RSRS_zscore, RSRS_Adj, RSRS_RShewed, RSRS_Passivation]
    
    # 融资融券
    FT = JYDB.getTable("融资融券交易明细")
    StockFinanceValue = FT.getFactor("融资余额(元)")
    StockSecurityValue = FT.getFactor("融券余额(元)")
    Mask = (fd.notnull(StockFinanceValue) | fd.notnull(StockSecurityValue))
    StockFinanceSecurityDiff = fd.fillna(StockFinanceValue, value=0) - fd.fillna(StockSecurityValue, value=0)
    StockFinanceSecurityDiff = fd.where(StockFinanceSecurityDiff, Mask, np.nan)
    FinanceValue = QS.FactorDB.SectionOperation(
        "FinanceValue",
        [StockFinanceValue, ComponentID, ComponentWeight],
        sys_args={
            "算子": IndexSumFun,
            "参数": {},
            "描述子截面": [StockIDs, None, None],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    SecurityValue = QS.FactorDB.SectionOperation(
        "SecurityValue",
        [StockSecurityValue, ComponentID, ComponentWeight],
        sys_args={
            "算子": IndexSumFun,
            "参数": {},
            "描述子截面": [StockIDs, None, None],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    FinanceSecurityDiff = QS.FactorDB.SectionOperation(
        "FinanceSecurityDiff",
        [StockFinanceSecurityDiff, ComponentID, ComponentWeight],
        sys_args={
            "算子": IndexSumFun,
            "参数": {},
            "描述子截面": [StockIDs, None, None],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors += [FinanceSecurityDiff, FinanceValue, SecurityValue]
    
    # 北向资金
    FT = StockDB.getFactor("stock_cn_shszc")
    StockSHSZCHoldingRatio = FT.getFactor("holding_ratio")
    SHSZCHoldingRatio = QS.FactorDB.SectionOperation(
        "SHSZCHoldingAmt",
        [StockSHSZCHoldingRatio, ComponentID, ComponentWeight],
        sys_args={
            "算子": IndexSumFun,
            "参数": {},
            "描述子截面": [StockIDs, None, None],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )    
    
    StockSHSZCHoldingAmt = FT.getFactor("holding_amount")
    SHSZCHoldingAmt = QS.FactorDB.SectionOperation(
        "SHSZCHoldingAmt",
        [StockSHSZCHoldingAmt, ComponentID, ComponentWeight],
        sys_args={
            "算子": IndexSumFun,
            "参数": {},
            "描述子截面": [StockIDs, None, None],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors += [SHSZCHoldingAmt, SHSZCHoldingRatio]
    
    # 大股东增减持
    FT = StockDB.getTable("stock_cn_share_chg")
    StockShareholderRatioChg = FT.getFactor("shareholder_ratio_chg")
    ShareholderRatioChg = QS.FactorDB.SectionOperation(
        "ShareholderRatioChg",
        [StockShareholderRatioChg, ComponentID, ComponentWeight],
        sys_args={
            "算子": IndexSumFun,
            "参数": {},
            "描述子截面": [StockIDs, None, None],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors.append(ShareholderRatioChg)
    
    UpdateArgs = {
        "因子表": "index_cn_factor_timing",
        "默认起始日": dt.datetime(2000, 1, 1),
        "最长回溯期": 365,
        "IDs": "外部指定"
    }
    
    return (Factors, UpdateArgs)

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_FactorTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Args = {"JYDB": JYDB, "id_info_file": [r"../conf/index/IndexIDs_cn.csv", r"../conf/index/IndexIDs_IndexMF.csv", r"../conf/index/IndexIDs_ETF.csv"]}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)

    StartDT, EndDT = dt.datetime(2000, 1, 1), dt.datetime(2021, 6, 30)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
    IDs = UpdateArgs["IDs"]
    #IDs = ["CI005917", "CI005918", "CI005919", "CI005920", "CI005921"]
    #IDs = ["CI005910", "CI005909", "CI005912", "CI005019", "CI005018", "CI005905", "CI005015"]
    IDs = ["H30267","930609","930610","930889","930890","930891","930892","930893","930895","930897","930898","H11020","H11021","H11023","H11024","H11026","H11027","H11028","930950","931153"]
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTRuler)
    CFT.setID(IDs)

    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
                  factor_db=TDB, table_name=TargetTable,
                  if_exists="update", subprocess_num=0)

    TDB.disconnect()
    JYDB.disconnect()