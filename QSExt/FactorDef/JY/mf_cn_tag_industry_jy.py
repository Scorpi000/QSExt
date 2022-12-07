# -*- coding: utf-8 -*-
"""公募基金行业标签(聚源)"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

def adjustCorr(f, idt, iid, x, args):
    TagCode, CorrTagCode, CorrTag = x
    if not isinstance(TagCode, list):
        return None
    if not isinstance(CorrTagCode, list):
        return [np.nan] * len(TagCode)
    try:
        return pd.Series(CorrTag, index=CorrTagCode).loc[TagCode].tolist()
    else:
        return [np.nan] * len(TagCode)

def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    FT = JYDB.getTable("公募基金行业标签变动", args={"多重映射": True, "只填起始日": False, "关联类型": "1", "指标周期": args.get("cycle", "6")})
    Factors.append(FT.getFactor("指标周期", new_name="cycle"))
    Factors.append(FT.getFactor("标签代码_R", new_name="tag_code"))
    Factors.append(FT.getFactor("标签名称", new_name="tag"))
    TagCode = FT.getFactor("标签代码")
    
    FT = JYDB.getTable("基金风格业绩相似度(行业)", args={"标签种类": "3", "指标周期": args.get("cycle", "6")})
    CorrTagCode = FT.getFactor("标签代码")
    CorrTag = FT.getFactor("指标值")
    TagCorr = QS.FactorDB.PointOperation(
        "tag_corr",
        [TagCode, CorrTagCode, CorrTag],
        sys_args={
            "算子": adjustCorr,
            "数据类型": "object"
        }
    )
    Factors.append(TagCorr)
    
    UpdateArgs = {
        "因子表": "mf_cn_tag_industry_jy",
        "因子库参数": {"检查写入值": True},
        "默认起始日": dt.datetime(2002,1,1),
        "最长回溯期": 3650,
        "IDs": "公募基金"
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
    
    Args = {"JYDB": JYDB, "LDB": TDB}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)
    
    StartDT, EndDT = dt.datetime(2010, 1, 1), dt.datetime(2021, 10, 20)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date()-dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
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