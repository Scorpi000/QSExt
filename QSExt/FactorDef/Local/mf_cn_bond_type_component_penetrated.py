# -*- coding: utf-8 -*-
"""公募基金债券大类持仓(穿透后)"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


# deprecated: 资产穿透, 返回: (ComponentID, PositionAmount, PositionWeight)
def penetrate_deprecated(f, idt, iid, x, args):
    nID = x[0].shape[0]
    IDs = np.array(iid)
    FundComponentID, FundPositionAmt = x[-2], x[-1]
    Rslt = []
    for i in range(nID):
        if not isinstance(FundComponentID[i], list):
            if not isinstance(x[1][i], list):
                Rslt.append((None, None, None))
            else:
                iTemp = np.array(x[2][i], dtype=float)
                if iTemp.shape[0]>0:
                    Rslt.append((x[1][i], iTemp.tolist(), (iTemp / float(x[0][i])).tolist()))
                else:
                    Rslt.append((None, None, None))
            continue
        if not isinstance(x[1][i], list):
            iAmt = pd.Series()
        else:
            iAmt = pd.Series(np.array(x[2][i], dtype=float), index=x[1][i])
        for j, jID in enumerate(FundComponentID[i]):
            jMask = (IDs==jID)
            if np.sum(jMask)==0: continue
            if isinstance(FundComponentID[jMask][0], list) and (len(FundComponentID[jMask][0])>0):
                raise Exception(f"'{iid[i]}' 持有的基金 '{jID}' 也持有基金!")
            if not isinstance(x[2][jMask][0], list): continue
            jWeight = np.array(x[2][jMask][0], dtype=float) / float(x[0][jMask][0])
            jAmt = pd.Series(jWeight * float(FundPositionAmt[i][j]), index=x[1][jMask][0])
            iAmt = iAmt.add(jAmt, fill_value=0)
        if iAmt.shape[0]>0:
            Rslt.append((iAmt.index.tolist(), iAmt.values.tolist(), (iAmt / float(x[0][i])).values.tolist()))
        else:
            Rslt.append((None, None, None))
    return Rslt

    
# 递归方式穿透单个基金
def _penetrate_single_fund(idx, mf_ids, total_asset, component_security_ids, component_security_amount, component_fund_ids, component_fund_amount, logger):
    if not isinstance(component_security_amount[idx], list):# 该基金不持有证券
        SecurityAmt = pd.Series()
    else:
        SecurityAmt = pd.Series(np.array(component_security_amount[idx], dtype=float), index=component_security_ids)
    iComponentFundIDs = component_fund_ids[idx]
    if isinstance(iComponentFundIDs, list) and (len(iComponentFundIDs)>0):# 该基金持有基金, 继续穿透
        for j, jID in enumerate(iComponentFundIDs):
            jIdx = mf_ids.searchsorted(jID)
            if (jIdx<mf_ids.shape[0]) and (mf_ids[jIdx]==jID):
                try:
                    jSecurityAmt = _penetrate_single_fund(jIdx, mf_ids, total_asset, component_security_ids, component_security_amount, component_fund_ids, component_fund_amount, logger)
                except RecursionError as e:
                    Logger.error(e)
                    Logger.debug(jID)
                    Logger.debug(component_fund_ids)
                    continue
                if jSecurityAmt.sum() > float(total_asset[jIdx]):
                    logger.error("'%s' 持有的成份总价值超过资产总值!" % (mf_ids[jIdx], ))
                jSecurityAmt = jSecurityAmt / float(total_asset[jIdx]) * float(component_fund_amount[idx][j])
                SecurityAmt = SecurityAmt.add(jSecurityAmt, fill_value=0)
            else:
                logger.warning("'%s' 持有的基金 '%s' 不在基金列表里!" % (mf_ids[idx], jID))
    return SecurityAmt

# 资产穿透, 返回: (ComponentID, PositionAmount, PositionWeight)
def penetrate(f, idt, iid, x, args):
    nID = x[0].shape[0]
    IDs = np.array(iid)
    Rslt = []
    for i in range(nID):
        iAmt = _penetrate_single_fund(i, IDs, x[0], x[1], x[2], x[3], x[4], f.Logger)
        if iAmt.shape[0]>0:
            Rslt.append((iAmt.index.tolist(), iAmt.tolist(), (iAmt / float(x[0][i])).tolist()))
        else:
            Rslt.append((None, None, None))
    return Rslt
    
    
def defFactor(args={}, debug=False):
    Factors = []

    LDB = args["LDB"]
    
    FT = LDB.getTable("mf_cn_asset_portfolio")
    TotalAsset = FT.getFactor("total_asset")
    ReportDate = FT.getFactor("report_date")
    InfoPublDate = FT.getFactor("info_pub_date")
    
    FT = LDB.getTable("mf_cn_bond_type_component", args={"多重映射": True})
    ComponentID = FT.getFactor("component_code")
    PositionAmount = FT.getFactor("amount")
    
    FT = LDB.getTable("mf_cn_fund_component", args={"多重映射": True})
    FundComponentID = FT.getFactor("component_code")
    FundPositionAmt = FT.getFactor("amount")

    PenetrateRslt = QS.FactorDB.SectionOperation(
        "PenetrateRslt", 
        [TotalAsset, ComponentID, PositionAmount, FundComponentID, FundPositionAmt], 
        sys_args={
            "算子":penetrate, 
            "数据类型":"object"
        }
    )
    
    ComponentID = fd.fetch(PenetrateRslt, 0, dtype="object", factor_name="component_code")
    Factors.append(ComponentID)
    Factors.append(fd.fetch(PenetrateRslt, 1, dtype="object", factor_name="amount"))
    Factors.append(fd.fetch(PenetrateRslt, 2, dtype="object", factor_name="weight"))
    Factors.append(ReportDate)
    Factors.append(InfoPublDate)

    UpdateArgs = {
        "因子表": "mf_cn_bond_type_component_penetrated",
        "因子库参数": {"检查写入值": True},
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 365 * 10,
        "IDs": "公募基金",
        "时点类型": "自然日"
    }

    return (Factors, UpdateArgs)


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB()
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    Args = {"LDB": TDB}
    Factors, UpdateArgs = defFactor(Args)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2020, 10, 9)
    #DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTs = QS.Tools.DateTime.getDateTimeSeries(StartDT, EndDT, timedelta=dt.timedelta(1))# 自然日
    #DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    DTRuler = QS.Tools.DateTime.getDateTimeSeries(StartDT-dt.timedelta(365), EndDT, timedelta=dt.timedelta(1))# 自然日
    #DTs = DTs[-1:]# 只保留最新数据
    
    #IDs = sorted(pd.read_csv("../conf/mf/MFIDs.csv", index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
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