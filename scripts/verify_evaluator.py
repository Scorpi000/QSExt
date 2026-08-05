"""因子评测入口（FactorEvaluator）端到端验证脚本。

使用真实数据从 JYDB 构建 PE_TTM 因子，运行完整的 IS/OOS 评测流程，
验证 evaluator.py 的 DAG 构建、执行、统计提取、评分和决策全链路。

使用方式：
    # 小样本验证（默认 50 只股票，2022-2024）
    python scripts/verify_evaluator.py

    # 全量验证
    python scripts/verify_evaluator.py --full

    # 自定义参数
    python scripts/verify_evaluator.py --sample-n 100 --start 2020-01 --end 2025-06
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

# 项目根目录加入 sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
from QSExt import __QS_MainPath__
load_dotenv(Path(__QS_MainPath__).parent / "config" / ".env")

from QSExt import setDefaultLogLevel
setDefaultLogLevel(logging.INFO)

logger = logging.getLogger("QSR.verify")


def parse_args():
    parser = argparse.ArgumentParser(description="FactorEvaluator 端到端验证")
    parser.add_argument("--full", action="store_true", help="全量验证（耗时较长）")
    parser.add_argument("--start", default="2022-01", help="评测起始年月 (YYYY-MM)")
    parser.add_argument("--end", default="2024-12", help="评测结束年月 (YYYY-MM)")
    parser.add_argument("--sample-n", type=int, default=50, help="小样本股票数量（--full 时忽略）")
    return parser.parse_args()


def main():
    args = parse_args()

    # ============================================================
    # Step 1: 连接 JYDB，获取数据基础
    # ============================================================
    logger.info("=" * 60)
    logger.info("Step 1: 连接 JYDB，获取数据基础")
    logger.info("=" * 60)

    from QuantStudio.Factor.JYDB import JYDB
    from QuantStudio.Tools.DateTimeFun import getMonthLastDateTime

    SDB = JYDB().connect()
    logger.info("  JYDB 连接成功")

    # 日期标尺（前面多取 2 年用于 IC 回溯，后面多取 3 个月用于 lookback）
    start_parts = args.start.split("-")
    end_parts = args.end.split("-")
    data_start = dt.datetime(int(start_parts[0]) - 2, int(start_parts[1]), 1)
    end_year, end_month = int(end_parts[0]), int(end_parts[1])
    end_month += 3
    if end_month > 12:
        end_year += end_month // 12
        end_month = end_month % 12
    data_end = dt.datetime(end_year, end_month, 28)
    DTRuler = SDB.getTradeDay(start_date=data_start, end_date=data_end)
    logger.info(f"  日期标尺: {DTRuler[0].date()} ~ {DTRuler[-1].date()} ({len(DTRuler)} 个交易日)")

    # 股票列表（从日行情表获取）
    FT_bar = SDB.getTable("日行情表")
    AllIDs = FT_bar.getID()
    logger.info(f"  全量股票数: {len(AllIDs)}")

    if args.full:
        SectionIDs = sorted(AllIDs)
    else:
        SectionIDs = sorted(AllIDs[:args.sample_n])
        logger.info(f"  小样本模式: 使用前 {len(SectionIDs)} 只股票")

    # 再平衡时点（月末）
    BalanceDTs = getMonthLastDateTime(DTRuler)
    BalanceDTs = [d for d in BalanceDTs if data_start <= d <= data_end]
    logger.info(f"  再平衡时点: {len(BalanceDTs)} 个月末")

    # ============================================================
    # Step 2: 构建因子对象
    # ============================================================
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 2: 构建因子对象")
    logger.info("=" * 60)

    from QSExt.FactorDef.FactorDefContent import FactorDefInput
    import QuantStudio.Factor.FactorOperator as fo
    from QuantStudio.Factor.BasicOperator import rename
    import numpy as np

    fdi = FactorDefInput(
        Debug=False,
        FDB={"JYDB": SDB},
        DTs=DTRuler,
        IDs=SectionIDs,
        SectionIDs=SectionIDs,
        DTRuler=DTRuler,
    )

    # ---- 候选因子：PE_TTM ----
    logger.info("  构建候选因子: PE_TTM ...")
    where, notnull = fo.Where(dtype="double"), fo.NotNull()

    # 归母净利润(TTM)
    FT_fin = SDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "最新"})
    NP_TTM = FT_fin.getFactor("归属母公司股东的净利润(TTM)")
    FT_fin_stib = SDB.getTable("科创板衍生报表数据", args={"CalcType": "最新"})
    NP_TTM_STIB = FT_fin_stib.getFactor("归属母公司股东的净利润(TTM)")
    NP_TTM = where(NP_TTM, notnull(NP_TTM), NP_TTM_STIB)

    # 总市值
    FT_mv = SDB.getTable("股票行情表现", args={"LookBack": 0})
    TotalMV = FT_mv.getFactor("总市值(万元)")
    FT_mv_stib = SDB.getTable("科创板行情表现", args={"LookBack": 0})
    TotalMV_STIB = FT_mv_stib.getFactor("总市值(元)")
    TotalMV_STIB = TotalMV_STIB / 10000  # 元 → 万元
    TotalMV = where(TotalMV, notnull(TotalMV), TotalMV_STIB)

    # PE_TTM = 总市值(万元) * 10000 / 归母净利润(TTM)
    candidate_factor = rename(TotalMV * 10000 / NP_TTM, factor_name="pe_ttm")
    logger.info(f"  候选因子: {candidate_factor.Name}")

    # ---- 价格因子 ----
    logger.info("  获取价格因子 ...")
    FT_close = SDB.getTable("日行情表", args={"LookBack": np.inf, "FilterCondition": "{Table}.ClosePrice>0"})
    FT_close_stib = SDB.getTable("科创板日行情", args={"LookBack": np.inf, "FilterCondition": "{Table}.ClosePrice>0"})
    Price = FT_close.getFactor("收盘价(元)")
    Price_STIB = FT_close_stib.getFactor("收盘价(元)")
    Price = where(Price, notnull(Price), Price_STIB)

    # ---- 筛选条件 ----
    logger.info("  获取筛选条件 ...")
    from QSExt.FactorDef.JY.stock_cn_status import defFactor as defStatusFactor
    status_fd = defStatusFactor(fdi=fdi, dep_fd={})
    IfListed = status_fd.getFactor(factor_name="if_listed")
    Mask = (IfListed == 1)

    # ---- 行业因子（可选，暂时跳过） ----
    Industry = None
    logger.info("  行业因子: 跳过（可选）")

    # ============================================================
    # Step 3: 配置评测参数
    # ============================================================
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 3: 配置评测参数")
    logger.info("=" * 60)

    from QSExt.LLMFactor.evaluation.config import EvalConfig

    # IS/OOS 分界：最后 2 年作为 OOS
    is_end_year = int(args.end.split("-")[0]) - 2
    config = EvalConfig(
        in_sample_start=args.start,
        in_sample_end=f"{is_end_year}-12",
        oos_start=f"{is_end_year + 1}-01",
        oos_end=args.end,
        corr_method="spearman",
        ic_lookback=31,
        period_lookback=1,
        ic_decay_periods=[1, 2, 3],
        group_num=5,
        min_alpha_t=3.0,
        min_composite_score=0.60,
        min_incremental_ic_t=2.0,
        min_oos_rankic=0.02,
        save_to_mining_log=False,
    )

    logger.info(f"  样本内: {config.in_sample_start} ~ {config.in_sample_end}")
    logger.info(f"  样本外: {config.oos_start} ~ {config.oos_end}")
    logger.info(f"  IC 衰减期: {config.ic_decay_periods}")
    logger.info(f"  分组数: {config.group_num}")
    logger.info(f"  写入日志库: {config.save_to_mining_log}")

    # ============================================================
    # Step 4: 运行评测
    # ============================================================
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 4: 运行 FactorEvaluator")
    logger.info("=" * 60)

    from QSExt.LLMFactor.evaluation.evaluator import FactorEvaluator

    evaluator = FactorEvaluator(config)

    t0 = time.time()
    report = evaluator.evaluate(
        factor=candidate_factor,
        price=Price,
        descriptor_ids=SectionIDs,
        dt_ruler=DTRuler,
        balance_dts=BalanceDTs,
        mask=Mask,
        industry=Industry,
        factor_name="pe_ttm",
        category="估值",
    )
    elapsed = time.time() - t0

    # ============================================================
    # Step 5: 输出结果
    # ============================================================
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 5: 评测结果")
    logger.info("=" * 60)

    logger.info(f"  耗时: {elapsed:.1f} 秒")
    logger.info(f"  因子名称: {report.factor_name}")
    logger.info(f"  决策: {report.decision.decision}")
    logger.info(f"  决策原因: {report.decision.reason}")
    logger.info(f"  因子类型: {report.decision.factor_type}")
    logger.info("")

    # 五维度评分
    logger.info("  五维度评分:")
    logger.info(f"    有效性:     {report.scores.effectiveness:.4f}")
    logger.info(f"    稳定性:     {report.scores.stability:.4f}")
    logger.info(f"    换手率:     {report.scores.turnover:.4f}")
    logger.info(f"    多样性:     {report.scores.diversity:.4f}")
    logger.info(f"    过拟合风险: {report.scores.overfitting_risk:.4f}")
    logger.info(f"    综合评分:   {report.scores.composite:.4f}")
    logger.info("")

    # IS 统计
    is_ic = report.is_stats.get("ic", {})
    logger.info("  样本内 IC 统计:")
    logger.info(f"    RankIC 均值: {is_ic.get('rankic_mean', 'N/A')}")
    logger.info(f"    ICIR:        {is_ic.get('icir', 'N/A')}")
    logger.info(f"    t 统计量:    {is_ic.get('t_stat', 'N/A')}")
    logger.info(f"    胜率:        {is_ic.get('win_rate', 'N/A')}")
    logger.info("")

    # OOS 统计
    oos_ic = report.oos_stats.get("ic", {})
    logger.info("  样本外 IC 统计:")
    logger.info(f"    RankIC 均值: {oos_ic.get('rankic_mean', 'N/A')}")
    logger.info(f"    ICIR:        {oos_ic.get('icir', 'N/A')}")
    logger.info("")

    # 分组回测
    is_port = report.is_stats.get("portfolio", {})
    if is_port:
        logger.info("  分组回测统计:")
        logger.info(f"    年化收益率: {is_port.get('annual_return', 'N/A')}")
        logger.info(f"    Sharpe:     {is_port.get('sharpe', 'N/A')}")
        logger.info(f"    最大回撤:   {is_port.get('max_drawdown', 'N/A')}")
        if "long_short_return" in is_port:
            logger.info(f"    多空收益:   {is_port['long_short_return']}")
            logger.info(f"    多空 Sharpe: {is_port['long_short_sharpe']}")
        logger.info("")

    # 决策检查详情
    logger.info("  决策检查详情:")
    for check_name, check_info in report.decision.checks.items():
        status = "✅" if check_info.get("passed", False) else "❌"
        val = check_info.get("value", "N/A")
        thr = check_info.get("threshold", "N/A")
        if isinstance(val, float):
            val = f"{val:.4f}"
        if isinstance(thr, float):
            thr = f"{thr:.4f}"
        logger.info(f"    {status} {check_name}: {val} (阈值: {thr})")

    # 报告文件
    report_dir = _ROOT / "local" / "workspace"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "eval_report_pe_ttm.html"
    report_path.write_text(report.report_html, encoding="utf-8")
    logger.info(f"\n  HTML 报告已保存: {report_path}")

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("验证完成")
    logger.info("=" * 60)
    summary = report.summary
    for k, v in summary.items():
        logger.info(f"  {k}: {v}")

    return report


if __name__ == "__main__":
    main()
