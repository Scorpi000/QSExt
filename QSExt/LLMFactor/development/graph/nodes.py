# -*- coding: utf-8 -*-
"""LangGraph 节点实现。

定义因子开发流程中各节点的异步执行逻辑：
  - generate_node: 代码生成（LLM）
  - verify_node: 五 Agent 验证（确定性 + LLM）
  - fix_node: 自动修复（LLM）
  - search_node: 参数搜索（Optuna）
  - log_node: 结果汇总
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from QSExt.LLMFactor.development.config import DevelopmentConfig
from QSExt.LLMFactor.development.graph.state import DevelopmentState

logger = logging.getLogger(__name__)


# ============================================================
# 辅助函数
# ============================================================


def _dataclass_to_dict(obj: Any) -> dict:
    """将 dataclass 转为可序列化的 dict。"""
    if obj is None:
        return None
    try:
        from dataclasses import asdict
        d = asdict(obj)
        # 处理 pd.DataFrame（不可 JSON 序列化）
        for k, v in d.items():
            if hasattr(v, "to_dict"):
                d[k] = v.to_dict()
        return d
    except Exception:
        return {"repr": repr(obj)}


# ============================================================
# 节点实现
# ============================================================


async def generate_node(state: DevelopmentState) -> dict:
    """代码生成节点。

    从假设文档生成因子定义代码 + 搜索空间 + 元数据。
    同时创建工作区目录并保存初始产物。

    Returns:
        {"generated_code": {...}, "workspace_dir": "..."}
    """
    logger.info("=" * 40)
    logger.info("Step 1: 代码生成")

    from QSExt.LLMFactor.development.code_generator import CodeGenerator
    from QSExt.LLMFactor.development.workspace import WorkspaceManager

    config = DevelopmentConfig(**state["config"])
    hypothesis = state["hypothesis"]

    # 创建工作区
    ws = WorkspaceManager()
    factor_name = hypothesis.get("factor_name", "unknown_factor")
    ws_dir = ws.create_workspace(factor_name)
    logger.info("工作区: %s", ws_dir)

    # 代码生成
    generator = CodeGenerator(config)
    generated = generator.generate(hypothesis)

    # 保存到工作区（同时保存为 factor_def.py 供验证器使用）
    ws.save_factor_code(ws_dir, generated.factor_code, generated.factor_module_name)
    ws.save_factor_code(ws_dir, generated.factor_code, "factor_def")
    ws.save_metadata(ws_dir, generated.metadata)
    if generated.search_space:
        ws.save_search_space(ws_dir, generated.search_space)

    # 生成并保存 README.md
    readme = _build_readme(hypothesis, generated)
    ws.save_readme(ws_dir, readme)

    logger.info(
        "代码生成完成: %s, 搜索空间 %d 个参数",
        generated.factor_module_name,
        len(generated.search_space),
    )

    return {
        "generated_code": _dataclass_to_dict(generated),
        "workspace_dir": str(ws_dir),
    }


async def verify_node(state: DevelopmentState) -> dict:
    """验证节点。

    运行五 Agent 验证流水线（语法/执行/泄漏/单位/语义）。

    Returns:
        {"validation_report": {...}, "attempt": N}
    """
    logger.info("=" * 40)
    logger.info("Step 2: 验证 (attempt %d)", state["attempt"] + 1)

    from QSExt.LLMFactor.development.verifier import VerificationPipeline

    config = DevelopmentConfig(**state["config"])
    hypothesis = state["hypothesis"]
    ws_dir = state["workspace_dir"]

    # 运行验证
    pipeline = VerificationPipeline(config)
    report = pipeline.run_all(ws_dir, hypothesis)

    logger.info(
        "验证完成: all_passed=%s, 通过=%d/%d",
        report.all_passed,
        sum(1 for _, r in pipeline.get_results(report) if r.passed),
        len(pipeline.get_results(report)),
    )

    return {
        "validation_report": _dataclass_to_dict(report),
        "attempt": state["attempt"] + 1,
    }


async def fix_node(state: DevelopmentState) -> dict:
    """自动修复节点。

    根据验证失败报告，调用 LLM 修复因子代码。

    Returns:
        {"generated_code": {...}} （更新后的代码）
    """
    logger.info("=" * 40)
    logger.info("Step 2b: 自动修复 (attempt %d)", state["attempt"])

    from QSExt.LLMFactor.development.code_generator import CodeGenerator
    from QSExt.LLMFactor.development.workspace import WorkspaceManager

    config = DevelopmentConfig(**state["config"])
    hypothesis = state["hypothesis"]
    ws_dir = Path(state["workspace_dir"])
    gen = state["generated_code"]
    module_name = gen["factor_module_name"]

    # 加载当前代码
    ws = WorkspaceManager()
    code = ws.load_factor_code(ws_dir, module_name)

    # 收集失败信息
    report = state["validation_report"]
    failed_validators = _collect_failures(report, config)

    if not failed_validators:
        logger.info("无失败验证器，跳过修复")
        return {}

    logger.info("修复: %s", [v["name"] for v in failed_validators])

    # 调用 LLM 修复
    generator = CodeGenerator(config)
    fixed_code = generator.fix(code, hypothesis, failed_validators)

    # 保存修复后的代码（同时更新 factor_def.py）
    ws.save_factor_code(ws_dir, fixed_code, module_name)
    ws.save_factor_code(ws_dir, fixed_code, "factor_def")

    # 更新 generated_code
    gen["factor_code"] = fixed_code

    logger.info("修复完成，代码长度: %d 字符", len(fixed_code))

    return {"generated_code": gen}


def _collect_failures(report: dict, config: DevelopmentConfig) -> list[dict]:
    """从验证报告中收集失败的验证器信息。"""
    failures = []
    validator_keys = [
        ("syntax", "syntax"),
        ("execution", "execution"),
    ]
    if config.enable_leak_test:
        validator_keys.append(("leak_test", "leak_test"))
    if config.enable_unit_check:
        validator_keys.append(("unit_check", "unit_check"))
    if config.enable_semantic_review:
        validator_keys.append(("semantic_review", "semantic_review"))

    for name, key in validator_keys:
        sub = report.get(key, {})
        if not sub.get("passed", True):
            issues = sub.get("issues", [])
            # SemanticValidator 的 issues 在 review_text 中
            if name == "semantic_review" and not issues:
                review = sub.get("review_text", "")
                if review:
                    issues = [review]
            failures.append({"name": name, "issues": issues})

    return failures


async def search_node(state: DevelopmentState) -> dict:
    """参数搜索节点。

    使用 Optuna 贝叶斯搜索最优超参数。
    配置 enable_param_search=False 或搜索空间为空时跳过。

    Returns:
        {"search_result": {...}}
    """
    logger.info("=" * 40)
    logger.info("Step 3: 参数搜索")

    config = DevelopmentConfig(**state["config"])
    gen = state["generated_code"]
    search_space = gen.get("search_space", {})
    ws_dir = Path(state["workspace_dir"])

    # 检查开关
    if not config.enable_param_search:
        logger.info("参数搜索已禁用 (enable_param_search=False)，跳过")
        return {"search_result": _empty_search_result(search_space)}

    if not search_space:
        logger.info("搜索空间为空，跳过参数搜索")
        return {"search_result": _empty_search_result(search_space)}

    from QSExt.LLMFactor.development.param_searcher import ParamSearcher
    from QSExt.LLMFactor.development.workspace import WorkspaceManager

    ws = WorkspaceManager()

    # 运行参数搜索
    searcher = ParamSearcher(config)
    result = searcher.search(str(ws_dir), search_space)

    # 保存结果
    ws.save_search_result(ws_dir, result)

    # 序列化
    result_dict = {
        "best_params": result.best_params,
        "best_rankic": result.best_rankic,
        "optimization_history": result.optimization_history.to_dict()
        if hasattr(result.optimization_history, "to_dict") else [],
        "sensitivity": result.sensitivity,
    }

    return {"search_result": result_dict}


def _empty_search_result(search_space: dict) -> dict:
    """构造空的搜索结果。"""
    return {
        "best_params": {},
        "best_rankic": 0.0,
        "optimization_history": [],
        "sensitivity": {},
        "search_space": search_space,
    }


async def log_node(state: DevelopmentState) -> dict:
    """结果汇总节点。

    将验证报告和搜索结果保存到工作区，构建最终 DevelopmentResult。

    Returns:
        {"development_result": {...}}
    """
    logger.info("=" * 40)
    logger.info("结果汇总")

    from QSExt.LLMFactor.development.workspace import WorkspaceManager

    ws = WorkspaceManager()
    ws_dir = Path(state["workspace_dir"])
    gen = state["generated_code"]
    report = state["validation_report"]
    search = state["search_result"]

    # 保存验证报告
    # 从 dict 重建 ValidationReport 以便 WorkspaceManager 处理
    if report:
        from QSExt.LLMFactor.development.models import (
            ExecutionReport, LeakTestReport, SemanticReviewReport,
            SyntaxReport, UnitCheckReport, ValidationReport, FixAttempt,
        )
        from dataclasses import asdict
        import json

        val_dir = ws_dir / "validation"
        val_dir.mkdir(exist_ok=True)

        for key, filename in [
            ("syntax", "syntax_report.json"),
            ("execution", "execution_report.json"),
            ("leak_test", "leak_test_report.json"),
            ("unit_check", "unit_check_report.json"),
        ]:
            sub = report.get(key, {})
            if sub:
                (val_dir / filename).write_text(
                    json.dumps(sub, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

        # 语义审查保存为 markdown
        semantic = report.get("semantic_review", {})
        if semantic.get("review_text"):
            (val_dir / "semantic_review.md").write_text(
                semantic["review_text"], encoding="utf-8"
            )

        # 验证汇总
        (val_dir / "validation_summary.json").write_text(
            json.dumps({
                "all_passed": report.get("all_passed", False),
                "auto_fix_count": report.get("auto_fix_count", state["attempt"]),
                "fix_history": report.get("fix_history", []),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # 构建最终结果
    all_passed = report.get("all_passed", False) if report else False
    auto_fix_count = report.get("auto_fix_count", state["attempt"]) if report else 0

    # 确定状态
    if all_passed:
        status = "completed"
    elif auto_fix_count >= DevelopmentConfig(**state["config"]).max_auto_fixes:
        status = "needs_manual"
    else:
        status = "validation_failed"

    result = {
        "factor_dir": str(ws_dir),
        "factor_code_path": str(ws_dir / f"{gen['factor_module_name']}.py"),
        "validation": report,
        "search_result": search,
        "status": status,
        "auto_fix_count": auto_fix_count,
        "factor_name": gen.get("metadata", {}).get("factor_name", "unknown"),
    }

    logger.info("开发完成: status=%s, auto_fix_count=%d", status, auto_fix_count)

    return {"development_result": result}


def _build_readme(hypothesis: dict, generated) -> str:
    """从假设文档和代码生成结果构建 README.md 内容。"""
    factor_name = hypothesis.get("factor_name", "unknown")
    category = hypothesis.get("category", "")
    market = hypothesis.get("market", "A股")
    frequency = hypothesis.get("frequency", "日频")
    description = hypothesis.get("factor_description", hypothesis.get("economic_rationale", ""))
    formula = hypothesis.get("formula", hypothesis.get("calculation_pseudo", ""))
    expected = hypothesis.get("expected_characteristics", {})
    data_req = hypothesis.get("data_requirements", {})
    references = hypothesis.get("references", [])

    lines = [
        f"# {factor_name}",
        "",
        "## 基本信息",
        "",
        f"- **类别**: {category}",
        f"- **市场**: {market}",
        f"- **频率**: {frequency}",
        f"- **模块名**: {generated.factor_module_name}",
        "",
        "## 经济逻辑",
        "",
        description.strip() if description else "（无）",
        "",
    ]

    if formula:
        lines.extend([
            "## 计算公式",
            "",
            "```",
            formula.strip(),
            "```",
            "",
        ])

    if expected:
        lines.extend([
            "## 预期特征",
            "",
        ])
        for key, val in expected.items():
            if val:
                lines.append(f"- **{key}**: {val}")
        lines.append("")

    fields = data_req.get("fields", [])
    if fields:
        lines.extend([
            "## 数据需求",
            "",
        ])
        for f in fields:
            if isinstance(f, dict):
                name = f.get("name", f.get("field", ""))
                table = f.get("table", "")
                desc = f.get("description", "")
                lines.append(f"- {table} / {name}: {desc}" if table else f"- {name}: {desc}")
            else:
                lines.append(f"- {f}")
        lines.append("")

    if references:
        lines.extend([
            "## 参考文献",
            "",
        ])
        for ref in references:
            lines.append(f"- {ref}")
        lines.append("")

    lines.extend([
        "## 搜索空间",
        "",
        f"参数数量: {len(generated.search_space)}",
        "",
    ])
    for name, spec in generated.search_space.items():
        lines.append(f"- `{name}`: {spec}")

    return "\n".join(lines)
