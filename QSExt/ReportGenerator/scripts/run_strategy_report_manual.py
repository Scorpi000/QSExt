# coding=utf-8
"""
手动运行策略报告生成脚本 —— 不依赖 settings 配置，手动构建运行环境。

适用场景:
    - 快速测试单策略报告生成
    - 调试策略报告渲染逻辑
    - 验证策略报告组件是否正确

使用方式:
    python run_strategy_report_manual.py
"""
import os
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Factor.Factor import DataFactor, FactorContext, FactorLocalContext
from QuantStudio.BackTest.Strategy.Strategy import MakeAccount
from QuantStudio.BackTest.Strategy.AllocationStrategy import CalcPortfolioNV
from QSExt.ReportGenerator.scenarios.single_strategy import SingleStrategyReport


# 相关配置
if __name__ == "__main__":
    # ---- 构建测试数据 ----
    np.random.seed(42)
    SectionIDs = [f"{str(i).zfill(6)}.SZ" for i in range(1, 21)]
    IDs = SectionIDs

    MaxStartDT = dt.datetime(2022, 12, 1)  # DTRuler 起始（需早于 StartDT 以满足回溯）
    StartDT = dt.datetime(2023, 1, 1)
    EndDT = dt.datetime(2024, 12, 31)
    # 简单的交易日序列（工作日）
    DTRuler = pd.bdate_range(MaxStartDT, EndDT).to_pydatetime().tolist()
    DTs = [d for d in DTRuler if d >= StartDT]
    print(f"截面: {len(SectionIDs)} 个, 时点: {len(DTs)} 个, {StartDT} ~ {EndDT}")

    # 价格因子（覆盖 DTRuler 全范围）
    PriceData = pd.DataFrame(
        np.random.rand(len(DTRuler), len(SectionIDs)) * 20 + 5,
        index=DTRuler, columns=SectionIDs,
    )
    Price = DataFactor(data=PriceData, args={"Name": "Price"})

    # 随机信号因子（目标权重，覆盖 DTs 范围）
    SignalData = pd.DataFrame(
        np.random.rand(len(DTs), len(SectionIDs)),
        index=DTs, columns=SectionIDs,
    )
    SignalData = SignalData.div(SignalData.sum(axis=1), axis=0)  # 归一化为权重
    Signal = DataFactor(data=SignalData, args={"Name": "Signal"})

    # 基准净值因子（可选，覆盖 DTs 范围）
    BmkNVData = pd.Series(
        (1 + np.random.randn(len(DTs)) * 0.005).cumprod() * 1e6,
        index=DTs,
    )
    BmkNV = DataFactor(data=BmkNVData.to_frame("BmkNV"), args={"Name": "BmkNV"})


# 创建策略和报告节点
if __name__ == "__main__":
    # 创建账户（策略）
    Account = MakeAccount(
        signal_type="目标权重",
        start_dt=DTs[0],
        init_cash=1e6,
    )(last_price=Price, signal=Signal)

    # 创建报告所需的上游节点（AccountStats）
    Nodes = SingleStrategyReport.create_nodes(
        Account,
        bmk_nv=BmkNV,
    )

    # 创建报告生成节点
    ReportNode = SingleStrategyReport(
        deps=Nodes,
        args={"Name": "策略回测报告", "OutputFormat": "html"},
        strategy_name="随机权重策略",
    )
    print(f"报告节点: {ReportNode._QSArgs.Name}")


# 执行引擎
if __name__ == "__main__":
    with FactorContext(
        Mode="DEBUG", PIDList=["0"],
        DTRuler=DTRuler, SectionIDs=SectionIDs,
    ) as Context:
        with Engine() as CalcEngine:
            Results = CalcEngine.run(
                [ReportNode], Context,
                fwd_data_list=[FactorLocalContext(DTs=DTs, IDs=IDs)],
            )

    Result = Results[0]
    print(f"报告 keys: {list(Result.keys())}")


# 保存报告
if __name__ == "__main__":
    OutputDir = r"D:\Data\QSReport"
    os.makedirs(OutputDir, exist_ok=True)

    Fmt = ReportNode._QSArgs.OutputFormat
    ReportKey = ReportNode._QSArgs.ReportKey
    Content = Result.get(ReportKey, "")
    if Content:
        FilePath = os.path.join(OutputDir, f"策略回测报告.{Fmt}")
        with open(FilePath, "w", encoding="utf-8") as f:
            f.write(Content)
        print(f"已保存: {FilePath}")
    print("完成")
