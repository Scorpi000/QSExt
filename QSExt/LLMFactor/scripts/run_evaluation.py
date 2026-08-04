# -*- coding: utf-8 -*-
"""因子评测 — 独立脚本。

加载已开发的因子代码，执行因子评测，生成评测报告。

用法::

    # 指定因子目录直接评测
    python -m QSExt.LLMFactor.scripts.run_evaluation --factor-dir workspace/FM_xxx/development

    # 同时指定假设文件（用于获取类别信息）
    python -m QSExt.LLMFactor.scripts.run_evaluation --factor-dir workspace/FM_xxx/development --hypothesis workspace/FM_xxx/hypothesis/hypothesis.yaml

    # 指定工作区目录
    python -m QSExt.LLMFactor.scripts.run_evaluation --factor-dir workspace/FM_xxx/development --workspace workspace/eval

    # 复用已有评测缓存
    python -m QSExt.LLMFactor.scripts.run_evaluation --factor-dir workspace/FM_xxx/development --no-clear-cache

    # 指定配置文件
    python -m QSExt.LLMFactor.scripts.run_evaluation --config my_pipeline.yaml --factor-dir workspace/FM_xxx/development

输出:
    - evaluation/eval_report.html : 评测报告（HTML）
    - evaluation/eval_summary.json : 评测摘要（JSON）
    - evaluation.log : 运行日志

环境要求:
    - PostgreSQL (JYDB) 连接可用
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from QSExt import __QS_MainPath__

load_dotenv(__QS_MainPath__ + "/config/.env")

from QSExt.LLMFactor.scripts._utils import (
    extract_factor_name_from_code,
    setup_logging,
)

__QS_Logger__ = logging.getLogger("QSR.pipeline.evaluation")


# ============================================================
# 评测上下文构建
# ============================================================

def build_evaluation_context(development_result: dict, workspace_dir: Path, pipeline_config=None):
    """从因子开发产出物构建评测所需的因子对象和参数。

    Args:
        development_result: 包含 factor_dir, factor_code_path, factor_name 的 dict
        workspace_dir: 工作区目录
        pipeline_config: PipelineConfig 实例

    Returns:
        (factor, price, IDs, DTRuler, balance_dts, factor_name) 元组，失败返回 None
    """
    from QSExt.FactorDef.FactorDefContent import FactorDefInput
    from QuantStudio.Factor.JYDB import JYDB
    from QSExt.LLMFactor.pipeline_config import PipelineConfig

    pc = pipeline_config or PipelineConfig()
    data_ctx = pc.data

    factor_dir = development_result.get("factor_dir", "")
    code_path = Path(factor_dir) / "factor_def.py"

    if not code_path.exists():
        for py_file in Path(factor_dir).glob("**/*.py"):
            if "defFactor" in py_file.read_text(encoding="utf-8"):
                code_path = py_file
                break

    if not code_path.exists():
        __QS_Logger__.error("factor_def.py 不存在: %s", code_path)
        return None

    __QS_Logger__.info("加载因子代码: %s", code_path)
    module_name = f"_pipeline_factor_{code_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(code_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "defFactor"):
        __QS_Logger__.error("因子模块缺少 defFactor 函数")
        return None

    __QS_Logger__.info("连接 JYDB...")
    SDB = JYDB().connect()

    DTRuler = SDB.getTradeDay(
        start_date=data_ctx.get_trade_day_start(),
        end_date=data_ctx.get_trade_day_end(),
    )
    __QS_Logger__.info("  交易日数量: %d", len(DTRuler))

    IDs = SDB.getStockID(dt=data_ctx.get_stock_date())
    if len(IDs) > data_ctx.max_stocks:
        IDs = IDs[:data_ctx.max_stocks]
    __QS_Logger__.info("  股票数量: %d", len(IDs))

    fdi = FactorDefInput(
        Debug=False,
        FDB={"JYDB": SDB},
        DTs=DTRuler,
        IDs=IDs,
        SectionIDs=IDs,
        DTRuler=DTRuler,
    )

    __QS_Logger__.info("执行 defFactor()...")
    result = module.defFactor(fdi=fdi)
    if isinstance(result, list):
        factors = result
    elif hasattr(result, "FactorList"):
        factors = result.FactorList
    else:
        __QS_Logger__.error("defFactor 返回未知类型: %s", type(result).__name__)
        return None

    if not factors:
        __QS_Logger__.error("defFactor 返回空列表")
        return None

    factor = factors[0]
    __QS_Logger__.info("  因子名称: %s", factor.Name)

    __QS_Logger__.info("获取价格数据...")
    price_FT = SDB.getTable("股票行情表现", args={"LookBack": 0})
    price = price_FT.getFactor("收盘价")

    balance_dts = _get_month_end_dates(DTRuler)
    __QS_Logger__.info("  再平衡时点数量: %d", len(balance_dts))

    factor_name = development_result.get("factor_name", "unknown_factor")
    return factor, price, IDs, DTRuler, balance_dts, factor_name


# ============================================================
# 评测执行
# ============================================================

def run_evaluation(
    factor, price, descriptor_ids, dt_ruler, balance_dts,
    factor_name: str, category: str, workspace_dir: Path,
    eval_config=None, cache=None,
) -> dict | None:
    """运行因子评测。

    Args:
        factor: 因子对象
        price: 价格因子
        descriptor_ids: 证券 ID 列表
        dt_ruler: 交易日序列
        balance_dts: 再平衡时点
        factor_name: 因子名称
        category: 因子类别
        workspace_dir: 工作区目录
        eval_config: EvalConfig 实例
        cache: 缓存管理器实例

    Returns:
        评测摘要 dict，失败返回 None
    """
    from QSExt.LLMFactor.evaluation import FactorEvaluator, EvalConfig

    __QS_Logger__.info("=" * 60)
    __QS_Logger__.info("因子评测")
    __QS_Logger__.info("  因子: %s", factor_name)
    __QS_Logger__.info("=" * 60)

    config = eval_config or EvalConfig()
    evaluator = FactorEvaluator(config)
    report = evaluator.evaluate(
        factor=factor, price=price,
        descriptor_ids=descriptor_ids, dt_ruler=dt_ruler,
        balance_dts=balance_dts, factor_name=factor_name,
        category=category, cache=cache,
    )

    evaluation_dir = workspace_dir / "evaluation"
    evaluation_dir.mkdir(parents=True, exist_ok=True)

    report_html_path = evaluation_dir / "eval_report.html"
    report_html_path.write_text(report.report_html, encoding="utf-8")

    summary = report.summary
    summary["scores"] = {
        "effectiveness": report.scores.effectiveness,
        "stability": report.scores.stability,
        "turnover": report.scores.turnover,
        "diversity": report.scores.diversity,
        "overfitting_risk": report.scores.overfitting_risk,
        "composite": report.scores.composite,
    }
    summary["decision_reason"] = report.decision.reason

    summary_path = evaluation_dir / "eval_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    __QS_Logger__.info("因子评测完成: decision=%s, composite=%.3f",
                       report.decision.decision, report.scores.composite)
    return summary


# ============================================================
# 辅助函数
# ============================================================

def _get_month_end_dates(dtruler: list) -> list:
    """从交易日序列中提取月末日期。

    Args:
        dtruler: 交易日序列

    Returns:
        月末日期列表
    """
    month_ends = []
    for i, d in enumerate(dtruler):
        if i == len(dtruler) - 1 or dtruler[i + 1].month != d.month:
            month_ends.append(d)
    return month_ends


# ============================================================
# 主入口
# ============================================================

def _default_config_path() -> str:
    """获取默认配置文件路径。"""
    return str(Path(__QS_MainPath__) / "LLMFactor" / "config" / "pipeline.yaml")


def main():
    parser = argparse.ArgumentParser(
        description="因子评测 — 加载因子代码并执行评测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--config", default=None, help="流水线配置文件路径")
    parser.add_argument("--factor-dir", required=True, help="因子目录路径（包含 factor_def.py）")
    parser.add_argument("--hypothesis", default=None, help="假设 YAML 文件路径（用于获取类别信息）")
    parser.add_argument("--workspace", default=None, help="工作区目录（默认使用 factor-dir 的父目录）")
    parser.add_argument(
        "--clear-cache", action=argparse.BooleanOptionalAction, default=True,
        help="是否清空评测缓存（默认：True）。使用 --no-clear-cache 复用已有缓存",
    )
    parser.add_argument("--log-level", default="INFO", help="日志级别")

    args = parser.parse_args()

    # 验证因子目录
    factor_dir = Path(args.factor_dir).resolve()
    if not factor_dir.exists():
        print(f"错误: 因子目录不存在: {args.factor_dir}", file=sys.stderr)
        sys.exit(1)

    # 查找因子代码文件
    code_path = factor_dir / "factor_def.py"
    if not code_path.exists():
        for py_file in factor_dir.glob("**/*.py"):
            if "defFactor" in py_file.read_text(encoding="utf-8"):
                code_path = py_file
                break
    if not code_path.exists():
        print(f"错误: 因子目录中未找到包含 defFactor 的 Python 文件: {args.factor_dir}", file=sys.stderr)
        sys.exit(1)

    # 确定工作区
    if args.workspace:
        workspace_dir = Path(args.workspace).resolve()
    else:
        workspace_dir = factor_dir.parent
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # 配置日志
    setup_logging(workspace_dir, args.log_level)

    # 加载配置
    from QSExt.LLMFactor.pipeline_config import PipelineConfig
    config_path = args.config or _default_config_path()
    pipeline_config = PipelineConfig.from_yaml(config_path)
    __QS_Logger__.info("已加载配置: %s", config_path)

    eval_config = pipeline_config.load_evaluation_config()
    eval_config.cache_start_mode = "new" if args.clear_cache else "continue"

    # 提取因子名称
    factor_name = extract_factor_name_from_code(code_path)
    __QS_Logger__.info("因子名称: %s", factor_name)

    # 构建 development_result
    development_result = {
        "factor_dir": str(factor_dir),
        "factor_code_path": str(code_path),
        "factor_name": factor_name,
        "status": "completed",
    }

    # 解析假设文件（获取类别信息）
    category = ""
    if args.hypothesis:
        hypothesis_path = Path(args.hypothesis)
        if hypothesis_path.exists():
            try:
                yaml_str = hypothesis_path.read_text(encoding="utf-8")
                from QSExt.LLMFactor.hypothesis.models import (
                    DirectionCandidate, HypothesisDoc, ResearchContext,
                )
                dummy_dir = DirectionCandidate(
                    direction_tag="from_file",
                    category="", description="", rationale="",
                )
                context = ResearchContext(direction=dummy_dir)
                doc = HypothesisDoc.from_llm_yaml(yaml_str, context)
                dev_input = doc.to_development_input()
                category = dev_input.get("category", "")
            except Exception as e:
                __QS_Logger__.warning("解析假设文件失败: %s", e)

    # 执行评测
    try:
        ctx = build_evaluation_context(development_result, workspace_dir, pipeline_config)
        if not ctx:
            __QS_Logger__.error("构建评测上下文失败")
            sys.exit(1)

        factor, price, ids, dtruler, balance_dts, factor_name = ctx
        evaluation_summary = run_evaluation(
            factor, price, ids, dtruler, balance_dts,
            factor_name, category, workspace_dir,
            eval_config=eval_config,
        )

        if not evaluation_summary:
            __QS_Logger__.error("因子评测失败")
            sys.exit(1)

    except Exception as e:
        __QS_Logger__.error("因子评测异常: %s", e, exc_info=True)
        sys.exit(1)

    __QS_Logger__.info("=" * 60)
    __QS_Logger__.info("因子评测完成")
    __QS_Logger__.info("  因子名称: %s", factor_name)
    __QS_Logger__.info("  决策: %s", evaluation_summary.get("decision", "unknown"))
    __QS_Logger__.info("  综合得分: %.3f", evaluation_summary.get("scores", {}).get("composite", 0))
    __QS_Logger__.info("  工作区: %s", workspace_dir)
    __QS_Logger__.info("=" * 60)


if __name__ == "__main__":
    main()
