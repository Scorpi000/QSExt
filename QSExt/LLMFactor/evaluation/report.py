# -*- coding: utf-8 -*-
"""报告数据准备模块。

将评测算子的输出组织为 QSExt ReportGenerator 所需的 DataContext 格式，
调用 LayoutRenderer 渲染生成 HTML/Markdown 评测报告。

用法：
    from QSExt.LLMFactor.evaluation.report import generate_eval_report

    html = generate_eval_report(
        is_output=is_output,
        oos_output=oos_output,
        scores=scores,
        decision=decision,
        factor_name="my_factor",
    )
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

# ReportGenerator 位于 D:\HST\QSExt，尚未集成到主 QSExt 包
_HST_QSEXT = str(Path(r"D:\HST\QSExt"))
if _HST_QSEXT not in sys.path:
    sys.path.insert(0, _HST_QSEXT)

from QSExt.ReportGenerator.core import DataContext
from QSExt.ReportGenerator.layout import LayoutRenderer
from QSExt.ReportGenerator.themes.base import Theme

from QSExt.LLMFactor.evaluation.config import EvalConfig
from QSExt.LLMFactor.evaluation.decision import DecisionResult
from QSExt.LLMFactor.evaluation.scoring import FiveDimScore

__QS_Logger__ = logging.getLogger("QSR.report")

# 报告配置文件路径
_REPORT_CONFIG_PATH = Path(__file__).parent / "report_config.yaml"


def _load_report_config() -> dict:
    """加载报告布局配置。"""
    import yaml
    with open(_REPORT_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def prepare_report_data(
    is_output: Dict[str, Any],
    oos_output: Dict[str, Any],
    scores: FiveDimScore,
    decision: DecisionResult,
    factor_name: str,
    config: Optional[EvalConfig] = None,
) -> DataContext:
    """将评测算子输出组织为 DataContext 格式。

    将样本内/外的 BTReport output 合并，添加评分和决策数据，
    构建 DataContext 供 LayoutRenderer 渲染。

    Parameters
    ----------
    is_output : dict
        样本内 BTReport.backward_compute() 产出的 dict
    oos_output : dict
        样本外 BTReport.backward_compute() 产出的 dict
    scores : FiveDimScore
        五维度评分结果
    decision : DecisionResult
        入库决策结果
    factor_name : str
        因子名称
    config : EvalConfig, optional
        评测配置（用于获取报告格式等）

    Returns
    -------
    DataContext
        组织好的数据上下文，可直接传给 LayoutRenderer
    """
    report_cfg = _load_report_config()

    # 合并样本内/外 output，样本内为主，样本外加 "OOS-" 前缀
    merged_output: Dict[str, Any] = {}
    for key, value in is_output.items():
        merged_output[key] = value
    for key, value in oos_output.items():
        oos_key = f"OOS-{key}" if not key.startswith("OOS-") else key
        merged_output[oos_key] = value

    # 创建 DataContext
    ctx = DataContext(
        output=merged_output,
        factor_names=[factor_name],
        config=report_cfg,
    )

    # 注入评分数据
    ctx.set("custom", "scores", scores.to_dataframe())

    # 注入决策数据（决策结果 + 检查详情）
    ctx.set("custom", "decision", _decision_summary_to_df(decision))
    ctx.set("custom", "decision_checks", decision.to_dataframe())

    # 注入因子元信息
    ctx.set("meta", "factor_name", factor_name)
    if config:
        ctx.set("meta", "is_range", f"{config.in_sample_start} ~ {config.in_sample_end}")
        ctx.set("meta", "oos_range", f"{config.oos_start} ~ {config.oos_end}")

    return ctx


def generate_eval_report(
    is_output: Dict[str, Any],
    oos_output: Dict[str, Any],
    scores: FiveDimScore,
    decision: DecisionResult,
    factor_name: str,
    config: Optional[EvalConfig] = None,
    fmt: str = "html",
) -> str:
    """生成完整评测报告。

    调用 QSExt LayoutRenderer 渲染报告。

    Parameters
    ----------
    is_output : dict
        样本内 BTReport output
    oos_output : dict
        样本外 BTReport output
    scores : FiveDimScore
        五维度评分
    decision : DecisionResult
        入库决策
    factor_name : str
        因子名称
    config : EvalConfig, optional
        评测配置
    fmt : str
        输出格式："html" 或 "markdown"

    Returns
    -------
    str
        完整的报告内容
    """
    report_cfg = _load_report_config()

    # 构建 DataContext
    ctx = prepare_report_data(
        is_output, oos_output, scores, decision, factor_name, config,
    )

    # 渲染
    theme = Theme()
    renderer = LayoutRenderer()
    report_content = renderer.render(
        report_config=report_cfg.get("report", {}),
        data_ctx=ctx,
        theme=theme,
        fmt=fmt,
    )

    __QS_Logger__.info(f"评测报告已生成: {factor_name} ({fmt})")
    return report_content


def _decision_summary_to_df(decision: DecisionResult) -> pd.DataFrame:
    """将决策摘要转换为 DataFrame（用于 stat_grid 展示）。"""
    return pd.DataFrame({
        "决策": [decision.decision],
        "决策原因": [decision.reason],
        "因子类型": [decision.factor_type],
    })
