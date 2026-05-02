# -*- coding: utf-8 -*-
"""公募基金规模因子"""
import datetime as dt

import numpy as np
import pandas as pd

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

# 调整基金份额持仓比例
def adjustRatio(f, idt, iid, x, args):
    InstitutionRatio = x[0]
    IndividualRatio = x[1]
    InstitutionRatio[InstitutionRatio>=100] = 0# 机构持有比例超过 100 的设为 0
    IndividualRatio[IndividualRatio>=100] = 0# 个人持有比例超过 100 的设为 0
    TotalRatio = np.nansum([InstitutionRatio, IndividualRatio], axis=0)
    # 机构持有比例多除 100 的错误调整
    Mask = ((TotalRatio<100) & (np.nansum([InstitutionRatio * 100, IndividualRatio], axis=0)==100))
    InstitutionRatio[Mask] = (InstitutionRatio * 100)[Mask]
    # 个人持有比例多除 100 的错误调整
    Mask = ((TotalRatio<100) & (np.nansum([InstitutionRatio, IndividualRatio * 100], axis=0)==100))
    IndividualRatio[Mask] = (IndividualRatio * 100)[Mask]
    # 机构持有比例多乘 100 的错误调整
    Mask = ((TotalRatio>100) & (np.nansum([InstitutionRatio / 100, IndividualRatio], axis=0)==100))
    InstitutionRatio[Mask] = (InstitutionRatio / 100)[Mask]
    # 个人持有比例多乘 100 的错误调整
    Mask = ((TotalRatio>100) & (np.nansum([InstitutionRatio, IndividualRatio / 100], axis=0)==100))
    IndividualRatio[Mask] = (IndividualRatio / 100)[Mask]
    # 将总权重超过 1 的作归一化处理
    InstitutionRatio = InstitutionRatio / 100
    IndividualRatio = IndividualRatio / 100
    TotalRatio = np.nansum([InstitutionRatio, IndividualRatio], axis=0)
    Mask = (TotalRatio>1)
    InstitutionRatio[Mask] = (InstitutionRatio / TotalRatio)[Mask]
    IndividualRatio[Mask] = (IndividualRatio / TotalRatio)[Mask]
    Rslt = np.zeros(InstitutionRatio.shape, dtype=[("0", float), ("1", float)])
    Rslt["0"] = InstitutionRatio
    Rslt["1"] = IndividualRatio
    return Rslt
    

def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    
    BalanceSheetFT = JYDB.getTable("公募基金资产负债表_新会计准则", args={"报告期": "所有", "计算方法": "最新"})
        
    # ####################### 资产净值 #######################
    FT = JYDB.getTable("公募基金净值", args={"回溯天数": np.inf, "公告时点字段": None, "忽略时间": True, "筛选条件": "{Table}.NV IS NOT NULL"})
    Factors.append(FT.getFactor("净资产值(元)", new_name="net_asset_value"))
        
    # ####################### 资产总值 #######################
    TAV = BalanceSheetFT.getFactor("资产总计", new_name="total_asset_value")
    Factors.append(TAV)
        
    # ####################### 份额变化率 #######################
    ShareChg_P0 = BalanceSheetFT.getFactor("基金份额总额(份)", args={"回溯期数": 0})
    ShareChg_P1 = BalanceSheetFT.getFactor("基金份额总额(份)", args={"回溯期数": 2})# 只有中报和年报中有数据
    Factors.append(Factorize(ShareChg_P0 / ShareChg_P1 - 1, factor_name="share_chg_rate"))
    
    # ####################### 现金流量 #######################
    FT = JYDB.getTable("公募基金所有者权益(基金净值)变动表", args={"报告期": "所有", "计算方法": "TTM", "所属类别": "9"})# 只有中报和年报中有数据
    Factors.append(FT.getFactor("基金份额交易产生的净值变动数", new_name="cash_flow_ttm"))
    
    # ####################### 机构(个人)投资者比例 #######################
    FT = JYDB.getTable("公募基金持有人结构信息", args={"回溯天数": np.inf, "忽略时间": True, "筛选条件": "({Table}.InstitutionHoldRatio>=0 OR {Table}.IndividualHoldRatio>=0)"})
    InstitutionRatio = FT.getFactor("机构持有比例(%)")
    IndividualRatio = FT.getFactor("个人持有比例(%)")
    AdjustedRatio = QS.FactorDB.PointOperation(
        "AdjustedRatio",
        [InstitutionRatio, IndividualRatio],
        sys_args={
            "算子": adjustRatio,
            "运算时点": "多时点",
            "运算ID": "多ID",
            "数据类型": "object"
        }
    )
    Factors.append(fd.fetch(AdjustedRatio, pos=0, factor_name="institution_ratio"))
    Factors.append(fd.fetch(AdjustedRatio, pos=1, factor_name="individual_ratio"))
    
    UpdateArgs = {
        "因子表": "mf_cn_factor_size",
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