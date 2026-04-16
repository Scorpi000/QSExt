# -*- coding: utf-8 -
"""A股行业分类"""
import os
import datetime as dt
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperatorized
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef


@FactorOperatorized(operator_type="Point", args={"Arity": 1, "DTMode": "多时点", "IDMode": "多ID", "DataType": "string"})
def mapValue(f, idt, iid, x, args):
    Data = x[0]
    Mapping = pd.Series(f.Args.ModelArgs["mapping"])
    TargetShape = Data.shape
    Data = Data.flatten(order="C")
    Rslt = np.full(shape=Data.shape, fill_value=None, dtype=Mapping.dtype)
    Mask = pd.notnull(Data)
    Rslt[Mask] = Mapping.reindex(index=Data[Mask]).values
    return Rslt.reshape(TargetShape)


def defFactor(fdi: FactorDefInput, dep_fd: Dict[str, FactorDef]) -> FactorDef:
    Factors = []
    
    JYDB = fdi.FDB["JYDB"]
    
    # # 申万行业, 2014 版
    # FT = JYDB.getTable("公司行业划分表", args={"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "24"}})
    # Factors.append(rename(FT.getFactor("一级行业名称"), factor_name="sw2014_level1"))
    # Factors.append(rename(FT.getFactor("一级行业代码"), factor_name="sw2014_code_level1"))
    # Factors.append(rename(FT.getFactor("二级行业名称"), factor_name="sw2014_level2"))
    # Factors.append(rename(FT.getFactor("二级行业代码"), factor_name="sw2014_code_level2"))
    # Factors.append(rename(FT.getFactor("三级行业名称"), factor_name="sw2014_level3"))
    # Factors.append(rename(FT.getFactor("三级行业代码"), factor_name="sw2014_code_level3"))
    
    # 申万行业, 2021 版
    FT = JYDB.getTable("公司行业划分表", args={"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "38"}})
    Factors.append(rename(FT.getFactor("一级行业名称"), factor_name="sw2021_level1"))
    Factors.append(rename(FT.getFactor("一级行业代码"), factor_name="sw2021_code_level1"))
    Factors.append(rename(FT.getFactor("二级行业名称"), factor_name="sw2021_level2"))
    Factors.append(rename(FT.getFactor("二级行业代码"), factor_name="sw2021_code_level2"))
    Factors.append(rename(FT.getFactor("三级行业名称"), factor_name="sw2021_level3"))
    Factors.append(rename(FT.getFactor("三级行业代码"), factor_name="sw2021_code_level3"))
    
    # # 中信行业
    # FT = JYDB.getTable("公司行业划分表", args={"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "3"}})
    # Factors.append(rename(FT.getFactor("一级行业名称"), factor_name="citic_level1"))
    # Factors.append(rename(FT.getFactor("一级行业代码"), factor_name="citic_code_level1"))
    # Factors.append(rename(FT.getFactor("二级行业名称"), factor_name="citic_level2"))
    # Factors.append(rename(FT.getFactor("二级行业代码"), factor_name="citic_code_level2"))
    # Factors.append(rename(FT.getFactor("三级行业名称"), factor_name="citic_level3"))
    # Factors.append(rename(FT.getFactor("三级行业代码"), factor_name="citic_code_level3"))
    
    # 中信行业, 2019 版
    FT = JYDB.getTable("公司行业划分表", args={"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "37"}})
    Factors.append(rename(FT.getFactor("一级行业名称"), factor_name="citic2019_level1"))
    Factors.append(rename(FT.getFactor("一级行业代码"), factor_name="citic2019_code_level1"))
    Factors.append(rename(FT.getFactor("二级行业名称"), factor_name="citic2019_level2"))
    Factors.append(rename(FT.getFactor("二级行业代码"), factor_name="citic2019_code_level2"))
    Factors.append(rename(FT.getFactor("三级行业名称"), factor_name="citic2019_level3"))
    Factors.append(rename(FT.getFactor("三级行业代码"), factor_name="citic2019_code_level3"))
    
    # 证监会行业, 2012 版
    FT = JYDB.getTable("公司行业划分表", args={"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "22"}})
    Factors.append(rename(FT.getFactor("一级行业名称"), factor_name="csrc2012_level1"))
    Factors.append(rename(FT.getFactor("一级行业代码"), factor_name="csrc2012_code_level1"))
    Factors.append(rename(FT.getFactor("二级行业名称"), factor_name="csrc2012_level2"))
    Factors.append(rename(FT.getFactor("二级行业代码"), factor_name="csrc2012_code_level2"))
    
    # # 中证指数行业, 2016 版
    # FT = JYDB.getTable("公司行业划分表", args={"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "28"}})
    # Factors.append(rename(FT.getFactor("一级行业名称"), factor_name="csi2016_level1"))
    # Factors.append(rename(FT.getFactor("一级行业代码"), factor_name="csi2016_code_level1"))
    # Factors.append(rename(FT.getFactor("二级行业名称"), factor_name="csi2016_level2"))
    # Factors.append(rename(FT.getFactor("二级行业代码"), factor_name="csi2016_code_level2"))
    # Factors.append(rename(FT.getFactor("三级行业名称"), factor_name="csi2016_level3"))
    # Factors.append(rename(FT.getFactor("三级行业代码"), factor_name="csi2016_code_level3"))
    # Factors.append(rename(FT.getFactor("四级行业名称"), factor_name="csi2016_level4"))
    # Factors.append(rename(FT.getFactor("四级行业代码"), factor_name="csi2016_code_level4"))
    
    # GICS 行业, 不更新, 最后更新时点: 2020-11-25
    FT = JYDB.getTable("公司行业划分表", args={"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "6"}})
    # Factors.append(rename(FT.getFactor("一级行业名称"), factor_name="gics_level1"))
    # Factors.append(rename(FT.getFactor("一级行业代码"), factor_name="gics_code_level1"))
    # Factors.append(rename(FT.getFactor("二级行业名称"), factor_name="gics_level2"))
    # Factors.append(rename(FT.getFactor("二级行业代码"), factor_name="gics_code_level2"))
    # Factors.append(rename(FT.getFactor("三级行业名称"), factor_name="gics_level3"))
    GICSLevel3Code = rename(FT.getFactor("三级行业代码"), factor_name="gics_code_level3")
    # Factors.append(rename(FT.getFactor("四级行业名称"), factor_name="gics_level4"))
    # Factors.append(rename(FT.getFactor("四级行业代码"), factor_name="gics_code_level4"))
    
    # # 聚源行业
    # FT = JYDB.getTable("公司行业划分表", args={"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "21"}})
    # Factors.append(rename(FT.getFactor("一级行业名称"), factor_name="jy_level1"))
    # Factors.append(rename(FT.getFactor("一级行业代码"), factor_name="jy_code_level1"))
    # Factors.append(rename(FT.getFactor("二级行业名称"), factor_name="jy_level2"))
    # Factors.append(rename(FT.getFactor("二级行业代码"), factor_name="jy_code_level2"))
    # Factors.append(rename(FT.getFactor("三级行业名称"), factor_name="jy_level3"))
    # Factors.append(rename(FT.getFactor("三级行业代码"), factor_name="jy_code_level3"))
    
    # 聚源行业, 2016 版, 类 GICS
    FT = JYDB.getTable("公司行业划分表", args={"OnlyStartFilled": False, "MultiMapping": False, "AdditionalCondition": {"行业划分标准": "30"}})
    Factors.append(rename(FT.getFactor("一级行业名称"), factor_name="jy2016_level1"))
    Factors.append(rename(FT.getFactor("一级行业代码"), factor_name="jy2016_code_level1"))
    Factors.append(rename(FT.getFactor("二级行业名称"), factor_name="jy2016_level2"))
    Factors.append(rename(FT.getFactor("二级行业代码"), factor_name="jy2016_code_level2"))
    Factors.append(rename(FT.getFactor("三级行业名称"), factor_name="jy2016_level3"))
    JY2016Level3Code = rename(FT.getFactor("三级行业代码"), factor_name="jy2016_code_level3")
    Factors.append(JY2016Level3Code)
    Factors.append(rename(FT.getFactor("四级行业名称"), factor_name="jy2016_level4"))
    Factors.append(rename(FT.getFactor("四级行业代码"), factor_name="jy2016_code_level4"))
    
    # Barra CNE5 风险模型行业
    JYIndustryMap = pd.read_csv(Path(os.path.abspath(__file__)).parent.parent / Path("./conf/barra_industry_jy.csv"), header=0, index_col=5).iloc[:, 0].astype("O")
    JYIndustryMap.index = JYIndustryMap.index.astype(str)
    BarraIndustry = mapValue(JY2016Level3Code, factor_args={"Name": "barra_industry", "ModelArgs": {"mapping": JYIndustryMap}})
    GICSIndustryMap = pd.read_csv(Path(os.path.abspath(__file__)).parent.parent / Path("./conf/barra_industry_gics.csv"), header=0, index_col=5).iloc[:, 0].astype("O")
    GICSIndustryMap.index = GICSIndustryMap.index.astype(str)
    GICSBarraIndustry = mapValue(GICSLevel3Code, factor_args={"ModelArgs": {"mapping": GICSIndustryMap}})
    BarraIndustry = fo.Where(dtype="string")(BarraIndustry, fo.NotNull()(BarraIndustry), GICSBarraIndustry, factor_args={"Name": "barra_industry"})
    Factors.append(BarraIndustry)
    
    return FactorDef(
        FDI=fdi,
        FactorList=Factors,
        TargetTable="stock_cn_industry",
        IDType="A股",
        Author="麦冬",
        Description="A股所属行业, 包括中信、申万、Barra、证监会等行业分类",
        DefScriptPath=__file__
    )
