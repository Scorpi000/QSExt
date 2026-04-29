# -*- coding: utf-8 -*-
"""A股状态"""
import datetime as dt
from typing import Dict

import numpy as np
import pandas as pd

from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


@FactorOperatorized(operator_type="Point", args={"Arity": 2, "DTMode": "多时点", "IDMode": "多ID", "DataType": "double"})
def ifListed(f, idt, iid, x, args):
    ListDate, StatusChg = x
    Listed = np.zeros(ListDate.shape)
    DTs = np.array([idt]).T.repeat(ListDate.shape[1], axis=1).astype("datetime64")
    Listed[ListDate <= DTs] = 1
    StatusChg = np.where(StatusChg != 4, np.nan, StatusChg)
    StatusChg = pd.DataFrame(StatusChg).ffill().values
    Listed[StatusChg == 4] = 0
    return Listed

@FactorOperatorized(operator_type="Point", args={"Arity": 1, "DTMode": "多时点", "IDMode": "多ID", "DataType": "double"})
def calcListDayNum(f, idt, iid, x, args):
    ListDate = x[0].astype("datetime64")
    DTs = np.array([idt], dtype="datetime64").T.repeat(ListDate.shape[1], axis=1)
    ListDayNum = (DTs - ListDate).astype("timedelta64[D]") / np.timedelta64(1, "D")
    ListDayNum[ListDayNum < 0] = np.nan
    return ListDayNum + 1

def mergeST(l):
    STSet = set()
    for i in l:
        if i==1:
            STSet.add("ST")
        elif i==2:
            STSet.discard("ST")
        elif i==3:
            STSet.add("PT")
        elif i==4:
            STSet.discard("PT")
        elif i==5:
            STSet.add("*ST")
        elif i==6:
            STSet.discard("*ST")
        elif i==7:
            STSet.discard("*ST")
            STSet.add("ST")
        elif i==8:
            STSet.discard("ST")
            STSet.add("*ST")
        elif i==9:
            STSet.add("退市整理期")
        elif i==10:
            STSet.add("高风险警示")
        elif i==11:
            STSet.discard("高风险警示")
        elif i==12:
            STSet.add("ST")
        elif i==13:
            STSet.discard("ST")
        elif i==14:
            STSet.add("*ST")
        elif i==15:
            STSet.discard("*ST")
        else:
            raise __QS_Error__(f"不能识别的特别处理代码: {i}")
    if STSet:
        return ",".join(STSet)
    else:
        return None

@FactorOperatorized(operator_type="Point", args={"Arity": 1, "DTMode": "多时点", "IDMode": "多ID", "DataType": "string"})
def calcST(f, idt, iid, x, args):
    STType = x[0]
    ST = np.full(shape=STType.shape, fill_value=None, dtype="O")
    ST[(STType == 1) | (STType == 7)] = "ST"
    ST[(STType == 5) | (STType == 8)] = "*ST"
    ST[STType == 3] = "PT"
    ST[STType == 9] = "退市整理期"
    ST[STType == 10] = "高风险警示"
    return ST

@FactorOperatorized(operator_type="Point", args={"Arity": 3, "DTMode": "多时点", "IDMode": "多ID", "DataType": "double"})
def ifTrading(f, idt, iid, x, args):
    Volume, SuspendDate, SuspendTime = x
    DTs = np.array([idt]).T.repeat(Volume.shape[1], axis=1)
    IfTrading = np.ones(shape=Volume.shape)
    Mask = (DTs>=dt.datetime(2008, 4, 1))
    VolMask = (pd.isnull(Volume) | (Volume<=0))
    IfTrading[(~Mask) & VolMask] = 0
    IfTrading[Mask & (VolMask | pd.notnull(SuspendDate))] = 0
    try:
        IfTrading[Mask & (~ VolMask) & (SuspendTime != "9:30:00") & (SuspendDate == DTs.astype(SuspendDate.dtype))] = 1
    except:
        IfTrading[Mask & (~ VolMask) & (SuspendTime != "9:30:00") & (SuspendDate == DTs)] = 1
    IfTrading[IfTrading != 1] = np.nan
    return IfTrading


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []

    JYDB = fdi.FDB["JYDB"]

    notnull = fo.NotNull()

    # 证券特征
    ListDate = JYDB.getTable("A股证券主表").getFactor("上市日期")
    ListDayNum = calcListDayNum(ListDate, factor_args={"Name": "listed_days"})
    Factors.append(ListDayNum)

    StatusChg = JYDB.getTable("上市状态更改", args={"LookBack": np.inf}).getFactor("变更类型")

    StatusChg_STIB = JYDB.getTable("科创板上市状态更改", args={"LookBack": np.inf}).getFactor("变更类型")
    StatusChg = fo.Where(dtype="double")(StatusChg, notnull(StatusChg), StatusChg_STIB)

    IfListed = ifListed(ListDate, StatusChg, factor_args={"Name": "if_listed"})
    Factors.append(IfListed)

    ST = JYDB.getTable("证券特别处理", args={"LookBack": np.inf, "Operator": mergeST, "OperatorDataType": "string", "MultiMapping": True, "OrderFields": [("信息发布日期", "ASC")]}).getFactor("特别处理(或撤销)类别")

    ST_STIB = JYDB.getTable("科创板证券简称更改", args={"FilterCondition": "{Table}.ChangeType<>99", "PublDTField": None, "LookBack": np.inf, "Operator": mergeST, "OperatorDataType": "string", "MultiMapping": True, "OrderFields": [("信息发布日期", "ASC")]}).getFactor("变更类型")
    ST = fo.Where(dtype="string")(ST, notnull(ST), ST_STIB, factor_args={"Name": "st"})

    # ST = calcST(ST, factor_args={"Name": "st"})
    Factors.append(ST)

    # 交易状态
    FT = JYDB.getTable("日行情表", args={"LookBack": 0})
    Volume = FT.getFactor("成交量(股)")

    FT = JYDB.getTable("科创板日行情", args={"LookBack": 0})
    Volume = fo.Where(dtype="double")(Volume, notnull(Volume), FT.getFactor("收盘成交量(股)"))

    FT = JYDB.getTable("停牌复牌表", args={"OnlyStartFilled": False, "MultiMapping": False})
    SuspendDate = FT.getFactor("停牌日期")
    SuspendTime = FT.getFactor("停牌时间")

    FT = JYDB.getTable("科创板停复牌", args={"LookBack": np.inf, "MultiMapping": True, "OrderFields": [("停复牌时间", "ASC")], "Operator": lambda s: s.iloc[-1], "OperatorDataType": "string"})
    SuspendDate_STIB = FT.getFactor("停复牌日期")
    SuspendTime_STIB = FT.getFactor("停复牌时间")
    SuspendType_STIB = FT.getFactor("停复牌类型")
    SuspendDate_STIB = fo.Where(dtype="object")(SuspendDate_STIB, SuspendType_STIB==1, None)
    SuspendTime_STIB = fo.Where(dtype="string")(SuspendTime_STIB, SuspendType_STIB==1, None)
    SuspendDate = fo.Where(dtype="object")(SuspendDate, notnull(SuspendDate), SuspendDate_STIB)
    SuspendTime = fo.Where(dtype="string")(SuspendTime, notnull(SuspendTime), SuspendTime_STIB)

    IfTrading = ifTrading(Volume, SuspendDate, SuspendTime, factor_args={"Name": "if_trading"})
    Factors.append(IfTrading)

    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_status",
        IDType="A股",
        Author="麦冬",
        Description="A股证券的状态信息, 包括是否上市、是否可以交易、特别处理等",
        DefScriptPath=__file__
    )