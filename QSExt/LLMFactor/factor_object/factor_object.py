# -*- coding: utf-8 -*-
"""L1 可执行因子对象标准

将 LLM 开发的因子目录（如 demo_stock_cn_factor_def/）封装为标准的 FactorObject，
提供统一的加载、执行、说明、验证接口。

使用示例::

    from QSExt.LLMFactor.factor_object import FactorObject

    fo = FactorObject("path/to/demo_stock_cn_factor_def")
    print(fo.name)           # "pe_ttm"
    print(fo.explain())      # 标准化说明文本
    print(fo.unit_test())    # 验证结果汇总

    # 需要 QuantStudio 环境
    factors = fo.replay(fdi)
"""
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class FactorObject:
    """一个因子的标准表示 — 从开发目录加载。

    目录结构约定::

        <factor_dir>/
            factor_def.py              # 必需：因子定义代码
            metadata.json              # 必需：机器可读元数据
            README.md                  # 可选：人类可读文档
            param_search/
                search_space.json      # 可选：超参数搜索空间
                best_params.json       # 可选：搜索结果
            validation/
                syntax_report.json     # 可选：语法检查结果
                leak_test_report.json  # 可选：泄漏检测报告
                semantic_review.md     # 可选：语义审查意见
    """

    def __init__(self, dir_path: str):
        """从因子开发目录加载。

        Args:
            dir_path: 因子开发目录路径

        Raises:
            FileNotFoundError: 目录不存在
            ValueError: 缺少必需文件（factor_def.py 或 metadata.json）
        """
        self._dir_path = Path(dir_path)
        if not self._dir_path.is_dir():
            raise FileNotFoundError(f"因子目录不存在: {dir_path}")

        # 校验必需文件
        missing = []
        if not (self._dir_path / "factor_def.py").exists():
            missing.append("factor_def.py")
        if not (self._dir_path / "metadata.json").exists():
            missing.append("metadata.json")
        if missing:
            raise ValueError(f"因子目录缺少必需文件: {', '.join(missing)}")

        # 懒加载缓存
        self._metadata: Optional[dict] = None
        self._code: Optional[str] = None
        self._readme: Optional[str] = None
        self._params: Optional[dict] = None
        self._search_space: Optional[dict] = None
        self._validation: Optional[dict] = None
        self._module: Optional[Any] = None

    # ============================================================
    # 基础属性
    # ============================================================

    @property
    def dir_path(self) -> Path:
        """因子目录路径"""
        return self._dir_path

    @property
    def metadata(self) -> dict:
        """metadata.json 原始内容"""
        if self._metadata is None:
            self._metadata = self._load_json("metadata.json")
        return self._metadata

    @property
    def code(self) -> str:
        """factor_def.py 源码"""
        if self._code is None:
            self._code = self._load_text("factor_def.py")
        return self._code

    @property
    def readme(self) -> Optional[str]:
        """README.md 内容，不存在时返回 None"""
        if self._readme is None:
            readme_path = self._dir_path / "README.md"
            if readme_path.exists():
                self._readme = readme_path.read_text(encoding="utf-8")
            else:
                self._readme = ""  # 标记已尝试加载
        return self._readme or None

    @property
    def params(self) -> dict:
        """param_search/best_params.json 内容"""
        if self._params is None:
            self._params = self._load_json("param_search/best_params.json", default={})
        return self._params

    @property
    def search_space(self) -> dict:
        """param_search/search_space.json 内容"""
        if self._search_space is None:
            self._search_space = self._load_json(
                "param_search/search_space.json", default={}
            )
        return self._search_space

    @property
    def validation(self) -> dict:
        """合并 validation/ 目录下所有 JSON 报告"""
        if self._validation is None:
            val_dir = self._dir_path / "validation"
            result = {}
            if val_dir.is_dir():
                for f in sorted(val_dir.iterdir()):
                    if f.suffix == ".json":
                        try:
                            result[f.stem] = json.loads(
                                f.read_text(encoding="utf-8")
                            )
                        except (json.JSONDecodeError, OSError):
                            result[f.stem] = None
            self._validation = result
        return self._validation

    # ---- metadata.json 便捷属性 ----

    @property
    def name(self) -> str:
        """因子名称"""
        return self.metadata.get("factor_name", "")

    @property
    def description(self) -> str:
        """因子描述"""
        return self.metadata.get("description", "")

    @property
    def formula(self) -> str:
        """因子公式"""
        return self.metadata.get("formula", "")

    @property
    def category(self) -> str:
        """因子分类"""
        return self.metadata.get("category", "")

    @property
    def market(self) -> str:
        """目标市场"""
        return self.metadata.get("market", "")

    @property
    def frequency(self) -> str:
        """数据频率"""
        return self.metadata.get("frequency", "")

    @property
    def tags(self) -> List[str]:
        """标签列表"""
        return self.metadata.get("tags", [])

    @property
    def hypothesis_id(self) -> Optional[str]:
        """关联的假设 ID"""
        return self.metadata.get("hypothesis_id")

    @property
    def qsid(self) -> Optional[str]:
        """注册后的 QSID"""
        return self.metadata.get("qsid")

    @property
    def status(self) -> str:
        """因子状态"""
        return self.metadata.get("status", "unknown")

    # ============================================================
    # 标准方法
    # ============================================================

    def replay(self, fdi: Any) -> List[Any]:
        """执行 factor_def.py 中的 defFactor()，返回 Factor 对象列表。

        动态导入因子模块并调用其 defFactor 函数。支持两种返回类型：
        - List[Factor]
        - Def（标准模式，返回 Def.FactorList）

        Args:
            fdi: DefInput 运行时上下文

        Returns:
            QuantStudio Factor 对象列表

        Raises:
            RuntimeError: 模块加载或执行失败
        """
        module = self._load_module()

        if not hasattr(module, "defFactor"):
            raise RuntimeError(
                f"factor_def.py 中未找到 defFactor 函数: {self._dir_path}"
            )

        try:
            result = module.defFactor(fdi=fdi)
        except Exception as e:
            raise RuntimeError(f"defFactor() 执行失败: {e}") from e

        # 处理两种返回类型
        if isinstance(result, list):
            return result
        elif hasattr(result, "FactorList"):
            return result.FactorList
        else:
            raise RuntimeError(
                f"defFactor() 返回了未知类型: {type(result).__name__}"
            )

    def explain(self) -> str:
        """基于 metadata + README 生成标准化说明文本。

        Returns:
            格式化的因子说明文本
        """
        lines = [
            f"# {self.name}",
            self.description,
            "",
            f"- 分类: {self.category}",
            f"- 市场: {self.market}",
            f"- 频率: {self.frequency}",
            f"- 公式: `{self.formula}`",
            f"- 标签: {', '.join(self.tags)}",
            f"- 状态: {self.status}",
        ]

        if self.hypothesis_id:
            lines.append(f"- 假设ID: {self.hypothesis_id}")
        if self.qsid:
            lines.append(f"- QSID: {self.qsid}")

        if self.readme:
            lines.extend(["", "## 详细说明", "", self.readme])

        return "\n".join(lines)

    def unit_test(self) -> dict:
        """汇总 validation/ 目录下的所有检查结果。

        Returns:
            验证结果字典::

                {
                    "passed": bool,      # 所有检查是否通过
                    "checks": {str: str}, # 各项检查结果
                    "details": dict,      # 详细信息
                    "issues": list,       # 发现的问题
                }
        """
        syntax = self.validation.get("syntax_report") or {}
        checks = {}
        # 从 syntax_report.json 提取各项检查结果
        for key in ("syntax", "execution", "leak_test", "unit_consistency", "semantic_review"):
            checks[key] = syntax.get(key, "unknown")

        has_checks = any(v != "unknown" for v in checks.values())
        passed = has_checks and all(
            v == "passed" for v in checks.values() if v != "unknown"
        )

        return {
            "passed": passed,
            "checks": checks,
            "details": syntax.get("details", {}),
            "issues": syntax.get("issues", []),
        }

    def to_archive(self) -> dict:
        """序列化为可存档的字典。

        用于写入 MiningLogDB 或导出归档。

        Returns:
            包含所有因子产物的字典
        """
        return {
            "dir_path": str(self._dir_path),
            "metadata": self.metadata,
            "params": self.params,
            "validation": self.validation,
            "code": self.code,
        }

    # ============================================================
    # 内部方法
    # ============================================================

    def _load_json(self, relative_path: str, default: Any = None) -> Any:
        """加载 JSON 文件。

        Args:
            relative_path: 相对于因子目录的路径
            default: 文件不存在时的默认值

        Returns:
            解析后的 JSON 对象
        """
        file_path = self._dir_path / relative_path
        if not file_path.exists():
            if default is not None:
                return default
            raise FileNotFoundError(f"文件不存在: {file_path}")
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败 ({relative_path}): {e}") from e

    def _load_text(self, relative_path: str) -> str:
        """加载文本文件。

        Args:
            relative_path: 相对于因子目录的路径

        Returns:
            文件内容
        """
        file_path = self._dir_path / relative_path
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        return file_path.read_text(encoding="utf-8")

    def _load_module(self) -> Any:
        """动态加载 factor_def.py 模块（带缓存）。

        Returns:
            已加载的 Python 模块对象
        """
        if self._module is not None:
            return self._module

        module_path = self._dir_path / "factor_def.py"
        spec = importlib.util.spec_from_file_location(
            f"_factor_def_{self.name}", str(module_path)
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法创建模块 spec: {module_path}")

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise RuntimeError(
                f"factor_def.py 加载失败: {e}"
            ) from e

        self._module = module
        return module


# ============================================================
# 工具函数
# ============================================================


def validate_factor_dir(dir_path: str) -> Tuple[bool, List[str]]:
    """校验因子目录结构完整性。

    检查必需文件和可选目录是否存在。

    Args:
        dir_path: 因子目录路径

    Returns:
        (is_valid, error_messages): 是否合法及错误信息列表
    """
    d = Path(dir_path)
    errors = []

    if not d.is_dir():
        return False, [f"目录不存在: {dir_path}"]

    # 必需文件
    if not (d / "factor_def.py").exists():
        errors.append("缺少必需文件: factor_def.py")
    if not (d / "metadata.json").exists():
        errors.append("缺少必需文件: metadata.json")
    elif (d / "metadata.json").exists():
        # 校验 metadata.json 可解析
        try:
            meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
            if not meta.get("factor_name"):
                errors.append("metadata.json 缺少 factor_name 字段")
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f"metadata.json 解析失败: {e}")

    # 校验 factor_def.py 可解析
    if (d / "factor_def.py").exists():
        try:
            code = (d / "factor_def.py").read_text(encoding="utf-8")
            if "defFactor" not in code:
                errors.append("factor_def.py 中未找到 defFactor 函数")
        except OSError as e:
            errors.append(f"factor_def.py 读取失败: {e}")

    return len(errors) == 0, errors
