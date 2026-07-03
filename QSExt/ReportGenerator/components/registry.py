# -*- coding: utf-8 -*-
"""组件注册表"""

from typing import Dict, List, Type


class ComponentRegistry:
    """全局组件注册表。

    使用方式：
        ComponentRegistry.register("chart", Chart)
        chart_cls = ComponentRegistry.get("chart")
    """

    _components: Dict[str, Type["Component"]] = {}  # noqa: F821

    @classmethod
    def register(cls, name: str, component_cls: Type["Component"]):  # noqa: F821
        """注册一个组件类"""
        cls._components[name] = component_cls

    @classmethod
    def get(cls, name: str) -> Type["Component"]:  # noqa: F821
        """获取已注册的组件类

        Raises:
            KeyError: 组件未注册时抛出
        """
        if name not in cls._components:
            raise KeyError(
                f"未注册的组件: '{name}'，"
                f"可用组件: {list(cls._components.keys())}"
            )
        return cls._components[name]

    @classmethod
    def list_all(cls) -> List[str]:
        """列出所有已注册组件名"""
        return list(cls._components.keys())
