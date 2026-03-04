# coding=utf8
import datetime as dt
from collections import OrderedDict

import numpy as np
import pandas as pd
from scipy import stats

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

# 按照市值和行业对样本进行分组
def partitionSample(f, idt, iid, x, args):
    IsListed, CatData, SubCatData = x[0], x[1], x[2]
    Mask = (pd.notnull(CatData) & pd.notnull(SubCatData) & (IsListed==1))
    AllCat = np.unique(CatData[Mask])
    Rslt = np.zeros(IsListed.shape)
    for j, jCat in enumerate(AllCat):
        jMask = ((CatData==jCat) & Mask)
        jSubCatMask = (SubCatData>np.nanmedian(SubCatData[jMask]))
        Rslt[(jMask & jSubCatMask)] = 2 * j + 1
        Rslt[(jMask & (~jSubCatMask))] = 2 * j + 2
    return Rslt

# 生成类别型因变量, +1, -1, 0 表示非样本
def genYLabel(f, idt, iid, x, args):
    TopBottomRatio = args["TopBottomRatio"]
    PartitionFactor, Return = x[0][0, :], x[1][0, :]
    AllCat = np.unique(PartitionFactor[PartitionFactor>0])
    YLabel = np.zeros(Return.shape)
    for jCat in AllCat:
        jMask = (PartitionFactor==jCat)
        jReturn = Return[jMask]
        jSelectedNum = int(jReturn.shape[0] * TopBottomRatio)
        if jSelectedNum==0:
            jSubMask = (Return>=np.nanmedian(jReturn))
            YLabel[jMask & jSubMask] = 1
            YLabel[jMask & (~jSubMask)] = -1
        else:
            YLabel[jMask & (Return >= np.nanpercentile(jReturn, (1-TopBottomRatio)*100))] = 1
            YLabel[jMask & (Return <= np.nanpercentile(jReturn, TopBottomRatio*100))] = -1
    return YLabel

# AdaBoost 模型
def AdaBoost(factor_data, ret_mask, level, quantile_num=5):
    # 逐层构造 weak classifier
    ret_mask = (ret_mask==1)
    nData = ret_mask.shape[0]
    h = np.zeros((quantile_num, level))# weak classifier
    SelectedIndex = [None] * level
    FactorIndex = np.arange(0, factor_data.shape[1])
    Weight = 1 / nData * np.ones(nData)
    Epsilon = 1 / nData
    for lLevel in range(level):
        ZMin = np.inf
        for k in FactorIndex:
            kFactorData = factor_data[:, k]
            kMask = np.isnan(kFactorData)
            if kFactorData.shape[0] - np.sum(kMask)<quantile_num: continue
            kWeight = Weight.copy()
            kWeight[kMask] = 0
            kWeight = kWeight / np.nansum(kWeight)
            kZ = 0.0
            kh = np.zeros(quantile_num)
            for jQuantile in range(quantile_num):
                RightThreshold = np.nanpercentile(kFactorData, (jQuantile+1) / quantile_num * 100)
                if jQuantile!=0:
                    LeftThreshold = np.nanpercentile(kFactorData, jQuantile / quantile_num * 100)
                    kjMask = ((kFactorData>LeftThreshold) & (kFactorData<=RightThreshold))
                else:
                    kjMask = (kFactorData<=RightThreshold)
                kjQuantileData = kFactorData[kjMask]
                kjWPos = np.nansum(kWeight[kjMask & ret_mask])
                kjWNeg = np.nansum(kWeight[kjMask & (~ret_mask)])
                kZ += np.sqrt(kjWPos * kjWNeg)
                if pd.notnull(kjWPos) and pd.notnull(kjWNeg):
                    kh[jQuantile] = 1 / 2 * np.log((kjWPos + Epsilon) / (kjWNeg + Epsilon))
            if kZ<ZMin:
                ZMin = kZ
                SelectedIndex[lLevel] = k
                h[:, lLevel] = kh
        if SelectedIndex[lLevel] is None:# 没有足够的数据
            return (None, None)
        lFactorData = factor_data[:, SelectedIndex[lLevel]]
        GroupData = np.zeros(nData, dtype=int) - 1
        for jQuantile in range(quantile_num):
            RightThreshold = np.nanpercentile(lFactorData, (jQuantile+1) / quantile_num * 100)
            if jQuantile!=0:
                LeftThreshold = np.nanpercentile(lFactorData, jQuantile / quantile_num * 100)
                GroupData[(lFactorData>LeftThreshold) & (lFactorData<=RightThreshold)] = jQuantile
            else:
                GroupData[lFactorData<=RightThreshold] = jQuantile
        for i in range(nData):
            if GroupData[i]!=-1:
                if ret_mask[i]:
                    Weight[i] = Weight[i] * np.exp(-h[GroupData[i], lLevel])
                else:
                    Weight[i] = Weight[i] * np.exp(h[GroupData[i], lLevel])
        Weight = Weight / np.nansum(Weight)
    return (h, SelectedIndex)

# 训练 AdaBoost 模型
def trainAdaBoostModel(f, idt, iid, x, args):
    IsListed = x[0][0, :]
    YLabel = x[1]
    Mask = (YLabel!=0)
    YLabel = YLabel[Mask]
    if YLabel.shape[0]==0:
        return np.full(shape=IsListed.shape, fill_value=np.nan)
    FactorData = np.array([ix[-1, :] for ix in x[2:]]).T
    h, SelectedIndex = AdaBoost(FactorData, YLabel, level=args["Level"], quantile_num=args["QuantileNum"])
    if h is None:
        return np.full(shape=IsListed.shape, fill_value=np.nan)
    NewFactorData = np.array([ix[-1, :] for ix in x[2:]]).T
    SAData = np.full(shape=(NewFactorData.shape[0],), fill_value=np.nan)
    for j, jIndex in enumerate(SelectedIndex):
        jFactorData = NewFactorData[:, jIndex]
        for kQuantile in range(args["QuantileNum"]):
            RightThreshold = np.nanpercentile(jFactorData, (kQuantile+1) / args["QuantitleNum"] * 100)
            if kQuantile!=0:
                LeftThreshold = np.nanpercentile(jFactorData, kQuantile / args["QuantileNum"] * 100)
                kMask = ((jFactorData>LeftThreshold) & (jFactorData<=RightThreshold))
            else:
                kMask = (jFactorData<=RightThreshold)
            jkSAData = SAData[kMask]
            kNAMask = np.isnan(jkSAData)
            jkSAData[~kNAMask] += h[kQuantile, j]
            jkSAData[kNAMask] = h[kQuantile, j]
            SAData[kMask] = jkSAData
    Rslt = np.full(shape=IsListed.shape, fill_value=np.nan)
    Rslt[Mask] = SAData
    return Rslt

# 训练失效信息模型
def trainLossModel(f, idt, iid, x, args):
    Return = x[2]
    LossFactor = x[1][:-1, :]
    IC = np.full(shape=(Return.shape[0],), fill_value=np.nan)
    for i in range(Return.shape[0]):
        iReturn = Return[i, :]
        iLossFactor = LossFactor[i, :]
        try:
            IC[i] = stats.spearmanr(iReturn, iLossFactor, nan_policy="omit").correlation
        except:
            pass
    ICMask = (IC<=np.nanmean(IC))
    IsListed = x[0][0, :]
    if np.sum(ICMask)<Return.shape[0] * 0.2:
        return np.full(shape=IsListed.shape, fill_value=np.nan)
    YLabel = x[3][ICMask, :]
    Mask = (YLabel!=0)
    YLabel = YLabel[Mask]
    FactorData = np.array([ix[:-1, :][ICMask, :][Mask] for ix in x[4:]]).T
    h, SelectedIndex = AdaBoost(FactorData, YLabel, level=args["Level"], quantile_num=args["QuantileNum"])
    NewFactorData = np.array([ix[-1, :] for ix in x[4:]]).T
    Mask = (IsListed==1)
    NewFactorData = NewFactorData[Mask, :]
    SAData = np.full(shape=(NewFactorData.shape[0], ), fill_value=np.nan)
    for j, jIndex in enumerate(SelectedIndex):
        jFactorData = NewFactorData[:, jIndex]
        for kQuantile in range(args["QuantileNum"]):
            RightThreshold = np.nanpercentile(jFactorData, (kQuantile+1) / args["QuantileNum"] * 100)
            if kQuantile!=0:
                LeftThreshold = np.nanpercentile(jFactorData, kQuantile / args["QuantileNum"] * 100)
                kMask = ((jFactorData>LeftThreshold) & (jFactorData<=RightThreshold))
            else:
                kMask = (jFactorData<=RightThreshold)
            jkSAData = SAData[kMask]
            kNAMask = np.isnan(jkSAData)
            jkSAData[~kNAMask] += h[kQuantile, j]
            jkSAData[kNAMask] = h[kQuantile, j]
            SAData[kMask] = jkSAData
    Rslt = np.full(shape=IsListed.shape, fill_value=np.nan)
    Rslt[Mask] = SAData
    return Rslt

def mergeModel(f, idt, iid, x, args):
    Rslt = np.zeros(x[0].shape)
    TotalWeight = np.zeros(x[0].shape)
    for i, ix in enumerate(x):
        iWeight = args["权重"][i]
        iMask = np.isnan(ix)
        ix[iMask] = 0.0
        Rslt += iWeight * ix
        TotalWeight += iWeight * (~iMask)
    TotalWeight[TotalWeight==0] = np.nan
    return Rslt / TotalWeight

def defFactor(args, debug=False):
    Factors = []
    
    SampleLen = args.get("sample_len", 12)
    Suffix = args.get("suffix", "1y")
    LDB = args["LDB"]
    
    FT = LDB.getTable("stock_cn_info_history")
    Industry = FT.getFactor("citic_industry")
    IsListed = FT.getFactor("if_listed")
    
    FT = LDB.getTable("stock_cn_quote_adj_backward_nafilled")
    FloatCap = FT.getFactor("negotiable_market_cap")
    Price = FT.getFactor("close")
    Return = Price / fd.lag(Price, 1, 1) - 1
    
    # 导入模型所用的因子
    FactorInfo = pd.read_csv(args["factor_info_file"], encoding="utf-8", header=0, index_col=None).set_index(["因子表", "因子名称"])
    if debug: FactorInfo = FactorInfo.iloc[:10, :]
    TableNames = FactorInfo.index.get_level_values(0).drop_duplicates()
    TrainFactors = OrderedDict()
    for iTable in TableNames:
        iFT = LDB.getTable(iTable)
        for jFactor in FactorInfo.loc[iTable].index:
            TrainFactors[jFactor] = iFT.getFactor(jFactor)
    nTrainFactor = len(TrainFactors)
    
    # 数据预处理形成训练样本
    PartitionFactor = QS.FactorDB.SectionOperation("分组因子", [IsListed, Industry, FloatCap], {"算子": partitionSample})
    for iFactor in TrainFactors:
        TrainFactors[iFactor] = fd.standardizeRank(TrainFactors[iFactor], mask=IsListed, cat_data=PartitionFactor, offset=0.0)
    YLabel = QS.FactorDB.PanelOperation("YLabel", [PartitionFactor, Return], {"算子": genYLabel, "参数": {"TopBottomRatio": 0.3}, "回溯期数": [1, 0]})
    
    # AdaBoost 模型
    ModelArgs = {"Level": 20, "QuantileNum": 5}
    ISNSAFactor = QS.FactorDB.PanelOperation(f"adaboost_{Suffix}", [IsListed, YLabel]+list(TrainFactors.values()), {"算子": trainAdaBoostModel, "参数": ModelArgs, "回溯期数": [1-1, SampleLen-1]+[SampleLen+1-1]*nTrainFactor})
    Factors.append(ISNSAFactor)
    
    # 失效信息模型
    ISNLSAFactor = QS.FactorDB.PanelOperation(f"adaboost_loss_{Suffix}", [IsListed, ISNSAFactor, Return, YLabel]+list(TrainFactors.values()), {"算子": trainLossModel, "参数": ModelArgs, "回溯期数": [0, 5*SampleLen, 5*SampleLen-1, 5*SampleLen-1]+[5*SampleLen]*nTrainFactor})
    Factors.append(ISNLSAFactor)
    
    # AdaBoost 合并模型
    Mask = (IsListed==1)
    ISNSAFactor = fd.standardizeZScore(ISNSAFactor, mask=Mask)
    ISNLSAFactor = fd.standardizeZScore(ISNLSAFactor, mask=Mask)
    ISNSA_WithL = QS.FactorDB.PointOperation(f"adaboost_with_loss_{Suffix}", [ISNSAFactor, ISNLSAFactor], {"算子": mergeModel, "参数": {"权重": [0.67, 0.33]}, "运算时点": "多时点", "运算ID": "多ID"})
    Factors.append(ISNSA_WithL)
    
    UpdateArgs = {
        "因子表": "stock_cn_multi_factor_ml_m",
        "默认起始日": dt.datetime(2005, 1, 1),
        "最长回溯期": 365 * 10,
        "IDs": "股票",
        "更新频率": "月"
    }
    
    return (Factors, UpdateArgs)

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    Args = {"LDB": TDB, "factor_info_file": "../conf/stock/stock_cn_multi_factor_classic.csv", "sample_len": 12, "suffix": "1y"}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2016, 1, 1), dt.datetime(2021, 7, 12)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365*7), end_date=EndDT.date(), output_type="datetime")
    DTs = QS.Tools.DateTime.getMonthLastDateTime(DTs)
    DTRuler = QS.Tools.DateTime.getMonthLastDateTime(DTRuler)
    
    IDs = JYDB.getStockID(is_current=False)
    
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