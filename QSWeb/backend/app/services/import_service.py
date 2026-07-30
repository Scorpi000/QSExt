"""
因子脚本导入服务

通过 importlib 加载 FactorDef 脚本模块，读取 __FACTOR_META__ 和验证 defFactor。
"""
import ast
import importlib.util
import os
import shutil
import sys
import tempfile
from typing import Optional
from dataclasses import dataclass, field

from app.core.config import settings


@dataclass
class ImportResult:
    """导入验证结果"""
    success: bool
    filename: str = ""
    saved_path: str = ""
    meta: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    has_def_factor: bool = False
    has_meta: bool = False
    was_renamed: bool = False
    original_filename: str = ""


class ImportService:
    """因子脚本导入服务"""

    # ── 公开 API ──

    def validate_import(self, code: str, filename: str = "factor.py") -> ImportResult:
        """通过实际导入模块来验证脚本，读取 __FACTOR_META__ 和检测 defFactor"""
        result = ImportResult(success=False, filename=filename)

        # 语法检查（快速失败）
        try:
            ast.parse(code)
        except SyntaxError as e:
            result.errors.append(f"语法错误: 行 {e.lineno}, {e.msg}")
            return result

        # 写入临时文件 → importlib 加载 → 读取元信息
        tmpdir = tempfile.mkdtemp()
        modname = filename.rsplit(".py", 1)[0]
        try:
            tmpfile = os.path.join(tmpdir, filename)
            with open(tmpfile, "w", encoding="utf-8") as f:
                f.write(code)

            sys.path.insert(0, tmpdir)
            try:
                spec = importlib.util.spec_from_file_location(modname, tmpfile)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # 读取 __FACTOR_META__
                meta = getattr(module, "__FACTOR_META__", None)
                if meta is None or not isinstance(meta, dict):
                    result.warnings.append("脚本未声明 __FACTOR_META__ 字典")
                    result.meta = {}
                    result.has_meta = False
                else:
                    result.meta = self._serialize_meta(meta)
                    result.has_meta = True

                # 检测 defFactor
                result.has_def_factor = (
                    hasattr(module, "defFactor") and callable(module.defFactor)
                )
                if not result.has_def_factor:
                    result.warnings.append("脚本缺少 defFactor(fdi) 函数定义")

            except ImportError as e:
                result.warnings.append(f"导入模块失败（缺少依赖）: {e}")
            except Exception as e:
                result.errors.append(f"模块加载异常: {e}")
                return result
            finally:
                sys.path.remove(tmpdir)
                sys.modules.pop(modname, None)

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        # 校验字段
        if result.has_meta:
            self._validate_meta_fields(result.meta, result.warnings)
        if result.meta.get("DBDeps"):
            for db_name in result.meta["DBDeps"]:
                result.warnings.append(
                    f"声明依赖因子库 '{db_name}'，请确保运行时已配置"
                )

        result.success = True
        return result

    def save_script(self, code: str, filename: str) -> tuple:
        """保存脚本到配置的 scripts_dir，自动处理重名

        Returns:
            (target_path, was_renamed, original_filename)
        """
        scripts_dir = settings.factor_def["scripts_dir"]
        os.makedirs(scripts_dir, exist_ok=True)

        if not filename.endswith(".py"):
            filename += ".py"

        original = filename
        target = os.path.join(scripts_dir, filename)

        if os.path.exists(target):
            base = filename.rsplit(".py", 1)[0]
            counter = 1
            while True:
                filename = f"{base}_{counter}.py"
                target = os.path.join(scripts_dir, filename)
                if not os.path.exists(target):
                    break
                counter += 1
            was_renamed = True
        else:
            was_renamed = False

        with open(target, "w", encoding="utf-8") as f:
            f.write(code)
        return target, was_renamed, original

    # ── 元信息处理 ──

    def _serialize_meta(self, meta: dict) -> dict:
        """将 __FACTOR_META__ 序列化为 JSON 兼容格式"""
        result = {}
        for k, v in meta.items():
            if isinstance(v, (str, int, float, bool, type(None))):
                result[k] = v
            elif isinstance(v, (list, tuple)):
                result[k] = [self._serialize_value(x) for x in v]
            elif isinstance(v, dict):
                result[k] = {str(dk): self._serialize_value(dv) for dk, dv in v.items()}
            else:
                result[k] = str(v)
        return result

    def _serialize_value(self, v):
        if isinstance(v, (str, int, float, bool, type(None))):
            return v
        if isinstance(v, dict):
            return {str(dk): self._serialize_value(dv) for dk, dv in v.items()}
        if isinstance(v, (list, tuple)):
            return [self._serialize_value(x) for x in v]
        return str(v)

    def _validate_meta_fields(self, meta: dict, warnings: list) -> None:
        if not meta.get("TargetTable"):
            warnings.append("__FACTOR_META__ 缺少 TargetTable 字段")
        if not meta.get("IDType"):
            warnings.append("__FACTOR_META__ 缺少 IDType 字段")
        if not meta.get("Description"):
            warnings.append("__FACTOR_META__ 缺少 Description 字段（建议补充）")

    def register_to_graph(self, script_path: str, settings_path: str) -> str:
        """通过 register_factors_to_graphdb.py 将脚本注册到 Neo4j

        调用 register_factors_to_graphdb.main() 走完整流程：
        JYDB 连接 → ID 解析 → defFactor 执行 → storeFactors → Neo4j 写入。

        Args:
            script_path: 因子脚本文件路径
            settings_path: FactorDef settings.py 路径

        Returns:
            注册结果摘要
        """
        from QSExt.FactorDef.scripts.register_factors_to_graphdb import (
            main as register_main,
            _build_profiles_from_modules,
        )

        # 文件路径 → Python 模块名
        # 将脚本所在目录临时加入 sys.path，使其可被 importlib 导入
        script_dir = os.path.dirname(os.path.abspath(script_path))
        modname = os.path.splitext(os.path.basename(script_path))[0]

        in_sys_path = script_dir in sys.path
        if not in_sys_path:
            sys.path.insert(0, script_dir)

        try:
            id_profiles = _build_profiles_from_modules(
                [modname], default_id_type="A股"
            )
            register_main(
                settings_path=settings_path,
                id_profiles=id_profiles,
                skip_embedding=True,
            )
        finally:
            if not in_sys_path:
                sys.path.remove(script_dir)

        return f"已注册: {script_path}"


# 全局实例
import_service = ImportService()
