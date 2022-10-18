# -*- coding: utf-8 -
"""A股行业分类"""
import os
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
Factorize = QS.FactorDB.Factorize
fd = QS.FactorDB.FactorTools

UpdateArgs = {
    "因子表": "stock_cn_industry",
    "默认起始日": dt.datetime(2002, 1, 1),
    "最长回溯期": 365,
    "IDs": "股票"
}

def adjustCode(f, idt, iid, x, args):
    Rslt = pd.DataFrame(x[0])
    Mask = pd.notnull(Rslt)
    Rslt = Rslt.where(Mask, "") + "0000"
    return Rslt.where(Mask, None).values

# args:
# JYDB: 聚源因子库对象
def defFactor(args={}):
    Factors = []
    
    JYDB = args["JYDB"]
    
    FT = JYDB.getTable("公司行业划分表", args={"只填起始日": False, "多重映射": False})
    
    # 申万行业, 2014 版
    Factors.append(FT.getFactor("一级行业名称", args={"行业划分标准": "24"}, new_name="sw2014_level1"))
    Factors.append(FT.getFactor("一级行业代码", args={"行业划分标准": "24"}, new_name="sw2014_code_level1"))
    Factors.append(FT.getFactor("二级行业名称", args={"行业划分标准": "24"}, new_name="sw2014_level2"))
    Factors.append(FT.getFactor("二级行业代码", args={"行业划分标准": "24"}, new_name="sw2014_code_level2"))
    Factors.append(FT.getFactor("三级行业名称", args={"行业划分标准": "24"}, new_name="sw2014_level3"))
    Factors.append(FT.getFactor("三级行业代码", args={"行业划分标准": "24"}, new_name="sw2014_code_level3"))
    
    # 申万行业, 2021 版
    Factors.append(FT.getFactor("一级行业名称", args={"行业划分标准": "38"}, new_name="sw2021_level1"))
    Factors.append(FT.getFactor("一级行业代码", args={"行业划分标准": "38"}, new_name="sw2021_code_level1"))
    Factors.append(FT.getFactor("二级行业名称", args={"行业划分标准": "38"}, new_name="sw2021_level2"))
    Factors.append(FT.getFactor("二级行业代码", args={"行业划分标准": "38"}, new_name="sw2021_code_level2"))
    Factors.append(FT.getFactor("三级行业名称", args={"行业划分标准": "38"}, new_name="sw2021_level3"))
    Factors.append(FT.getFactor("三级行业代码", args={"行业划分标准": "38"}, new_name="sw2021_code_level3"))
    
    # 中信行业
    Factors.append(FT.getFactor("一级行业名称", args={"行业划分标准": "3"}, new_name="citic_level1"))
    Factors.append(FT.getFactor("一级行业代码", args={"行业划分标准": "3"}, new_name="citic_code_level1"))
    Factors.append(FT.getFactor("二级行业名称", args={"行业划分标准": "3"}, new_name="citic_level2"))
    Factors.append(FT.getFactor("二级行业代码", args={"行业划分标准": "3"}, new_name="citic_code_level2"))
    Factors.append(FT.getFactor("三级行业名称", args={"行业划分标准": "3"}, new_name="citic_level3"))
    Factors.append(FT.getFactor("三级行业代码", args={"行业划分标准": "3"}, new_name="citic_code_level3"))
    #ZXCode = FT.getFactor("一级行业代码", args={"行业划分标准": "3"})
    #ZXCode = QS.FactorDB.PointOperation("citic_code", [ZXCode], sys_args={"算子": adjustCode, "运算时点": "多时点", "运算ID": "多ID"})
    #Factors.append(ZXCode)
    #Factors.append(FT.getFactor("一级行业名称", args={"行业划分标准": "3"}, new_name="citic"))
    
    # 中信行业, 2019 版
    Factors.append(FT.getFactor("一级行业名称", args={"行业划分标准": "37"}, new_name="citic2019_level1"))
    Factors.append(FT.getFactor("一级行业代码", args={"行业划分标准": "37"}, new_name="citic2019_code_level1"))
    Factors.append(FT.getFactor("二级行业名称", args={"行业划分标准": "37"}, new_name="citic2019_level2"))
    Factors.append(FT.getFactor("二级行业代码", args={"行业划分标准": "37"}, new_name="citic2019_code_level2"))
    Factors.append(FT.getFactor("三级行业名称", args={"行业划分标准": "37"}, new_name="citic2019_level3"))
    Factors.append(FT.getFactor("三级行业代码", args={"行业划分标准": "37"}, new_name="citic2019_code_level3"))
    
    # 证监会行业, 2012 版
    Factors.append(FT.getFactor("一级行业名称", args={"行业划分标准": "22"}, new_name="csrc2012_level1"))
    Factors.append(FT.getFactor("一级行业代码", args={"行业划分标准": "22"}, new_name="csrc2012_code_level1"))
    Factors.append(FT.getFactor("二级行业名称", args={"行业划分标准": "22"}, new_name="csrc2012_level2"))
    Factors.append(FT.getFactor("二级行业代码", args={"行业划分标准": "22"}, new_name="csrc2012_code_level2"))
    
    # 中证指数行业, 2016 版
    Factors.append(FT.getFactor("一级行业名称", args={"行业划分标准": "28"}, new_name="csi2016_level1"))
    Factors.append(FT.getFactor("一级行业代码", args={"行业划分标准": "28"}, new_name="csi2016_code_level1"))
    Factors.append(FT.getFactor("二级行业名称", args={"行业划分标准": "28"}, new_name="csi2016_level2"))
    Factors.append(FT.getFactor("二级行业代码", args={"行业划分标准": "28"}, new_name="csi2016_code_level2"))
    Factors.append(FT.getFactor("三级行业名称", args={"行业划分标准": "28"}, new_name="csi2016_level3"))
    Factors.append(FT.getFactor("三级行业代码", args={"行业划分标准": "28"}, new_name="csi2016_code_level3"))
    Factors.append(FT.getFactor("四级行业名称", args={"行业划分标准": "28"}, new_name="csi2016_level4"))
    Factors.append(FT.getFactor("四级行业代码", args={"行业划分标准": "28"}, new_name="csi2016_code_level4"))
    
    # GICS 行业, 不更新, 最后更新时点: 2020-11-25
    Factors.append(FT.getFactor("一级行业名称", args={"行业划分标准": "6"}, new_name="gics_level1"))
    Factors.append(FT.getFactor("一级行业代码", args={"行业划分标准": "6"}, new_name="gics_code_level1"))
    Factors.append(FT.getFactor("二级行业名称", args={"行业划分标准": "6"}, new_name="gics_level2"))
    Factors.append(FT.getFactor("二级行业代码", args={"行业划分标准": "6"}, new_name="gics_code_level2"))
    Factors.append(FT.getFactor("三级行业名称", args={"行业划分标准": "6"}, new_name="gics_level3"))
    Factors.append(FT.getFactor("三级行业代码", args={"行业划分标准": "6"}, new_name="gics_code_level3"))
    Factors.append(FT.getFactor("四级行业名称", args={"行业划分标准": "6"}, new_name="gics_level4"))
    Factors.append(FT.getFactor("四级行业代码", args={"行业划分标准": "6"}, new_name="gics_code_level4"))
    
    # 聚源行业
    Factors.append(FT.getFactor("一级行业名称", args={"行业划分标准": "21"}, new_name="jy_level1"))
    Factors.append(FT.getFactor("一级行业代码", args={"行业划分标准": "21"}, new_name="jy_code_level1"))
    Factors.append(FT.getFactor("二级行业名称", args={"行业划分标准": "21"}, new_name="jy_level2"))
    Factors.append(FT.getFactor("二级行业代码", args={"行业划分标准": "21"}, new_name="jy_code_level2"))
    Factors.append(FT.getFactor("三级行业名称", args={"行业划分标准": "21"}, new_name="jy_level3"))
    Factors.append(FT.getFactor("三级行业代码", args={"行业划分标准": "21"}, new_name="jy_code_level3"))
    
    # 聚源行业, 2016 版, 类 GICS
    Factors.append(FT.getFactor("一级行业名称", args={"行业划分标准": "30"}, new_name="jy2016_level1"))
    Factors.append(FT.getFactor("一级行业代码", args={"行业划分标准": "30"}, new_name="jy2016_code_level1"))
    Factors.append(FT.getFactor("二级行业名称", args={"行业划分标准": "30"}, new_name="jy2016_level2"))
    Factors.append(FT.getFactor("二级行业代码", args={"行业划分标准": "30"}, new_name="jy2016_code_level2"))
    Factors.append(FT.getFactor("三级行业名称", args={"行业划分标准": "30"}, new_name="jy2016_level3"))
    JY2016Level3Code = FT.getFactor("三级行业代码", args={"行业划分标准": "30"}, new_name="jy2016_code_level3")
    Factors.append(JY2016Level3Code)
    Factors.append(FT.getFactor("四级行业名称", args={"行业划分标准": "30"}, new_name="jy2016_level4"))
    Factors.append(FT.getFactor("四级行业代码", args={"行业划分标准": "30"}, new_name="jy2016_code_level4"))
    
    # Barra CNE5 风险模型行业
    Path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../conf/stock/barra_industry_jy.csv")
    JYIndustryMap = pd.read_csv(Path, header=0, index_col=5).iloc[:, 0]
    JYIndustryMap.index = JYIndustryMap.index.astype(str)
    JYBarraIndustry = fd.map_value(JY2016Level3Code, JYIndustryMap, data_type="string")
    Path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../conf/stock/barra_industry_gics.csv")
    GICSIndustryMap = pd.read_csv(Path, header=0, index_col=5).iloc[:, 0]
    GICSIndustryMap.index = GICSIndustryMap.index.astype(str)
    GICSBarraIndustry = fd.map_value(JY2016Level3Code, GICSIndustryMap, data_type="string")
    BarrayIndustry = fd.where(JYBarraIndustry, fd.notnull(JYBarraIndustry), GICSBarraIndustry, data_type="string", factor_name="barra_industry")
    Factors.append(BarrayIndustry)
    
    return Factors

if __name__=="__main__":
    import logging
    Logger = logging.getLogger()
    
    JYDB = QS.FactorDB.JYDB()
    JYDB.connect()
    
    TDB = QS.FactorDB.HDF5DB()
    TDB.connect()
    
    StartDT, EndDT = dt.datetime(2022, 10, 1), dt.datetime(2022, 10, 15)
    DTs = JYDB.getTradeDay(start_date=StartDT.date(), end_date=EndDT.date())
    DTRuler = JYDB.getTradeDay(start_date=StartDT.date() - dt.timedelta(365), end_date=EndDT.date())
    
    IDs = JYDB.getStockID()
    
    Args = {"JYDB": JYDB}
    Factors = defFactor(args=Args)
    
    CFT = QS.FactorDB.CustomFT(UpdateArgs["因子表"])
    CFT.addFactors(factor_list=Factors)
    CFT.setDateTime(DTs)
    CFT.setID(IDs)
    
    TargetTable = CFT.Name
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs,
        factor_db=TDB, table_name=TargetTable,
        if_exists="update", subprocess_num=20)
    
    TDB.disconnect()
    JYDB.disconnect()