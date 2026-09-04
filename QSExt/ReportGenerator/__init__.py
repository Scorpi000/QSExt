# -*- coding: utf-8 -*-
"""
回测报告生成系统

提供基于 YAML 配置 + 组件库的报告生成框架。

核心设计：
- ``ReportGenerator`` 是通用的报告生成计算图节点，继承自 ``ReportNode``
- ``create_nodes()`` 类方法定义场景所需的上游数据节点（回测、风险、优化器等）
- ``generate_report()`` 将上游节点产出渲染为报告，输出包含 ``ReportKey`` 供 ``BTReport`` 聚合

子类化一个场景::

    class SingleFactorReport(ReportGenerator):
        @classmethod
        def create_nodes(cls, factors, price=None, ...):
            nodes = [...]
            return nodes

        def generate_report(self, output_list):
            # 按依赖顺序从 output_list 取数据，组织成 DataContext
            ...
            return layout_renderer.render(config, ctx, theme, fmt)
"""

from typing import Any, Dict, List

from pydantic import Field

from QuantStudio.BackTest.BackTestModel import ReportNode
from QuantStudio.Core.Node import Node


class ReportGenerator(ReportNode):
    """报告生成计算图节点。

    继承 ``ReportNode``，可直接嵌入回测计算图，也可被 ``BTReport`` 聚合。
    子类需实现两个方法：
    - ``create_nodes()``：定义场景需要哪些上游数据节点
    - ``generate_report()``：将上游节点产出渲染为报告，直接写入 ReportKey
    """

    class __QS_ArgClass__(ReportNode.__QS_ArgClass__):
        Name: str = Field(default="报告生成器", frozen=True, title="名称")
        OutputFormat: str = Field(default="html", title="输出格式", description="报告输出格式：html 或 markdown")
        ThemeName: str = Field(default="default", title="主题名称")
        ChartEngine: str = Field(default="plotly", title="图表引擎", description="plotly（交互式）或 matplotlib（静态）")

    # ---- 子类必须实现 ----

    @classmethod
    def create_nodes(cls, *args, **kwargs) -> List[Node]:
        """创建报告所需的计算图节点。

        子类实现此方法，返回上游数据节点列表。
        这些节点可以是回测、因子分析、风险模型等任意类型的 Node。

        Returns:
            上游数据节点列表，顺序与 generate_report 中 output_list 一致
        """
        raise NotImplementedError

    def generate_report(self, output_list: List[Any]) -> Dict[str, str]:
        """根据上游节点的运行结果生成报告。

        子类实现此方法，将 output_list 渲染后直接写入 ReportKey。

        Args:
            output_list: 上游节点的产出列表，顺序与 create_nodes 返回的节点一致

        Returns:
            {ReportKey: 报告内容}
        """
        raise NotImplementedError

    # ---- Node DAG 接口 ----

    def backward_compute(self, path, bwd_data_list, context, local_context=None):
        return self.generate_report(bwd_data_list)
