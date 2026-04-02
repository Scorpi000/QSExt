# coding=utf8
"""基于机器学习的多因子模型"""
import datetime as dt
from collections import OrderedDict

import numpy as np
import pandas as pd
from scipy import stats
from sklearn import svm
import xgboost as xgb
import lightgbm as lgb

from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.Factor.FactorOperator import RankStandardization, ZScoreStandardization
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


@FactorOperatorized(operator_type="Section", args={"Arity": 3, "DTMode": "单时点"})
def partitionSample(f, idt, iid, x, args):
    """按照两个分类数据对样本进行分组"""
    IsListed, CatData, SubCatData = x[0], x[1], x[2]
    Mask = (pd.notnull(CatData) & pd.notnull(SubCatData) & (IsListed==1))
    AllCat = np.unique(CatData[Mask])
    Rslt = np.zeros(IsListed.shape)
    for j, jCat in enumerate(AllCat):
        jMask = ((CatData==jCat) & Mask)
        jSubCatMask = (SubCatData > np.nanmedian(SubCatData[jMask]))
        Rslt[(jMask & jSubCatMask)] = 2 * j + 1
        Rslt[(jMask & (~jSubCatMask))] = 2 * j + 2
    return Rslt

@FactorOperatorized(operator_type="Panel", args={"Arity": 2, "LookBack": [1, 0], "ModelArgs": {"TopBottomRatio": 0.3}, "DTMode": "单时点"})
def genYLabel(f, idt, iid, x, args):
    """生成类别型因变量, +1, -1, 0 表示非样本"""
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

def AdaBoost(factor_data, ret_mask, level, quantile_num=5):
    """AdaBoost 模型"""
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
            if kFactorData.shape[0] - np.sum(kMask) < quantile_num: continue
            kWeight = Weight.copy()
            kWeight[kMask] = 0
            kWeight = kWeight / np.nansum(kWeight)
            kZ = 0.0
            kh = np.zeros(quantile_num)
            for jQuantile in range(quantile_num):
                RightThreshold = np.nanpercentile(kFactorData, (jQuantile+1) / quantile_num * 100)
                if jQuantile!=0:
                    LeftThreshold = np.nanpercentile(kFactorData, jQuantile / quantile_num * 100)
                    kjMask = ((kFactorData > LeftThreshold) & (kFactorData <= RightThreshold))
                else:
                    kjMask = (kFactorData <= RightThreshold)
                # kjQuantileData = kFactorData[kjMask]
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

@FactorOperatorized(operator_type="Panel", args={"Arity": None, "ModelArgs": {"Level": 20, "QuantileNum": 5}, "DTMode": "单时点"})
def trainAdaBoostModel(f, idt, iid, x, args):
    """训练 AdaBoost 模型"""
    IsListed = x[0][0, :]
    YLabel = x[1]
    Mask = (YLabel!=0)
    YLabel = YLabel[Mask]
    if YLabel.shape[0]==0:
        return np.full(shape=IsListed.shape, fill_value=np.nan)
    FactorData = np.array([ix[:-1, :][Mask] for ix in x[2:]]).T
    h, SelectedIndex = AdaBoost(FactorData, YLabel, level=args["Level"], quantile_num=args["QuantileNum"])
    if h is None:
        return np.full(shape=IsListed.shape, fill_value=np.nan)
    NewFactorData = np.array([ix[-1, :] for ix in x[2:]]).T
    Mask = (IsListed==1)
    NewFactorData = NewFactorData[Mask, :]
    SAData = np.full(shape=(NewFactorData.shape[0],), fill_value=np.nan)
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

@FactorOperatorized(operator_type="Panel", args={"Arity": None, "ModelArgs": {"Level": 20, "QuantileNum": 5}, "DTMode": "单时点"})
def trainLossModel(f, idt, iid, x, args):
    """训练失效信息模型"""
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
    ICMask = (IC <= np.nanmean(IC))
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

@FactorOperatorized(operator_type="Point", args={"Arity": 2, "ModelArgs": {"Weight": [0.67, 0.33]}, "DTMode": "多时点", "IDMode": "多ID"})
def mergeModel(f, idt, iid, x, args):
    Rslt = np.zeros(x[0].shape)
    TotalWeight = np.zeros(x[0].shape)
    for i, ix in enumerate(x):
        iWeight = args["Weight"][i]
        iMask = np.isnan(ix)
        ix = np.where(iMask, 0.0, ix)
        Rslt += iWeight * ix
        TotalWeight += iWeight * (~ iMask)
    TotalWeight[TotalWeight==0] = np.nan
    return Rslt / TotalWeight

@FactorOperatorized(operator_type="Panel", args={"Arity": None, "ModelArgs": {"ModelParams": {"C": 1.0}}, "DTMode": "单时点"})
def trainSVMModel(f, idt, iid, x, args):
    """训练 SVM 模型"""
    IsListed = x[0][0, :]
    YLabel = x[1]
    Mask = (YLabel!=0)
    YLabel = YLabel[Mask]
    if YLabel.shape[0]==0:
        return np.full(shape=IsListed.shape, fill_value=np.nan)
    FactorData = np.array([ix[:-1, :][Mask] for ix in x[2:]]).T
    Mask = np.all(pd.notnull(FactorData), axis=1)
    FactorData, YLabel = FactorData[Mask, :], YLabel[Mask]
    clf = svm.SVC(**args["ModelParams"])
    clf.fit(FactorData, YLabel)
    NewFactorData = np.array([ix[-1, :] for ix in x[2:]]).T
    Mask = (IsListed==1) & np.all(pd.notnull(NewFactorData), axis=1)
    NewFactorData = NewFactorData[Mask, :]
    SAData = clf.decision_function(NewFactorData)
    Rslt = np.full(shape=IsListed.shape, fill_value=np.nan)
    Rslt[Mask] = SAData
    return Rslt


XGBParams = {
    'objective': 'binary:logistic',  # 二分类问题
    'eval_metric': ['auc', 'logloss'],
    'max_depth': 5,                   # 树深度, 防止过拟合
    'eta': 0.05,                      # 学习率
    'subsample': 0.8,                 # 样本采样比例
    'colsample_bytree': 0.8,          # 特征采样比例
    'min_child_weight': 50,           # 叶子节点最小样本数 (防止过拟合)
    'gamma': 0.1,                     # 节点分裂最小损失减少
    'reg_alpha': 0.1,                 # L1正则化
    'reg_lambda': 1.0,                # L2正则化
    'scale_pos_weight': 1,            # 正负样本权重平衡
    'seed': 42,
    'tree_method': 'hist',            # 快速直方图算法
}

@FactorOperatorized(operator_type="Panel", args={"Arity": None, "ModelArgs": {"ModelParams": XGBParams}, "DTMode": "单时点"})
def trainXGBModel(f, idt, iid, x, args):
    """训练 XGBoost 模型"""
    IsListed = x[0][0, :]
    YLabel = x[1]
    Mask = (YLabel!=0)
    YLabel = YLabel[Mask]
    if YLabel.shape[0]==0:
        return np.full(shape=IsListed.shape, fill_value=np.nan)
    FactorData = np.array([ix[:-1, :][Mask] for ix in x[2:]]).T
    FactorData = np.where(pd.notnull(FactorData), FactorData, np.nanmedian(FactorData, axis=0))# 缺失值填充
    YLabel = np.where(YLabel==-1, 0, YLabel)
    Mask = np.all(pd.notnull(FactorData), axis=1)
    FactorData, YLabel = FactorData[Mask, :], YLabel[Mask]
    DTrain = xgb.DMatrix(FactorData, label=YLabel)
    Params = args.get("ModelParams", {})
    bst = xgb.train(
        Params,
        DTrain,
        num_boost_round=1000,
        evals=[(DTrain, 'train')],
        early_stopping_rounds=50,
        # verbose_eval=100
        verbose_eval=False
    )
    NewFactorData = np.array([ix[-1, :] for ix in x[2:]]).T
    Mask = (IsListed == 1)
    # Mask = (IsListed==1) & np.all(pd.notnull(NewFactorData), axis=1)
    NewFactorData = NewFactorData[Mask, :]
    NewFactorData = np.where(pd.notnull(NewFactorData), NewFactorData, np.nanmedian(NewFactorData, axis=0))# 缺失值填充
    # SAData = bst.predict_proba(NewFactorData)
    SAData = bst.predict(xgb.DMatrix(NewFactorData))
    Rslt = np.full(shape=IsListed.shape, fill_value=np.nan)
    Rslt[Mask] = SAData
    return Rslt

@FactorOperatorized(operator_type="Panel", args={"Arity": None, "ModelArgs": {"ModelParams": XGBParams}, "DTMode": "单时点"})
def trainXGBLossModel(f, idt, iid, x, args):
    """训练失效信息模型"""
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
    ICMask = (IC <= np.nanmean(IC))
    IsListed = x[0][0, :]
    if np.sum(ICMask)<Return.shape[0] * 0.2:
        return np.full(shape=IsListed.shape, fill_value=np.nan)
    YLabel = x[3][ICMask, :]
    Mask = (YLabel != 0)
    YLabel = YLabel[Mask]
    FactorData = np.array([ix[:-1, :][ICMask, :][Mask] for ix in x[4:]]).T

    YLabel = np.where(YLabel==-1, 0, YLabel)
    Mask = np.all(pd.notnull(FactorData), axis=1)
    FactorData, YLabel = FactorData[Mask, :], YLabel[Mask]
    DTrain = xgb.DMatrix(FactorData, label=YLabel)
    Params = args.get("ModelParams", {})
    bst = xgb.train(
        Params,
        DTrain,
        num_boost_round=1000,
        evals=[(DTrain, 'train')],
        early_stopping_rounds=50,
        # verbose_eval=100
        verbose_eval=False
    )
    NewFactorData = np.array([ix[-1, :] for ix in x[4:]]).T
    Mask = (IsListed==1)
    NewFactorData = NewFactorData[Mask, :]
    NewFactorData = np.where(pd.notnull(NewFactorData), NewFactorData, np.nanmedian(NewFactorData, axis=0))# 缺失值填充
    SAData = bst.predict(xgb.DMatrix(NewFactorData))
    Rslt = np.full(shape=IsListed.shape, fill_value=np.nan)
    Rslt[Mask] = SAData
    return Rslt


LGBParams = {
    'objective': "multiclass",
    'num_class': 2,
    'metric': 'multi_logloss',
    'boosting_type': 'gbdt',
    'num_leaves': 31,
    'max_depth': 6,
    'learning_rate': 0.05,
    'feature_fraction': 0.8,      # 列采样
    'bagging_fraction': 0.8,       # 行采样
    'bagging_freq': 5,
    'min_child_samples': 20,
    'reg_alpha': 0.1,              # L1正则
    'reg_lambda': 0.1,             # L2正则
    'verbose': -1,
    'random_state': 42
}

@FactorOperatorized(operator_type="Panel", args={"Arity": None, "ModelArgs": {"ModelParams": LGBParams}, "DTMode": "单时点"})
def trainLGBModel(f, idt, iid, x, args):
    """训练 LightGBM 模型"""
    IsListed = x[0][0, :]
    YLabel = x[1]
    Mask = (YLabel!=0)
    YLabel = YLabel[Mask]
    if YLabel.shape[0]==0:
        return np.full(shape=IsListed.shape, fill_value=np.nan)
    FactorData = np.array([ix[:-1, :][Mask] for ix in x[2:]]).T
    FactorData = np.where(pd.notnull(FactorData), FactorData, np.nanmedian(FactorData, axis=0))# 缺失值填充
    YLabel = np.where(YLabel==-1, 0, YLabel)
    Mask = np.all(pd.notnull(FactorData), axis=1)
    FactorData, YLabel = FactorData[Mask, :], YLabel[Mask]
    DTrain = lgb.Dataset(FactorData, label=YLabel)
    Params = args.get("ModelParams", {})
    Model = lgb.train(
        Params,
        DTrain,
        num_boost_round=500
    )
    NewFactorData = np.array([ix[-1, :] for ix in x[2:]]).T
    Mask = (IsListed == 1)
    # Mask = (IsListed==1) & np.all(pd.notnull(NewFactorData), axis=1)
    NewFactorData = NewFactorData[Mask, :]
    NewFactorData = np.where(pd.notnull(NewFactorData), NewFactorData, np.nanmedian(NewFactorData, axis=0))# 缺失值填充
    SAData = Model.predict(lgb.Dataset(NewFactorData))
    Rslt = np.full(shape=IsListed.shape, fill_value=np.nan)
    Rslt[Mask] = SAData
    return Rslt


def defFactor(fdi: FactorDefInput):
    Factors = []
    
    SampleLen = fdi.ModelArgs.get("sample_len", 12)
    Suffix = fdi.ModelArgs.get("suffix", "1y")
    FactorInfo = fdi.ModelArgs["factor_info"]
    LDB = fdi.FDB["LDB"]
    
    FT = LDB.getTable("stock_cn_industry")
    Industry = FT.getFactor("citic2019_level1")
    FT = LDB.getTable("stock_cn_status")
    IsListed = FT.getFactor("if_listed")
    
    FT = LDB.getTable("stock_cn_day_bar_nafilled")
    FloatCap = FT.getFactor("float_cap")

    FT = LDB.getTable("stock_cn_day_bar_adj_backward_nafilled")
    Price = FT.getFactor("close")
    Return = Price / fo.Lag(lag_period=1, window=1)(Price) - 1
    
    # 导入模型所用的因子
    TableNames = sorted(FactorInfo["因子表"].unique())
    TrainFactors = OrderedDict()
    for iTable in TableNames:
        iFT = LDB.getTable(iTable)
        for jFactor in FactorInfo[FactorInfo["因子表"]==iTable].index:
            TrainFactors[jFactor] = iFT.getFactor(jFactor)
    nTrainFactor = len(TrainFactors)
    
    # 数据预处理形成训练样本
    PartitionFactor = partitionSample(IsListed, Industry, FloatCap, factor_args={"Name": "分组因子"})
    standardizeRank = RankStandardization(ascending=True, offset=0)
    for iFactor in TrainFactors:
        TrainFactors[iFactor] = standardizeRank(TrainFactors[iFactor], mask=IsListed, cat_data=PartitionFactor)
    YLabel = genYLabel(PartitionFactor, Return, factor_args={"Name": "YLabel"})
    
    # AdaBoost 模型
    ISNSAFactor = trainAdaBoostModel.new(args={"Arity": 2 + nTrainFactor, "LookBack": [1-1, SampleLen-1] + [SampleLen+1-1]*nTrainFactor})(*([IsListed, YLabel]+list(TrainFactors.values())), factor_args={"Name": f"adaboost_{Suffix}"})
    Factors.append(ISNSAFactor)
    
    # 失效信息模型
    ISNLSAFactor = trainLossModel.new(args={"Arity": 4 + nTrainFactor, "LookBack": [0, 5*SampleLen, 5*SampleLen-1, 5*SampleLen-1] + [5*SampleLen]*nTrainFactor})(*([IsListed, ISNSAFactor, Return, YLabel]+list(TrainFactors.values())), factor_args={"Name": f"adaboost_loss_{Suffix}"})
    Factors.append(ISNLSAFactor)
    
    # AdaBoost 合并模型
    Mask = (IsListed==1)
    standardizeZScore = ZScoreStandardization()
    ISNSAFactor = standardizeZScore(ISNSAFactor, mask=Mask)
    ISNLSAFactor = standardizeZScore(ISNLSAFactor, mask=Mask)
    ISNSA_WithL = mergeModel(ISNSAFactor, ISNLSAFactor, factor_args={"Name": f"adaboost_with_loss_{Suffix}"})
    Factors.append(ISNSA_WithL)

    # SVM 模型
    ISNSVMFactor = trainSVMModel.new(args={"Arity": 2 + nTrainFactor, "LookBack": [1-1, SampleLen-1] + [SampleLen+1-1]*nTrainFactor})(*([IsListed, YLabel]+list(TrainFactors.values())), factor_args={"Name": f"svm_{Suffix}"})
    Factors.append(ISNSVMFactor)

    # XGBoost 模型
    ISNXGBFactor = trainXGBModel.new(args={"Arity": 2 + nTrainFactor, "LookBack": [1-1, SampleLen-1] + [SampleLen+1-1]*nTrainFactor})(*([IsListed, YLabel]+list(TrainFactors.values())), factor_args={"Name": f"xgboost_{Suffix}"})
    Factors.append(ISNXGBFactor)

    # XGBoost 失效信息模型
    ISNLXGBFactor = trainXGBLossModel.new(args={"Arity": 4 + nTrainFactor, "LookBack": [0, 5*SampleLen, 5*SampleLen-1, 5*SampleLen-1] + [5*SampleLen]*nTrainFactor})(*([IsListed, ISNXGBFactor, Return, YLabel]+list(TrainFactors.values())), factor_args={"Name": f"xgboost_loss_{Suffix}"})
    Factors.append(ISNLXGBFactor)

    # XGBoost 合并模型
    ISNXGB_WithL = mergeModel(standardizeZScore(ISNXGBFactor, mask=Mask), standardizeZScore(ISNLXGBFactor, mask=Mask), factor_args={"Name": f"xgboost_with_loss_{Suffix}"})
    Factors.append(ISNXGB_WithL)

    # LightGBM 模型
    ISNLGBFactor = trainLGBModel.new(args={"Arity": 2 + nTrainFactor, "LookBack": [1-1, SampleLen-1] + [SampleLen+1-1]*nTrainFactor})(*([IsListed, YLabel]+list(TrainFactors.values())), factor_args={"Name": f"lgboost_{Suffix}"})
    Factors.append(ISNLGBFactor)

    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        # FactorList=[ISNLXGBFactor, ISNXGB_WithL],
        TargetTable="stock_cn_multi_factor_ml",
        IDType="A股",
        MaxLookBack=365 * 10,
        Freq="1m",
        Author="麦冬",
        Description="基于机器学习的股票多因子模型",
        DefScriptPath=__file__
    )
