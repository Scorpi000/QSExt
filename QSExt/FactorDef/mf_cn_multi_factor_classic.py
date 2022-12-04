# coding=utf-8
"""公募基金简单多因子模型"""
import os
import datetime as dt
from collections import OrderedDict

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

def calc_IC(f, idt, iid, x, args):
    if idt[-1] not in args["ic_dts"]: return np.full(shape=(len(iid),), fill_value=np.nan)
    PreIdx = idt.index(args["ic_dts"][args["ic_dts"].index(idt[-1]) - 1])
    Ret = x[1][-1] / x[1][PreIdx] - 1
    Mask = (x[0][PreIdx]==1)
    Data = x[2][PreIdx]
    return np.full(shape=(len(iid),), fill_value=pd.Series(Data[Mask]).corr(pd.Series(Ret[Mask]), method="spearman"))
    
def calc_IC_avg(f, idt, iid, x, args):
    IC = x[0][pd.notnull(x[0][:, 0]), :]
    if IC.shape[0]<args["look_back"]:
        return np.full(shape=(len(iid),), fill_value=np.nan)
    return np.nanmean(IC[-args["look_back"]:, :], axis=0)

def calc_IC_IR(f, idt, iid, x, args):
    IC = x[0][pd.notnull(x[0][:, 0]), :]
    if IC.shape[0]<args["look_back"]:
        return np.full(shape=(len(iid),), fill_value=np.nan)
    IC = IC[-args["look_back"]:, :]
    return np.nanmean(IC, axis=0) / np.nanstd(IC, ddof=1, axis=0)

def defFactor(args={}):
    Factors = []

    LDB = args["LDB"]

    # 基金是否存续
    Exist = LDB.getTable("mf_cn_status").getFactor("if_exist")
    Mask = (Exist==1)
    
    # 基金分类
    FT = LDB.getTable("mf_cn_type")
    FundType = FT.getFactor("jy_type_second")
    
    # 基金净值
    FT = JYDB.getTable("公募基金复权净值")
    NetValueAdj = FT.getFactor("复权单位净值", args={"回溯天数": np.inf})
    NetValueAdj = fd.where(NetValueAdj, Mask, np.nan)

    FactorInfo = QS.Tools.File.readCSV2Pandas(args["factor_info_file"], encoding="utf8").set_index(["因子表", "因子名称"])
    TableNames = FactorInfo.index.get_level_values(0).drop_duplicates()
    Descriptors = OrderedDict()
    for iTable in TableNames:
        iFT = LDB.getTable(iTable)
        for jFactor in FactorInfo.loc[iTable].index:
            Descriptors[jFactor] = iFT.getFactor(jFactor)

    # 分位数变换标准化
    for iTable in TableNames:
        for jFactor in FactorInfo.loc[iTable].index:
            Descriptors[jFactor] = fd.standardizeQuantile(Descriptors[jFactor], mask=Mask, cat_data=None, ascending=(FactorInfo.loc[iTable].loc[jFactor,"排序方向"]=="降序"))

    # 合并因子形成大类风格因子
    StyleFactors = OrderedDict()
    for iStyle in pd.unique(FactorInfo["大类指标"]):
        iDescriptors = [Descriptors[iFactor] for iFactor in FactorInfo[FactorInfo["大类风格"]==iStyle].index.get_level_values(1)]
        StyleFactors[iStyle] = fd.nanmean(*iDescriptors, weights=None, ignore_nan_weight=False)

    # 大类风格因子的标准化
    for iStyle in StyleFactors:
        StyleFactors[iStyle] = Factorize(fd.standardizeQuantile(StyleFactors[iStyle], mask=Mask, cat_data=FundType, ascending=True), factor_name=iStyle.lower())
    Factors += list(StyleFactors.values())
    
    # ---------------------------------等权合并大类风格因子形成综合得分----------------------------------------------------
    Score_EW = Factorize(fd.nanmean(*list(StyleFactors.values()), weights=None, ignore_nan_weight=False), "score_ew")
    Factors += [Score_EW]

    # 计算因子的月度IC
    StyleICs = OrderedDict()
    for iStyle in StyleFactors:
        StyleICs[iStyle] = QS.FactorDB.PanelOperation(
            "IC_"+iStyle, 
            [Exist, NetValueAdj, StyleFactors[iStyle]], 
            sys_args={
                "算子": calc_IC, 
                "参数": {"ic_dts": args["ic_dts"]},
                "回溯期数":[31, 31, 31],
                "运算时点": "单时点",
                "输出形式": "全截面",
                "数据类型": "double"
            }
        )
    
    # 计算IC的年度均值
    StyleICAvgs = OrderedDict()
    for iStyle in StyleFactors:
        StyleICAvgs[iStyle] = QS.FactorDB.TimeOperation(
            "ICAvg_"+iStyle, 
            [StyleICs[iStyle]], 
            sys_args={
                "算子": calc_IC_avg, 
                "参数": {"look_back": 12},
                "回溯期数":[366], 
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
    
    # ---------------------------------IC 加权合并大类风格因子形成综合得分------------------------------------------------
    Score_IC = Factorize(fd.nansum(*[StyleFactors[iStyle]*StyleICAvgs[iStyle]*(StyleICAvgs[iStyle]>0) for iStyle in StyleFactors]) / fd.nansum(*[StyleICAvgs[iStyle]*(StyleICAvgs[iStyle]>0) for iStyle in StyleFactors]), factor_name="score_ic")
    Factors += [Score_IC]

    # 计算IC_IR
    StyleIRs = OrderedDict()
    for iStyle in StyleFactors:
        StyleIRs[iStyle] = QS.FactorDB.TimeOperation(
            "IR_"+iStyle, 
            [StyleICs[iStyle]], 
            sys_args={
                "算子": calc_IC_IR, 
                "参数": {"look_back": 12},
                "回溯期数": [366], 
                "运算时点": "单时点",
                "运算ID": "多ID",
                "数据类型": "double"
            }
        )
    
    # -----------------------------------IC_IR 加权合并大类风格因子形成综合得分-------------------------------------------
    Score_IR = Factorize(fd.nansum(*[StyleFactors[iStyle]*StyleIRs[iStyle]*(StyleIRs[iStyle]>0) for iStyle in StyleFactors]) / fd.nansum(*[StyleIRs[iStyle]*(StyleIRs[iStyle]>0) for iStyle in StyleFactors]), factor_name="score_ir")
    Factors += [Score_IR]
    
    UpdateArgs = {
        "因子表": "mf_cn_multi_factor_classic",
        "默认起始日": dt.datetime(2002, 1, 1),
        "最长回溯期": 365,
        "IDs": "股票"
    }
    
    return Factors, UpdateArgs

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
    IDs = JYDB.getMutualFundID(is_current=False)
    
    Args = {
        "JYDB": JYDB, 
        "LDB": TDB,
        "factor_info_file": "../conf/mf_cn_multi_factor_classic.csv",
        "ic_dts": QS.Tools.DateTime.getMonthLastDateTime(DTRuler),
        "ic_look_back": 12
    }
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
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
