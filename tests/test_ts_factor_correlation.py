# coding=utf-8
"""
测试时序因子相关性回测模块

使用 BaoStock 数据验证 CalcTimeSeriesCorrelation 算子和 TimeSeriesCorrelation 节点。

使用方式:
    cd d:\HST\QSExt
    python -m tests.test_ts_factor_correlation
"""
import datetime as dt

from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Factor.Factor import FactorContext
from QuantStudio.Factor.BaoStockDB import BaoStockDB
from QuantStudio.BackTest.BackTestModel import DTLocalContext
from QSExt.BackTest.TSFactor.Correlation import createTimeSeriesCorrelationNodes


if __name__ == "__main__":
    # 连接数据库
    BSDB = BaoStockDB().connect()

    # 获取因子
    FT = BSDB.getTable("A股K线数据", args={"LookBack": 0})
    Price = FT.getFactor("close")
    Factor1 = FT.getFactor("open")
    Factor2 = FT.getFactor("high")
    Factors = [Factor1, Factor2]

    # 股票列表
    SectionIDs = ["000001.SZ", "000002.SZ", "000003.SZ", "600519.SH"]
    print(f"股票数量: {len(SectionIDs)}")

    # 构建时点数据
    MaxStartDT = dt.datetime(2020, 1, 1)
    StartDT = dt.datetime(2024, 1, 1)
    EndDT = dt.datetime(2024, 6, 30)
    DTRuler = BSDB.getTradeDay(start_date=MaxStartDT, end_date=EndDT)
    DTs = BSDB.getTradeDay(start_date=StartDT, end_date=EndDT)
    if not DTs:
        print("计算时点序列为空")
        exit(0)
    print(f"时点范围: {DTs[0].strftime('%Y-%m-%d')} ~ {DTs[-1].strftime('%Y-%m-%d')} ({len(DTs)} 个)")


# 使用工厂函数创建节点
if __name__ == "__main__":
    Operator, TSCorrFactor, TSCorrNode, ReportNode = createTimeSeriesCorrelationNodes(
        factors=Factors,
        price=Price,
        descriptor_ids=SectionIDs,
        forecast_period=1,
        lag=0,
        summary_window=0,  # 扩展窗口
        min_summary_window=2,
        corr_method="spearman",
        factor_name_list=[f.Name for f in Factors],
    )
    print(f"报告节点: {ReportNode._QSArgs.Name}")


# 执行引擎
if __name__ == "__main__":
    with FactorContext(Mode="DEBUG", PIDList=["0"], DTRuler=DTRuler, SectionIDs=SectionIDs) as Context:
        with Engine() as CalcEngine:
            Results = CalcEngine.run([ReportNode], Context, fwd_data_list=[DTLocalContext(DTs=DTs)])

    Result = Results[0]
    print(f"结果 keys: {list(Result.keys())}")


# 打印结果
if __name__ == "__main__":
    if "统计数据" in Result:
        print("\n统计数据:")
        print(Result["统计数据"])
    if "Report" in Result:
        # 保存报告
        import os
        OutputDir = r"D:\Data\QSReport"
        os.makedirs(OutputDir, exist_ok=True)
        FilePath = os.path.join(OutputDir, "时序相关性报告.html")
        with open(FilePath, "w", encoding="utf-8") as f:
            f.write(Result["Report"])
        print(f"报告已保存: {FilePath}")
    print("完成")
