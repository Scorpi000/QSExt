# -*- coding: utf-8 -*-
"""公募基金基本信息"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

def strCode(f, idt, iid, x, args):
    Mask = pd.isnull(x[0])
    d = x[0].astype(np.int).astype(np.str).astype("O")
    d[Mask] = None
    return d

# args 应该包含的参数
# JYDB: 聚源因子库对象
def defFactor(args={}, debug=False):
    Factors = []

    JYDB = args["JYDB"]

    FT = JYDB.getTable("公募基金证券主表")
    # 特征属性
    Factors.append(FT.getFactor("中文名称", new_name="name"))
    Factors.append(FT.getFactor("证券简称", new_name="abbr"))
    
    # 相关代码
    FT = JYDB.getTable("公募基金概况")
    Factors.append(FT.getFactor("基金主代码_R", new_name="main_code"))
    Factors.append(FT.getFactor("前端申购代码", new_name="front_code"))
    Factors.append(FT.getFactor("后端申购代码", new_name="back_code"))
    Factors.append(FT.getFactor("基金交易代码(交易所交易代码)", new_name="security_code"))
    
    # 相关日期
    EstablishDate = FT.getFactor("设立日期")
    Factors.append(fd.strftime(EstablishDate, "%Y-%m-%d", factor_name="establish_date"))
    Factors.append(fd.strftime(FT.getFactor("上市日期"), "%Y-%m-%d", factor_name="listed_date"))
    Factors.append(fd.strftime(FT.getFactor("存续期起始日"), "%Y-%m-%d", factor_name="start_date"))
    ExpireDate = FT.getFactor("存续期截止日")
    Factors.append(fd.strftime(ExpireDate, "%Y-%m-%d", factor_name="expire_date"))
    Factors.append(fd.strftime(FT.getFactor("清算起始日"), "%Y-%m-%d", factor_name="clear_start_date"))
    Factors.append(fd.strftime(FT.getFactor("清算截止日"), "%Y-%m-%d", factor_name="clear_end_date"))
    
    # 主体信息
    Factors.append(FT.getFactor("基金经理", new_name="fund_manager"))
    Factors.append(QS.FactorDB.PointOperation("fund_advisor_code", [FT.getFactor("基金管理人")], sys_args={"算子": strCode, "运算时点": "多时点", "运算ID": "多ID", "数据类型": "string"}))
    Factors.append(FT.getFactor("基金管理人_R", new_name="fund_advisor"))
    Factors.append(QS.FactorDB.PointOperation("fund_trustee_code", [FT.getFactor("基金托管人")], sys_args={"算子": strCode, "运算时点": "多时点", "运算ID": "多ID", "数据类型": "string"}))
    Factors.append(FT.getFactor("基金托管人_R", new_name="fund_trustee"))
    
    # 投资信息
    Factors.append(FT.getFactor("业绩比较基准", new_name="perf_benchmark"))
    
    # 基金分类
    Factors.append(FT.getFactor("基金运作方式_R", new_name="operation_type"))# ETF, LOF, 开放式等
    Factors.append(FT.getFactor("基金投资类型_R", new_name="investment_type"))# 成长性, 平衡性等
    Factors.append(FT.getFactor("基金投资风格_R", new_name="investment_style"))# 股票型, 特殊策略型等
    Factors.append(FT.getFactor("基金类别", new_name="fund_type"))# 股票型, 混合型, 债券型, 保本型, 货币型, 其他型
    IfFoF = FT.getFactor("是否FOF")
    IfFoF = fd.where(IfFoF, mask=(IfFoF!=2), other=0, factor_name="if_fof")
    Factors.append(IfFoF)
    
    UpdateArgs = {
        "因子表": "mf_cn_info",
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