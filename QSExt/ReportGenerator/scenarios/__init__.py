# -*- coding: utf-8 -*-
"""报告场景注册表

提供 ``ScenarioRegistry``，管理报告场景（ReportGenerator 子类）的注册与查找。
每个场景关联一个类型（``factor`` 或 ``strategy``），用于驱动脚本的输入加载逻辑。

使用方式::

    from QSExt.ReportGenerator.scenarios import ScenarioRegistry

    ScenarioRegistry.register("single_factor", SingleFactorReport, "factor")
    cls = ScenarioRegistry.get("single_factor")
    scenario_type = ScenarioRegistry.get_type("single_factor")  # "factor"
"""

from typing import Dict, List, Type


class ScenarioRegistry:
    """报告场景注册表。

    通过名称注册和查找 ReportGenerator 子类。
    每个场景关联一个类型（``factor`` 或 ``strategy``），用于驱动脚本的输入加载逻辑。
    """

    _scenarios: Dict[str, Type] = {}
    _types: Dict[str, str] = {}  # name -> "factor" | "strategy"

    @classmethod
    def register(cls, name: str, scenario_cls, scenario_type: str = "factor"):
        """注册一个场景类。

        Args:
            name: 场景名称
            scenario_cls: ReportGenerator 子类
            scenario_type: 场景类型，``"factor"`` 或 ``"strategy"``
        """
        cls._scenarios[name] = scenario_cls
        cls._types[name] = scenario_type

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
    def get_type(cls, name: str) -> str:
        """获取场景类型。

        Returns:
            ``"factor"`` 或 ``"strategy"``，未注册时返回 ``"factor"``
        """
        return cls._types.get(name, "factor")

    @classmethod
    def list_all(cls) -> List[str]:
        """列出所有已注册场景名。"""
        return list(cls._scenarios.keys())


def _register_builtin_scenarios():
    """注册所有内置场景。"""
    from QSExt.ReportGenerator.scenarios.single_factor.scenario import (
        SingleFactorReport,
    )
    from QSExt.ReportGenerator.scenarios.single_strategy.scenario import (
        SingleStrategyReport,
    )
    from QSExt.ReportGenerator.scenarios.multi_strategy.scenario import (
        MultiStrategyReport,
    )
    from QSExt.ReportGenerator.scenarios.multi_factor.scenario import (
        MultiFactorReport,
    )

    ScenarioRegistry.register("single_factor", SingleFactorReport, "factor")
    ScenarioRegistry.register("multi_factor", MultiFactorReport, "factor")
    ScenarioRegistry.register("single_strategy", SingleStrategyReport, "strategy")
    ScenarioRegistry.register("multi_strategy", MultiStrategyReport, "strategy")


_register_builtin_scenarios()
