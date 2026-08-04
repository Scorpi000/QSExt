# -*- coding: utf-8 -*-
"""Step 2: 五 Agent 验证流水线编排。

编排五个验证 Agent，确保生成的代码正确、无泄漏、语义一致。
支持自动修复循环（最多 N 次，由配置控制）。

验证顺序：
    1. Agent A: 语法检查（必须通过才继续）
    2. Agent B: 执行验证（必须通过才继续）
    3. Agent C: 未来信息检测（可选）
    4. Agent D: 单位检查（可选）
    5. Agent E: 语义审查（可选，LLM）

使用示例::

    from QSExt.LLMFactor.development.verifier import VerificationPipeline
    from QSExt.LLMFactor.development.config import DevelopmentConfig

    config = DevelopmentConfig()
    pipeline = VerificationPipeline(config)
    report = pipeline.run_all(factor_dir, hypothesis)
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from QSExt.LLMFactor.development.config import DevelopmentConfig
from QSExt.LLMFactor.development.models import (
    ExecutionReport,
    FixAttempt,
    LeakTestReport,
    SemanticReviewReport,
    SyntaxReport,
    UnitCheckReport,
    ValidationReport,
)
from QSExt.LLMFactor.development.validators.syntax_validator import SyntaxValidator
from QSExt.LLMFactor.development.validators.execution_validator import ExecutionValidator
from QSExt.LLMFactor.development.validators.leak_validator import LeakValidator
from QSExt.LLMFactor.development.validators.unit_validator import UnitValidator
from QSExt.LLMFactor.development.validators.semantic_validator import SemanticValidator

__QS_Logger__ = logging.getLogger("QSR.development.verifier")


class VerificationPipeline:
    """五 Agent 验证流水线。

    根据配置动态启用/禁用各验证器。语法检查和执行验证始终启用。

    Attributes:
        config: 开发配置
        validators: 验证器列表（按执行顺序）
    """

    def __init__(self, config: DevelopmentConfig):
        self.config = config

        # 始终启用的验证器
        self.validators = [
            ("syntax", SyntaxValidator()),
            ("execution", ExecutionValidator()),
        ]

        # 可选验证器（由配置控制）
        if config.enable_leak_test:
            self.validators.append(("leak_test", LeakValidator()))
        if config.enable_unit_check:
            self.validators.append(("unit_check", UnitValidator()))
        if config.enable_semantic_review:
            self.validators.append(("semantic_review", SemanticValidator(config)))

    def run_all(self, factor_dir: str, hypothesis: dict) -> ValidationReport:
        """运行所有验证器。

        Args:
            factor_dir: 因子目录路径
            hypothesis: 假设文档

        Returns:
            ValidationReport
        """
        results = {}

        for name, validator in self.validators:
            __QS_Logger__.info(f"运行验证器: {name}")
            try:
                result = validator.validate(factor_dir, hypothesis)
                results[name] = result

                if not result.passed:
                    __QS_Logger__.warning(f"验证器 {name} 未通过: {result.issues}")
                    # Agent A/B 失败则跳过后续验证（依赖关系）
                    if name in ("syntax", "execution"):
                        __QS_Logger__.info(f"跳过后续验证器（{name} 未通过）")
                        break
                else:
                    __QS_Logger__.info(f"验证器 {name} 通过")
            except Exception as e:
                __QS_Logger__.error(f"验证器 {name} 异常: {e}")
                results[name] = self._create_error_report(name, e)

        # 构建汇总报告
        report = ValidationReport(
            syntax=results.get("syntax", SyntaxReport(passed=False, issues=["未执行"])),
            execution=results.get("execution", ExecutionReport(passed=False, issues=["未执行"])),
            leak_test=results.get("leak_test", LeakTestReport(passed=True, method="未启用")),
            unit_check=results.get("unit_check", UnitCheckReport(passed=True)),
            semantic_review=results.get("semantic_review", SemanticReviewReport(passed=True)),
            all_passed=all(r.passed for r in results.values()),
        )

        return report

    def get_results(self, report: ValidationReport) -> list[tuple[str, any]]:
        """从报告中提取所有验证器名称和结果。

        Args:
            report: 验证报告

        Returns:
            [(名称, 报告), ...]
        """
        pairs = [
            ("syntax", report.syntax),
            ("execution", report.execution),
        ]
        if self.config.enable_leak_test:
            pairs.append(("leak_test", report.leak_test))
        if self.config.enable_unit_check:
            pairs.append(("unit_check", report.unit_check))
        if self.config.enable_semantic_review:
            pairs.append(("semantic_review", report.semantic_review))
        return pairs

    def _create_error_report(self, name: str, error: Exception):
        """为异常的验证器创建错误报告。"""
        error_msg = f"验证器异常: {error}"
        if name == "syntax":
            return SyntaxReport(passed=False, issues=[error_msg])
        elif name == "execution":
            return ExecutionReport(passed=False, issues=[error_msg])
        elif name == "leak_test":
            return LeakTestReport(passed=False, issues=[error_msg])
        elif name == "unit_check":
            return UnitCheckReport(passed=False, issues=[error_msg])
        elif name == "semantic_review":
            return SemanticReviewReport(passed=False, review_text=error_msg)
        else:
            return SyntaxReport(passed=False, issues=[error_msg])


def develop_factor_with_fix(
    hypothesis: dict,
    config: DevelopmentConfig,
    generated_code: "GeneratedCode",
    workspace_dir: Path,
    code_generator: "CodeGenerator",
) -> ValidationReport:
    """带自动修复的验证流程。

    Args:
        hypothesis: 假设文档
        config: 开发配置
        generated_code: 代码生成结果
        workspace_dir: 工作区目录
        code_generator: 代码生成器

    Returns:
        最终的 ValidationReport
    """
    from QSExt.LLMFactor.development.workspace import WorkspaceManager

    ws = WorkspaceManager()
    verifier = VerificationPipeline(config)
    fix_history: list[FixAttempt] = []
    module_name = generated_code.factor_module_name

    for attempt in range(config.max_auto_fixes + 1):
        __QS_Logger__.info(f"验证尝试 {attempt + 1}/{config.max_auto_fixes + 1}")

        # 运行验证
        report = verifier.run_all(str(workspace_dir), hypothesis)

        if report.all_passed:
            fix_history.append(FixAttempt(
                attempt=attempt,
                timestamp=datetime.now().isoformat(),
                failed_validators=[],
                failure_reasons=[],
                fix_applied=False,
                fix_description="全部通过",
                result_status="passed",
            ))
            __QS_Logger__.info("所有验证通过")
            break

        # 收集失败信息
        failed_info = []
        failed_names = []
        for name, result in verifier.get_results(report):
            if not result.passed:
                failed_names.append(name)
                failed_info.append({
                    "name": name,
                    "issues": result.issues,
                })

        if attempt < config.max_auto_fixes:
            # 自动修复
            __QS_Logger__.info(f"尝试修复: {failed_names}")
            try:
                code = ws.load_factor_code(workspace_dir, module_name)
                fixed_code = code_generator.fix(code, hypothesis, failed_info)
                ws.save_factor_code(workspace_dir, fixed_code, module_name)

                fix_history.append(FixAttempt(
                    attempt=attempt,
                    timestamp=datetime.now().isoformat(),
                    failed_validators=failed_names,
                    failure_reasons=[str(info["issues"]) for info in failed_info],
                    fix_applied=True,
                    fix_description=f"修复 {', '.join(failed_names)}",
                    result_status="retried",
                ))
            except Exception as e:
                __QS_Logger__.error(f"自动修复失败: {e}")
                fix_history.append(FixAttempt(
                    attempt=attempt,
                    timestamp=datetime.now().isoformat(),
                    failed_validators=failed_names,
                    failure_reasons=[str(info["issues"]) for info in failed_info],
                    fix_applied=False,
                    fix_description=f"修复异常: {e}",
                    result_status="needs_manual",
                ))
                break
        else:
            # 超过最大修复次数
            __QS_Logger__.warning(f"超过最大修复次数 ({config.max_auto_fixes})")
            fix_history.append(FixAttempt(
                attempt=attempt,
                timestamp=datetime.now().isoformat(),
                failed_validators=failed_names,
                failure_reasons=[str(info["issues"]) for info in failed_info],
                fix_applied=False,
                fix_description="超过最大修复次数",
                result_status="needs_manual",
            ))

    # 更新报告
    report.auto_fix_count = attempt
    report.fix_history = fix_history
    return report
