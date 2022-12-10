# coding=utf-8
"""实体工具"""
import time

import numpy as np
import pandas as pd

import QuantStudio.api as QS
from QuantStudio.Tools.DataTypeConversionFun import expandListElementDataFrame
from QSExt.FactorDataBase.Neo4jDB import Neo4jDB

def readEntityData(target_dt, args={}):
    # 读取数据
    IDs, FactorInfo = args.get("ids", None), args["factor_info"]
    Data = None
    for iIdx in FactorInfo["来源序号"].unique():
        iFactorInfo = FactorInfo[FactorInfo["来源序号"]==iIdx]
        iArgStr = iFactorInfo["参数"].iloc[0]
        if pd.isnull(iArgStr): iArgs = {}
        elif isinstance(iArgStr, str): iArgs = eval(iArgStr)
        else: raise Exception(f"无法识别的参数: {iArgStr}")
        iSourceDB = args[iFactorInfo["来源库"].iloc[0]].connect()
        iSourceTable = iFactorInfo["来源表"].iloc[0]
        iFT = iSourceDB.getTable(iSourceTable, args=iArgs)
        iMethod = iFactorInfo.iloc[0].get("读取方法", "readData")
        if iMethod=="readData":
            iData = iFT.readData(factor_names=iFactorInfo["来源因子"].tolist(), ids=IDs, dts=[target_dt]).iloc[0]
        elif iMethod=="readSQLData":
            iData = iFT.readSQLData(factor_names=iFactorInfo["来源因子"].tolist(), ids=IDs, start_dt=target_dt, end_dt=target_dt)
            iData = iData.loc[:, ["ID"] + iFactorInfo["来源因子"].tolist()].set_index(["ID"])
        else:
            raise Exception(f"不支持的数据读取方法: {iMethod}")
        iData = iData.rename(columns={v: k for k, v in iFactorInfo["来源因子"].items()})
        if iData is None:
            Data = iData
        else:
            Data = pd.merge(Data, iData, how="outer", left_index=True, right_index=True)
    return Data, args

def writeEntityData(target_dt, data, args={}):
    TDB = args["TDB"].connect()
    
    FactorInfo = args["factor_info"]
    # 调整数据类型
    for iFactorName in data.columns:
        iDataType = FactorInfo.loc[iFactorName, "数据类型"]
        if iDataType=="double":
            data[iFactorName] = data[iFactorName].astype(float)
        elif iDataType=="datetime":
            if pd.notnull(data[iFactorName]).any():
                Tmp = data[iFactorName].where(pd.notnull(data[iFactorName]), pd.NaT).dt.stftime("%Y-%m-%d")
                data[iFactorName] = Tmp.where(Tmp!="NaT", None)
        elif iDataType=="string":
            if FactorInfo.loc[iFactorName, "清除非法字符"]:
                data[iFactorName] = data[iFactorName].where(pd.notnull(data[iFactorName]), None)
                for iStr in args.get("illegal_str", ["\n", "\r"]):
                    data[iFactorName] = data[iFactorName].str.replace(iStr, "")
    data["EndDate"] = target_dt.strftime("%Y-%m-%d")
    TDB.Logger.inf(f"实体数量: {data.shape[0]}")
    
    # 写入数据
    IDField = args.get("id_field", "ID")
    ParentLabels = args.get("parent_labels", [])
    if args["add_label"] and ParentLabels:# 如果有已经写入的父标签实体, 先在父标签实体之上增加本实体标签
        TDB.writeEntityLabel(args["labels"], data.index.tolist(), ParentLabels, IDField)
    StartT = time.perf_counter()
    TDB.writeEntityData(data, args["labels"], entity_id=IDField, if_exists=args.get("if_exists", "update"))
    TDB.Logger.info(f"写入 TDB 时间: {time.perf_counter() - StartT}")
    TDB.createEntityIndex(args["labels"][0], [IDField])# 创建索引
    return 0

def genEntityArgs(target_dt, config, csv_import_path, csv_export_path, if_exists="update", periodic_size=10000):
    ExcelFile = pd.ExcelFile(config[0])
    Args = {
        "JYDB": QS.FactorDB.JYDB(),
        "HDF5DB": QS.FactorDB.HDF5DB(),
        #"StockFactorDB": QS.FactorDB.SQLDB(),
        #"StockDB": QS.FactorDB.SQLDB(),
        "factor_info": pd.read_excel(ExcelFile, sheet_name=config[1], header=0, index_col=0, skiprows=3, nrows=None),
        "labels": pd.read_excel(ExcelFile, sheet_name=config[1], header=None, index_col=0, skiprows=0, nrows=1).iloc[0].dropna().tolist(),
        "parent_labels": pd.read_excel(ExcelFile, sheet_name=config[1], header=None, index_col=0, skiprows=1, nrows=1).iloc[0].dropna().tolist(),
        "add_label": False,
        "id_field": "ID",
        "if_exists": if_exists,
        "TDB": Neo4jDB(sys_args={"定期数量": periodic_size})
    }
    return Args

def readRelationData(target_dt, args={}):
    IDs, RelationInfo = args.get("ids", None), args["relation_info"]
    Data = None
    for jIdx in RelationInfo["关系序号"].unique():
        jRelationInfo = RelationInfo[RelationInfo["关系序号"]==jIdx]
        jData = None
        for iIdx in jRelationInfo["来源序号"].unique():
            iRelationInfo = jRelationInfo[jRelationInfo["来源序号"]==iIdx]
            iArgStr = iRelationInfo["参数"].iloc[0]
            if pd.isnull(iArgStr): iArgs = {}
            elif isinstance(iArgStr, str): iArgs = eval(iArgStr)
            else: raise Exception(f"无法识别的参数: {iArgStr}")
            iSourceDB = args[iRelationInfo["来源库"].iloc[0]].connect()
            iSourceTable = iRelationInfo["来源表"].iloc[0]
            iFT = iSourceDB.getTable(iSourceTable, args=iArgs)
            if IDs is None:
                iIDs = iFT.getID()
            else:
                iIDs = IDs
            iMethod = iRelationInfo.iloc[0]
            if iMethod=="readData":
                iData = iFT.readData(factor_names=iRelationInfo["来源因子"].tolist(), ids=iIDs, dts=[target_dt]).iloc[:, 0]
                iData = iData.rename(columns=iRelationInfo.loc[:, ["属性", "来源因子"]].set_index(["来源因子"]).iloc[:, 0].to_dict())
                iData.index = iData.index.set_names(("源ID" if "目标ID" in iData.columns else "目标ID",))
                if iRelationInfo["多重映射"].iloc[0]:
                    iData = expandListElementDataFrame(iData, expand_index=True)
                else:
                    iData = iData.reset_index()
            elif iMethod=="readSQLData":
                iData = iFT.readSQLData(factor_names=iRelationInfo["来源因子"].tolist(), ids=iIDs, start_dt=target_dt, end_dt=target_dt)
                iData = iData.loc[:, ["ID"] + iRelationInfo["来源因子"].tolist()]
                iData = iData.rename(columns=iRelationInfo.loc[:, ["属性", "来源因子"]].set_index(["来源因子"]).iloc[:, 0].to_dict())
                iData[("源ID" if "目标ID" in Data.columns else "目标ID")] = iData.pop("ID")
            iData = iData[pd.notnull(iData["源ID"]) & pd.notnull(iData["目标ID"])]
            iData["源ID"] = iData["源ID"].astype(str)
            iData["目标ID"] = iData["目标ID"].astype(str)
            iData = iData.set_index(["源ID", "目标ID"])
            if jData is None:
                jData = iData
            else:
                jData = pd.merge(jData, iData, how="outer", left_index=True, right_index=True)
        if Data is None:
            Data = jData
        else:
            Data = Data.append(jData, ignore_index=False)
    return Data, args

def writeRelationData(target_dt, data, args={}):
    RelationInfo = args["relation_info"]
    # 调整数据类型
    for iFactorName in data.columns:
        iMask = (RelationInfo["属性"]==iFactorName)
        iDataType = RelationInfo["数据类型"][iMask].iloc[0]
        if iDataType=="double":
            data[iFactorName] = data[iFactorName].astype(float)
        elif iDataType=="datetime":
            if pd.notnull(data[iFactorName]).any():
                Tmp = data[iFactorName].where(pd.notnull(data[iFactorName]), pd.NaT).dt.stftime("%Y-%m-%d")
                data[iFactorName] = Tmp.where(Tmp!="NaT", None)
        elif iDataType=="string":
            if RelationInfo["清除非法字符"][iMask].iloc[0]:
                data[iFactorName] = data[iFactorName].where(pd.notnull(data[iFactorName]), None)
                for iStr in args.get("illegal_str", ["\n", "\r"]):
                    data[iFactorName] = data[iFactorName].str.replace(iStr, "")
    data["EndDate"] = target_dt.strftime("%Y-%m-%d")
    TDB = args["TDB"].connect()
    TDB.Logger.inf(f"关系数量: {data.shape[0]}")    
    # 写入数据
    StartT = time.perf_counter()
    TDB.writeRelationData(
        data, 
        args["relation_label"], 
        args["source_labels"], 
        args["target_labels"], 
        if_exists=args.get("if_exists", "replace"),
        source_id=RelationInfo["源ID属性"].iloc[0],
        target_id=RelationInfo["目标ID属性"].iloc[0],
        create_entity=args.get("create_entity", False)
    )
    TDB.Logger.info(f"写入 TDB 时间: {time.perf_counter() - StartT}")

def genRelationArgs(target_dt, config, relation_label, source_labels, target_labels, csv_import_path, csv_export_path, if_exists="replace_all", periodic_size=-1, create_entity=False):
    ExcelFile = pd.ExcelFile(config[0])
    Args = {
        "JYDB": QS.FactorDB.JYDB(),
        "HDF5DB": QS.FactorDB.HDF5DB(),
        #"StockFactorDB": QS.FactorDB.SQLDB(),
        #"StockDB": QS.FactorDB.SQLDB(),
        #"FundDB": QS.FactorDB.SQLDB(),
        "relation_label": relation_label,
        "source_labels": source_labels,
        "target_labels": target_labels,
        "create_entity": create_entity,
        "if_exists": if_exists,
        "TDB": Neo4jDB(sys_args={"定期数量": periodic_size})
    }
    ExcelFile = pd.ExcelFile(config[0])
    RelationInfo = pd.read_excel(ExcelFile, sheet_name=config[1], header=0, index_col=None, skiprows=0)
    Args["relation_info"] = RelationInfo[(RelationInfo["源标签"]==",".join(Args["source_labels"])) & (RelationInfo["目标标签"]==",".join(Args["target_labels"])) & (RelationInfo["关系标签"]==Args["relation_label"])]
    return Args