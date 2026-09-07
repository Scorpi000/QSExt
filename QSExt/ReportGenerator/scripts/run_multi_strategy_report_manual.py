# coding=utf-8
"""
手动运行多策略对比报告生成脚本 —— 不依赖 settings 配置，手动构建运行环境。

策略逻辑：均线交叉策略（不同参数对比）
    - 策略A：MA5/MA20 均线交叉
    - 策略B：MA10/MA30 均线交叉
    - 当短期均线上穿长期均线时买入，下穿时卖出
    - 等权配置所有买入的标的

适用场景:
    - 快速测试多策略对比报告生成
    - 调试多策略对比报告渲染逻辑
    - 验证多策略对比报告组件是否正确

使用方式:
    python run_multi_strategy_report_manual.py
"""
import os
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Factor import FactorOperator as fo
from QuantStudio.Factor.Factor import FactorContext, FactorLocalContext
from QuantStudio.Factor.BaoStockDB import BaoStockDB
from QuantStudio.BackTest.Strategy.Strategy import MakeAccount
from QSExt.ReportGenerator.scenarios.multi_strategy import MultiStrategyReport


# 相关配置
if __name__ == "__main__":
    # 连接数据库
    BSDB = BaoStockDB().connect()

    # 获取行情数据
    FT = BSDB.getTable("A股K线数据", args={"LookBack": 30})
    close = FT.getFactor("close")

    # 股票列表
    SectionIDs = ["000001.SZ", "000002.SZ", "000003.SZ", "600519.SH"]
    IDs = SectionIDs
    print(f"SectionIDs: {len(SectionIDs)} 个")

    # 构建时点数据
    MaxStartDT = dt.datetime(2020, 1, 1)
    StartDT = dt.datetime(2024, 1, 1)
    EndDT = dt.datetime(2024, 6, 30)
    DTRuler = BSDB.getTradeDay(start_date=MaxStartDT, end_date=EndDT)
    DTs = BSDB.getTradeDay(start_date=StartDT, end_date=EndDT)
    if not DTs:
        print("计算时点序列为空")
        exit(0)
    else:
        print(f"DTs: {len(DTs)} 个, {StartDT} ~ {EndDT}")


# 构建策略
if __name__ == "__main__":
    # 策略参数
    Strategies = [
        {"name": "MA5/MA20均线交叉", "short": 5, "long": 20},
        {"name": "MA10/MA30均线交叉", "short": 10, "long": 30},
    ]

    Accounts = []
    StrategyNames = []

    for cfg in Strategies:
        short_w, long_w = cfg["short"], cfg["long"]
        ma_short = fo.RollingMean(window=short_w, min_periods=short_w)(close)
        ma_long = fo.RollingMean(window=long_w, min_periods=long_w)(close)

        # 信号：短期均线 >= 长期均线时买入，归一化为权重
        Signal = fo.Where()(1, ma_short >= ma_long, 0)
        Signal = Signal / fo.Aggregate(aggr_func=np.nansum)(Signal)

        Account = MakeAccount(
            signal_type="目标权重",
            start_dt=DTs[0],
            init_cash=1e6,
        )(last_price=close, signal=Signal)

        Accounts.append(Account)
        StrategyNames.append(cfg["name"])
        print(f"策略构建完成: {cfg['name']}")


# 创建策略和报告节点
if __name__ == "__main__":
    # 创建报告所需的上游节点（每个策略一个 AccountStats）
    Nodes = MultiStrategyReport.create_nodes(Accounts)

    # 创建报告生成节点
    ReportNode = MultiStrategyReport(
        deps=Nodes,
        args={"Name": "多策略对比报告", "OutputFormat": "html"},
        strategy_names=StrategyNames,
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
        FilePath = os.path.join(OutputDir, f"多策略对比报告.{Fmt}")
        with open(FilePath, "w", encoding="utf-8") as f:
            f.write(Content)
        print(f"已保存: {FilePath}")
    print("完成")
