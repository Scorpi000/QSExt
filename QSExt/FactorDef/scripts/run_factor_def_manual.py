# coding=utf-8
"""
手动运行因子定义脚本 —— 不依赖 settings 配置，手动构建运行环境。

适用场景:
    - 快速测试单个因子定义文件
    - 调试因子计算逻辑
    - 验证因子数据是否正确
"""
import datetime as dt

from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Factor.Factor import FactorContext, FactorLocalContext
from QuantStudio.Factor.FactorStorer import FactorStorer
from QuantStudio.Factor.BaoStockDB import BaoStockDB
from QuantStudio.Factor.HDF5DB import HDF5DB
from QSExt.FactorDef.FactorDefContent import FactorDefInput, build_dep_fd
from QSExt.FactorDef import stock_cn_factor_example2 as factor_mod


# 相关配置
if __name__ == "__main__":
    FactorMeta = getattr(factor_mod, "__FACTOR_META__", {})

    # 连接数据库
    BSDB = BaoStockDB().connect()

    # 构建股票列表
    # SectionIDs = BSDB.getStockID(is_current=False)
    SectionIDs = ["000001.SZ", "000002.SZ", "000003.SZ", "600519.SH"]
    IDs = SectionIDs
    print(f"SectionIDs: {len(SectionIDs)} 个")
    print(f"IDs: {len(IDs)} 个")

    # 构建时点数据
    # 时间范围
    MaxStartDT = dt.datetime(2020, 1, 1)   # DTRuler 起始日
    StartDT = dt.datetime(2024, 1, 15)     # 计算起始日
    EndDT = dt.datetime(2024, 1, 20)       # 计算截止日
    DTRuler = BSDB.getTradeDay(start_date=MaxStartDT, end_date=EndDT)
    DTs = BSDB.getTradeDay(start_date=StartDT, end_date=EndDT)
    if not DTs:
        print("计算时点序列为空")
        exit(0)
    else: print(f"DTs: {len(DTs)} 个, {StartDT} ~ {EndDT}")


# 执行定义
if __name__ == "__main__":
    # 构建 FactorDefInput
    FDI = FactorDefInput(
        FDB={"BSDB": BSDB},
        DTs=DTs,
        IDs=IDs,
        SectionIDs=SectionIDs,
        DTRuler=DTRuler,
    )

    # 递归解析依赖并执行因子定义, 收集所有因子
    # build_dep_fd 会自动解析 __FACTOR_META__["FactorDeps"] 中声明的依赖
    Modules = [(factor_mod, {}, {})]
    FactorDefDict, FactorDefs = build_dep_fd(Modules, FDI)
    FactorList = sum([iFactorDef.FactorList for iFactorDef, _ in FactorDefs], [])
    if not FactorList:
        print("没有因子需要执行")
        exit(0)
    print(f"因子: {[f.Name for f in FactorList]}")

    # 构建 FactorStorer
    TDB = HDF5DB(args={"MainDir": r"D:\Data\HDF5DB_Test"}).connect()
    Storer = FactorStorer(deps=FactorList, args={"TargetFDB": TDB, "TargetTable": FactorMeta["TargetTable"]})

    # 执行引擎运行计算图
    with FactorContext(Mode="DEBUG", PIDList=["0"], DTRuler=DTRuler, SectionIDs=[]) as Context:
        with Engine() as CalcEngine:
            CalcEngine.run([Storer], Context, fwd_data_list=[FactorLocalContext(DTs=DTs, IDs=IDs, SectionIDs=SectionIDs)])

    print("执行完成")
    BSDB.disconnect()


# 读取数据
if __name__ == "__main__":
    LDB = HDF5DB(args={"MainDir": r"D:\Data\HDF5DB_Test"}).connect()
    FT = LDB.getTable(FactorMeta["TargetTable"])
    print(FT.getFactorMetaData(key="DataType"))
    Data = FT.readData(factor_names=["close"], ids=IDs, dts=DTs)
    print(Data.iloc[0])