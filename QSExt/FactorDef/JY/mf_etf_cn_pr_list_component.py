# -*- coding: utf-8 -*-
"""ETF 申赎清单成份明细"""
from typing import Dict

import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QuantStudio.Tools.DataTypeConversionFun import expandListElementDataFrame
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef
from QSExt.FactorDef.JY.stock_cn_day_bar_nafilled import defFactor as defStockDayBar


@FactorOperatorized(operator_type="Section", args={"Arity": 4, "DTMode": "单时点", "DataType": "object"})
def calcWeight(f, idt, iid, x, args):
    ComponentPrice = pd.Series(x[-1], index=f.Operator.Args.DescriptorSection[-1])
    ComponentInfo = pd.DataFrame({"ComponentID": x[0], "Num": x[1], "Amt": x[2]}, index=iid)
    ComponentInfo = expandListElementDataFrame(ComponentInfo)
    ComponentInfo.columns = ["ID"] + ComponentInfo.columns[1:].tolist()
    ComponentInfo["Num"] = ComponentInfo["Num"].astype(float)
    ComponentInfo = pd.merge(ComponentInfo, ComponentPrice.to_frame(name="Close"), how="left", left_on=["ComponentID"], right_index=True)
    ComponentInfo["CalcedAmt"] = ComponentInfo["Num"] * ComponentInfo["Close"]
    ComponentInfo["Amt"] = ComponentInfo["CalcedAmt"].where(pd.notnull(ComponentInfo["CalcedAmt"]), ComponentInfo["Amt"].astype(float))
    TotalAmt = ComponentInfo.groupby(["ID"])["Amt"].sum()
    ComponentInfo = pd.merge(ComponentInfo, TotalAmt.to_frame("TotalAmt"), how="left", left_on=["ID"], right_index=True)
    ComponentInfo["Weight"] = ComponentInfo["Amt"] / ComponentInfo["TotalAmt"]
    return ComponentInfo.groupby(["ID"])["Weight"].apply(lambda s: s.tolist()).reindex(index=iid).values

def calcSubstituteAmt(df):
    ApplyAmt = df["申购替代金额(元)"].astype(float).where(pd.notnull(df["申购替代金额(元)"]), df["固定替代金额(元)"]) / (1 + df["申购现金替代溢价比例"].astype(float).fillna(0))
    RedeemAmt = df["赎回替代金额(元)"].astype(float).where(pd.notnull(df["赎回替代金额(元)"]), df["固定替代金额(元)"]) / (1 - df["赎回现金替代折价比例"].astype(float).fillna(0))
    return ApplyAmt.where(pd.notnull(ApplyAmt), RedeemAmt).tolist()

def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]

    ComponentIDs = fdi.ModelArgs["component_ids"]
    
    FT = JYDB.getTable("公募基金ETF申购赎回成份股信息(公募基金ID)")
    ComponentID = FT.getFactor("成份股内部编码_R")
    Factors.append(rename(ComponentID, factor_name="component_code"))
    ComponentNum = FT.getFactor("股票数量(股)")
    Factors.append(rename(ComponentNum, factor_name="volume"))
    Factors.append(rename(FT.getFactor("现金替代标志_R"), factor_name="cash_substitute"))

    FT = JYDB.getTable("公募基金ETF申购赎回成份股信息(公募基金ID)", args={"MultiMapping": True, "Operator": calcSubstituteAmt, "OperatorDataType": "object", "AdditionalFields": ["申购替代金额(元)", "申购现金替代溢价比例", "赎回替代金额(元)", "赎回现金替代折价比例"]})
    SubstituteAmt = FT.getFactor("固定替代金额(元)")

    StockDayBarDef = dep_fd.get("stock_cn_day_bar_nafilled", defStockDayBar(fdi=fdi, dep_fd=dep_fd))
    StockClose = StockDayBarDef.getFactor(factor_name="close")

    # 根据申赎清单估计的持仓权重
    calculateWeight = calcWeight.new(args={"DescriptorSection": [None, None, None, ComponentIDs]})
    ComponentWeight = calculateWeight(ComponentID, ComponentNum, SubstituteAmt, StockClose, factor_args={"Name": "weight"})
    Factors.append(ComponentWeight)
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="mf_etf_cn_pr_list_component",
        IDType="ETF",
        Author="麦冬",
        Description="ETF申购赎回清单信息",
        DefScriptPath=__file__
    )
