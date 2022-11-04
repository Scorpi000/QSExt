# -*- coding: utf-8 -*-
"""指数行情"""
import datetime as dt

import datetime as dt
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# args 应该包含的参数
# JYDB: 聚源因子库对象
# id_info_file: ID 配置信息文件地址
def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    FT = JYDB.getTable("指数行情")
    PreClose = FT.getFactor("昨收盘(元-点)", new_name="pre_close")
    Factors.append(PreClose)
    Factors.append(FT.getFactor("今开盘(元-点)", new_name="open"))
    Factors.append(FT.getFactor("最高价(元-点)", new_name="high"))
    Factors.append(FT.getFactor("最低价(元-点)", new_name="low"))
    Close = FT.getFactor("收盘价(元-点)", new_name="close")
    Factors.append(Close)
    Factors.append(FT.getFactor("成交量", new_name="volume"))
    Factors.append(FT.getFactor("成交金额(元)", new_name="amount"))
    Factors.append(Factorize(Close / PreClose - 1, factor_name="chg"))
    Factors.append(FT.getFactor("流通市值", new_name="negotiable_market_cap"))
    
    # 生成指数 ID
    if isinstance(args["id_info_file"], str):
        IDs = sorted(pd.read_csv(args["id_info_file"], index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0])
    else:
        IDs = []
        for iInfoFile in args["id_info_file"]:
            IDs += pd.read_csv(iInfoFile, index_col=None, header=None, encoding="utf-8", engine="python").iloc[:, 0].tolist()
        IDs = sorted(set(IDs))
    
    UpdateArgs = {"因子表": "index_cn_quote",
                  "默认起始日": dt.datetime(2000, 1, 1),
                  "最长回溯期": 365,
                  "IDs": IDs}
    
    return (Factors, UpdateArgs)

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB(logger=Logger)
    JYDB.connect()
    
    #TDB = QS.FactorDB.SQLDB(config_file="SQLDBConfig_FactorTest.json", logger=Logger)
    TDB = QS.FactorDB.HDF5DB(logger=Logger)
    TDB.connect()
    
    Args = {"JYDB": JYDB, "id_info_file": [r"../conf/index/IndexIDs_cn.csv", r"../conf/index/IndexIDs_IndexMF.csv", r"../conf/index/IndexIDs_ETF.csv"]}
    Factors, UpdateArgs = defFactor(args=Args, debug=True)

    StartDT, EndDT = dt.datetime(2000, 1, 1), dt.datetime(2021, 6, 30)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date(), output_type="datetime")
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date(), output_type="datetime")
    
    IDs = UpdateArgs["IDs"]
    #IDs = ["CI005917", "CI005918", "CI005919", "CI005920", "CI005921"]
    #IDs = ["CI005910", "CI005909", "CI005912", "CI005019", "CI005018", "CI005905", "CI005015"]
    IDs = ["H30267","930609","930610","930889","930890","930891","930892","930893","930895","930897","930898","H11020","H11021","H11023","H11024","H11026","H11027","H11028","930950","931153"]
    
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
