# -*- coding: utf-8 -*-
"""公募基金股票仓位测算"""
import datetime as dt

import numpy as np
import pandas as pd
import cvxpy as cvx

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools
Factorize = QS.FactorDB.Factorize

POSITION_LIMIT = {
    "标准股票型": (0.8, 0.95),
    "偏股型": (0.6, 0.95),
    "灵活配置型": (0, 0.95),
}

P_LAMBDA = {
    "标准股票型": 2.5e-6,
    "偏股型": 1.5e-6,
    "灵活配置型": 4e-6,
}

def calc_stock_position_lasso(mf_return, index_return, has_constant=False, p_lambda=1e-7, min_weight=1e-4, cvx_kwargs={}):
    X, Y = index_return.values, mf_return
    Mask = (np.all(pd.notnull(X), axis=1) & pd.notnull(Y))
    if has_constant:
        X, Y = np.c_[np.ones((np.sum(Mask),)), X[Mask, :]], Y[Mask]
    else:
        X, Y = X[Mask, :], Y[Mask]
    
    nSample, nVar = X.shape
    beta = cvx.Variable(nVar)
    if has_constant:
        Obj = cvx.Minimize(1 / (2*nSample) * cvx.sum((Y - X * beta) ** 2) + p_lambda * cvx.sum(cvx.abs(beta[1:])))
        Prob = cvx.Problem(Obj, [beta[1:]>=0, beta[1:]<=1])
    else:
        Obj = cvx.Minimize(1 / (2*nSample) * cvx.sum((Y - X * beta) ** 2) + p_lambda * cvx.sum(cvx.abs(beta)))
        Prob = cvx.Problem(Obj, [beta>=0, beta<=1])        
    try:
        Prob.solve(**cvx_kwargs)
    except:
        Status = "fail"
    else:
        Status = Prob.status
    if Status not in (cvx.INFEASIBLE, cvx.UNBOUNDED, cvx.INFEASIBLE_INACCURATE, "fail"):
        if has_constant:
            w = pd.Series(beta.value[1:], index=index_return.columns)
        else:
            w = pd.Series(beta.value, index=index_return.columns)
        w[w<min_weight] = 0
        return (w, Status)
    else:
        return (None, Status)

def get_nv(f, idt, iid, x, args):
    nv, type = x
    mask = np.isin(type, ["标准股票型", "偏股型", "灵活配置型"])
    return nv[mask]

def get_position(f, idt, iid, x, args):
    mf_return, industry_return, mf_type = x
    industry_index_ids = args["industry_index_ids"]
    industry_return_df = pd.DataFrame(industry_return, columns=industry_index_ids)
    res_list = np.full(mf_return.shape[1], None, dtype="O")
    for i in range(mf_return.shape[1]):
        if mf_type[60, i] not in P_LAMBDA:
            res = (pd.Series([np.nan] * 29, index=industry_index_ids), "optimal")
        else:
            try:
                res = calc_stock_position_lasso(mf_return[:, i], industry_return_df, p_lambda=P_LAMBDA[mf_type[60, i]])
            except Exception as e:
                f.Logger.warning(e)
                f.Logger.warning(f"code: {iid[i]}")
                f.Logger.warning(f"dt: {idt[-1]}")
                res = (pd.Series([np.nan] * 29, index=industry_index_ids), "optimal")
            else:
                if res[1] in (cvx.INFEASIBLE, cvx.UNBOUNDED, cvx.INFEASIBLE_INACCURATE, "fail"):
                    res = (pd.Series([np.nan] * 29, index=industry_index_ids), "optimal")
        all = (np.nan if res[0].notna().sum()==0 else res[0].sum())
        res_list[i] = res[0].values.tolist() + [all]
    return res_list

def get_code(f, idt, iid, x, args):
    mf_type = x[0]
    industry_index_ids = args["industry_index_ids"] + ["ALL"]
    res = np.full(x[0].shape, None, dtype="O")
    res[:] = [[industry_index_ids] * mf_type.shape[1]] * mf_type.shape[0]
    res[~np.isin(mf_type, ("标准股票型", "偏股型", "灵活配置型"))] = np.nan
    return res

def defFactor(args={}, debug=False):
    Factors = []
    
    JYDB = args["JYDB"]
    LDB = args["LDB"]
    industry_index_ids = args["industry_index_ids"]
    
    FT = LDB.getTable("mf_cn_type")
    MFType = FT.getFactor("jy_type_second")
    
    FT = LDB.getTable("mf_cn_net_value_nafilled")
    MFNV = FT.getFactor("unit_net_value_adj")
    MFReturn = MFNV / fd.lag(MFNV, 1, 1) - 1
    
    FT = JYDB.getTable("指数行情")
    IndustryIndexPrice = FT.getFactor("收盘价(元-点)")
    IndustryIndexReturn = IndustryIndexPrice / fd.lag(IndustryIndexPrice, 1, 1) - 1
    
    industry_code = QS.FactorDB.PointOperation(
        "industry_code",
        [MFType],
        sys_args={
            "算子": get_code,
            "参数": {"industry_index_ids": industry_index_ids},
            "运算时点": "多时点",
            "运算ID": "多ID",
            "数据类型": "object"
        }
    )
    Factors.append(industry_code)
    
    position = QS.FactorDB.PanelOperation(
        "position",
        [MFReturn, IndustryIndexReturn, MFType],
        sys_args={
            "算子": get_position,
            "参数": {"industry_index_ids": industry_index_ids},
            "回溯期数": [60] * 3,
            "描述子截面": [None, industry_index_ids, None],
            "运算时点": "单时点",
            "输出形式": "全截面",
            "数据类型": "object"
        }
    )
    Factors.append(position)
    
    UpdateArgs = {
        "因子表": "mf_cn_position_stock",
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
    
    Args = {"JYDB": JYDB, "LDB": TDB, "industry_index_ids": sorted(pd.read_csv("../conf/citic_industry.csv", index_col=0, header=0, encoding="utf-8", encoding="python")["index_code"])}
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