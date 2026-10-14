"""应用无关的结果投影节点，不在编译阶段访问计算结果。"""
from pydantic import Field

from QuantStudio.Core.Identity import ExecutionEffect
from QuantStudio.Core.Input import DependencyModel
from QuantStudio.Core.Node import Node


class SelectResult(Node):
    """在执行时按字段或下标逐级选择上游结果。"""

    __QS_ExecutionEffect__ = ExecutionEffect.PURE

    class __QS_DepClass__(DependencyModel):
        source: Node = Field(title="待投影的结果节点")

    class __QS_ArgClass__(Node.__QS_ArgClass__):
        Path: tuple[str | int, ...] = Field(default=(), frozen=True, title="结果路径")

    def backward_compute(self, path, inputs, context, local_context=None):
        """读取已完成的上游结果，不重复构造或计算上游。"""
        value = inputs.source
        for key in self._QSArgs.Path:
            value = value[key]
        return value
