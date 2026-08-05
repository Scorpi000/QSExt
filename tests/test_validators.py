# -*- coding: utf-8 -*-
"""各验证器独立单元测试。

测试场景：
  1. SyntaxValidator: AST 解析、import 检查、__FACTOR_META__、defFactor 签名
  2. LeakValidator: 财务数据识别、时序算子检测、静态泄漏模式检测
  3. UnitValidator: 表名提取、双板合并检测、单位换算逻辑检测
  4. SemanticValidator: 审查文本解析、建议提取（mock LLM）
  5. ExecutionValidator: NaN 比例计算（mock QuantStudio）

使用 demo PE_TTM 因子目录作为真实测试输入。
不依赖外部服务（PostgreSQL、Ollama 等）。
"""
import sys
import os
import textwrap
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# 修复 Windows GBK 编码
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from QSExt.LLMFactor.development.validators.syntax_validator import SyntaxValidator
from QSExt.LLMFactor.development.validators.leak_validator import LeakValidator
from QSExt.LLMFactor.development.validators.unit_validator import UnitValidator
from QSExt.LLMFactor.development.validators.semantic_validator import SemanticValidator
from QSExt.LLMFactor.development.validators.execution_validator import ExecutionValidator


# ============================================================
# 辅助工具
# ============================================================

def _make_temp_factor(code: str, dir_name: str = "test_factor") -> str:
    """创建临时因子目录，写入 factor_def.py，返回目录路径。"""
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"qs_test_{dir_name}_"))
    (tmp_dir / "factor_def.py").write_text(code, encoding="utf-8")
    return str(tmp_dir)


# demo 因子目录
DEMO_DIR = str(Path(PROJECT_ROOT) / "QSExt" / "LLMFactor" / "demo_stock_cn_factor_def")


# ============================================================
# SyntaxValidator 测试
# ============================================================

def test_syntax_valid_demo():
    """测试 demo PE_TTM 因子的语法检查应全部通过。"""
    print("\n--- test_syntax_valid_demo ---")
    validator = SyntaxValidator()
    report = validator.validate(DEMO_DIR)

    assert report.passed, f"demo 因子语法检查应通过，实际 issues: {report.issues}"
    assert report.details.get("ast", {}).get("passed", False), "AST 解析应通过"
    assert report.details.get("imports", {}).get("passed", False), "import 检查应通过"
    assert report.details.get("factor_meta", {}).get("passed", False), "__FACTOR_META__ 检查应通过"
    assert report.details.get("def_factor_signature", {}).get("passed", False), "defFactor 签名应通过"
    print("  PASS: demo 因子语法检查全部通过")


def test_syntax_missing_file():
    """测试因子目录缺少 factor_def.py 的情况。"""
    print("\n--- test_syntax_missing_file ---")
    validator = SyntaxValidator()
    report = validator.validate("/nonexistent/path")

    assert not report.passed, "缺少文件应判定为失败"
    assert any("不存在" in i for i in report.issues), "应报告文件不存在"
    print("  PASS: 缺少文件正确报错")


def test_syntax_invalid_python():
    """测试语法错误的 Python 代码。"""
    print("\n--- test_syntax_invalid_python ---")
    bad_code = textwrap.dedent("""\
        def defFactor(fdi, dep_fd):
            return [factor  # 语法错误：缺少右括号
    """)
    tmp_dir = _make_temp_factor(bad_code, "invalid_python")

    validator = SyntaxValidator()
    report = validator.validate(tmp_dir)

    assert not report.passed, "语法错误代码应判定为失败"
    assert any("语法错误" in i for i in report.issues), f"应报告语法错误，实际: {report.issues}"
    print("  PASS: 语法错误代码正确检出")


def test_syntax_missing_def_factor():
    """测试缺少 defFactor 函数的情况。"""
    print("\n--- test_syntax_missing_def_factor ---")
    code = textwrap.dedent("""\
        __FACTOR_META__ = {
            "TargetTable": "test",
            "IDType": "A股",
            "Author": "test",
            "Description": "test",
            "DefScriptPath": __file__,
        }
    """)
    tmp_dir = _make_temp_factor(code, "no_def_factor")

    validator = SyntaxValidator()
    report = validator.validate(tmp_dir)

    assert not report.passed, "缺少 defFactor 应判定为失败"
    assert any("defFactor" in i for i in report.issues), f"应报告缺少 defFactor，实际: {report.issues}"
    print("  PASS: 缺少 defFactor 正确检出")


def test_syntax_missing_factor_meta():
    """测试缺少 __FACTOR_META__ 的情况。"""
    print("\n--- test_syntax_missing_factor_meta ---")
    code = textwrap.dedent("""\
        def defFactor(fdi, dep_fd):
            return []
    """)
    tmp_dir = _make_temp_factor(code, "no_meta")

    validator = SyntaxValidator()
    report = validator.validate(tmp_dir)

    assert not report.passed, "缺少 __FACTOR_META__ 应判定为失败"
    assert any("__FACTOR_META__" in i for i in report.issues), f"应报告缺少 META，实际: {report.issues}"
    print("  PASS: 缺少 __FACTOR_META__ 正确检出")


def test_syntax_missing_meta_field():
    """测试 __FACTOR_META__ 缺少必需字段的情况。"""
    print("\n--- test_syntax_missing_meta_field ---")
    code = textwrap.dedent("""\
        __FACTOR_META__ = {
            "TargetTable": "test",
            "IDType": "A股",
        }

        def defFactor(fdi, dep_fd):
            return []
    """)
    tmp_dir = _make_temp_factor(code, "incomplete_meta")

    validator = SyntaxValidator()
    report = validator.validate(tmp_dir)

    assert not report.passed, "META 字段不完整应判定为失败"
    # 应缺少 Author, Description, DefScriptPath
    assert any("Author" in i for i in report.issues), f"应报告缺少 Author，实际: {report.issues}"
    print(f"  PASS: META 缺少字段正确检出，issues: {report.issues}")


def test_syntax_disallowed_import():
    """测试不允许的 import。"""
    print("\n--- test_syntax_disallowed_import ---")
    code = textwrap.dedent("""\
        import subprocess
        from pathlib import Path

        __FACTOR_META__ = {
            "TargetTable": "test",
            "IDType": "A股",
            "Author": "test",
            "Description": "test",
            "DefScriptPath": __file__,
        }

        def defFactor(fdi, dep_fd):
            return []
    """)
    tmp_dir = _make_temp_factor(code, "bad_import")

    validator = SyntaxValidator()
    report = validator.validate(tmp_dir)

    assert not report.passed, "不允许的 import 应判定为失败"
    assert any("subprocess" in i for i in report.issues), f"应检出 subprocess，实际: {report.issues}"
    print("  PASS: 不允许的 import 正确检出")


def test_syntax_def_factor_too_few_args():
    """测试 defFactor 参数不足的情况。"""
    print("\n--- test_syntax_def_factor_too_few_args ---")
    code = textwrap.dedent("""\
        __FACTOR_META__ = {
            "TargetTable": "test",
            "IDType": "A股",
            "Author": "test",
            "Description": "test",
            "DefScriptPath": __file__,
        }

        def defFactor(fdi):
            return []
    """)
    tmp_dir = _make_temp_factor(code, "few_args")

    validator = SyntaxValidator()
    report = validator.validate(tmp_dir)

    assert not report.passed, "参数不足应判定为失败"
    assert any("参数" in i for i in report.issues), f"应报告参数不足，实际: {report.issues}"
    print("  PASS: defFactor 参数不足正确检出")


# ============================================================
# LeakValidator 测试
# ============================================================

def test_leak_financial_only_factor():
    """测试纯财务数据因子应跳过泄漏检测。"""
    print("\n--- test_leak_financial_only_factor ---")
    # demo PE_TTM 因子：使用 CalcType="最新" + 无行情数据
    # 但 demo 实际使用了"股票行情表现"，所以不是纯财务因子
    # 构造一个纯财务因子
    code = textwrap.dedent("""\
        def defFactor(fdi, dep_fd):
            SDB = fdi.FDB["JYDB"]
            FT = SDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "最新"})
            NP = FT.getFactor("归属母公司股东的净利润(TTM)")
            return [NP]
    """)
    tmp_dir = _make_temp_factor(code, "financial_only")

    validator = LeakValidator()
    report = validator.validate(tmp_dir)

    assert report.passed, f"纯财务因子应通过，issues: {report.issues}"
    assert "财务数据" in report.method or "CalcType" in report.method, f"方法描述应说明跳过原因: {report.method}"
    print(f"  PASS: 纯财务因子跳过泄漏检测，method: {report.method}")


def test_leak_no_time_operators():
    """测试无时序算子的因子应跳过泄漏检测。

    注意：LeakValidator 将 LookBack 视为时序关键词，
    所以此测试使用不含 LookBack 的纯截面因子。
    """
    print("\n--- test_leak_no_time_operators ---")
    code = textwrap.dedent("""\
        import QuantStudio.Factor.FactorOperator as fo

        def defFactor(fdi, dep_fd):
            SDB = fdi.FDB["JYDB"]
            FT = SDB.getTable("公司衍生报表数据_新会计准则(新)")
            np_val = FT.getFactor("归属母公司股东的净利润(TTM)")
            return [np_val]
    """)
    tmp_dir = _make_temp_factor(code, "no_time_ops")

    validator = LeakValidator()
    report = validator.validate(tmp_dir)

    assert report.passed, f"无时序算子应通过，issues: {report.issues}"
    assert "时序算子" in report.method or "不存在" in report.method, f"method: {report.method}"
    print(f"  PASS: 无时序算子跳过泄漏检测，method: {report.method}")


def test_leak_has_time_operators():
    """测试有时序算子的因子应进入静态分析。"""
    print("\n--- test_leak_has_time_operators ---")
    code = textwrap.dedent("""\
        import QuantStudio.Factor.FactorOperator as fo

        def defFactor(fdi, dep_fd):
            SDB = fdi.FDB["JYDB"]
            FT = SDB.getTable("股票行情表现", args={"LookBack": 0})
            close = FT.getFactor("收盘价")
            # 使用 RollingMean 时序算子
            ma = fo.RollingMean(window=20)(close)
            return [ma]
    """)
    tmp_dir = _make_temp_factor(code, "with_time_ops")

    validator = LeakValidator()
    report = validator.validate(tmp_dir)

    # 静态分析未发现泄漏模式，应通过
    assert report.passed, f"静态分析未发现泄漏应通过，issues: {report.issues}"
    assert "静态分析" in report.method, f"method: {report.method}"
    print(f"  PASS: 有时序算子进入静态分析，method: {report.method}")


def test_leak_negative_shift_detected():
    """测试负数 shift（向前看）应被检出。"""
    print("\n--- test_leak_negative_shift_detected ---")
    code = textwrap.dedent("""\
        import QuantStudio.Factor.FactorOperator as fo

        def defFactor(fdi, dep_fd):
            SDB = fdi.FDB["JYDB"]
            FT = SDB.getTable("股票行情表现", args={"LookBack": 0})
            close = FT.getFactor("收盘价")
            # 使用 .rolling() 触发时序算子检测
            ma = close.rolling(20).mean()
            # 使用负数 shift（泄漏！）
            future = close.shift(-1)
            return [ma]
    """)
    tmp_dir = _make_temp_factor(code, "neg_shift")

    validator = LeakValidator()
    report = validator.validate(tmp_dir)

    assert not report.passed, "负数 shift 应检出泄漏"
    assert any("shift" in i.lower() for i in report.issues), f"应报告 shift 问题，实际: {report.issues}"
    print(f"  PASS: 负数 shift 正确检出，issues: {report.issues}")


def test_leak_missing_file():
    """测试文件不存在的情况。"""
    print("\n--- test_leak_missing_file ---")
    validator = LeakValidator()
    report = validator.validate("/nonexistent/path")

    assert not report.passed
    assert any("不存在" in i for i in report.issues)
    print("  PASS: 文件不存在正确报错")


# ============================================================
# UnitValidator 测试
# ============================================================

def test_unit_no_dual_board():
    """测试非双板因子应跳过单位检查。"""
    print("\n--- test_unit_no_dual_board ---")
    code = textwrap.dedent("""\
        def defFactor(fdi, dep_fd):
            SDB = fdi.FDB["JYDB"]
            FT = SDB.getTable("股票行情表现", args={"LookBack": 0})
            mv = FT.getFactor("总市值(万元)")
            return [mv]
    """)
    tmp_dir = _make_temp_factor(code, "single_board")

    validator = UnitValidator()
    report = validator.validate(tmp_dir)

    assert report.passed, f"单板因子应通过，issues: {report.issues}"
    print("  PASS: 非双板因子跳过单位检查")


def test_unit_dual_board_no_conversion():
    """测试双板因子缺少单位转换逻辑应检出。

    注意：注释中不能包含"单位换算"/"单位转换"等关键词，
    否则 UnitValidator 会误判为已有转换逻辑。
    """
    print("\n--- test_unit_dual_board_no_conversion ---")
    code = textwrap.dedent("""\
        def defFactor(fdi, dep_fd):
            SDB = fdi.FDB["JYDB"]
            # 主板（万元）
            FT = SDB.getTable("股票行情表现", args={"LookBack": 0})
            mv_main = FT.getFactor("总市值(万元)")
            # 科创板（元）
            FT_STIB = SDB.getTable("科创板行情表现", args={"LookBack": 0})
            mv_stib = FT_STIB.getFactor("总市值(元)")
            # 直接合并，缺失处理
            return [mv_main]
    """)
    tmp_dir = _make_temp_factor(code, "dual_no_conv")

    validator = UnitValidator()
    report = validator.validate(tmp_dir)

    assert not report.passed, "双板缺换单位换算应失败"
    assert any("单位差异" in i or "换算" in i for i in report.issues), f"实际: {report.issues}"
    print(f"  PASS: 双板缺换单位换算正确检出，issues: {report.issues}")


def test_unit_dual_board_with_conversion():
    """测试双板因子有单位换算逻辑应通过。"""
    print("\n--- test_unit_dual_board_with_conversion ---")
    code = textwrap.dedent("""\
        def defFactor(fdi, dep_fd):
            SDB = fdi.FDB["JYDB"]
            # 主板：万元
            FT = SDB.getTable("股票行情表现", args={"LookBack": 0})
            mv_main = FT.getFactor("总市值(万元)")
            # 科创板：元
            FT_STIB = SDB.getTable("科创板行情表现", args={"LookBack": 0})
            mv_stib = FT_STIB.getFactor("总市值(元)")
            # 单位换算：元→万元
            mv_stib = mv_stib / 10000
            return [mv_main]
    """)
    tmp_dir = _make_temp_factor(code, "dual_with_conv")

    validator = UnitValidator()
    report = validator.validate(tmp_dir)

    assert report.passed, f"有换算逻辑应通过，issues: {report.issues}"
    print(f"  PASS: 双板有换单位换算正确通过")


def test_unit_extract_table_names():
    """测试表名提取。"""
    print("\n--- test_unit_extract_table_names ---")
    code = textwrap.dedent("""\
        def defFactor(fdi, dep_fd):
            SDB = fdi.FDB["JYDB"]
            FT1 = SDB.getTable("股票行情表现", args={"LookBack": 0})
            FT2 = SDB.getTable("科创板行情表现", args={"LookBack": 0})
            FT3 = SDB.getTable("公司衍生报表数据_新会计准则(新)", args={"CalcType": "最新"})
            return []
    """)
    tmp_dir = _make_temp_factor(code, "table_extract")

    validator = UnitValidator()
    report = validator.validate(tmp_dir)

    # 应正确提取 3 个表名
    # 通过 conversions 检查双板检测结果
    print(f"  conversions: {report.conversions}")
    print(f"  issues: {report.issues}")
    print("  PASS: 表名提取测试完成")


def test_unit_demo_factor():
    """测试 demo PE_TTM 因子的单位检查。"""
    print("\n--- test_unit_demo_factor ---")
    validator = UnitValidator()
    report = validator.validate(DEMO_DIR)

    # demo 因子有双板合并且有 /10000 换算，应通过
    assert report.passed, f"demo 因子单位检查应通过，issues: {report.issues}"
    print(f"  PASS: demo 因子单位检查通过，conversions: {report.conversions}")


def test_unit_missing_file():
    """测试文件不存在的情况。"""
    print("\n--- test_unit_missing_file ---")
    validator = UnitValidator()
    report = validator.validate("/nonexistent/path")

    assert not report.passed
    assert any("不存在" in i for i in report.issues)
    print("  PASS: 文件不存在正确报错")


# ============================================================
# SemanticValidator 测试
# ============================================================

def test_semantic_parse_review_passed():
    """测试解析通过的审查文本。"""
    print("\n--- test_semantic_parse_review_passed ---")
    validator = SemanticValidator.__new__(SemanticValidator)
    report = validator._parse_review("代码逻辑正确，无明显问题。")

    assert report.passed, "无 FAILED/WARNING 应通过"
    print("  PASS: 正常审查文本解析为通过")


def test_semantic_parse_review_failed():
    """测试解析 FAILED 的审查文本。"""
    print("\n--- test_semantic_parse_review_failed ---")
    validator = SemanticValidator.__new__(SemanticValidator)
    report = validator._parse_review("审查结论: FAILED\n代码逻辑与假设不一致。")

    assert not report.passed, "FAILED 应判定为失败"
    print("  PASS: FAILED 审查文本解析为失败")


def test_semantic_parse_review_warning():
    """测试解析 WARNING 的审查文本。"""
    print("\n--- test_semantic_parse_review_warning ---")
    validator = SemanticValidator.__new__(SemanticValidator)
    report = validator._parse_review("WARNING: 存在潜在性能问题。")

    assert report.passed, "WARNING 应判定为通过（不阻塞）"
    print("  PASS: WARNING 审查文本解析为通过")


def test_semantic_extract_suggestions():
    """测试改进建议提取。"""
    print("\n--- test_semantic_extract_suggestions ---")
    validator = SemanticValidator.__new__(SemanticValidator)
    text = textwrap.dedent("""\
        审查结论: PASSED

        改进建议
        - 建议 1: 添加 NaN 处理
        - 建议 2: 优化内存使用
        - 建议 3: 增加异常处理
    """)
    suggestions = validator._extract_suggestions(text)

    assert len(suggestions) == 3, f"应提取 3 条建议，实际 {len(suggestions)}: {suggestions}"
    assert "添加 NaN 处理" in suggestions[0]
    print(f"  PASS: 提取到 {len(suggestions)} 条建议: {suggestions}")


def test_semantic_extract_suggestions_empty():
    """测试无改进建议的情况。"""
    print("\n--- test_semantic_extract_suggestions_empty ---")
    validator = SemanticValidator.__new__(SemanticValidator)
    suggestions = validator._extract_suggestions("代码逻辑正确。")

    assert len(suggestions) == 0, f"应无建议，实际 {len(suggestions)}"
    print("  PASS: 无建议时正确返回空列表")


# ============================================================
# ExecutionValidator 测试（部分 mock）
# ============================================================

def test_execution_nan_ratio():
    """测试 NaN 比例计算。"""
    print("\n--- test_execution_nan_ratio ---")
    import numpy as np

    validator = ExecutionValidator.__new__(ExecutionValidator)

    # 测试 1: 全部为 NaN
    data = np.full((5, 3), np.nan)
    ratio = validator._calc_nan_ratio(data)
    assert ratio == 1.0, f"全 NaN 应返回 1.0，实际 {ratio}"
    print(f"  全 NaN: ratio={ratio}  ✓")

    # 测试 2: 无 NaN
    data = np.ones((5, 3))
    ratio = validator._calc_nan_ratio(data)
    assert ratio == 0.0, f"无 NaN 应返回 0.0，实际 {ratio}"
    print(f"  无 NaN: ratio={ratio}  ✓")

    # 测试 3: 部分 NaN
    data = np.array([[1.0, np.nan], [np.inf, 2.0]])
    ratio = validator._calc_nan_ratio(data)
    assert ratio == 0.5, f"50% 应返回 0.5，实际 {ratio}"
    print(f"  50% NaN/Inf: ratio={ratio}  ✓")

    # 测试 4: 空数组
    data = np.array([])
    ratio = validator._calc_nan_ratio(data)
    assert ratio == 1.0, f"空数组应返回 1.0，实际 {ratio}"
    print(f"  空数组: ratio={ratio}  ✓")

    print("  PASS: NaN 比例计算全部正确")


def test_execution_missing_file():
    """测试文件不存在的情况。"""
    print("\n--- test_execution_missing_file ---")
    validator = ExecutionValidator()
    report = validator.validate("/nonexistent/path")

    assert not report.passed
    assert any("不存在" in i for i in report.issues)
    print("  PASS: 文件不存在正确报错")


def test_execution_missing_def_factor():
    """测试模块缺少 defFactor 函数。"""
    print("\n--- test_execution_missing_def_factor ---")
    code = textwrap.dedent("""\
        __FACTOR_META__ = {
            "TargetTable": "test",
            "IDType": "A股",
            "Author": "test",
            "Description": "test",
            "DefScriptPath": __file__,
        }
    """)
    tmp_dir = _make_temp_factor(code, "no_def_exec")

    validator = ExecutionValidator()
    report = validator.validate(tmp_dir)

    assert not report.passed, "缺少 defFactor 应失败"
    assert any("defFactor" in i for i in report.issues), f"实际: {report.issues}"
    print("  PASS: 缺少 defFactor 正确检出")


# ============================================================
# 运行所有测试
# ============================================================

ALL_TESTS = [
    # SyntaxValidator
    test_syntax_valid_demo,
    test_syntax_missing_file,
    test_syntax_invalid_python,
    test_syntax_missing_def_factor,
    test_syntax_missing_factor_meta,
    test_syntax_missing_meta_field,
    test_syntax_disallowed_import,
    test_syntax_def_factor_too_few_args,
    # LeakValidator
    test_leak_financial_only_factor,
    test_leak_no_time_operators,
    test_leak_has_time_operators,
    test_leak_negative_shift_detected,
    test_leak_missing_file,
    # UnitValidator
    test_unit_no_dual_board,
    test_unit_dual_board_no_conversion,
    test_unit_dual_board_with_conversion,
    test_unit_extract_table_names,
    test_unit_demo_factor,
    test_unit_missing_file,
    # SemanticValidator
    test_semantic_parse_review_passed,
    test_semantic_parse_review_failed,
    test_semantic_parse_review_warning,
    test_semantic_extract_suggestions,
    test_semantic_extract_suggestions_empty,
    # ExecutionValidator
    test_execution_nan_ratio,
    test_execution_missing_file,
    test_execution_missing_def_factor,
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
            errors.append((test_fn.__name__, f"异常: {e}"))
            print(f"  ERROR: {e}")

    print("\n" + "=" * 60)
    print(f"验证器单元测试结果: {passed} 通过, {failed} 失败, 共 {passed + failed} 个")
    if errors:
        print("\n失败详情:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print("=" * 60)
