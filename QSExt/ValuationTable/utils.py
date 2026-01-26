# -*- coding: utf-8 -*-
import re
import json
import datetime as dt
from typing import Mapping

import numpy as np
import pandas as pd
import statsmodels.api as sm

from QuantStudio.Tools.QSObjects import Panel

# 解析日期
def find_date(string):
    """从字符串中识别日期

    :param string: str，字符串
    :return: datetime or None, 日期
    """
    res = re.search(r"\d{4}-\d{1,2}-\d{1,2}", string)
    if res is not None:
        y, m, d = res.group(0).split("-")
        return dt.datetime(int(y), int(m), int(d))
    res = re.search(r"\d{4}/\d{1,2}/\d{1,2}", string)
    if res is not None:
        y, m, d = res.group(0).split("/")
        return dt.datetime(int(y), int(m), int(d))
    res = re.search(r"\d{4}[0,1]{1}\d{1}\d{2}", string)
    if res is not None:
        y, m, d = res.group(0)[:4], res.group(0)[4:6], res.group(0)[6:]
        return dt.datetime(int(y), int(m), int(d))
    res = re.search(r"\d{4}年\d{1,2}月\d{1,2}日", string)
    if res is not None:
        res = res.group(0)
        res = res.replace("年", "-")
        res = res.replace("月", "-")
        res = res.replace("日", "-")
        y, m, d = res.split("-")
        return dt.datetime(int(y), int(m), int(d))
    return None

# 寻找备案编号
def find_reg_code(input_string):
    matches = re.findall(r"[0-9A-Za-z]{6,100}", input_string)
    pattern = re.compile(r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{6}$')
    return [imatch.upper() for imatch in matches if re.match(pattern, imatch) is not None]

# 估值表写入因子库
def writeValuationTable2FDB(detail, detail_table, summary, summary_table, fdb, if_exists="update"):
    if "检查写入值" in fdb.Args.ArgNames:
        OldVal = fdb.Args["检查写入值"]
        fdb.Args["检查写入值"] = True
    if (detail is not None) and (not detail.empty):
        detail = detail.set_index(["the_datetime", "symbol"])
        detail = Panel({iFactor: detail[iFactor].groupby(axis=0, level=[0, 1]).apply(lambda s: s.tolist()).unstack() for iFactor in detail.columns})
        fdb.writeData(detail, detail_table, if_exists=if_exists, data_type={})
    if (summary is not None) and (not summary.empty):
        summary = summary.set_index(["the_datetime", "symbol"])
        summary = Panel({iFactor: summary[iFactor].groupby(axis=0, level=[0, 1]).apply(lambda s: s.tolist()).unstack() for iFactor in summary.columns})
        fdb.writeData(summary, summary_table, if_exists=if_exists, data_type={"value": "double"})
    if "检查写入值" in fdb.Args.ArgNames:
        fdb.Args["检查写入值"] = OldVal
    return 0

# 提取 PDF 文件中的表格
def extractPDFTable(path):
    import pdfplumber
    table_settings = {
        "vertical_strategy": "text",
        "horizontal_strategy": "lines"
    }
    pdf = pdfplumber.open(path)
    table_list = []
    for page in pdf.pages:
        tables_count = page.extract_tables(table_settings=table_settings)
        for table in tables_count:
            now_table = pd.DataFrame(table)
            table_list.append(now_table)
    return pd.concat(table_list)

# 判断是否是 5 级估值表
def checkLevel5VT(df):
    AccountCode = df[0].loc[df.index[df[0].str.contains("科目").fillna(False)][-1]:df.index[df[0].str.slice(0, 4).str.fullmatch("\d{4}").fillna(False)][-1]]
    AccountCodeLen = AccountCode.str.len()
    MaxLenAccountCode = AccountCode[AccountCodeLen==AccountCodeLen.max()].iloc[0]
    ParentAccountCode = AccountCode[AccountCode.apply(lambda s: MaxLenAccountCode.startswith(s)) & (AccountCode!=MaxLenAccountCode)]
    ParentAccountCodeLen = ParentAccountCode.str.len()
    ParentAccountCode = ParentAccountCode[ParentAccountCodeLen==ParentAccountCodeLen.max()].iloc[0]
    return (len(ParentAccountCode) >= 10)

# 计算加权平均
# df: DataFrame(columns=[weight_col,...])
# weight_col: 作为权重的列
def calcWeightedAvg(df, weight_col, ignore_na=True):
    df = df.copy()
    Weight = df.pop(weight_col)
    if ignore_na:
        Mask = (df.T.notnull() & Weight.notnull())
        Weight = Mask * Weight
    return (df.T * Weight).sum(axis=1) / Weight.sum(axis=int(ignore_na))

def shiftDataFrame(df, target_col, periods=1, dropna=True, ascending=True, ruler=None):
    if not ruler:
        Vals = sorted(set(df[target_col].dropna().tolist()), reverse=(not ascending))
    else:
        Vals = sorted(ruler, reverse=(not ascending))
    if periods>=0:
        Mapping = {Vals[i]: Vals[i+periods] for i in range(len(Vals)-periods)}
    else:
        Mapping = {Vals[i]: Vals[i+periods] for i in range(abs(periods), len(Vals))}
    df[target_col] = df[target_col].replace(Mapping).where(df[target_col].isin(Mapping), None)
    if dropna:
        return df[df[target_col].notnull()]
    else:
        df[df[target_col].isnull()] = None
        return df

# 合并证券持仓
def mergeComponent(df, idt, iid, logger, first_cols=[], sum_cols=[]):
    Rslt = pd.Series(index=df.columns, dtype="O")
    Rslt["account_code"] = ",".join(df["account_code"])
    Rslt["account_name"] = df["account_name"].str.strip().iloc[0]
    Rslt["exchange"] = df["exchange"].iloc[0]
    Rslt["security_code"] = df["security_code"].iloc[0]
    Rslt["shares"] = df["shares"].sum()
    Rslt["cost"] = df["cost"].sum()
    Rslt["unit_code"] = (Rslt["cost"] / Rslt["shares"] if Rslt["shares"]!=0 else np.nan)
    Rslt["price"] = df["price"].mean()
    Rslt["market_value"] = df["market_value"].sum()
    Rslt["value"] = df["value"].sum()
    Rslt["chg"] = df["chg"].sum()
    Rslt["weight_in_nv"] = df["weight_in_nv"].sum()
    if df["account_name"].str.strip().unique().shape[0]>1:
        logger.error({"msg": f"时点={idt}, symbol={iid}, 交易所为 '{Rslt['exchange']}', 证券代码为 '{Rslt['security_code']}' 的股票成本科目名称并不唯一: {df['account_name'].unique().tolist()}", "alarm": True, "name": "account_name_diff", "source": "QSExt.ValuationTable.utils.mergeComponent"})
    for iCol in first_cols: Rslt[iCol] = df[iCol].iloc[0]
    for iCol in sum_cols: Rslt[iCol] = df[iCol].sum()
    return Rslt

# 合并应收红利
def _mergeDividendReceivable(df, idt, iid, logger, first_cols=[], sum_cols=[]):
    Rslt = pd.Series(index=df.columns, dtype="O")
    Rslt["account_code"] = ",".join(df["account_code"])
    Rslt["account_name"] = df["account_name"].iloc[0]
    Rslt["exchange"] = df["exchange"].iloc[0]
    Rslt["security_code"] = df["security_code"].iloc[0]
    Rslt["dividend_receivable"] = df["dividend_receivable"].sum()
    if df["account_name"].str.strip().unique().shape[0]>1:
        logger.error({"msg": f"时点={idt}, symbol={iid}, 交易所为 '{Rslt['exchange']}', 证券代码为 '{Rslt['security_code']}' 的应收股利科目名称并不唯一: {df['account_name'].unique().tolist()}", "alarm": True, "name": "account_name_diff", "source": "QSExt.ValuationTable.utils._mergeDividendReceivable"})
    for iCol in first_cols: Rslt[iCol] = df[iCol].iloc[0]
    for iCol in sum_cols: Rslt[iCol] = df[iCol].sum()
    return Rslt

# 合并应计利息
def _mergeAccruedInterest(df, idt, iid, logger, first_cols=[], sum_cols=[]):
    Rslt = pd.Series(index=df.columns, dtype="O")
    Rslt["account_code"] = ",".join(df["account_code"])
    Rslt["account_name"] = df["account_name"].iloc[0]
    Rslt["exchange"] = df["exchange"].iloc[0]
    Rslt["security_code"] = df["security_code"].iloc[0]
    Rslt["accrued_interest"] = df["accrued_interest"].sum()
    if df["account_name"].str.strip().unique().shape[0]>1:
        logger.error({"msg": f"时点={idt}, symbol={iid}, 交易所为 '{Rslt['exchange']}', 证券代码为 '{Rslt['security_code']}' 的应计利息科目名称并不唯一: {df['account_name'].unique().tolist()}", "alarm": True, "name": "account_name_diff", "source": "QSExt.ValuationTable.utils._mergeAccruedInterest"})
    for iCol in first_cols: Rslt[iCol] = df[iCol].iloc[0]
    for iCol in sum_cols: Rslt[iCol] = df[iCol].sum()
    return Rslt

# 合并减值准备
def _mergeDepreciationReserve(df, idt, iid, logger, first_cols=[], sum_cols=[]):
    Rslt = pd.Series(index=df.columns, dtype="O")
    Rslt["account_code"] = ",".join(df["account_code"])
    Rslt["account_name"] = df["account_name"].iloc[0]
    Rslt["exchange"] = df["exchange"].iloc[0]
    Rslt["security_code"] = df["security_code"].iloc[0]
    Rslt["depreciation_reserve"] = df["depreciation_reserve"].sum()
    if df["account_name"].str.strip().unique().shape[0]>1:
        logger.error({"msg": f"时点={idt}, symbol={iid}, 交易所为 '{Rslt['exchange']}', 证券代码为 '{Rslt['security_code']}' 的减值准备科目名称并不唯一: {df['account_name'].unique().tolist()}", "alarm": True, "name": "account_name_diff", "source": "QSExt.ValuationTable.utils._mergeDepreciationReserve"})
    for iCol in first_cols: Rslt[iCol] = df[iCol].iloc[0]
    for iCol in sum_cols: Rslt[iCol] = df[iCol].sum()
    return Rslt

# 合并应收利息
def _mergeInterestReceivable(df, idt, iid, logger, first_cols=[], sum_cols=[]):
    Rslt = pd.Series(index=df.columns, dtype="O")
    Rslt["account_code"] = ",".join(df["account_code"])
    Rslt["account_name"] = df["account_name"].iloc[0]
    Rslt["exchange"] = df["exchange"].iloc[0]
    Rslt["security_code"] = df["security_code"].iloc[0]
    Rslt["interest_receivable"] = df["interest_receivable"].sum()
    if df["account_name"].str.strip().unique().shape[0]>1:
        logger.error({"msg": f"时点={idt}, symbol={iid}, 交易所为 '{Rslt['exchange']}', 证券代码为 '{Rslt['security_code']}' 的应收利息科目名称并不唯一: {df['account_name'].unique().tolist()}", "alarm": True, "name": "account_name_diff", "source": "QSExt.ValuationTable.utils._mergeInterestReceivable"})
    for iCol in first_cols: Rslt[iCol] = df[iCol].iloc[0]
    for iCol in sum_cols: Rslt[iCol] = df[iCol].sum()
    return Rslt

# 合并应付利息
def _mergeInterestPayable(df, idt, iid, logger, first_cols=[], sum_cols=[]):
    Rslt = pd.Series(index=df.columns, dtype="O")
    Rslt["account_code"] = ",".join(df["account_code"])
    Rslt["account_name"] = df["account_name"].iloc[0]
    Rslt["exchange"] = df["exchange"].iloc[0]
    Rslt["security_code"] = df["security_code"].iloc[0]
    Rslt["interest_payable"] = df["interest_payable"].sum()
    if df["account_name"].str.strip().unique().shape[0]>1:
        logger.error({"msg": f"时点={idt}, symbol={iid}, 交易所为 '{Rslt['exchange']}', 证券代码为 '{Rslt['security_code']}' 的应付利息科目名称并不唯一: {df['account_name'].unique().tolist()}", "alarm": True, "name": "account_name_diff", "source": "QSExt.ValuationTable.utils._mergeInterestPayable"})
    for iCol in first_cols: Rslt[iCol] = df[iCol].iloc[0]
    for iCol in sum_cols: Rslt[iCol] = df[iCol].sum()
    return Rslt

# 检查科目问题
def _checkAccountCode(idt, iid, df, Component, ComponentMapping, logger):
    SecurityCodes = Component["security_code"].unique().tolist()
    Level1Codes = list(ComponentMapping.index.get_level_values(0).str.slice(0, 4).unique())
    NotKnownAccountCodes = set(df["parent_code"][df["security_code"].isin(SecurityCodes) & df["account_code"].str.slice(0, 4).isin(Level1Codes)].unique()).difference(ComponentMapping.index.get_level_values(0))
    if NotKnownAccountCodes:
        logger.error({"msg": f"时点={idt}, symbol={iid}: 无法识别的科目代码 {NotKnownAccountCodes}", "alarm": True, "name": "account_name_diff", "source": "QSExt.ValuationTable.utils._checkAccountCode"})

# 抽取股票持仓
# idt: 估值时点, datetime
# iid: symbol, str
# df: 估值表数据, DataFrame(columns=["account_code", "account_name", "parent_code", "account_name_std", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info"])
# args: 参数集，{"ComponentMapping": {规则名称: DataFrame}, "RuleConfig": DataFrame(index=[symbol], columns=["规则"])
#   其中，ComponentMapping: 科目映射，RuleConfig: 科目配置
# 返回：DataFrame(columns=["account_code", "account_name", "exchange", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info", "dividend_receivable"])
def calcStockComponent(idt, iid, df, args, logger):
    FactorNames = ["account_code", "account_name", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info"]
    iTmp = df[df["account_name_std"].notnull() & (df["account_name_std"]!="nan")].loc[:, ["account_code", "account_name_std"]].rename(columns={"account_code": "parent_code", "account_name_std": "parent_name_std"})
    df = pd.merge(df, iTmp, how="left", left_on=["parent_code"], right_on=["parent_code"])
    df = df[df["security_code"].notnull()]
    if df.empty: return pd.DataFrame(columns=["exchange", *FactorNames, "dividend_receivable"])
    RuleName = args["RuleConfig"]["规则"].get(iid, None)
    if not RuleName: RuleName = json.loads(df["ext_info"].iloc[0])["account_system"]
    ComponentMapping = args["ComponentMapping"][RuleName]
    # 解析持仓明细
    iComponentMapping = ComponentMapping[ComponentMapping["科目类别"]=="成本"]
    iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    Component = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"交易所": "exchange"})
    Component = Component.loc[:, ["exchange"] + FactorNames]
    if not Component.empty:
        Component["exchange"] = Component["exchange"].fillna("")
        Component = Component.groupby(["exchange", "security_code"], as_index=False).apply(mergeComponent, idt, iid, logger)
    # 解析应收股利
    iComponentMapping = ComponentMapping[ComponentMapping["科目类别"] == "应收股利"]
    iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "dividend_receivable", "交易所": "exchange"}).loc[:, ["security_code", "exchange", "dividend_receivable", "account_code", "account_name"]]
    if not iComponent.empty:
        iComponent["exchange"] = iComponent["exchange"].fillna("")
        iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeDividendReceivable, idt, iid, logger).reset_index(drop=True)
        Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
        Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
        Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
    if Component.empty: return pd.DataFrame(columns=["exchange", *FactorNames, "dividend_receivable"])
    # 调整证券代码
    SecurityCodes = Component["security_code"].str.extract(r"(\d+)").iloc[:, 0]
    Component["security_code"] = SecurityCodes.where(Component["exchange"].isin(("SSE", "SZSE", "BSE", "HKEX")),  Component["security_code"])
    # 检查问题
    _checkAccountCode(idt, iid, df, Component, ComponentMapping, logger)
    # 调整数据列
    Component["ext_info"] = json.dumps({"account_system": RuleName})
    Component = Component.reindex(columns=["exchange", *FactorNames, "dividend_receivable"])
    Component["exchange"] = Component["exchange"].where((Component["exchange"].notnull() & (Component["exchange"]!="")), None)
    return Component

# 抽取债券持仓
# idt: 估值时点, datetime
# iid: symbol, str
# df: 估值表数据, DataFrame(columns=["account_code", "account_name", "parent_code", "account_name_std", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info"])
# args: 参数集，{"ComponentMapping": {规则名称: DataFrame}, "RuleConfig": DataFrame(index=[symbol], columns=["规则"])
#   其中，ComponentMapping: 科目映射，RuleConfig: 科目配置
# 返回：DataFrame(columns=["account_code", "account_name", "exchange", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info", "accrued_interest", "interest_receivable", "depreciation_reserve"])
def calcBondComponent(idt, iid, df, args, logger):
    FactorNames = ["account_code", "account_name", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info"]
    iTmp = df[df["account_name_std"].notnull() & (df["account_name_std"]!="nan")].loc[:, ["account_code", "account_name_std"]].rename(columns={"account_code": "parent_code", "account_name_std": "parent_name_std"})
    df = pd.merge(df, iTmp, how="left", left_on=["parent_code"], right_on=["parent_code"])
    df = df[df["security_code"].notnull()]
    if df.empty: return pd.DataFrame(columns=["exchange", "security_type", *FactorNames, "accrued_interest", "interest_receivable", "depreciation_reserve"])
    RuleName = args["RuleConfig"]["规则"].get(iid, None)
    if not RuleName: RuleName = json.loads(df["ext_info"].iloc[0])["account_system"]
    ComponentMapping = args["ComponentMapping"][RuleName]
    # 解析持仓明细
    if RuleName=="招商":
        iComponentMapping = ComponentMapping[(ComponentMapping["level"]==3) & (ComponentMapping["科目类别"]=="成本")]
    else:
        iComponentMapping = ComponentMapping[ComponentMapping["科目类别"]=="成本"]
        iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    Component = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"交易所": "exchange", "标的类别": "security_type"})
    Component = Component.loc[:, ["exchange", "security_type"] + FactorNames]
    if not Component.empty:
        Component["exchange"] = Component["exchange"].fillna("")
        Component = Component.groupby(["exchange", "security_code"], as_index=False).apply(mergeComponent, idt, iid, logger)
    # 解析应计利息
    if RuleName=="招商":
        iComponentMapping = ComponentMapping[(ComponentMapping["level"]==3) & (ComponentMapping["科目类别"]=="应计利息")]
    else:
        iComponentMapping = ComponentMapping[ComponentMapping["科目类别"]=="应计利息"]
        iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "accrued_interest", "交易所": "exchange", "标的类别": "security_type"}).loc[:, ["security_code", "exchange", "accrued_interest", "account_code", "security_type", "account_name"]]
    if not iComponent.empty:
        iComponent["exchange"] = iComponent["exchange"].fillna("")
        iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeAccruedInterest, idt, iid, logger, first_cols=["security_type"]).reset_index(drop=True)
        Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
        Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
        Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
        Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
    # 解析减值准备
    if RuleName == "招商":
        iComponentMapping = ComponentMapping[(ComponentMapping["level"] == 3) & ComponentMapping["科目类别"].str.contains("减值准备").fillna(False)]
    else:
        iComponentMapping = ComponentMapping[ComponentMapping["科目类别"].str.contains("减值准备").fillna(False)]
        iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "depreciation_reserve", "交易所": "exchange", "标的类别": "security_type"}).loc[:, ["security_code", "exchange", "depreciation_reserve", "account_code", "security_type", "account_name"]]
    if not iComponent.empty:
        iComponent["exchange"] = iComponent["exchange"].fillna("")
        iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeDepreciationReserve, idt, iid, logger, first_cols=["security_type"]).reset_index(drop=True)
        Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
        Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
        Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
        Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
    # 解析应收利息
    if RuleName == "招商":
        iComponentMapping = ComponentMapping[(ComponentMapping["level"] == 3) & (ComponentMapping["科目类别"] == "应收利息")]
    else:
        iComponentMapping = ComponentMapping[ComponentMapping["科目类别"] == "应收利息"]
        iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "interest_receivable", "交易所": "exchange", "标的类别": "security_type"}).loc[:, ["security_code", "exchange", "interest_receivable", "account_code", "security_type", "account_name"]]
    if not iComponent.empty:
        iComponent["exchange"] = iComponent["exchange"].fillna("")
        iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeInterestReceivable, idt, iid, logger, first_cols=["security_type"]).reset_index(drop=True)
        Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
        Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
        Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
        Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
    if Component.empty: return pd.DataFrame(columns=["exchange", "security_type", *FactorNames, "accrued_interest", "interest_receivable", "depreciation_reserve"])
    # 检查问题
    _checkAccountCode(idt, iid, df, Component, ComponentMapping, logger)
    # 调整数据列
    Component["ext_info"] = json.dumps({"account_system": RuleName})
    Component = Component.reindex(columns=["exchange", "security_type", *FactorNames, "accrued_interest", "interest_receivable", "depreciation_reserve"])
    Component["exchange"] = Component["exchange"].where((Component["exchange"].notnull() & (Component["exchange"]!="")), None)
    return Component

# 抽取资产支持证券持仓
# idt: 估值时点, datetime
# iid: symbol, str
# df: 估值表数据, DataFrame(columns=["account_code", "account_name", "parent_code", "account_name_std", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info"])
# args: 参数集，{"ComponentMapping": {规则名称: DataFrame}, "RuleConfig": DataFrame(index=[symbol], columns=["规则"])
#   其中，ComponentMapping: 科目映射，RuleConfig: 科目配置
# 返回：DataFrame(columns=["account_code", "account_name", "exchange", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info", "accrued_interest", "interest_receivable", "depreciation_reserve"])
def calcABSComponent(idt, iid, df, args, logger):
    FactorNames = ["account_code", "account_name", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info"]
    iTmp = df[df["account_name_std"].notnull() & (df["account_name_std"]!="nan")].loc[:, ["account_code", "account_name_std"]].rename(columns={"account_code": "parent_code", "account_name_std": "parent_name_std"})
    df = pd.merge(df, iTmp, how="left", left_on=["parent_code"], right_on=["parent_code"])
    df = df[df["security_code"].notnull()]
    if df.empty: return pd.DataFrame(columns=["exchange", "security_type", *FactorNames, "accrued_interest", "interest_receivable", "depreciation_reserve"])
    RuleName = args["RuleConfig"]["规则"].get(iid, None)
    if not RuleName: RuleName = json.loads(df["ext_info"].iloc[0])["account_system"]
    ComponentMapping = args["ComponentMapping"][RuleName]
    # 解析持仓明细
    iComponentMapping = ComponentMapping[ComponentMapping["科目类别"]=="成本"]
    iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    Component = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"交易所": "exchange", "标的类别": "security_type"})
    Component = Component.loc[:, ["exchange", "security_type"] + FactorNames]
    if not Component.empty:
        Component["exchange"] = Component["exchange"].fillna("")
        Component = Component.groupby(["exchange", "security_code"], as_index=False).apply(mergeComponent, idt, iid, logger)
    # 解析应计利息
    iComponentMapping = ComponentMapping[ComponentMapping["科目类别"]=="应计利息"]
    iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "accrued_interest", "交易所": "exchange", "标的类别": "security_type"}).loc[:, ["security_code", "exchange", "accrued_interest", "account_code", "security_type", "account_name"]]
    if not iComponent.empty:
        iComponent["exchange"] = iComponent["exchange"].fillna("")
        iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeAccruedInterest, idt, iid, logger, first_cols=["security_type"]).reset_index(drop=True)
        Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
        Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
        Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
        Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
    # 解析减值准备
    iComponentMapping = ComponentMapping[ComponentMapping["科目类别"].str.contains("减值准备").fillna(False)]
    iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "depreciation_reserve", "交易所": "exchange", "标的类别": "security_type"}).loc[:, ["security_code", "exchange", "depreciation_reserve", "account_code", "security_type", "account_name"]]
    if not iComponent.empty:
        iComponent["exchange"] = iComponent["exchange"].fillna("")
        iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeDepreciationReserve, idt, iid, logger, first_cols=["security_type"]).reset_index(drop=True)
        Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
        Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
        Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
        Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
    # 解析应收利息
    iComponentMapping = ComponentMapping[ComponentMapping["科目类别"] == "应收利息"]
    iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "interest_receivable", "交易所": "exchange", "标的类别": "security_type"}).loc[:, ["security_code", "exchange", "interest_receivable", "account_code", "security_type", "account_name"]]
    if not iComponent.empty:
        iComponent["exchange"] = iComponent["exchange"].fillna("")
        iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeInterestReceivable, idt, iid, logger, first_cols=["security_type"]).reset_index(drop=True)
        Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
        Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
        Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
        Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
    if Component.empty: return pd.DataFrame(columns=["exchange", "security_type", *FactorNames, "accrued_interest", "interest_receivable", "depreciation_reserve"])
    # 检查问题
    _checkAccountCode(idt, iid, df, Component, ComponentMapping, logger)
    # 调整数据列
    Component["ext_info"] = json.dumps({"account_system": RuleName})
    Component = Component.reindex(columns=["exchange", "security_type", *FactorNames, "accrued_interest", "interest_receivable", "depreciation_reserve"])
    Component["exchange"] = Component["exchange"].where((Component["exchange"].notnull() & (Component["exchange"]!="")), None)
    return Component

# 抽取逆回购持仓
# idt: 估值时点, datetime
# iid: symbol, str
# df: 估值表数据, DataFrame(columns=["account_code", "account_name", "parent_code", "account_name_std", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info"])
# args: 参数集，{"ComponentMapping": {规则名称: DataFrame}, "RuleConfig": DataFrame(index=[symbol], columns=["规则"])
#   其中，ComponentMapping: 科目映射，RuleConfig: 科目配置
# 返回：DataFrame(columns=["account_code", "account_name", "exchange", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info", "accrued_interest", "interest_receivable", "depreciation_reserve"])
def calcReverseRepoComponent(idt, iid, df, args, logger):
    FactorNames = ["account_code", "account_name", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info"]
    iTmp = df[df["account_name_std"].notnull() & (df["account_name_std"]!="nan")].loc[:, ["account_code", "account_name_std"]].rename(columns={"account_code": "parent_code", "account_name_std": "parent_name_std"})
    df = pd.merge(df, iTmp, how="left", left_on=["parent_code"], right_on=["parent_code"])
    if df["security_code"].isnull().all(): return pd.DataFrame(columns=["exchange", "security_type", "underlying_asset", *FactorNames, "accrued_interest", "interest_receivable", "depreciation_reserve"])
    RuleName = args["RuleConfig"]["规则"].get(iid, None)
    if not RuleName: RuleName = json.loads(df["ext_info"].iloc[0])["account_system"]
    ComponentMapping = args["ComponentMapping"][RuleName]
    # 解析持仓明细
    iComponentMapping = ComponentMapping[ComponentMapping["科目类别"]=="成本"]
    iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    Component = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"交易所": "exchange", "标的类别": "security_type", "交易标的": "underlying_asset"})
    Component = Component.loc[:, ["exchange", "parent_code", "security_type", "underlying_asset"] + FactorNames]
    Component["exchange"] = Component["exchange"].fillna("")
    if not Component.empty:
        SecurityAlloc = pd.merge(Component, df.set_index(["account_code"]).loc[:, ["parent_code"]].rename(columns={"parent_code": "parent_parent_code"}), how="left", left_on=["parent_code"], right_index=True)
        def _tmpf(df):
            df["value"] = df["value"] / df["value"].sum()
            return df
        SecurityAlloc = SecurityAlloc.set_index(["parent_parent_code"]).groupby(axis=0, level=0)[["account_code", "exchange", "security_code", "value"]].apply(_tmpf)
        Component.pop("parent_code")
        Component = Component.groupby(["exchange", "security_code"], as_index=False).apply(mergeComponent, idt, iid, logger, first_cols=["security_type", "underlying_asset"])
    # 解析应计利息
    if not Component.empty:
        iComponentMapping = ComponentMapping[ComponentMapping["科目类别"]=="应计利息"]
        iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
        iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "accrued_interest", "交易所": "exchange", "标的类别": "security_type", "交易标的": "underlying_asset"}).loc[:, ["security_code", "exchange", "accrued_interest", "account_code", "security_type", "underlying_asset", "account_name"]]
        if not iComponent.empty:
            iComponent["exchange"] = iComponent["exchange"].fillna("")
            iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeAccruedInterest, idt, iid, logger, first_cols=["security_type", "underlying_asset"]).reset_index(drop=True)
            Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
            Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
            Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
            Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
            Component["underlying_asset"] = Component["underlying_asset"].where(Component["underlying_asset"].notnull(), Component.pop("underlying_asset_y"))
        else:
            iComponent = pd.merge(df, iComponentMapping, left_on=["account_code", "account_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "accrued_interest"}).loc[:, ["accrued_interest", "parent_code"]]
            if not iComponent.empty:# 没有明细记录，但有汇总记录，将汇总值按持仓估值摊到每个标的上，测试案例：国金证券金创鑫6号集合资产管理计划(2022-11-30)
                iComponent = iComponent.groupby(["parent_code"]).sum()
                AccruedInterest = pd.merge(SecurityAlloc, iComponent, how="left", left_index=True, right_index=True)
                AccruedInterest["accrued_interest"] = AccruedInterest["accrued_interest"] * AccruedInterest["value"]
                AccruedInterest = AccruedInterest.groupby(["exchange", "security_code"], as_index=False)[["accrued_interest"]].sum()
                Component = pd.merge(Component, AccruedInterest, how="left", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"])
            else:
                Component["accrued_interest"] = np.nan
    # 解析减值准备
    if not Component.empty:
        iComponentMapping = ComponentMapping[ComponentMapping["科目类别"].str.contains("减值准备").fillna(False)]
        iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
        iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "depreciation_reserve", "交易所": "exchange", "标的类别": "security_type"}).loc[:, ["security_code", "exchange", "depreciation_reserve", "account_code", "security_type", "account_name"]]
        if not iComponent.empty:
            iComponent["exchange"] = iComponent["exchange"].fillna("")
            iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeDepreciationReserve, idt, iid, logger, first_cols=["security_type", "underlying_asset"]).reset_index(drop=True)
            Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
            Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
            Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
            Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
        else:
            iComponent = pd.merge(df, iComponentMapping, left_on=["account_code", "account_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "depreciation_reserve"}).loc[:, ["depreciation_reserve", "parent_code"]]
            if not iComponent.empty:  # 没有明细记录，但有汇总记录，将汇总值按持仓估值摊到每个标的上，测试案例：国金证券金创鑫6号集合资产管理计划(2022-11-30)
                iComponent = iComponent.groupby(["parent_code"]).sum()
                DepreciationReserve = pd.merge(SecurityAlloc, iComponent, how="left", left_index=True, right_index=True)
                DepreciationReserve["depreciation_reserve"] = DepreciationReserve["depreciation_reserve"] * AccruedInterest["value"]
                DepreciationReserve = DepreciationReserve.groupby(["exchange", "security_code"], as_index=False)[["depreciation_reserve"]].sum()
                Component = pd.merge(Component, DepreciationReserve, how="left", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"])
            else:
                Component["depreciation_reserve"] = np.nan
    # 解析应收利息
    iComponentMapping = ComponentMapping[ComponentMapping["科目类别"] == "应收利息"]
    iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "interest_receivable", "交易所": "exchange", "标的类别": "security_type", "交易标的": "underlying_asset"}).loc[:, ["security_code", "exchange", "interest_receivable", "account_code", "security_type", "underlying_asset", "account_name"]]
    if not iComponent.empty:
        iComponent["exchange"] = iComponent["exchange"].fillna("")
        iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeInterestReceivable, idt, iid, logger, first_cols=["security_type", "underlying_asset"]).reset_index(drop=True)
        Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
        Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
        Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
        Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
    if Component.empty: return pd.DataFrame(columns=["exchange", "security_type", "underlying_asset", *FactorNames, "accrued_interest", "interest_receivable", "depreciation_reserve"])
    # 检查问题
    _checkAccountCode(idt, iid, df, Component, ComponentMapping, logger)
    # 调整数据列
    Component["ext_info"] = json.dumps({"account_system": RuleName})
    Component = Component.reindex(columns=["exchange", "security_type", "underlying_asset", *FactorNames, "accrued_interest", "interest_receivable", "depreciation_reserve"])
    Component["exchange"] = Component["exchange"].where((Component["exchange"].notnull() & (Component["exchange"]!="")), None)
    return Component

# 抽取回购持仓
# idt: 估值时点, datetime
# iid: symbol, str
# df: 估值表数据, DataFrame(columns=["account_code", "account_name", "parent_code", "account_name_std", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info"])
# args: 参数集，{"ComponentMapping": {规则名称: DataFrame}, "RuleConfig": DataFrame(index=[symbol], columns=["规则"])
#   其中，ComponentMapping: 科目映射，RuleConfig: 科目配置
# 返回：DataFrame(columns=["account_code", "account_name", "exchange", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info", "accrued_interest", "interest_receivable", "depreciation_reserve"])
def calcRepoComponent(idt, iid, df, args, logger):
    FactorNames = ["account_code", "account_name", "security_code", "shares", "unit_cost", "cost", "price", "market_value", "value", "chg", "weight_in_nv", "ext_info"]
    iTmp = df[df["account_name_std"].notnull() & (df["account_name_std"]!="nan")].loc[:, ["account_code", "account_name_std"]].rename(columns={"account_code": "parent_code", "account_name_std": "parent_name_std"})
    df = pd.merge(df, iTmp, how="left", left_on=["parent_code"], right_on=["parent_code"])
    if df["security_code"].isnull().all(): return pd.DataFrame(columns=["exchange", "security_type", "underlying_asset", *FactorNames, "accrued_interest", "interest_payable"])
    RuleName = args["RuleConfig"]["规则"].get(iid, None)
    if not RuleName: RuleName = json.loads(df["ext_info"].iloc[0])["account_system"]
    ComponentMapping = args["ComponentMapping"][RuleName]
    # 解析持仓明细
    iComponentMapping = ComponentMapping[ComponentMapping["科目类别"]=="成本"]
    Component = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"交易所": "exchange", "标的类别": "security_type", "交易标的": "underlying_asset"})
    Component = Component.loc[:, ["exchange", "parent_code", "security_type", "underlying_asset"] + FactorNames]
    Component["exchange"] = Component["exchange"].fillna("")
    # 解析应计利息
    if not Component.empty:
        iComponentMapping = ComponentMapping[ComponentMapping["科目类别"]=="应计利息"]
        iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
        iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "accrued_interest", "交易所": "exchange", "标的类别": "security_type", "交易标的": "underlying_asset"}).loc[:, ["security_code", "exchange", "accrued_interest", "account_code", "security_type", "underlying_asset", "account_name"]]
        if not iComponent.empty:
            Component.pop("parent_code")
            Component = Component.groupby(["exchange", "security_code"], as_index=False).apply(mergeComponent, idt, iid, logger, first_cols=["security_type", "underlying_asset"])
            iComponent["exchange"] = iComponent["exchange"].fillna("")
            iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeAccruedInterest, idt, iid, logger, first_cols=["security_type", "underlying_asset"]).reset_index(drop=True)
            Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
            Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
            Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
            Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
            Component["underlying_asset"] = Component["underlying_asset"].where(Component["underlying_asset"].notnull(), Component.pop("underlying_asset_y"))
        else:
            iComponent = pd.merge(df, iComponentMapping, left_on=["account_code", "account_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "accrued_interest"}).loc[:, ["accrued_interest", "parent_code"]]
            if not iComponent.empty:# 没有明细记录，但有汇总记录，将汇总值按持仓估值摊到每个标的上，测试案例：国金证券金创鑫6号集合资产管理计划(2022-11-30)
                iComponent = iComponent.groupby(["parent_code"]).sum()
                Component = pd.merge(Component, df.set_index(["account_code"]).loc[:, ["parent_code"]].rename(columns={"parent_code": "parent_parent_code"}), how="left", left_on=["parent_code"], right_index=True)
                def _tmpf(df):
                    df["value"] = df["value"] / df["value"].sum()
                    return df
                SecurityAlloc = Component.set_index(["parent_parent_code"]).groupby(axis=0, level=0)[["account_code", "value"]].apply(_tmpf)
                SecurityAlloc = pd.merge(SecurityAlloc, iComponent, how="left", left_index=True, right_index=True)
                SecurityAlloc["accrued_interest"] = SecurityAlloc["accrued_interest"] * SecurityAlloc["value"]
                Component = pd.merge(Component, SecurityAlloc.set_index(["account_code"]).loc[:, ["accrued_interest"]], how="left", left_on=["account_code"], right_index=True)
                Component.pop("parent_parent_code")
                Component.pop("parent_code")
                Component = Component.groupby(["exchange", "security_code"], as_index=False).apply(mergeComponent, idt, iid, logger, first_cols=["security"])
                iComponent = iComponent.groupby(["parent_code"]).sum()
                AccruedInterest = pd.merge(SecurityAlloc, iComponent, how="left", left_index=True, right_index=True)
                AccruedInterest["accrued_interest"] = AccruedInterest["accrued_interest"] * AccruedInterest["value"]
                AccruedInterest = AccruedInterest.groupby(["exchange", "security_code"], as_index=False)[["accrued_interest"]].sum()
                Component = pd.merge(Component, AccruedInterest, how="left", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"])
            else:
                Component["accrued_interest"] = np.nan
    # 解析减值准备
    if not Component.empty:
        iComponentMapping = ComponentMapping[ComponentMapping["科目类别"].str.contains("减值准备").fillna(False)]
        iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
        iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "depreciation_reserve", "交易所": "exchange", "标的类别": "security_type"}).loc[:, ["security_code", "exchange", "depreciation_reserve", "account_code", "security_type", "account_name"]]
        if not iComponent.empty:
            iComponent["exchange"] = iComponent["exchange"].fillna("")
            iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeDepreciationReserve, idt, iid, logger, first_cols=["security_type", "underlying_asset"]).reset_index(drop=True)
            Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
            Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
            Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
            Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
        else:
            iComponent = pd.merge(df, iComponentMapping, left_on=["account_code", "account_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "depreciation_reserve"}).loc[:, ["depreciation_reserve", "parent_code"]]
            if not iComponent.empty:  # 没有明细记录，但有汇总记录，将汇总值按持仓估值摊到每个标的上，测试案例：国金证券金创鑫6号集合资产管理计划(2022-11-30)
                iComponent = iComponent.groupby(["parent_code"]).sum()
                DepreciationReserve = pd.merge(SecurityAlloc, iComponent, how="left", left_index=True, right_index=True)
                DepreciationReserve["depreciation_reserve"] = DepreciationReserve["depreciation_reserve"] * AccruedInterest["value"]
                DepreciationReserve = DepreciationReserve.groupby(["exchange", "security_code"], as_index=False)[["depreciation_reserve"]].sum()
                Component = pd.merge(Component, DepreciationReserve, how="left", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"])
            else:
                Component["depreciation_reserve"] = np.nan
    # 解析应收利息
    iComponentMapping = ComponentMapping[ComponentMapping["科目类别"] == "应收利息"]
    iComponentMapping = iComponentMapping[iComponentMapping["level"] == iComponentMapping["level"].max()]
    iComponent = pd.merge(df, iComponentMapping, left_on=["parent_code", "parent_name_std"], right_index=True, suffixes=("", "_y")).rename(columns={"value": "interest_receivable", "交易所": "exchange", "标的类别": "security_type", "交易标的": "underlying_asset"}).loc[:, ["security_code", "exchange", "interest_receivable", "account_code", "security_type", "underlying_asset", "account_name"]]
    if not iComponent.empty:
        iComponent["exchange"] = iComponent["exchange"].fillna("")
        iComponent = iComponent.groupby(["exchange", "security_code"], as_index=False).apply(_mergeInterestReceivable, idt, iid, logger, first_cols=["security_type", "underlying_asset"]).reset_index(drop=True)
        Component = pd.merge(Component, iComponent, how="outer", left_on=["exchange", "security_code"], right_on=["exchange", "security_code"], suffixes=("", "_y"))
        Component["account_code"] = Component["account_code"].where(Component["account_code"].notnull(), Component.pop("account_code_y"))
        Component["account_name"] = Component["account_name"].where(Component["account_name"].notnull(), Component.pop("account_name_y"))
        Component["security_type"] = Component["security_type"].where(Component["security_type"].notnull(), Component.pop("security_type_y"))
    if Component.empty: return pd.DataFrame(columns=["exchange", "security_type", "underlying_asset", *FactorNames, "accrued_interest", "interest_receivable", "depreciation_reserve"])
    # 检查问题
    _checkAccountCode(idt, iid, df, Component, ComponentMapping, logger)
    # 调整数据列
    Component["ext_info"] = json.dumps({"account_system": RuleName})
    Component = Component.reindex(columns=["exchange", "security_type", "underlying_asset", *FactorNames, "accrued_interest", "interest_receivable", "depreciation_reserve"])
    Component["exchange"] = Component["exchange"].where((Component["exchange"].notnull() & (Component["exchange"]!="")), None)
    return Component


