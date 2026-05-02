# -*- coding: utf-8 -*-
"""公募基金基金经理"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

def adjustDT(f, idt, iid, x, args):
    if isinstance(x[0], list):
        return [(None if pd.isnull(iDT) else iDT.strftime("%Y-%m-%d")) for iDT in x[0]]
    else:
        return x[0]

# args 应该包含的参数
# JYDB: 聚源因子库对象
def defFactor(args={}, debug=False):
    Factors = []

    JYDB = args["JYDB"]

    FT = JYDB.getTable("公募基金经理(新)", args={"多重映射": True, "只填起始日": True})
    Factors.append(FT.getFactor("所属人员代码", new_name="manager_code"))
    Factors.append(FT.getFactor("姓名", new_name="manager_name"))
    Factors.append(FT.getFactor("职位名称_R", new_name="post"))
    Factors.append(FT.getFactor("在任与否", new_name="incumbent"))
    Factors.append(FT.getFactor("任职天数", new_name="management_time"))
    Factors.append(FT.getFactor("任职期间基金净值增长率", new_name="performance"))
    
    AccessionDate = QS.FactorDB.PointOperation(
        "accession_date",
        [FT.getFactor("到任日期")],
        sys_args={
            "算子": adjustDT,
            "运算时点": "单时点",
            "运算ID": "单ID",
            "数据类型": "object"
        }
    )
    Factors.append(AccessionDate)
    
    DimissionDate = QS.FactorDB.PointOperation(
        "dimission_date",
        [FT.getFactor("离职日期")],
        sys_args={
            "算子": adjustDT,
            "运算时点": "单时点",
            "运算ID": "单ID",
            "数据类型": "object"
        }
    )
    Factors.append(DimissionDate)
    
    InfoPublDate = QS.FactorDB.PointOperation(
        "info_pub_date",
        [FT.getFactor("信息发布日期")],
        sys_args={
            "算子": adjustDT,
            "运算时点": "单时点",
            "运算ID": "单ID",
            "数据类型": "object"            
        }
    )
    Factors.append(InfoPublDate)
                    
    UpdateArgs = {
        "因子表": "mf_cn_fund_manager",
        "因子库参数": {"检查写入值": True},
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": "公募基金"
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