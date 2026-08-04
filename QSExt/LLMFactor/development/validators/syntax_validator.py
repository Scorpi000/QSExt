# -*- coding: utf-8 -*-
"""Agent A: 语法检查验证器。

检查项：
    1. AST 解析验证（ast.parse）
    2. import 路径验证（QuantStudio.* / QSExt.*）
    3. __FACTOR_META__ 字典完整性校验
    4. defFactor 函数签名校验

使用示例::

    validator = SyntaxValidator()
    report = validator.validate(factor_dir, hypothesis)
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

from QSExt.LLMFactor.development.models import SyntaxReport

__QS_Logger__ = logging.getLogger("QSR.development.syntax_validator")

# 允许的 import 路径前缀
ALLOWED_IMPORT_PREFIXES = [
    "QuantStudio.",
    "QSExt.",
    "numpy", "np",
    "pandas", "pd",
    "scipy",
    "datetime",
    "typing",
    "math",
    "collections",
    "functools",
    "itertools",
    "copy",
    "logging",
    "os", "sys",
]

# __FACTOR_META__ 必需字段
REQUIRED_META_FIELDS = ["TargetTable", "IDType", "Author", "Description", "DefScriptPath"]


class SyntaxValidator:
    """语法检查验证器（Agent A）。"""

    def validate(self, factor_dir: str, hypothesis: dict = None) -> SyntaxReport:
        """执行语法检查。

        Args:
            factor_dir: 因子目录路径
            hypothesis: 假设文档（未使用，保持接口一致）

        Returns:
            SyntaxReport
        """
        issues = []
        details = {}

        code_path = Path(factor_dir) / "factor_def.py"
        if not code_path.exists():
            return SyntaxReport(
                passed=False,
                issues=["factor_def.py 不存在"],
                details={"file_exists": False},
            )

        code = code_path.read_text(encoding="utf-8")

        # 1. AST 解析
        ast_result = self._check_ast(code)
        details["ast"] = ast_result
        if not ast_result["passed"]:
            issues.extend(ast_result["issues"])
            # AST 失败则跳过后续检查
            return SyntaxReport(passed=False, issues=issues, details=details)

        # 2. import 路径验证
        import_result = self._check_imports(code)
        details["imports"] = import_result
        if not import_result["passed"]:
            issues.extend(import_result["issues"])

        # 3. __FACTOR_META__ 完整性
        meta_result = self._check_factor_meta(code)
        details["factor_meta"] = meta_result
        if not meta_result["passed"]:
            issues.extend(meta_result["issues"])

        # 4. defFactor 签名
        sig_result = self._check_def_factor_signature(code)
        details["def_factor_signature"] = sig_result
        if not sig_result["passed"]:
            issues.extend(sig_result["issues"])

        return SyntaxReport(
            passed=len(issues) == 0,
            issues=issues,
            details=details,
        )

    def _check_ast(self, code: str) -> dict:
        """AST 解析验证。"""
        try:
            ast.parse(code)
            return {"passed": True, "issues": []}
        except SyntaxError as e:
            return {
                "passed": False,
                "issues": [f"语法错误 (行 {e.lineno}): {e.msg}"],
            }

    def _check_imports(self, code: str) -> dict:
        """import 路径验证。"""
        issues = []
        tree = ast.parse(code)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not self._is_allowed_import(alias.name):
                        issues.append(f"不允许的 import: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if not self._is_allowed_import(module):
                    issues.append(f"不允许的 import: from {module} import ...")

        return {"passed": len(issues) == 0, "issues": issues}

    def _is_allowed_import(self, module_name: str) -> bool:
        """检查模块名是否在允许列表中。"""
        for prefix in ALLOWED_IMPORT_PREFIXES:
            if module_name == prefix or module_name.startswith(prefix + ".") or module_name.startswith(prefix):
                return True
        return False

    def _check_factor_meta(self, code: str) -> dict:
        """__FACTOR_META__ 完整性校验。"""
        issues = []

        # 检查 __FACTOR_META__ 是否存在
        if "__FACTOR_META__" not in code:
            issues.append("缺少 __FACTOR_META__ 字典")
            return {"passed": False, "issues": issues}

        # 提取并解析 __FACTOR_META__ 的内容
        # 使用正则匹配（AST 方式较复杂，因为是模块级字典赋值）
        meta_match = re.search(
            r"__FACTOR_META__\s*=\s*\{(.*?)\}",
            code,
            re.DOTALL,
        )
        if not meta_match:
            issues.append("__FACTOR_META__ 格式不正确（无法提取字典内容）")
            return {"passed": False, "issues": issues}

        meta_content = meta_match.group(0)

        # 检查必需字段
        for field in REQUIRED_META_FIELDS:
            if f'"{field}"' not in meta_content and f"'{field}'" not in meta_content:
                issues.append(f"__FACTOR_META__ 缺少必需字段: {field}")

        return {"passed": len(issues) == 0, "issues": issues}

    def _check_def_factor_signature(self, code: str) -> dict:
        """defFactor 函数签名校验。"""
        issues = []
        tree = ast.parse(code)

        def_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "defFactor":
                def_func = node
                break

        if def_func is None:
            issues.append("未找到 defFactor 函数")
            return {"passed": False, "issues": issues}

        # 检查参数数量（至少 2 个: fdi, dep_fd）
        args = def_func.args
        total_args = len(args.args) + len(args.posonlyargs) + len(args.kwonlyargs)
        if total_args < 2:
            issues.append(f"defFactor 参数数量不足（期望至少 2 个，实际 {total_args} 个）")

        return {"passed": len(issues) == 0, "issues": issues}
