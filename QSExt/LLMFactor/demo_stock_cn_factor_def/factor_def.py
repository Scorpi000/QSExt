# -*- coding: utf-8 -*-
from typing import List

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.BasicOperator import rename
import QuantStudio.Factor.FactorOperator as fo
from QSExt.DefModule.DefContent import DefInput


__FACTOR_META__ = {
    "TargetTable": "stock_cn_factor_llm",# 固定不变
    "IDType": "A股",# 固定不变
    "Author": "QSAgent",# 固定不变
    "Description": "A股滚动市盈率 (PE_TTM) 因子，PE_TTM = 总市值(元) / 归属于母公司股东的净利润(TTM)(元)",# 该脚本定义的因子的描述信息
    "DefScriptPath": __file__,# 固定不变
}

def defFactor(fdi: DefInput) -> List[Factor]:
    JYDB = fdi.FDB["JYDB"]

    # ---- 归母净利润(TTM) ----
    # 主板：公司衍生报表数据_新会计准则(新)，CalcType="最新" 取最新已公告财报的 TTM 值
    FT = JYDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "最新"})
    NP_TTM = FT.getFactor("归属母公司股东的净利润(TTM)")

    # 科创板：科创板衍生报表数据
    FT_STIB = JYDB.getTable("科创板衍生报表数据", args={"CalcType": "最新"})
    NP_TTM_STIB = FT_STIB.getFactor("归属母公司股东的净利润(TTM)")

    # 合并主板与科创板（主板优先，缺失时以科创板填充）
    where = fo.Where(dtype="double")
    notnull = fo.NotNull()
    NP_TTM = where(NP_TTM, notnull(NP_TTM), NP_TTM_STIB)

    # ---- 总市值 ----
    # 主板：股票行情表现，LookBack=0 不回溯填充缺失值
    FT = JYDB.getTable("股票行情表现", args={"LookBack": 0})
    TotalMV = FT.getFactor("总市值(万元)")

    # 科创板：科创板行情表现（单位：元）
    FT_STIB = JYDB.getTable("科创板行情表现", args={"LookBack": 0})
    TotalMV_STIB = FT_STIB.getFactor("总市值(元)")

    # 统一单位：万元（将科创板元→万元）
    TotalMV_STIB = TotalMV_STIB / 10000

    # 合并主板与科创板
    TotalMV = where(TotalMV, notnull(TotalMV), TotalMV_STIB)

    # ---- PE_TTM ----
    # PE_TTM = 总市值(元) / 归母净利润(TTM)(元)
    # TotalMV 单位为万元，×10000 转换为元
    pe_ttm = rename(TotalMV * 10000 / NP_TTM, factor_name="pe_ttm")

    return [pe_ttm]


# 测试代码
if __name__ == "__main__":
    import datetime as dt

    from QuantStudio.Factor.JYDB import JYDB

    SDB = JYDB().connect()

    # 构建测试时点和股票列表
    DTRuler = JYDB.getTradeDay(start_date=dt.datetime(2013, 1, 1), end_date=dt.datetime(2025, 4, 30))
    DTs = [dt.datetime(2025, 4, 24), dt.datetime(2025, 4, 25), dt.datetime(2025, 4, 28), dt.datetime(2025, 4, 29), dt.datetime(2025, 4, 30)]
    IDs = ["000001.SZ", "000003.SZ", "688579.SH", "874819.BJ"]
    SectionIDs = sorted(IDs + ["600519.SH"])
    print(f"时点标尺: {DTRuler[0].strftime('%Y-%m-%d')} ~ {DTRuler[-1].strftime('%Y-%m-%d')}")
    print(f"测试区间: {DTs[0].strftime('%Y-%m-%d')} ~ {DTs[-1].strftime('%Y-%m-%d')}")
    print(f"截面股票数量: {len(SectionIDs)}")
    print(f"测试股票数量: {len(IDs)}")

    fdi = DefInput(
        Debug=True,
        FDB={"JYDB": SDB},
        DTs=DTs,
        IDs=IDs,
        SectionIDs=SectionIDs,
        DTRuler=DTRuler
    )

    # 构建因子
    print("\n--- 因子构建 ---")
    factors = defFactor(fdi=fdi)
    for f in factors:
        print(f"\n--- 因子名称: {f.Name} ---")
        print(f"数据类型: {f.getMetaData(key='DataType')}")
        data = f.readData(ids=IDs, dts=DTs, section_ids=SectionIDs, dt_ruler=DTRuler)
        print(f"数据 shape (时间×股票): {data.shape}")
        print(data)
