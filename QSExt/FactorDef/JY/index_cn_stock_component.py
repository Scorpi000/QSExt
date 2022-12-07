# -*- coding: utf-8 -*-
"""指数成份"""
import datetime as dt

import datetime as dt
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

def adjustUnit(f, idt, iid, x, args):
    if isinstance(x[0], list):
        return (np.array(x[0], dtype="float") / 100).tolist()
    else:
        return x[0]

# args 应该包含的参数
# JYDB: 聚源因子库对象
# id_info_file: ID 配置信息文件地址
def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    FT = JYDB.getTable("指数成份股权重(指数ID)", args={"公告时点字段": None, "忽略时间": True, "回溯天数": np.inf})
    ComponentID = FT.getFactor("成份股内部编码_R", new_name="component_code")
    Factors.append(ComponentID)
    
    PositionWeight = FT.getFactor("权重(%)")
    PositionWeight = QS.FactorDB.PointOperation(
        "weight", 
        [PositionWeight], 
        sys_args={
            "算子": adjustUnit, 
            "数据类型": "object"
        }
    )
    Factors.append(PositionWeight)
    
    UpdateArgs = {
        "因子表": "index_cn_stock_component",
        "默认起始日": dt.datetime(2000, 1, 1),
        "最长回溯期": 365,
        "IDs": "外部指定"
    }
    
    return (Factors, UpdateArgs)

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_FactorTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    # 生成指数 ID
    IDs = []
    for iInfoFile in [r"../conf/index/IndexIDs_IndexMF.csv"]:
        IDs += pd.read_csv(iInfoFile, index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0].tolist()
    IDs = sorted(set(IDs))
    
    Args = {"JYDB": JYDB}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)

    StartDT, EndDT = dt.datetime(2000, 1, 1), dt.datetime(2021, 6, 30)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTRuler)
    CFT.setID(IDs)

    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
                  factor_db=TDB, table_name=TargetTable,
                  if_exists="update", subprocess_num=0)

    TDB.disconnect()
    JYDB.disconnect()
