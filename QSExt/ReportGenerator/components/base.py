# -*- coding: utf-8 -*-
"""组件基类"""

from abc import ABCMeta, abstractmethod
from typing import Any


class Component(metaclass=ABCMeta):
    """报告可视化组件基类。

    每个组件实例通过 render() 方法将数据 + 参数 + 主题 → HTML/Markdown 片段。
    子类通过 name 属性注册到 ComponentRegistry。
    """

    name: str = "component"

    @abstractmethod
    def render(self, data: Any, params: dict, theme: "Theme",
               renderer: "ReportRenderer") -> str:
        """渲染组件为字符串片段。

        Args:
            data: 由 DataContext.get(source, key) 提供的原始数据
            params: YAML 中声明的组件参数
            theme: 当前主题
            renderer: 当前输出格式的渲染器
        """
