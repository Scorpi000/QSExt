# coding=utf-8
"""
手动运行多因子对比报告生成脚本 —— 不依赖 settings 配置，手动构建运行环境。

适用场景:
    - 快速测试多因子对比报告生成
    - 调试多因子对比报告渲染逻辑
    - 验证多因子对比报告组件是否正确

使用方式:
    python run_multi_factor_report_manual.py
"""
import os
import datetime as dt

from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Factor.Factor import FactorContext
from QuantStudio.Factor.BaoStockDB import BaoStockDB
from QuantStudio.BackTest.BackTestModel import DTLocalContext
from QSExt.ReportGenerator.scenarios.multi_factor import MultiFactorReport


# 相关配置
if __name__ == "__main__":
    # 连接数据库
    BSDB = BaoStockDB().connect()

    # 获取多个因子
    FT = BSDB.getTable("A股K线数据", args={"LookBack": 0})
    Factor1 = FT.getFactor("open")
    Factor2 = FT.getFactor("high")
    Factor3 = FT.getFactor("low")
    Factors = [Factor1, Factor2, Factor3]

    # 参考因子（可选）
    Price = FT.getFactor("close")  # 价格因子

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


# 创建报告节点
if __name__ == "__main__":
    # 创建多因子对比报告所需的上游节点（IC、IC衰减、分位数组合、换手率）
    Nodes = MultiFactorReport.create_nodes(
        Factors,
        price=Price,
        descriptor_ids=SectionIDs,
        dtruler=DTRuler,
    )

    # 因子名称列表
    FactorNames = [f.Name for f in Factors]

    # 创建报告生成节点
    ReportNode = MultiFactorReport(
        deps=Nodes,
        args={"Name": "多因子对比报告", "OutputFormat": "html"},
        factor_names=FactorNames,
    )
    print(f"报告节点: {ReportNode._QSArgs.Name}")


# 执行引擎
if __name__ == "__main__":
    with FactorContext(Mode="DEBUG", PIDList=["0"], DTRuler=DTRuler, SectionIDs=SectionIDs) as Context:
        with Engine() as CalcEngine:
            Results = CalcEngine.run([ReportNode], Context, fwd_data_list=[DTLocalContext(DTs=DTs)])

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
        FilePath = os.path.join(OutputDir, f"多因子对比报告.{Fmt}")
        with open(FilePath, "w", encoding="utf-8") as f:
            f.write(Content)
        print(f"已保存: {FilePath}")
    print("完成")
