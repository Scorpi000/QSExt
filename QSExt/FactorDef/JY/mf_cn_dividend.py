# -*- coding: utf-8 -*-
"""公募基金分红"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize


def strftime(l):
    return [(iDT.strtime("%Y-%m-%d") if pd.notnull(iDT) else None) for iDT in l.tolist()]

# args 应该包含的参数
# JYDB: 聚源因子库对象
def defFactor(args={}, debug=False):
    Factors = []

    JYDB = args["JYDB"]

    FT = JYDB.getTable("公募基金分红", args={"多重映射": True, "事件进程代码":"3131", "时点字段": "除息日"})
    Factors.append(FT.getFactor("派现比例(含税10派X元)", new_name="cash_dividend"))
    Factors.append(FT.getFactor("实派比例(税后10派X元)", new_name="actual_cash_dividend"))
    Factors.append(FT.getFactor("信息发布日期", args={"算子": strftime}, new_name="info_pub_date"))
    Factors.append(FT.getFactor("权益登记日", args={"算子": strftime}, new_name="right_reg_date"))
    Factors.append(FT.getFactor("除息日", args={"算子": strftime}, new_name="ex_dividend_date"))
    Factors.append(FT.getFactor("场内除息日", args={"算子": strftime}, new_name="in_ex_date"))
    Factors.append(FT.getFactor("场外除息日", args={"算子": strftime}, new_name="out_ex_date"))
    Factors.append(FT.getFactor("发放日", args={"算子": strftime}, new_name="execute_date"))
    Factors.append(FT.getFactor("场内发放日", args={"算子": strftime}, new_name="in_execute_date"))
    Factors.append(FT.getFactor("场外发放日", args={"算子": strftime}, new_name="out_execute_date"))
    Factors.append(FT.getFactor("红利再投资日", args={"算子": strftime}, new_name="reinvest_date"))
    Factors.append(FT.getFactor("红利再投资份额到帐日", args={"算子": strftime}, new_name="reinvest_to_account_date"))
    Factors.append(FT.getFactor("红利再投资份额可赎回日", args={"算子": strftime}, new_name="reinvest_redemption_date"))
                                                
    UpdateArgs = {
        "因子表": "mf_cn_dividend",
        "因子库参数": {"检查写入值": True},
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": "公募基金",
        "时点类型": "自然日"
    }

    return (Factors, UpdateArgs)


if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_WMTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Args = {"JYDB": JYDB}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    #DTs = DTs[-1:]# 只保留最新数据
    
    #IDs = sorted(pd.read_csv("."+os.sep+"MFIDs.csv", index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
    IDs = JYDB.getMutualFundID(is_current=False)
    #IDs = ["159956.OF"]
    
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