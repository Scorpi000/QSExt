# -*- coding: utf-8 -*-
"""Tests for QSExt.LLMFactor.factor_object"""
import json
import os
import tempfile
from pathlib import Path

import pytest


DEMO_DIR = Path(__file__).resolve().parent.parent / "QSExt" / "LLMFactor" / "demo_stock_cn_factor_def"


# ============================================================
# 辅助 fixture
# ============================================================

@pytest.fixture
def demo_dir():
    """返回 demo 因子目录路径（跳过不存在的情况）"""
    if not DEMO_DIR.is_dir():
        pytest.skip(f"demo 目录不存在: {DEMO_DIR}")
    return str(DEMO_DIR)


@pytest.fixture
def tmp_factor_dir(tmp_path):
    """创建一个最小合法因子目录"""
    factor_dir = tmp_path / "test_factor"
    factor_dir.mkdir()

    # metadata.json
    meta = {
        "factor_name": "test_factor",
        "category": "测试",
        "market": "A股",
        "frequency": "日频",
        "description": "测试因子",
        "formula": "A + B",
        "hypothesis_id": None,
        "qsid": None,
        "status": "test",
        "tags": ["测试"],
    }
    (factor_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )

    # factor_def.py
    code = '''# -*- coding: utf-8 -*-
def defFactor(fdi, dep_fd):
    """最小因子定义，用于测试"""
    return []
'''
    (factor_dir / "factor_def.py").write_text(code, encoding="utf-8")

    return str(factor_dir)


@pytest.fixture
def tmp_factor_dir_full(tmp_path):
    """创建一个完整的因子目录（含所有可选文件）"""
    factor_dir = tmp_path / "test_factor_full"
    factor_dir.mkdir()

    # metadata.json
    meta = {
        "factor_name": "full_factor",
        "category": "测试",
        "market": "A股",
        "frequency": "日频",
        "description": "完整测试因子",
        "formula": "X * Y",
        "hypothesis_id": "H001",
        "qsid": "QS_TEST_001",
        "status": "validated",
        "tags": ["测试", "完整"],
    }
    (factor_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )

    # factor_def.py
    code = '''# -*- coding: utf-8 -*-
def defFactor(fdi, dep_fd):
    """完整因子定义"""
    return []
'''
    (factor_dir / "factor_def.py").write_text(code, encoding="utf-8")

    # README.md
    (factor_dir / "README.md").write_text(
        "# Full Factor\n\n这是一个完整测试因子。", encoding="utf-8"
    )

    # param_search/
    ps_dir = factor_dir / "param_search"
    ps_dir.mkdir()
    (ps_dir / "search_space.json").write_text("{}", encoding="utf-8")
    (ps_dir / "best_params.json").write_text(
        json.dumps({"method": "TPE", "best_params": {"LookBack": 5}}),
        encoding="utf-8",
    )

    # validation/
    val_dir = factor_dir / "validation"
    val_dir.mkdir()
    syntax_report = {
        "syntax": "passed",
        "execution": "passed",
        "leak_test": "passed",
        "unit_consistency": "passed",
        "semantic_review": "passed",
        "details": {"syntax": "AST 解析通过"},
        "issues": [],
        "auto_fix_count": 0,
    }
    (val_dir / "syntax_report.json").write_text(
        json.dumps(syntax_report, ensure_ascii=False), encoding="utf-8"
    )
    (val_dir / "leak_test_report.json").write_text(
        json.dumps({"result": "no_leak"}), encoding="utf-8"
    )
    (val_dir / "semantic_review.md").write_text(
        "# 语义审查\n\n通过。", encoding="utf-8"
    )

    return str(factor_dir)


# ============================================================
# FactorObject — 基础加载
# ============================================================

class TestFactorObjectInit:
    """构造函数测试"""

    def test_load_demo_dir(self, demo_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(demo_dir)
        assert fo.name == "pe_ttm"

    def test_load_minimal_dir(self, tmp_factor_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        assert fo.name == "test_factor"

    def test_dir_not_found(self):
        from QSExt.LLMFactor.factor_object import FactorObject
        with pytest.raises(FileNotFoundError, match="不存在"):
            FactorObject("/nonexistent/path")

    def test_missing_factor_def(self, tmp_path):
        from QSExt.LLMFactor.factor_object import FactorObject
        d = tmp_path / "no_code"
        d.mkdir()
        (d / "metadata.json").write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="factor_def.py"):
            FactorObject(str(d))

    def test_missing_metadata(self, tmp_path):
        from QSExt.LLMFactor.factor_object import FactorObject
        d = tmp_path / "no_meta"
        d.mkdir()
        (d / "factor_def.py").write_text("def defFactor(fdi, dep_fd): pass", encoding="utf-8")
        with pytest.raises(ValueError, match="metadata.json"):
            FactorObject(str(d))


# ============================================================
# FactorObject — 属性
# ============================================================

class TestFactorObjectProperties:
    """属性访问测试"""

    def test_metadata_properties(self, tmp_factor_dir_full):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir_full)
        assert fo.name == "full_factor"
        assert fo.description == "完整测试因子"
        assert fo.formula == "X * Y"
        assert fo.category == "测试"
        assert fo.market == "A股"
        assert fo.frequency == "日频"
        assert fo.tags == ["测试", "完整"]
        assert fo.hypothesis_id == "H001"
        assert fo.qsid == "QS_TEST_001"
        assert fo.status == "validated"

    def test_metadata_defaults(self, tmp_factor_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        assert fo.hypothesis_id is None
        assert fo.qsid is None
        assert fo.status == "test"

    def test_code(self, tmp_factor_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        assert "defFactor" in fo.code

    def test_readme_exists(self, tmp_factor_dir_full):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir_full)
        assert fo.readme is not None
        assert "完整测试因子" in fo.readme

    def test_readme_missing(self, tmp_factor_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        assert fo.readme is None

    def test_params(self, tmp_factor_dir_full):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir_full)
        assert fo.params["method"] == "TPE"
        assert fo.params["best_params"]["LookBack"] == 5

    def test_params_missing(self, tmp_factor_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        assert fo.params == {}

    def test_search_space(self, tmp_factor_dir_full):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir_full)
        assert fo.search_space == {}

    def test_validation(self, tmp_factor_dir_full):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir_full)
        assert "syntax_report" in fo.validation
        assert fo.validation["syntax_report"]["syntax"] == "passed"

    def test_validation_missing(self, tmp_factor_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        assert fo.validation == {}

    def test_dir_path(self, tmp_factor_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        assert fo.dir_path == Path(tmp_factor_dir)

    def test_metadata_lazy_load(self, tmp_factor_dir):
        """验证懒加载：多次访问返回同一对象"""
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        m1 = fo.metadata
        m2 = fo.metadata
        assert m1 is m2


# ============================================================
# FactorObject — 方法
# ============================================================

class TestFactorObjectMethods:
    """方法测试"""

    def test_explain(self, tmp_factor_dir_full):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir_full)
        text = fo.explain()
        assert "# full_factor" in text
        assert "完整测试因子" in text
        assert "分类: 测试" in text
        assert "市场: A股" in text
        assert "公式: `X * Y`" in text
        assert "假设ID: H001" in text
        assert "QSID: QS_TEST_001" in text
        assert "详细说明" in text

    def test_explain_no_readme(self, tmp_factor_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        text = fo.explain()
        assert "# test_factor" in text
        assert "详细说明" not in text

    def test_unit_test_all_passed(self, tmp_factor_dir_full):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir_full)
        result = fo.unit_test()
        assert result["passed"] is True
        assert result["checks"]["syntax"] == "passed"
        assert result["checks"]["execution"] == "passed"
        assert result["checks"]["leak_test"] == "passed"

    def test_unit_test_no_validation(self, tmp_factor_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        result = fo.unit_test()
        assert result["passed"] is False  # 没有检查结果
        assert all(v == "unknown" for v in result["checks"].values())

    def test_to_archive(self, tmp_factor_dir_full):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir_full)
        archive = fo.to_archive()
        assert archive["dir_path"] == tmp_factor_dir_full
        assert archive["metadata"]["factor_name"] == "full_factor"
        assert "code" in archive
        assert "params" in archive
        assert "validation" in archive

    def test_replay_returns_empty_list(self, tmp_factor_dir):
        """最小因子 defFactor 返回空列表"""
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        result = fo.replay(fdi=None)
        assert result == []

    def test_replay_caches_module(self, tmp_factor_dir):
        """多次 replay 应复用已加载的模块"""
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(tmp_factor_dir)
        r1 = fo.replay(fdi=None)
        r2 = fo.replay(fdi=None)
        assert r1 == r2

    def test_replay_no_defFactor(self, tmp_path):
        """factor_def.py 中没有 defFactor 函数"""
        from QSExt.LLMFactor.factor_object import FactorObject
        d = tmp_path / "no_func"
        d.mkdir()
        (d / "metadata.json").write_text('{"factor_name": "x"}', encoding="utf-8")
        (d / "factor_def.py").write_text("X = 1", encoding="utf-8")
        fo = FactorObject(str(d))
        with pytest.raises(RuntimeError, match="defFactor"):
            fo.replay(fdi=None)


# ============================================================
# validate_factor_dir
# ============================================================

class TestValidateFactorDir:
    """validate_factor_dir 函数测试"""

    def test_valid_dir(self, tmp_factor_dir):
        from QSExt.LLMFactor.factor_object import validate_factor_dir
        ok, errors = validate_factor_dir(tmp_factor_dir)
        assert ok is True
        assert errors == []

    def test_valid_full_dir(self, tmp_factor_dir_full):
        from QSExt.LLMFactor.factor_object import validate_factor_dir
        ok, errors = validate_factor_dir(tmp_factor_dir_full)
        assert ok is True
        assert errors == []

    def test_not_a_dir(self):
        from QSExt.LLMFactor.factor_object import validate_factor_dir
        ok, errors = validate_factor_dir("/nonexistent/path")
        assert ok is False
        assert len(errors) == 1
        assert "不存在" in errors[0]

    def test_missing_files(self, tmp_path):
        from QSExt.LLMFactor.factor_object import validate_factor_dir
        d = tmp_path / "empty"
        d.mkdir()
        ok, errors = validate_factor_dir(str(d))
        assert ok is False
        assert len(errors) >= 2

    def test_invalid_metadata(self, tmp_path):
        from QSExt.LLMFactor.factor_object import validate_factor_dir
        d = tmp_path / "bad_meta"
        d.mkdir()
        (d / "factor_def.py").write_text("def defFactor(fdi, dep_fd): pass", encoding="utf-8")
        (d / "metadata.json").write_text("not json", encoding="utf-8")
        ok, errors = validate_factor_dir(str(d))
        assert ok is False
        assert any("解析失败" in e for e in errors)

    def test_missing_factor_name(self, tmp_path):
        from QSExt.LLMFactor.factor_object import validate_factor_dir
        d = tmp_path / "no_name"
        d.mkdir()
        (d / "factor_def.py").write_text("def defFactor(fdi, dep_fd): pass", encoding="utf-8")
        (d / "metadata.json").write_text("{}", encoding="utf-8")
        ok, errors = validate_factor_dir(str(d))
        assert ok is False
        assert any("factor_name" in e for e in errors)

    def test_missing_defFactor(self, tmp_path):
        from QSExt.LLMFactor.factor_object import validate_factor_dir
        d = tmp_path / "no_func"
        d.mkdir()
        (d / "factor_def.py").write_text("X = 1", encoding="utf-8")
        (d / "metadata.json").write_text('{"factor_name": "x"}', encoding="utf-8")
        ok, errors = validate_factor_dir(str(d))
        assert ok is False
        assert any("defFactor" in e for e in errors)


# ============================================================
# demo 目录集成测试
# ============================================================

class TestDemoIntegration:
    """使用 demo_stock_cn_factor_def 的集成测试"""

    def test_demo_metadata(self, demo_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(demo_dir)
        assert fo.name == "pe_ttm"
        assert fo.category == "估值"
        assert fo.market == "A股"
        assert fo.frequency == "日频"
        assert "PE_TTM" in fo.description
        assert fo.status == "demo"
        assert "估值" in fo.tags

    def test_demo_code_contains_defFactor(self, demo_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(demo_dir)
        assert "def defFactor" in fo.code
        assert "__FACTOR_META__" in fo.code

    def test_demo_readme(self, demo_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(demo_dir)
        assert fo.readme is not None
        assert "PE_TTM" in fo.readme

    def test_demo_params(self, demo_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(demo_dir)
        assert fo.params["method"] == "TPE"

    def test_demo_validation(self, demo_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(demo_dir)
        result = fo.unit_test()
        assert result["passed"] is True

    def test_demo_explain(self, demo_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(demo_dir)
        text = fo.explain()
        assert "pe_ttm" in text
        assert "估值" in text

    def test_demo_archive(self, demo_dir):
        from QSExt.LLMFactor.factor_object import FactorObject
        fo = FactorObject(demo_dir)
        archive = fo.to_archive()
        assert archive["metadata"]["factor_name"] == "pe_ttm"
        assert len(archive["code"]) > 0
