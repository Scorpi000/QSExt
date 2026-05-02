# -*- coding: utf-8 -*-
"""公募基金分类因子"""
import os
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

def r2_type_fun(f, idt, iid, x, args):
    Info = args["info"].loc[:, "RawTypeCode"]
    RawCode = x[0]
    R2Type = np.full(shape=RawCode.shape, fill_value=None, dtype="O")
    for iType in Info.index:
        iInfo = Info.loc[[iType]]
        iMask = (RawCode==iInfo.iloc[0])
        for j in range(1, iInfo.shape[0]):
            iMask = (iMask | (RawCode==iInfo.iloc[j]))
        R2Type[iMask] = iType
    return R2Type

def wm_type_fun(f, idt, iid, x, args):
    GoldMFList = args["mf_gold_list"]
    WMType = pd.DataFrame(x[0], index=idt, columns=iid)
    WMType.loc[:, WMType.columns.intersection(GoldMFList)] = "黄金型"
    return WMType.values

# args 应该包含的参数
# JYDB: 聚源因子库对象
# r2_fund_type_config: R2财富基金分类配置文件
# mf_gold_list: 黄金基金分类配置文件
def defFactor(args={}, debug=False):
    Factors = []

    JYDB = args["JYDB"]
    
    # 证监会分类
    FT = JYDB.getTable("公募基金概况附表")
    CSRCType = FT.getFactor("数据", args={"类别代码":"10"}, new_name="csrc_type")
    Factors.append(CSRCType)
    
    # 风险等级
    RiskLevel = FT.getFactor("数据", args={"类别代码":"74"}, new_name="risk_level")
    Factors.append(RiskLevel)
    
    # 晨星分类
    Factors.append(FT.getFactor("数据", args={"类别代码":"11"}, new_name="morning_star_type"))
    
    # 聚源分类
    FT = JYDB.getTable("公募基金聚源分类")
    Factors.append(FT.getFactor("一级分类名称", new_name="jy_type_first"))
    Factors.append(FT.getFactor("二级分类名称", new_name="jy_type_second"))
    Factors.append(FT.getFactor("三级分类名称", new_name="jy_type_third"))
    
    # R2财富分类
    R2TypeInfo = pd.read_csv(args["r2_fund_type_config"], index_col=None, header=0, encoding="utf-8", engine="python")
    JYTypeCode = FT.getFactor("二级分类代码")
    R2Type = QS.FactorDB.PointOperation("r2_type_first", [JYTypeCode], sys_args={"算子": r2_type_fun, "参数": {"info": R2TypeInfo.set_index(["R2Type1"])}, "运算时点": "多时点", "运算ID": "多ID", "数据类型": "string"})
    Factors.append(R2Type)
    R2Type = QS.FactorDB.PointOperation("r2_type_second", [JYTypeCode], sys_args={"算子": r2_type_fun, "参数": {"info": R2TypeInfo.set_index(["R2Type2"])}, "运算时点": "多时点", "运算ID": "多ID", "数据类型": "string"})
    Factors.append(R2Type)
    
    # 财富管理分类
    WMTypeInfo = pd.read_csv(args["mf_gold_list"], index_col=0, header=0, encoding="utf-8", engine="python")
    WMType = QS.FactorDB.PointOperation("wm_type", [CSRCType], {"算子": wm_type_fun, "参数": {"mf_gold_list": WMTypeInfo.index.tolist()}, "运算时点": "多时点", "运算ID": "多ID", "数据类型": "string"})
    Factors.append(WMType)
    
    # 其他分类
    FT = JYDB.getTable("公募基金概况")
    Factors.append(FT.getFactor("份额属性_R", new_name="share_type"))# 对分级基金: 稳健性, 进取型
    
    UpdateArgs = {"因子表": "mf_cn_type",
                  "默认起始日": dt.datetime(2002,1,1),
                  "最长回溯期": 3650,
                  "IDs": "公募基金"}
    
    return (Factors, UpdateArgs)


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Args = {"JYDB": JYDB, "r2_fund_type_config": "/home/hushuntai/Scripts/因子定义/conf/mf/r2_fund_type_config.csv", "mf_gold_list": "/home/hushuntai/Scripts/因子定义/conf/mf/mf_gold_list.csv"}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2020, 6, 1), dt.datetime(2020, 9, 25)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    #DTs = DTs[-1:]# 只保留最新数据
    
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