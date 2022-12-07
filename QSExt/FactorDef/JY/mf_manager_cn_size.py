# -*- coding: utf-8 -*-
"""基金经理规模因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

def _count(f, idt, iid, x, args):
    FundCode = x[0]
    Mask = pd.Series(x[1], index=f.Args.DescriptorSection[1])
    MainCode = pd.Series(x[2], index=f.Args.DescriptorSection[2])
    Rslt = np.full_like(FundCode, fill_value=np.nan)
    for i, iIDs in enumerate(FundCode):
        if isinstance(iIDs, list) and (len(iIDs)>0):
            Rslt[i] = MainCode.loc[iIDs][Mask.loc[iIDs]].unique().shape[0]
    return Rslt

def _sum(f, idt, iid, x, args):
    FundCode = x[0]
    Mask = pd.Series(x[1], index=f.Args.DescriptorSection[1])
    MFVal = pd.Series(x[2], index=f.Args.DescriptorSection[2])
    Rslt = np.full_like(FundCode, fill_value=np.nan)
    for i, iIDs in enumerate(FundCode):
        if isinstance(iIDs, list) and (len(iIDs)>0):
            Rslt[i] = MFVal.loc[iIDs][Mask.loc[iIDs]].sum(min_count=1)
    return Rslt

def _weighted_sum(f, idt, iid, x, args):
    FundCode = x[0]
    Mask = pd.Series(x[1], index=f.Args.DescriptorSection[1])
    MFVal = pd.Series(x[2], index=f.Args.DescriptorSection[2])
    MFWeight = pd.Series(x[2], index=f.Args.DescriptorSection[2])
    Rslt = np.full_like(FundCode, fill_value=np.nan)
    for i, iIDs in enumerate(FundCode):
        if isinstance(iIDs, list) and (len(iIDs)>0):
            iVal = MFVal.loc[iIDs]
            iWeight = MFWeight.loc[iIDs]
            iMask = (pd.notnull(iVal) & pd.notnull(iWeight) & Mask.loc[iIDs])
            iVal, iWeight = iVal[iMask], iWeight[iMask]
            Rslt[i] = (iVal * (iWeight / iWeight.sum())).sum(min_count=1)
    return Rslt


def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"].connect()
    LDB = args["LDB"]
    
    IDs = JYDB.getTable("公募基金经理(新)(基金经理ID)", args={"多重映射": True}).getID()
    MFIDs = JYDB.getMutualFundID(is_current=False)
    
    FT = JYDB.getTable("公募基金经理(新)(基金经理ID)", args={"多重映射": True})
    FundCode = FT.getFactor("基金内部编码_R", args={"只填起始日": False})
    
    FT = LDB.getTable("mf_cn_status")
    Mask = (FT.getFactor("if_exist")==1)
    
    FT = LDB.getTable("mf_cn_type")
    MFType = FT.getFactor(args["MFType"])
    
    FT = LDB.getTable("mf_cn_info")
    MainCode = FT.getFactor("main_code")
    MainCode = fd.where(MainCode, fd.notnull(MainCode), QS.FactorDB.DataFactor("Code", pd.Series(MFIDs, index=MFIDs), data_type="string"))
    
    SizeFT = LDB.getTable("mf_cn_factor_size")
    
    for iType in ["All"]+args["MFAllTypes"]:
        if iType=="All":
            iMask = Mask
        else:
            iMask = (Mask & (MFType==iType))
    
    # ####################### 管理产品数量 #######################
    ProductNum = QS.FactorDB.SectionOperation(
        f"product_num_{iType}",
        [FundCode, iMask, MainCode],
        sys_args={
            "算子": _count,
            "描述子截面": [None, MFIDs, MFIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors.append(ProductNum)
       
    # ####################### 管理资产净值 #######################
    MFNAV = SizeFT.getFactor("net_asset_value")
    NAV = QS.FactorDB.SectionOperation(
        f"net_asset_value_{iType}",
        [FundCode, iMask, MFNAV],
        sys_args={
            "算子": _sum,
            "描述子截面": [None, MFIDs, MFIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors.append(NAV)
    
    # ####################### 管理资产总值 #######################
    MFTAV = SizeFT.getFactor("total_asset_value")
    TAV = QS.FactorDB.SectionOperation(
        f"total_asset_value_{iType}",
        [FundCode, iMask, MFTAV],
        sys_args={
            "算子": _sum,
            "描述子截面": [None, MFIDs, MFIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors.append(TAV)
    
    # ####################### 机构(个人)投资者比例 #######################
    MFInstitutionRatio = SizeFT.getFactor("institution_ratio")
    InstitutionRatio = QS.FactorDB.SectionOperation(
        f"institution_ratio_{iType}",
        [FundCode, iMask, MFInstitutionRatio, MFNAV],
        sys_args={
            "算子": _weighted_sum,
            "描述子截面": [None, MFIDs, MFIDs, MFIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors.append(InstitutionRatio)
    
    MFIndividualRatio = SizeFT.getFactor("individual_ratio")
    IndividualRatio = QS.FactorDB.SectionOperation(
        f"institution_ratio_{iType}",
        [FundCode, iMask, MFIndividualRatio, MFNAV],
        sys_args={
            "算子": _weighted_sum,
            "描述子截面": [None, MFIDs, MFIDs, MFIDs],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "double"
        }
    )
    Factors.append(IndividualRatio)
    
    UpdateArgs = {
        "因子表": "mf_manager_cn_factor_size",
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": IDs
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
    
    SQLStr = "SELECT FundTypeName FROM mf_fundtype WHERE Standard=75 AND StandardLevel=2 ORDER BY DisclosureCode"
    MFAllTypes = [iType[0] for iType in JYDB.fetchall(sql_str=SQLStr) if iType[0].find("其他")==-1]
    
    Args = {"JYDB": JYDB, "LDB": TDB, "MFType": "jy_type_second", "MFAllTypes": MFAllTypes, "weight": "ew", "rebalance": "m"}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
    IDs = UpdateArgs["IDs"]
    
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