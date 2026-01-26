# -*- coding: utf-8 -*-
import os
import re
import logging
import datetime as dt

import pandas as pd

from QSExt import __QS_MainPath__
from QSExt.ValuationTable.utils import mergeComponent, calcCashComponent, calcStockComponent, calcBondComponent, calcABSComponent, calcReverseRepoComponent, calcRepoComponent, calcMFComponent

def main(tdb, start_dt=None, end_dt=None, symbols=None, args={}, logger=None):
    AssetMapping = {
        "cash": "现金",
        "stock": "股票",
        "bond": "债券",
        "abs": "资产支持证券",
        "reverse_repo": "逆回购",
        "repo": "正回购",
        "mf": "基金",
        "future": "期货",
        "option": "期权",
        "warrant": "权证",
        "swap": "互换",
        "other_derivative": "其他衍生品",
        "financial_product": "理财",
        "other_asset": "其他资产",
        "margin": "融券",
        "financing": "融资",
        "expense": "费用"
    }

    # 参数设置
    iLogger = (logging.getLogger() if not logger else logger)
    StartDT = (pd.to_datetime(start_dt) if start_dt else None)
    EndDT = (pd.to_datetime(end_dt) if end_dt else None)
    Symbols = ([] if not symbols else symbols)
    TargetAssets = args.get("target_asset", sorted(AssetMapping.keys()))

    # 读取辅助信息
    with pd.ExcelFile(os.path.join(__QS_MainPath__, f"Resource{os.sep}Info.xlsx"), engine="openpyxl") as xlsFile:
        ExchangeInfo = pd.read_excel(xlsFile, "交易所", index_col=None, header=0)
        ExchangeInfo["ExchangeCode"] = ExchangeInfo["ExchangeCode"].astype(int).astype(str)
        ExchangeInfo = ExchangeInfo.set_index(["ExchangeCode"])
        FutureInfo = pd.read_excel(xlsFile, "期货", index_col=None, header=0)
        PFMapping = pd.read_excel(xlsFile, "私募产品映射", index_col=None, header=0)
    PFMapping["fund_id"] = PFMapping["fund_id"].astype(int).astype(str)

    # 读取估值表数据
    AccountDetail = readValuationData("pf_cn_valuation_detail", symbols=Symbols, start_dt=StartDT, end_dt=EndDT)
    if AccountDetail.empty: return
    AccountDetail = AccountDetail.groupby(["the_datetime", "symbol"], as_index=False).apply(lambda df: df[df["account_type"]==df["account_type"].max()]).reset_index(drop=True)

    # 读取科目配置体系
    ComponentMapping = {}
    with pd.ExcelFile(os.path.join(__QS_MainPath__, f"ValuationTable{os.sep}估值表科目.xlsx"), engine="openpyxl") as xlsFile:
        for iRuleName in xlsFile.sheet_names:
            iComponentMapping = pd.read_excel(xlsFile, iRuleName, index_col=None, header=0)
            iComponentMapping["accout_code"] = iComponentMapping["account_code"].astype(str)
            ComponentMapping[iRuleName] = iComponentMapping.set_index(["account_code", "account_name"])
    Args = {"RuleConfig": pd.read_excel(os.path.join(__QS_MainPath__, f"ValuationTable{os.sep}估值表规则配置.xlsx"), "科目规则", index_col=0, header=0, engine="openpyxl")}

    # 解析投资组合
    Component = {}
    # 现金投资组合
    if "cash" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"]=="现金"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcCashComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        Component["cash"] = iComponent

    # 股票投资组合
    if "stock" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "股票"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcStockComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        Component["stock"] = iComponent

    # 债券投资组合
    if "bond" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "债券"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcBondComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        # 映射债券代码
        if not iComponent.empty:
            iComponent = chg_bond_security_code(iComponent.reset_index(), ExchangeInfo, iLogger)
            Mask = (iComponent["security_code_adj"].isnull() & iComponent["security_code"].notnull())
            if Mask.any(): iLogger.error({"msg": f"无法匹配到证券代码的债券: {iComponentMapping[Mask]}", "alarm": True, "name": "not_known_code", "source": "QSExt.ValuationTable.script.gen_component.main"})
            iComponent["security_code"] = iComponent["security_code"].where(Mask, iComponent.pop("security_code_adj"))
            iComponent = iComponent.groupby(["the_datetime", "symbol", "exchange", "security_code"], as_index=False, dropna=False).apply(lambda df: mergeComponent(df, df["the_datetime"].iloc[0], df["symbol"].iloc[0], iLogger, first_cols=["the_datetime", "symbol", "security_type", "ext_info"], sum_cols=["accrued_interest", "interest_receivable", "depreciation_reserve"]))
            iComponent = iComponent.set_index(["the_datetime", "symbol"])
        Component["bond"] = iComponent

    # 资产支持证券投资组合
    if "abs" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "资产支持证券"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcABSComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        # 映射ABS代码
        if not iComponent.empty:
            iComponent = chg_bond_security_code(iComponent.reset_index(), ExchangeInfo, iLogger)
            Mask = (iComponent["security_code_adj"].isnull() & iComponent["security_code"].notnull())
            if Mask.any(): iLogger.error({"msg": f"无法匹配到证券代码的资产支持证券: {iComponentMapping[Mask]}", "alarm": True, "name": "not_known_code", "source": "QSExt.ValuationTable.script.gen_component.main"})
            iComponent["security_code"] = iComponent["security_code"].where(Mask, iComponent.pop("security_code_adj"))
            iComponent = iComponent.groupby(["the_datetime", "symbol", "exchange", "security_code"], as_index=False, dropna=False).apply(lambda df: mergeComponent(df, df["the_datetime"].iloc[0], df["symbol"].iloc[0], iLogger, first_cols=["the_datetime", "symbol", "security_type", "ext_info"], sum_cols=["accrued_interest", "interest_receivable", "depreciation_reserve"]))
            iComponent = iComponent.set_index(["the_datetime", "symbol"])
        Component["abs"] = iComponent

    # 逆回购投资组合
    if "reverse_repo" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "逆回购"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcReverseRepoComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        # 映射回购代码
        if not iComponent.empty:
            iComponent = chg_repo_security_code(iComponent.reset_index(), ExchangeInfo, iLogger)
            Mask = (iComponent["security_code_adj"].isnull() & iComponent["security_code"].notnull())
            if Mask.any(): iLogger.error({"msg": f"无法匹配到证券代码的逆回购: {iComponentMapping[Mask]}", "alarm": True, "name": "not_known_code", "source": "QSExt.ValuationTable.script.gen_component.main"})
            iComponent["security_code"] = iComponent["security_code"].where(Mask, iComponent.pop("security_code_adj"))
            iComponent = iComponent.groupby(["the_datetime", "symbol", "exchange", "security_code"], as_index=False, dropna=False).apply(lambda df: mergeComponent(df, df["the_datetime"].iloc[0], df["symbol"].iloc[0], iLogger, first_cols=["the_datetime", "symbol", "security_type", "underlying_asset", "ext_info"], sum_cols=["accrued_interest", "interest_receivable", "depreciation_reserve"]))
            iComponent = iComponent.set_index(["the_datetime", "symbol"])
        Component["reverse_repo"] = iComponent

    # 正回购投资组合
    if "repo" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "正回购"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcRepoComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        # 映射回购代码
        if not iComponent.empty:
            iComponent = chg_repo_security_code(iComponent.reset_index(), ExchangeInfo, iLogger)
            Mask = (iComponent["security_code_adj"].isnull() & iComponent["security_code"].notnull())
            if Mask.any(): iLogger.error({"msg": f"无法匹配到证券代码的逆回购: {iComponentMapping[Mask]}", "alarm": True, "name": "not_known_code", "source": "QSExt.ValuationTable.script.gen_component.main"})
            iComponent["security_code"] = iComponent["security_code"].where(Mask, iComponent.pop("security_code_adj"))
            iComponent = iComponent.groupby(["the_datetime", "symbol", "exchange", "security_code"], as_index=False, dropna=False).apply(lambda df: mergeComponent(df, df["the_datetime"].iloc[0], df["symbol"].iloc[0], iLogger, first_cols=["the_datetime", "symbol", "security_type", "underlying_asset", "ext_info"], sum_cols=["accrued_interest", "interest_payable"]))
            iComponent = iComponent.set_index(["the_datetime", "symbol"])
        Component["reverse_repo"] = iComponent

    # 公募基金投资组合
    if "mf" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "基金"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcMFComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        Component["mf"] = iComponent

    # 期货投资组合
    if "future" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "期货"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcFutureComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        iPattern = r"^[a-zA-Z]+"
        iVariety = iComponent["security_code"].apply(lambda s: re.search(iPattern, s).group(0).upper() if re.search(iPattern, s) else None)
        iTypeMapping = FutureInfo.set_index(["品种代码"])["类型"]
        iMask = iVariety.isin(iTypeMapping.index)
        if not iMask.all(): iLogger.error({"msg": f"无法识别类型的期货代码: {iComponent['security_code'][~iMask].tolist()}", "alarm": True, "name": "not_known_code", "source": "QSExt.ValuationTable.script.gen_component.main"})
        iComponent["security_type"] = iVariety.replace(iTypeMapping).where(iMask, None)
        Component["future"] = iComponent

    # 期权投资组合
    if "option" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "期权"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcOptionComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        Component["option"] = iComponent

    # 权证投资组合
    if "warrant" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "权证"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcWarrantComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        Component["warrant"] = iComponent

    # 互换投资组合
    if "swap" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "互换"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcSwapComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        Component["swap"] = iComponent

    # 其他衍生品投资组合
    if "other_derivative" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping.index.get_level_values(0).str.slice(0, 2).isin(("31", "32")) & (~iComponentMapping["资产类型"].isin(list(AssetMapping.values())))] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcOtherDerivativeComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        Component["other_derivative"] = iComponent

    # 理财产品持仓组合
    if "financial_product" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "理财"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcFinancialProductComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        # 映射回购代码
        if not iComponent.empty:
            iComponent = chg_repo_security_code(iComponent.reset_index(), ExchangeInfo, iLogger)
            Mask = (iComponent["security_code_adj"].isnull() & iComponent["security_code"].notnull())
            if Mask.any(): iLogger.error({"msg": f"无法匹配到证券代码的逆回购: {iComponentMapping[Mask]}", "alarm": True, "name": "not_known_code", "source": "QSExt.ValuationTable.script.gen_component.main"})
            iComponent["security_code"] = iComponent["security_code"].where(Mask, iComponent.pop("security_code_adj"))
            iComponent = iComponent.groupby(["the_datetime", "symbol", "exchange", "security_code"], as_index=False, dropna=False).apply(lambda df: mergeComponent(df, df["the_datetime"].iloc[0], df["symbol"].iloc[0], iLogger, first_cols=["the_datetime", "symbol", "security_type", "underlying_asset", "ext_info"], sum_cols=["accrued_interest", "interest_payable"]))
            iComponent = iComponent.set_index(["the_datetime", "symbol"])
        Component["reverse_repo"] = iComponent

    # 其他资产投资组合
    if "other_asset" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping.index.get_level_values(0).str.slice(0, 1).isin(("1",)) & (~iComponentMapping["资产类型"].isin(list(AssetMapping.values())))] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcOtherAssetComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        Component["other_asset"] = iComponent

    # 融券持仓组合
    if "margin" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "融券"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcOtherAssetComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        Component["margin"] = iComponent

    # 融资持仓组合
    if "financing" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "融资"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcFinancingComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        Component["financing"] = iComponent

    # 费用持仓组合
    if "expense" in TargetAssets:
        Args["ComponentMapping"] = {iRuleName: iComponentMapping[iComponentMapping["资产类型"] == "费用"] for iRuleName, iComponentMapping in ComponentMapping.items()}
        iComponent = AccountDetail.groupby(by=["the_datetime", "symbol"], as_index=True).apply(lambda df: calcExpenseComponent(df["the_datetime"].iloc[0], df["symbol"].iloc[0], df, Args, iLogger))
        iComponent = iComponent.droplevel(2, axis=0)
        Component["expense"] = iComponent

    with pd.ExcelFile(os.path.join(__QS_MainPath__, f"ValuationTable{os.sep}估值表数据字典.xlsx"), engine="openpyxl") as xlsFile:
        for iAsset in TargetAssets:
            iAssetName = AssetMapping[iAsset]
            iComponent = Component[iAsset]
            if iComponent.empty: continue
            iFieldTypes = pd.read_excel(xlsFile, f"{iAssetName}组合明细", index_col=0, header=0)
            tdb.deleteTable(f"pf_cn_component_{iAsset}")
            tdb.createDBTable(f'pf_cn_component_{iAsset}', iFieldTypes["数据类型"].to_dict(), lefecycle=args.get("lifecycle", 63), field_comment=iFieldTypes["字段中文名"].to_dict())
            tdb.writeDataFrame(iComponent, f"pf_cn_component_{iAsset}", if_exists="update")

if __name__=="__main__":
    print("===")