# coding: utf-8
import numpy as np

import QuantStudio.api as QS
fd = QS.FactorDB.FactorTools# 内置算子
Factorize = QS.FactorDB.Factorize# 公式因子化函数
FactorOperation = QS.FactorDB.FactorOperation# 函数算子化装饰器

# 创建因子库
LDB = QS.FactorDB.HDF5DB().connect()# 本地因子库
JYDB = QS.FactorDB.JYDB().connect()# 聚源库
WDB = QS.FactorDB.WindDB2().connect()# Wind 库

# 基本因子 - 行情因子: 来自本地因子库
FT = LDB.getTable("stock_cn_day_bar_nafilled")
IfTrading = FT.getFactor("if_trading")
TotalCap = FT.getFactor("total_cap")
Turnover = FT.getFactor("turnover")

# 基本因子 - 财务因子: 来自 Wind 库
FT = WDB.getTable("中国A股资产负债表")
LongDebt = FT.getFactor("非流动负债合计", args={"计算方法": "最新", "报告期": "年报"})

# 基本因子 - 财务因子：来自聚源库
FT = JYDB.getTable("利润分配表_新会计准则")
EPS0 = FT.getFactor("基本每股收益", args={"计算方法": "最新", "报告期": "年报", "回溯年数": 0})
EPS1 = FT.getFactor("基本每股收益", args={"计算方法": "最新", "报告期": "年报", "回溯年数": 1})
EPS2 = FT.getFactor("基本每股收益", args={"计算方法": "最新", "报告期": "年报", "回溯年数": 2})
EPS3 = FT.getFactor("基本每股收益", args={"计算方法": "最新", "报告期": "年报", "回溯年数": 3})
EPS4 = FT.getFactor("基本每股收益", args={"计算方法": "最新", "报告期": "年报", "回溯年数": 4})

# 衍生因子 - MLEV
MLEV = Factorize((LongDebt + TotalCap) / TotalCap, factor_name="MLEV")

# 衍生因子 - LNCAP
LNCAP = fd.log(TotalCap, factor_name="LNCAP")

# 衍生因子 - EGRO
EGRO = fd.regress_change_rate(EPS4, EPS3, EPS2, EPS1, EPS0, factor_name="EGRO")

# 衍生因子 - STOM
@FactorOperation(operation_type="TimeOperation", sys_args={
    "参数": {"非空率": 0.8},
    "回溯期数": [21-1, 21-1],
    "运算ID": "多ID",
    "运算时点": "单时点"
})
def calcSTOM(f, idt, iid, x, args):
    Turnover, IfTrading = x
    Rslt = np.log(np.nansum(Turnover, axis=0))
    Rslt[np.sum(IfTrading == 1, axis=0) / Turnover.shape[0] < args['非空率']] = np.nan
    return Rslt
STOM = calcSTOM("STOM", [Turnover, IfTrading])

# 需要输出数据的因子
Factors = [MLEV, EGRO, STOM]