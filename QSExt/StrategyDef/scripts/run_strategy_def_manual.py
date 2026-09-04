# coding=utf-8
"""
手动运行策略定义脚本 —— 不依赖 settings 配置，手动构建运行环境。

适用场景:
    - 快速测试单个策略定义文件
    - 调试策略计算逻辑
    - 验证策略信号是否正确
"""
import datetime as dt

from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Factor.Factor import FactorContext, FactorLocalContext
from QuantStudio.Factor.FactorStorer import FactorStorer
from QuantStudio.Factor.BaoStockDB import BaoStockDB
from QuantStudio.Factor.HDF5DB import HDF5DB
from QuantStudio.BackTest.BackTestModel import DTLocalContext
from QuantStudio.BackTest.Strategy.Strategy import AccountStats
from QuantStudio.BackTest.BTResultDB import HDF5BTResultDB
from QuantStudio.BackTest.BTStorer import BTStorer
from QSExt.StrategyDef.StrategyDefContent import StrategyDefInput, build_dep_sd
from QSExt.StrategyDef import stock_cn_strategy_example as strategy_mod


# 相关配置
if __name__ == "__main__":
    StrategyMeta = getattr(strategy_mod, "__STRATEGY_META__", {})

    # 连接数据库
    BSDB = BaoStockDB().connect()

    # 构建股票列表
    # SectionIDs = BSDB.getStockID(is_current=False)
    SectionIDs = ["000001.SZ", "000002.SZ", "000003.SZ", "600519.SH"]
    IDs = SectionIDs
    print(f"SectionIDs: {len(SectionIDs)} 个")
    print(f"IDs: {len(IDs)} 个")

    # 构建时点数据
    MaxStartDT = dt.datetime(2020, 1, 1)   # DTRuler 起始日
    StartDT = dt.datetime(2024, 6, 5)     # 计算起始日
    EndDT = dt.datetime(2024, 12, 31)       # 计算截止日
    DTRuler = BSDB.getTradeDay(start_date=MaxStartDT, end_date=EndDT)
    DTs = BSDB.getTradeDay(start_date=StartDT, end_date=EndDT)
    if not DTs:
        print("计算时点序列为空")
        exit(0)
    else: print(f"DTs: {len(DTs)} 个, {StartDT} ~ {EndDT}")


# 执行定义
if __name__ == "__main__":
    # 构建 StrategyDefInput
    SDI = StrategyDefInput(
        FDB={"BSDB": BSDB},
        DTs=DTs,
        IDs=IDs,
        SectionIDs=SectionIDs,
        DTRuler=DTRuler,
    )

    # 递归解析依赖并执行策略定义, 收集所有策略
    # build_dep_sd 会自动解析 __STRATEGY_META__["FactorDeps"] 和 ["StrategyDeps"]
    Modules = [(strategy_mod, {}, {})]
    StrategyDefDict, StrategyDefs = build_dep_sd(Modules, SDI)
    StrategyList = sum([iStrategyDef.StrategyList for iStrategyDef, _ in StrategyDefs if iStrategyDef], [])
    if not StrategyList:
        print("没有策略需要执行")
        exit(0)
    print(f"策略: {[Strategy.Name for Strategy in StrategyList]}")

    # 构建信号存储（FactorStorer）和回测结果存储（BTStorer）
    # 策略信号 → FactorStorer
    TDB = HDF5DB(args={"MainDir": r"D:\Data\HDF5DB_Test"}).connect()
    SignalStorer = FactorStorer(deps=StrategyList, args={"TargetFDB": TDB, "TargetTable": StrategyMeta["TargetTable"]})

    # 回测结果 → BTStorer
    BTResultDB = HDF5BTResultDB(args={"MainDir": r"D:\Data\HDF5BTResult"})
    BTResultStorer = BTStorer(
        deps=[AccountStats(account=Strategy, args={"AccountSection": SDI.SectionIDs, "Name": Strategy.Name}) for Strategy in StrategyList],
        args={"TargetDB": BTResultDB, "GroupName": StrategyMeta["TargetTable"], "Metadata": {k: StrategyMeta[k] for k in ["Author", "Description"]}},
    )

    # 执行引擎运行计算图
    NodeList = [SignalStorer, BTResultStorer]
    FwdDataList = [
        FactorLocalContext(DTs=DTs, IDs=IDs, SectionIDs=SectionIDs),
        DTLocalContext(DTs=DTs)
    ]
    with FactorContext(Mode="DEBUG", PIDList=["0"], DTRuler=DTRuler, SectionIDs=[]) as Context:
        with Engine() as CalcEngine:
            CalcEngine.run(NodeList, Context, fwd_data_list=FwdDataList)

    print("执行完成")
    BSDB.disconnect()


# 读取数据
if __name__ == "__main__":
    LDB = HDF5DB(args={"MainDir": r"D:\Data\HDF5DB_Test"}).connect()
    FT = LDB.getTable(StrategyMeta["TargetTable"])
    print(FT.getFactorMetaData(key="DataType"))
    # Data = FT.readData(factor_names=["strategy_from_signal"], ids=IDs, dts=DTs)
    # print(Data.iloc[0])
