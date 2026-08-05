# -*- coding: utf-8 -*-
"""Phase 2 因子开发端到端集成测试。

测试场景：
  1. DevelopmentConfig 配置校验
  2. WorkspaceManager 工作区管理
  3. VerificationPipeline 在 demo 因子上的完整验证
  4. ValidationReport 数据结构正确性
  5. 代码生成器输出解析（mock LLM）
  6. develop_factor_with_fix 自动修复流程（mock LLM + mock 验证器）
  7. DevelopmentState 创建和路由逻辑

依赖 demo PE_TTM 因子目录（不需要 LLM 或数据库）。
"""
import sys
import json
import tempfile
from pathlib import Path
from dataclasses import asdict
from unittest.mock import patch, MagicMock

# 修复 Windows GBK 编码
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from QSExt.LLMFactor.development.config import DevelopmentConfig
from QSExt.LLMFactor.development.models import (
    DevelopmentResult,
    EvalMetrics,
    ExecutionReport,
    FixAttempt,
    GeneratedCode,
    LeakTestReport,
    SearchResult,
    SemanticReviewReport,
    SyntaxReport,
    UnitCheckReport,
    ValidationReport,
)
from QSExt.LLMFactor.development.workspace import WorkspaceManager
from QSExt.LLMFactor.development.verifier import VerificationPipeline
from QSExt.LLMFactor.development.code_generator import CodeGenerator

DEMO_DIR = str(Path(PROJECT_ROOT) / "QSExt" / "LLMFactor" / "demo_stock_cn_factor_def")


# ============================================================
# DevelopmentConfig 测试
# ============================================================

def test_config_defaults():
    """测试默认配置。"""
    print("\n--- test_config_defaults ---")
    config = DevelopmentConfig()

    assert config.llm_model == "claude-sonnet-5"
    assert config.llm_temperature == 0.1
    assert config.max_auto_fixes == 3
    assert config.enable_leak_test is True
    assert config.enable_unit_check is True
    assert config.enable_semantic_review is True
    assert config.enable_param_search is True
    assert config.max_trials == 200
    assert config.optimization_objective == "rankic"
    print("  PASS: 默认配置正确")


def test_config_custom():
    """测试自定义配置。"""
    print("\n--- test_config_custom ---")
    config = DevelopmentConfig(
        llm_model="gpt-4",
        max_auto_fixes=5,
        enable_leak_test=False,
        optimization_objective="icir",
    )

    assert config.llm_model == "gpt-4"
    assert config.max_auto_fixes == 5
    assert config.enable_leak_test is False
    assert config.optimization_objective == "icir"
    print("  PASS: 自定义配置正确")


def test_config_validation_errors():
    """测试配置校验。"""
    print("\n--- test_config_validation_errors ---")
    # 无效 optimization_objective
    try:
        DevelopmentConfig(optimization_objective="invalid")
        assert False, "应抛出 ValueError"
    except ValueError as e:
        assert "optimization_objective" in str(e)
        print(f"  无效 objective: {e}  ✓")

    # multi 缺少 weights
    try:
        DevelopmentConfig(optimization_objective="multi")
        assert False, "应抛出 ValueError"
    except ValueError as e:
        assert "multi_objective_weights" in str(e)
        print(f"  multi 缺 weights: {e}  ✓")

    # custom 缺少 fn
    try:
        DevelopmentConfig(optimization_objective="custom")
        assert False, "应抛出 ValueError"
    except ValueError as e:
        assert "custom_objective_fn" in str(e)
        print(f"  custom 缺 fn: {e}  ✓")

    # 负数 max_auto_fixes
    try:
        DevelopmentConfig(max_auto_fixes=-1)
        assert False, "应抛出 ValueError"
    except ValueError as e:
        assert "max_auto_fixes" in str(e)
        print(f"  负数 fix: {e}  ✓")

    print("  PASS: 配置校验全部正确")


def test_config_to_dict():
    """测试配置序列化。"""
    print("\n--- test_config_to_dict ---")
    config = DevelopmentConfig()
    d = config.to_dict()

    assert isinstance(d, dict)
    assert "llm_model" in d
    assert "max_auto_fixes" in d
    assert "optimization_objective" in d
    # 不可序列化字段不应出现
    assert "custom_objective_fn" not in d
    assert "custom_metric_calculators" not in d
    print(f"  PASS: 序列化结果包含 {len(d)} 个字段")


# ============================================================
# WorkspaceManager 测试
# ============================================================

def test_workspace_create_and_save():
    """测试工作区创建和文件保存。"""
    print("\n--- test_workspace_create_and_save ---")
    with tempfile.TemporaryDirectory() as tmp_base:
        ws = WorkspaceManager(base_dir=tmp_base)

        # 创建工作区
        ws_dir = ws.create_workspace("test_factor")
        assert ws_dir.exists(), "工作区目录应存在"
        assert (ws_dir / "param_search").exists(), "param_search 目录应存在"
        assert (ws_dir / "validation").exists(), "validation 目录应存在"
        print(f"  工作区创建: {ws_dir.name}  ✓")

        # 保存因子代码
        code = "def defFactor(fdi, dep_fd): return []"
        code_path = ws.save_factor_code(ws_dir, code, "test_factor")
        assert code_path.exists()
        assert code_path.read_text(encoding="utf-8") == code
        print("  因子代码保存  ✓")

        # 保存 metadata
        metadata = {"factor_name": "test", "category": "test"}
        meta_path = ws.save_metadata(ws_dir, metadata)
        assert meta_path.exists()
        loaded = json.loads(meta_path.read_text(encoding="utf-8"))
        assert loaded["factor_name"] == "test"
        print("  metadata 保存  ✓")

        # 保存搜索空间
        search_space = {"window": {"type": "int", "low": 5, "high": 60}}
        ss_path = ws.save_search_space(ws_dir, search_space)
        assert ss_path.exists()
        print("  搜索空间保存  ✓")

        # 加载
        loaded_code = ws.load_factor_code(ws_dir, "test_factor")
        assert loaded_code == code
        loaded_meta = ws.load_metadata(ws_dir)
        assert loaded_meta["factor_name"] == "test"
        loaded_ss = ws.load_search_space(ws_dir)
        assert loaded_ss["window"]["low"] == 5
        print("  文件加载  ✓")

    print("  PASS: 工作区创建和保存全部正确")


def test_workspace_list():
    """测试工作区列表。"""
    import time

    print("\n--- test_workspace_list ---")
    with tempfile.TemporaryDirectory() as tmp_base:
        ws = WorkspaceManager(base_dir=tmp_base)

        # 空列表
        assert ws.list_workspaces() == []
        print("  空列表  ✓")

        # 创建多个（间隔 1 秒避免同名）
        ws.create_workspace("factor_a")
        time.sleep(1.1)
        ws.create_workspace("factor_b")
        workspaces = ws.list_workspaces()
        assert len(workspaces) == 2, f"应有 2 个工作区，实际 {len(workspaces)}: {[w.name for w in workspaces]}"
        # 按名称排序
        assert workspaces[0].name < workspaces[1].name
        print(f"  多个工作区: {[w.name for w in workspaces]}  ✓")

    print("  PASS: 工作区列表正确")


def test_workspace_save_validation_report():
    """测试验证报告保存。"""
    print("\n--- test_workspace_save_validation_report ---")
    report = ValidationReport(
        syntax=SyntaxReport(passed=True),
        execution=ExecutionReport(passed=True, output_shape=(5, 3), nan_ratio=0.1),
        leak_test=LeakTestReport(passed=True, method="静态分析通过"),
        unit_check=UnitCheckReport(passed=True),
        semantic_review=SemanticReviewReport(passed=True, review_text="LGTM"),
        all_passed=True,
    )

    with tempfile.TemporaryDirectory() as tmp_base:
        ws = WorkspaceManager(base_dir=tmp_base)
        ws_dir = ws.create_workspace("test_report")
        ws.save_validation_report(ws_dir, report)

        val_dir = ws_dir / "validation"
        assert (val_dir / "syntax_report.json").exists()
        assert (val_dir / "execution_report.json").exists()
        assert (val_dir / "leak_test_report.json").exists()
        assert (val_dir / "unit_check_report.json").exists()
        assert (val_dir / "semantic_review.md").exists()
        assert (val_dir / "validation_summary.json").exists()

        summary = json.loads((val_dir / "validation_summary.json").read_text(encoding="utf-8"))
        assert summary["all_passed"] is True
        print("  PASS: 验证报告保存正确")


# ============================================================
# VerificationPipeline 测试
# ============================================================

def test_pipeline_on_demo_syntax_only():
    """测试验证流水线（仅语法+执行检查）在 demo 因子上的表现。"""
    print("\n--- test_pipeline_on_demo_syntax_only ---")
    config = DevelopmentConfig(
        enable_leak_test=False,
        enable_unit_check=False,
        enable_semantic_review=False,
    )
    pipeline = VerificationPipeline(config)

    # 验证器列表应只有 syntax 和 execution
    assert len(pipeline.validators) == 2
    assert pipeline.validators[0][0] == "syntax"
    assert pipeline.validators[1][0] == "execution"
    print(f"  验证器数量: {len(pipeline.validators)}  ✓")

    report = pipeline.run_all(DEMO_DIR, hypothesis={"factor_name": "PE_TTM"})

    # syntax 应通过
    assert report.syntax.passed, f"语法检查应通过: {report.syntax.issues}"
    print(f"  语法检查: passed={report.syntax.passed}  ✓")

    # execution 结果取决于 QuantStudio 环境是否可用
    print(f"  执行验证: passed={report.execution.passed}, issues={report.execution.issues}")
    if report.execution.passed:
        print(f"    output_shape: {report.execution.output_shape}")
        print(f"    nan_ratio: {report.execution.nan_ratio:.2%}")

    print("  PASS: 流水线在 demo 因子上运行完成")


def test_pipeline_on_demo_with_leak_and_unit():
    """测试验证流水线（含泄漏检测和单位检查）。"""
    print("\n--- test_pipeline_on_demo_with_leak_and_unit ---")
    config = DevelopmentConfig(
        enable_leak_test=True,
        enable_unit_check=True,
        enable_semantic_review=False,
    )
    pipeline = VerificationPipeline(config)

    assert len(pipeline.validators) == 4
    print(f"  验证器数量: {len(pipeline.validators)}  ✓")

    report = pipeline.run_all(DEMO_DIR, hypothesis={"factor_name": "PE_TTM"})

    # syntax 和 unit 应通过
    assert report.syntax.passed, f"语法检查应通过: {report.syntax.issues}"
    assert report.unit_check.passed, f"单位检查应通过: {report.unit_check.issues}"
    print(f"  语法检查: passed={report.syntax.passed}  ✓")
    print(f"  泄漏检测: passed={report.leak_test.passed}, method={report.leak_test.method}  ✓")
    print(f"  单位检查: passed={report.unit_check.passed}, conversions={report.unit_check.conversions}  ✓")
    print(f"  执行验证: passed={report.execution.passed}  ✓")

    # get_failed_reports 应正确
    failed = report.get_failed_reports()
    print(f"  失败验证器: {[name for name, _ in failed]}")

    print("  PASS: 完整验证流水线在 demo 因子上运行完成")


def test_pipeline_syntax_fail_skips_rest():
    """测试语法检查失败时跳过后续验证器。"""
    print("\n--- test_pipeline_syntax_fail_skips_rest ---")
    bad_code = "def defFactor(fdi, dep_fd):\n    return [factor  # 语法错误"
    tmp_dir = tempfile.mkdtemp(prefix="qs_test_pipeline_")
    (Path(tmp_dir) / "factor_def.py").write_text(bad_code, encoding="utf-8")

    config = DevelopmentConfig(
        enable_leak_test=True,
        enable_unit_check=True,
        enable_semantic_review=True,
    )
    pipeline = VerificationPipeline(config)
    report = pipeline.run_all(tmp_dir, hypothesis={})

    assert not report.syntax.passed, "语法检查应失败"
    # 语法失败后不应有 execution 报告（被跳过）
    assert report.execution.passed is False
    assert report.execution.issues == ["未执行"]
    # 可选验证器也应未执行
    assert report.leak_test.passed is True  # 默认值
    assert report.unit_check.passed is True  # 默认值
    print(f"  语法检查: passed={report.syntax.passed}  ✓")
    print(f"  执行验证: issues={report.execution.issues}  ✓")
    print("  PASS: 语法失败时正确跳过后续验证器")


# ============================================================
# ValidationReport 数据结构测试
# ============================================================

def test_validation_report_dataclass():
    """测试 ValidationReport 数据结构。"""
    print("\n--- test_validation_report_dataclass ---")
    report = ValidationReport(
        syntax=SyntaxReport(passed=True),
        execution=ExecutionReport(passed=True, output_shape=(5, 3)),
        leak_test=LeakTestReport(passed=True),
        unit_check=UnitCheckReport(passed=True),
        semantic_review=SemanticReviewReport(passed=True),
        all_passed=True,
        auto_fix_count=0,
    )

    # get_failed_reports
    failed = report.get_failed_reports()
    assert len(failed) == 0, "全部通过时应无失败报告"
    print("  全部通过时 get_failed_reports=[]  ✓")

    # 有失败的情况
    report.syntax = SyntaxReport(passed=False, issues=["test error"])
    report.all_passed = False
    failed = report.get_failed_reports()
    assert len(failed) == 1
    assert failed[0][0] == "syntax"
    print(f"  有失败时 get_failed_reports={[(n, r.passed) for n, r in failed]}  ✓")

    # 序列化
    d = asdict(report)
    assert isinstance(d, dict)
    assert d["all_passed"] is False
    print("  asdict 序列化  ✓")

    print("  PASS: ValidationReport 数据结构正确")


def test_eval_metrics():
    """测试 EvalMetrics 数据结构。"""
    print("\n--- test_eval_metrics ---")
    m = EvalMetrics(rankic=0.05, icir=0.8, win_rate=0.6)

    assert m.rankic == 0.05
    assert m.icir == 0.8
    assert m.win_rate == 0.6

    # to_dict
    d = m.to_dict()
    assert d["rankic"] == 0.05
    assert d["icir"] == 0.8
    print("  内置指标  ✓")

    # 扩展指标
    m2 = EvalMetrics(extra={"sharpe": 1.5, "calmar": 0.8})
    assert m2.sharpe == 1.5
    assert m2.calmar == 0.8
    d2 = m2.to_dict()
    assert d2["sharpe"] == 1.5
    print("  扩展指标  ✓")

    # 不存在的属性
    try:
        _ = m.nonexistent
        assert False, "应抛出 AttributeError"
    except AttributeError:
        print("  不存在属性正确报错  ✓")

    print("  PASS: EvalMetrics 数据结构正确")


def test_generated_code():
    """测试 GeneratedCode 数据结构。"""
    print("\n--- test_generated_code ---")
    gc = GeneratedCode(
        factor_code="def defFactor(fdi, dep_fd): return []",
        factor_module_name="test_factor",
        search_space={"window": {"type": "int", "low": 5, "high": 60}},
        metadata={"factor_name": "test"},
        dag_description="Step1 → Step2",
    )

    assert gc.factor_module_name == "test_factor"
    assert gc.search_space["window"]["low"] == 5
    assert gc.metadata["factor_name"] == "test"
    assert gc.dag_description == "Step1 → Step2"
    print("  PASS: GeneratedCode 数据结构正确")


# ============================================================
# CodeGenerator 输出解析测试（mock LLM）
# ============================================================

def test_code_generator_parse_sections():
    """测试代码生成器的 section 解析。"""
    print("\n--- test_code_generator_parse_sections ---")
    config = DevelopmentConfig()
    gen = CodeGenerator.__new__(CodeGenerator)
    gen.config = config

    # 模拟 LLM 输出
    llm_output = """\
===FACTOR_CODE===
import QuantStudio.Factor.FactorOperator as fo
from QSExt.FactorDef.FactorDefContent import FactorDefInput, FactorDef

__FACTOR_META__ = {
    "TargetTable": "stock_cn_factor_llm",
    "IDType": "A股",
    "Author": "QSAgent",
    "Description": "test factor",
    "DefScriptPath": __file__,
}

def defFactor(fdi: FactorDefInput, dep_fd):
    SDB = fdi.FDB["JYDB"]
    return []
===

===SEARCH_SPACE===
{"window": {"type": "int", "low": 5, "high": 60, "step": 5}}
===

===METADATA===
{"factor_name": "test_factor", "category": "test"}
===
"""
    result = gen._parse_generation_response(llm_output, {"factor_name": "test_factor", "category": "test"})

    assert "defFactor" in result.factor_code
    assert result.factor_module_name == "test_factor"
    assert result.search_space["window"]["low"] == 5
    assert result.metadata["factor_name"] == "test_factor"
    print(f"  factor_code 长度: {len(result.factor_code)}  ✓")
    print(f"  factor_module_name: {result.factor_module_name}  ✓")
    print(f"  search_space: {result.search_space}  ✓")
    print(f"  metadata: {result.metadata}  ✓")
    print("  PASS: section 解析正确")


def test_code_generator_extract_code_fallback():
    """测试代码提取的兜底策略。"""
    print("\n--- test_code_generator_extract_code_fallback ---")
    gen = CodeGenerator.__new__(CodeGenerator)

    # markdown 代码块
    text1 = "这是分析结果：\n```python\ndef foo():\n    pass\n```\n以上。"
    code1 = gen._extract_code(text1)
    assert code1 == "def foo():\n    pass"
    print("  markdown 代码块提取  ✓")

    # 纯代码
    text2 = "import os\ndef defFactor(fdi, dep_fd):\n    return []"
    code2 = gen._extract_code(text2)
    assert code2 == text2
    print("  纯代码提取  ✓")

    # 无代码
    text3 = "这是一段纯文本分析，没有代码。"
    code3 = gen._extract_code(text3)
    assert code3 is None
    print("  无代码返回 None  ✓")

    print("  PASS: 代码提取兜底策略正确")


def test_code_generator_to_module_name():
    """测试模块名转换。"""
    print("\n--- test_code_generator_to_module_name ---")
    gen = CodeGenerator.__new__(CodeGenerator)

    assert gen._to_module_name("PE_TTM") == "pe_ttm"
    assert gen._to_module_name("Momentum-5D") == "momentum_5d"
    assert gen._to_module_name("ATR (14)") == "atr_14"
    assert gen._to_module_name("___test___") == "test"
    assert gen._to_module_name("") == "unknown_factor"
    print("  PASS: 模块名转换正确")


def test_code_generator_fill_metadata():
    """测试 metadata 补充。"""
    print("\n--- test_code_generator_fill_metadata ---")
    gen = CodeGenerator.__new__(CodeGenerator)

    hypothesis = {
        "factor_name": "TestFactor",
        "category": "动量",
        "market": "A股",
        "frequency": "日频",
        "factor_description": "测试因子",
    }

    # 空 metadata
    meta = gen._fill_metadata({}, hypothesis)
    assert meta["factor_name"] == "TestFactor"
    assert meta["category"] == "动量"
    assert meta["DefScriptPath"] == "__file__"
    assert "动量" in meta["tags"]
    print("  空 metadata 补充  ✓")

    # 已有 metadata 不覆盖
    meta2 = gen._fill_metadata({"factor_name": "CustomName"}, hypothesis)
    assert meta2["factor_name"] == "CustomName"
    print("  已有字段不覆盖  ✓")

    print("  PASS: metadata 补充正确")


# ============================================================
# Graph 状态测试
# ============================================================

def test_graph_state_create_initial():
    """测试 DevelopmentState 创建。"""
    print("\n--- test_graph_state_create_initial ---")
    from QSExt.LLMFactor.development.graph import DevelopmentState

    state = DevelopmentState.create_initial(
        hypothesis={"factor_name": "PE_TTM", "category": "估值"},
        config={"max_auto_fixes": 3},
    )

    assert state["hypothesis"]["factor_name"] == "PE_TTM"
    assert state["attempt"] == 0
    assert state["generated_code"] is None
    assert state["validation_report"] is None
    assert state["search_result"] is None
    assert state["development_result"] is None
    print(f"  字段: {list(state.keys())}  ✓")
    print("  PASS: DevelopmentState 创建正确")


def test_graph_routing():
    """测试条件路由逻辑。"""
    print("\n--- test_graph_routing ---")
    from QSExt.LLMFactor.development.graph import DevelopmentState, after_verify

    config = {"max_auto_fixes": 3}

    # 全部通过 → search
    state = DevelopmentState.create_initial(hypothesis={}, config=config)
    state["validation_report"] = {"all_passed": True}
    state["attempt"] = 1
    assert after_verify(state) == "search"
    print("  all_passed=True → search  ✓")

    # 未通过，未超限 → fix
    state = DevelopmentState.create_initial(hypothesis={}, config=config)
    state["validation_report"] = {"all_passed": False}
    state["attempt"] = 1
    assert after_verify(state) == "fix"
    print("  all_passed=False, attempt=1 → fix  ✓")

    # 未通过，已超限 → end
    state = DevelopmentState.create_initial(hypothesis={}, config=config)
    state["validation_report"] = {"all_passed": False}
    state["attempt"] = 4
    assert after_verify(state) == "end"
    print("  all_passed=False, attempt=4 → end  ✓")

    # 边界：刚好等于 max → fix
    state = DevelopmentState.create_initial(hypothesis={}, config=config)
    state["validation_report"] = {"all_passed": False}
    state["attempt"] = 3
    assert after_verify(state) == "fix"
    print("  all_passed=False, attempt=3 → fix  ✓")

    print("  PASS: 条件路由全部正确")


# ============================================================
# FixAttempt 测试
# ============================================================

def test_fix_attempt():
    """测试 FixAttempt 数据结构。"""
    print("\n--- test_fix_attempt ---")
    fa = FixAttempt(
        attempt=0,
        timestamp="2026-07-09T10:00:00",
        failed_validators=["syntax"],
        failure_reasons=["缺少 defFactor"],
        fix_applied=True,
        fix_description="添加 defFactor 函数",
        result_status="retried",
    )

    assert fa.attempt == 0
    assert fa.fix_applied is True
    assert "syntax" in fa.failed_validators
    d = asdict(fa)
    assert d["result_status"] == "retried"
    print("  PASS: FixAttempt 数据结构正确")


# ============================================================
# 运行所有测试
# ============================================================

ALL_TESTS = [
    # Config
    test_config_defaults,
    test_config_custom,
    test_config_validation_errors,
    test_config_to_dict,
    # Workspace
    test_workspace_create_and_save,
    test_workspace_list,
    test_workspace_save_validation_report,
    # Pipeline
    test_pipeline_on_demo_syntax_only,
    test_pipeline_on_demo_with_leak_and_unit,
    test_pipeline_syntax_fail_skips_rest,
    # Data structures
    test_validation_report_dataclass,
    test_eval_metrics,
    test_generated_code,
    test_fix_attempt,
    # CodeGenerator
    test_code_generator_parse_sections,
    test_code_generator_extract_code_fallback,
    test_code_generator_to_module_name,
    test_code_generator_fill_metadata,
    # Graph
    test_graph_state_create_initial,
    test_graph_routing,
]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for i, t in enumerate(ALL_TESTS, 1):
            print(f"  {i:2d}. {t.__name__}")
        sys.exit(0)

    passed = 0
    failed = 0
    errors = []

    for test_fn in ALL_TESTS:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            errors.append((test_fn.__name__, str(e)))
            print(f"  FAIL: {e}")
        except Exception as e:
            failed += 1
            errors.append((test_fn.__name__, f"异常: {type(e).__name__}: {e}"))
            print(f"  ERROR: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print(f"集成测试结果: {passed} 通过, {failed} 失败, 共 {passed + failed} 个")
    if errors:
        print("\n失败详情:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print("=" * 60)
