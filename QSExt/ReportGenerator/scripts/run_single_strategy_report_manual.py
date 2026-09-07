# coding=utf-8
"""
手动运行策略报告生成脚本 —— 不依赖 settings 配置，手动构建运行环境。

策略逻辑：均线交叉策略（来自 stock_cn_strategy_example）
    - 当短期均线上穿长期均线时买入，下穿时卖出
    - 等权配置所有买入的标的

适用场景:
    - 快速测试单策略报告生成
    - 调试策略报告渲染逻辑
    - 验证策略报告组件是否正确

使用方式:
    python run_single_strategy_report_manual.py
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
from QSExt.ReportGenerator.scenarios.single_strategy import SingleStrategyReport


# 相关配置
if __name__ == "__main__":
    # 连接数据库
    BSDB = BaoStockDB().connect()

    # 获取行情数据
    FT = BSDB.getTable("A股K线数据", args={"LookBack": LONG_WINDOW})
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
    else: print(f"DTs: {len(DTs)} 个, {StartDT} ~ {EndDT}")


# 构建策略
if __name__ == "__main__":
    # 策略参数
    SHORT_WINDOW = 5
    LONG_WINDOW = 20
    
    # 计算短期和长期均线
    ma_short = fo.RollingMean(window=SHORT_WINDOW, min_periods=SHORT_WINDOW)(close)
    ma_long = fo.RollingMean(window=LONG_WINDOW, min_periods=LONG_WINDOW)(close)

    # 生成信号：短期均线 >= 长期均线时买入，归一化为权重
    Signal = fo.Where()(1, ma_short >= ma_long, 0)
    Signal = Signal / fo.Aggregate(aggr_func=np.nansum)(Signal)

    # 构造策略账户
    Account = MakeAccount(
        signal_type="目标权重",
        start_dt=DTs[0],
        init_cash=1e6,
    )(last_price=close, signal=Signal)
    print(f"策略构建完成: MA{SHORT_WINDOW}/MA{LONG_WINDOW} 均线交叉")


# 创建报告节点
if __name__ == "__main__":
    # 创建报告所需的上游节点（AccountStats）
    Nodes = SingleStrategyReport.create_nodes(Account)

    # 创建报告生成节点
    ReportNode = SingleStrategyReport(
        deps=Nodes,
        args={"Name": "均线交叉策略报告", "OutputFormat": "html"},
        strategy_name=f"MA{SHORT_WINDOW}/MA{LONG_WINDOW}均线交叉",
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
        FilePath = os.path.join(OutputDir, f"均线交叉策略报告.{Fmt}")
        with open(FilePath, "w", encoding="utf-8") as f:
            f.write(Content)
        print(f"已保存: {FilePath}")
    print("完成")
