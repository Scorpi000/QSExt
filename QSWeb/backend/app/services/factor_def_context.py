"""
全局 FactorDef 上下文服务

从 settings.py 构建可复用的 FactorDefInput 基础上下文，
供各 API 端点即时执行因子定义脚本获取 Factor 对象列表。
"""

import importlib.util
import logging
import os
import sys
from typing import Dict, List, Optional

from app.core.config import settings as app_settings

logger = logging.getLogger(__name__)


def _file_to_module_path(filepath: str) -> Optional[str]:
    """尝试将 .py 文件路径转为 Python 模块路径

    通过反向搜索包路径: 从文件所在目录向上查找，
    找到第一个不在任何包中的目录作为根。
    """
    filepath = os.path.abspath(filepath)
    if not filepath.endswith('.py'):
        return None

    modname = os.path.splitext(os.path.basename(filepath))[0]
    directory = os.path.dirname(filepath)
    parts = [modname]

    # 从文件目录向上查找 __init__.py
    while directory and os.path.isfile(os.path.join(directory, '__init__.py')):
        parts.insert(0, os.path.basename(directory))
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent

    return '.'.join(parts)


class FactorDefContext:
    """全局 FactorDef 运行时上下文

    从 QSWebConfig.yaml 中 factor_def.settings_path 指定的 settings.py
    构建 FactorDBPool 和 FactorDefInput，支持即时执行任意因子定义脚本的 defFactor。
    """

    def __init__(self):
        self._builder = None
        self._fdi = None
        self._loaded = False

    @property
    def is_available(self) -> bool:
        """上下文是否可用"""
        if not self._loaded:
            self._load()
        return self._builder is not None

    def _load(self):
        """加载 settings 并构建 FactorDefInputBuilder"""
        self._loaded = True
        settings_path = app_settings.factor_def.get("settings_path")
        if not settings_path:
            logger.warning("未配置 factor_def.settings_path，FactorDefContext 不可用")
            return

        settings_path = os.path.expanduser(settings_path)
        if not os.path.isfile(settings_path):
            logger.warning(f"settings 文件不存在: {settings_path}")
            return

        try:
            from QSExt.FactorDef.FactorDefContent import FactorDefInputBuilder, FactorDefSettings

            settings = FactorDefSettings.from_module(settings_path)
            self._builder = FactorDefInputBuilder(settings)
            self._builder.init()
            self._fdi = self._builder.build()
            logger.info(f"FactorDefContext 已初始化, {len(self._fdi.FDB)} 个因子库, "
                        f"{len(self._fdi.IDs)} IDs, {len(self._fdi.DTs)} DTs")

        except Exception as e:
            logger.error(f"FactorDefContext 初始化失败: {e}")
            self._builder = None
            self._fdi = None

    @property
    def fdi(self) -> "FactorDefInput":
        """基础 FactorDefInput 实例"""
        if not self.is_available:
            raise RuntimeError("FactorDefContext 不可用")
        return self._fdi

    def execute_script(self, script_path: str) -> List:
        """执行因子定义脚本，返回因子对象列表

        使用 FactorDefInputBuilder 构建的基础 fdi，调用脚本的 defFactor(fdi)，
        包含完整的 FDB、DTs、IDs 上下文。自动解析 FactorDeps 依赖。

        Args:
            script_path: .py 脚本路径

        Returns:
            List[Factor] 因子对象列表
        """
        if not self.is_available:
            raise RuntimeError("FactorDefContext 不可用")

        script_path = os.path.abspath(os.path.expanduser(script_path))
        if not os.path.isfile(script_path):
            raise ValueError(f"脚本不存在: {script_path}")

        from QSExt.FactorDef.FactorDefContent import build_dep_fd

        # 加载脚本模块
        modname = f"_qsweb_fd_{os.path.splitext(os.path.basename(script_path))[0]}"
        script_dir = os.path.dirname(script_path)
        in_sys_path = script_dir in sys.path
        if not in_sys_path:
            sys.path.insert(0, script_dir)

        try:
            spec = importlib.util.spec_from_file_location(modname, script_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if not hasattr(mod, "defFactor"):
                raise ValueError("脚本未定义 defFactor 函数")

            # 构建包装模块列表传入 build_dep_fd
            modules = [(mod, {}, {})]
            fdi = self._builder.build()

            dep_fd, factor_defs = build_dep_fd(modules, fdi)

            all_factors = []
            for fd, _ in factor_defs:
                if fd is not None:
                    all_factors.extend(fd.FactorList)

            return all_factors

        finally:
            sys.modules.pop(modname, None)
            if not in_sys_path:
                sys.path.remove(script_dir)

    def get_script_terminals(self, script_path: str) -> List[dict]:
        """从脚本获取因子的叶节点终端因子列表

        执行 defFactor 获取因子, 展开每个因子提取 DataFactor 叶节点去重。

        Returns:
            [{"conn_id": ..., "table_name": ..., "factor_name": ...}, ...]
        """
        from QuantStudio.Factor.FactorOperation import DerivativeFactor
        from QuantStudio.Factor.Factor import DataFactor
        from QSExt.GPFactor.GPLearn import flattenFactor2PN

        factors = self.execute_script(script_path)
        terminals = []
        seen = set()

        for factor in factors:
            pn = flattenFactor2PN(factor)
            for node in pn:
                if isinstance(node, DerivativeFactor):
                    continue
                ft = getattr(node, "_FactorTable", None)
                if ft is None:
                    continue
                conn_id = ft.FactorDB.Name if ft.FactorDB else ""
                table_name = ft.Name
                key = f"{conn_id}/{table_name}/{node.Name}"
                if key not in seen:
                    seen.add(key)
                    terminals.append({
                        "conn_id": conn_id,
                        "table_name": table_name,
                        "factor_name": node.Name,
                    })

        return terminals


# 全局单例
factor_def_context = FactorDefContext()
