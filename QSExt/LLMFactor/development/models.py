# -*- coding: utf-8 -*-
"""因子开发模块数据模型定义。

定义因子开发流程中的核心数据结构：
  - EvalMetrics: 因子评估指标（内置 + 扩展）
  - GeneratedCode: 代码生成结果
  - 各类验证报告（SyntaxReport, ExecutionReport, LeakTestReport 等）
  - SearchResult: 参数搜索结果
  - FixAttempt: 自动修复尝试记录
  - DevelopmentResult: 因子开发阶段完整输出

数据契约对齐方案文档 7.2 节。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd


# ============================================================
# 评估指标
# ============================================================

@dataclass
class EvalMetrics:
    """因子评估指标集合。

    内置指标由 ParamSearcher 自动计算，扩展指标由用户自定义
    MetricCalculator 追加到 extra 字典中。支持通过属性访问扩展指标。

    Attributes:
        rankic: Rank IC 均值
        icir: IC 信息比率
        win_rate: IC 胜率
        max_drawdown: 最大回撤
        turnover: 换手率
        extra: 用户扩展指标
    """
    # ---- 内置指标 ----
    rankic: float = 0.0
    icir: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    turnover: float = 0.0

    # ---- 扩展指标 ----
    extra: dict = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        """支持通过属性访问扩展指标。"""
        extra = object.__getattribute__(self, "extra")
        if name in extra:
            return extra[name]
        raise AttributeError(f"EvalMetrics 没有指标 '{name}'")

    def to_dict(self) -> dict[str, float]:
        """转为扁平字典。"""
        result = {
            "rankic": self.rankic,
            "icir": self.icir,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "turnover": self.turnover,
        }
        result.update(self.extra)
        return result


# ============================================================
# 代码生成
# ============================================================

@dataclass
class GeneratedCode:
    """代码生成结果。

    Attributes:
        factor_code: 完整的 factor_def.py 代码
        factor_module_name: 模块名（不含 .py）
        search_space: 超参数搜索空间定义
        metadata: metadata.json 内容
        dag_description: DAG 分解描述（调试用）
    """
    factor_code: str
    factor_module_name: str
    search_space: dict
    metadata: dict
    dag_description: str = ""


# ============================================================
# 验证报告
# ============================================================

@dataclass
class SyntaxReport:
    """Agent A: 语法检查报告。

    Attributes:
        passed: 是否通过
        issues: 发现的问题列表
        details: 详细检查结果
    """
    passed: bool
    issues: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


@dataclass
class ExecutionReport:
    """Agent B: 执行验证报告。

    Attributes:
        passed: 是否通过
        output_shape: readData() 输出维度
        nan_ratio: NaN 值比例
        issues: 发现的问题列表
    """
    passed: bool
    output_shape: Optional[tuple] = None
    nan_ratio: float = 1.0
    issues: list[str] = field(default_factory=list)


@dataclass
class LeakTestReport:
    """Agent C: 未来信息泄漏检测报告。

    Attributes:
        passed: 是否通过
        test_dates: 测试日期列表
        max_diff: 最大差异值
        correlation: 最小相关系数
        method: 测试方法描述
        issues: 发现的问题列表
    """
    passed: bool
    test_dates: list[str] = field(default_factory=list)
    max_diff: float = 0.0
    correlation: float = 1.0
    method: str = ""
    issues: list[str] = field(default_factory=list)


@dataclass
class UnitCheckReport:
    """Agent D: 单位检查报告。

    Attributes:
        passed: 是否通过
        conversions: 单位换算记录 {字段: {主板单位, 科创板单位, 换算逻辑}}
        issues: 发现的问题列表
    """
    passed: bool
    conversions: dict = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


@dataclass
class SemanticReviewReport:
    """Agent E: 语义审查报告。

    Attributes:
        passed: 是否通过
        review_text: 审查意见全文
        suggestions: 改进建议列表
    """
    passed: bool
    review_text: str = ""
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """验证汇总报告。

    Attributes:
        syntax: Agent A 报告
        execution: Agent B 报告
        leak_test: Agent C 报告
        unit_check: Agent D 报告
        semantic_review: Agent E 报告
        auto_fix_count: 自动修复尝试次数
        all_passed: 是否全部通过
        fix_history: 修复历史记录
    """
    syntax: SyntaxReport
    execution: ExecutionReport
    leak_test: LeakTestReport
    unit_check: UnitCheckReport
    semantic_review: SemanticReviewReport
    auto_fix_count: int = 0
    all_passed: bool = False
    fix_history: list[FixAttempt] = field(default_factory=list)

    def get_failed_reports(self) -> list[tuple[str, Any]]:
        """获取所有未通过的验证报告。

        Returns:
            [(验证器名称, 报告对象), ...]
        """
        name_report_pairs = [
            ("syntax", self.syntax),
            ("execution", self.execution),
            ("leak_test", self.leak_test),
            ("unit_check", self.unit_check),
            ("semantic_review", self.semantic_review),
        ]
        return [(name, report) for name, report in name_report_pairs if not report.passed]


@dataclass
class FixAttempt:
    """单次修复尝试记录。

    Attributes:
        attempt: 第几次尝试（从 0 开始）
        timestamp: 时间戳
        failed_validators: 失败的验证器名称列表
        failure_reasons: 各验证器的失败原因摘要
        fix_applied: 是否成功生成修复代码
        fix_description: 修复动作描述
        result_status: 结果状态 ("passed" / "retried" / "needs_manual")
    """
    attempt: int
    timestamp: str
    failed_validators: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    fix_applied: bool = False
    fix_description: str = ""
    result_status: str = "retried"  # "passed" / "retried" / "needs_manual"


# ============================================================
# 参数搜索
# ============================================================

@dataclass
class SearchResult:
    """参数搜索结果。

    Attributes:
        best_params: 最优参数配置
        best_rankic: 最优目标值
        optimization_history: 优化历史（Optuna trials DataFrame）
        sensitivity: 参数敏感性分析
    """
    best_params: dict = field(default_factory=dict)
    best_rankic: float = 0.0
    optimization_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    sensitivity: dict = field(default_factory=dict)


# ============================================================
# 因子开发阶段完整输出
# ============================================================

@dataclass
class DevelopmentResult:
    """因子开发阶段完整输出，对齐方案 7.2 节数据契约。

    Attributes:
        factor_dir: 因子目录路径
        factor_code_path: factor_def.py 路径
        validation: 验证汇总报告
        search_result: 参数搜索结果
        status: 最终状态 ("completed" / "needs_manual" / "validation_failed")
    """
    factor_dir: str
    factor_code_path: str
    validation: ValidationReport
    search_result: SearchResult
    status: str = "completed"  # "completed" / "needs_manual" / "validation_failed"
