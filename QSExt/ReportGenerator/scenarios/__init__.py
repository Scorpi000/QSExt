# -*- coding: utf-8 -*-
"""报告场景注册表

提供 ``ScenarioRegistry``，管理报告场景（ReportGenerator 子类）的注册与查找。

使用方式::

    from QSExt.ReportGenerator.scenarios import ScenarioRegistry

    ScenarioRegistry.register("single_factor", SingleFactorReport)
    cls = ScenarioRegistry.get("single_factor")
"""

from typing import Dict, List, Type


class ScenarioRegistry:
    """报告场景注册表。

    通过名称注册和查找 ReportGenerator 子类。
    """

    _scenarios: Dict[str, Type] = {}

    @classmethod
    def register(cls, name: str, scenario_cls):
        """注册一个场景类。"""
        cls._scenarios[name] = scenario_cls

    @classmethod
    def get(cls, name: str):
        """获取已注册的场景类。

        Raises:
            KeyError: 场景未注册时抛出
        """
        if name not in cls._scenarios:
            raise KeyError(
                f"未注册的报告场景: '{name}'，"
                f"可用场景: {list(cls._scenarios.keys())}"
            )
        return cls._scenarios[name]

    @classmethod
    def list_all(cls) -> List[str]:
        """列出所有已注册场景名。"""
        return list(cls._scenarios.keys())


def _register_builtin_scenarios():
    """注册所有内置场景。"""
    from QSExt.ReportGenerator.scenarios.single_factor.scenario import (
        SingleFactorReport,
    )

    ScenarioRegistry.register("single_factor", SingleFactorReport)


_register_builtin_scenarios()
