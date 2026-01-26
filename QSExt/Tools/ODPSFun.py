# -*- coding: utf-8 -*-
import re

import pandas as pd
import sqlglot


def findRightParenthesis(txt, left_idx):
    LeftCount, StartIdx = 1, left_idx + 1
    for iMatch in re.finditer("\(|\)", txt[StartIdx:]):
        iMark = txt[StartIdx:][iMatch.span()[0]: iMatch.span()[1]]
        if iMark == "(":
            LeftCount += 1
        else:
            LeftCount -= 1
        if LeftCount == 0:
            return StartIdx + iMatch.span()[0]
    return None


# 将一般的 SQL 查询转成 ODPS 格式
def modifySQL2ODPS(sql_str: str, odps_info, pattern, target_partition={}, union=True):
    if union:
        Unions = re.findall("[\t \n]union[\t \n]", sql_str, flags=re.IGNORECASE)
        if Unions:
            SQLStrs = re.split("[\t \n]union[\t \n]", sql_str, flags=re.IGNORECASE)
            CompletedSQLStrs, NonCompletedSQLStrs = [], []
            for i, iSQLStr in enumerate(SQLStrs):
                if iSQLStr.count("(")==iSQLStr.count(")"):
                    if NonCompletedSQLStrs:
                        CompletedSQLStrs.append(modifySQL2ODPS(" UNION ".join(NonCompletedSQLStrs), odps_info, pattern, target_partition=target_partition, union=False))
                        NonCompletedSQLStrs = []
                    CompletedSQLStrs.append(modifySQL2ODPS(iSQLStr, odps_info, pattern, target_partition=target_partition))
                else:
                    NonCompletedSQLStrs.append(iSQLStr)
            if NonCompletedSQLStrs:
                CompletedSQLStrs.append(modifySQL2ODPS(" UNION ".join(NonCompletedSQLStrs), odps_info, pattern, target_partition=target_partition, union=False))
            return " UNION ".join(CompletedSQLStrs)
    NoSubSQL, SubSQLs, SubPlaceholders = sql_str, [], []
    iMatch = re.search("SELECT", NoSubSQL, re.IGNORECASE)
    StartIdx = iMatch.span()[1]
    NoSubSQL, StartStr = NoSubSQL[StartIdx:], NoSubSQL[:StartIdx]
    iMatch = re.search("SELECT", NoSubSQL, re.IGNORECASE)
    i = 0
    while iMatch:
        iStartIdx = iMatch.span()[0]
        iStartIdx = len(NoSubSQL[:iStartIdx]) - 1 - NoSubSQL[:iStartIdx][::-1].find("(")
        iEndIdx = findRightParenthesis(NoSubSQL, iStartIdx)
        iSubSQL = NoSubSQL[iStartIdx+1:iEndIdx]
        SubPlaceholders.append(f"$t{i}$")
        NoSubSQL = NoSubSQL[:iStartIdx] + SubPlaceholders[-1] + NoSubSQL[iEndIdx+1:]
        SubSQLs.append("(" + modifySQL2ODPS(iSubSQL, odps_info, pattern, target_partition) + ")")
        i += 1
        iMatch = re.search("SELECT", NoSubSQL, re.IGNORECASE)
    NoSubSQL = StartStr + NoSubSQL
    TableNames = sorted(set(pattern.findall(NoSubSQL)))
    ODPSTableNames = []
    for iTableName in TableNames:
        if iTableName.lower() in odps_info.index:
            iODPSTableName = odps_info.loc[iTableName.lower(), "ODPSTableName"]
            if isinstance(iODPSTableName, pd.Series): iODPSTableName = iODPSTableName.iloc[0]
            NoSubSQL = NoSubSQL.replace(iTableName, iODPSTableName)
            ODPSTableNames.append(iODPSTableName)
        else:
            ODPSTableNames.append(None)
    NoSubSQLExp = sqlglot.parse_one(NoSubSQL)
    UniODPSTableNames = set()
    for i, iTableName in enumerate(TableNames):
        if ODPSTableNames[i] and (ODPSTableNames[i] not in UniODPSTableNames):
            iPTField, iTargetPT = odps_info.loc[TableNames[i].lower(), "分区字段"], odps_info.loc[TableNames[i].lower(), "分区"]
            if isinstance(iPTField, pd.Series): iPTField, iTargetPT = iPTField.iloc[0], iTargetPT.iloc[0]
            iTargetPTs = {iPTField: iTargetPT}
            iTargetPTs.update(target_partition.get(TableNames[i], {}))
            for ijPTField, ijPTValue in iTargetPTs.items():
                if (not ijPTValue) or (ijPTValue=="MAX_PT"):
                    NoSubSQLExp = NoSubSQLExp.where(f"{ODPSTableNames[i]}.{ijPTField} = MAX_PT('{ODPSTableNames[i]}')")
                else:
                    NoSubSQLExp = NoSubSQLExp.where(f"{ODPSTableNames[i]}.{ijPTField} = {ijPTValue}")
            UniODPSTableNames.add(ODPSTableNames[i])
    SQLStr = NoSubSQLExp.sql()
    for i, iSubSQL in enumerate(SubSQLs):
        SQLStr = SQLStr.replace(SubPlaceholders[i], iSubSQL)
    # 特殊处理
    SQLStr = re.sub(r"AS\s+TEXT|AS\s+CHAR", "AS STRING", SQLStr, flags=re.IGNORECASE)
    SQLStr = re.sub(r"(?<!TO_)DATE\s*\(", "TO_DATE(", SQLStr, flags=re.IGNORECASE)
    return SQLStr

if __name__ == "__main__":
    SQLStr = """
        SELECT 
            *
        FROM SecuMain
        WHERE SecuCode = "000001"
        AND SecuMarket IN (83, 90, 18)
        AND SecuCategory IN (1, 41)
    """
    ODPSInfo = pd.DataFrame([("证券主表", "SecuMain", "antefi.ods_secumain_gildatav2", "MAX_PT", "dt")], columns=["TableName", "DBTableName", "ODPSTableName", "分区", "分区字段"])
    ODPSInfo["DBTableName"] = ODPSInfo["DBTableName"].str.lower()
    ODPSInfo = ODPSInfo.set_index(["DBTableName"])
    Pattern = re.compile("|".join(sorted(ODPSInfo.index, reverse=True)), flags=re.IGNORECASE)
    ODPSSQL = modifySQL2ODPS(SQLStr, ODPSInfo, Pattern)
    print(ODPSSQL)
