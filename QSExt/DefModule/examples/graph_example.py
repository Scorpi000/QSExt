"""无需数据库的多输出 Node 示例，可直接上传到 QSWeb 的定义脚本导入窗口。"""
from pydantic import Field

from QuantStudio.Core.Input import DependencyModel, EmptyDependencies
from QuantStudio.Core.Node import Node
from QuantStudio.Factor.Factor import DataFactor
from QSExt.DefModule.DefContent import DefInput


__GRAPH_META__ = {
    "Description": "共享输入的普通节点与独立因子输出",
    "MaxLookBack": 0,
    "ModelArgs": {"value": "常量值，默认 3"},
}


class Value(Node):
    __QS_DepClass__ = EmptyDependencies

    class __QS_ArgClass__(Node.__QS_ArgClass__):
        Value: int = Field(default=3)

    def backward_compute(self, path, inputs, context, local_context=None):
        return self.Args.Value


class Summary(Node):
    class __QS_DepClass__(DependencyModel):
        values: tuple[Value, ...]

    def backward_compute(self, path, inputs, context, local_context=None):
        return {"total": sum(inputs.values)}


def defNode(di: DefInput) -> list[Node]:
    value = di.ModelArgs.get("value", 3)
    shared = Value(args={"Name": "value", "Value": value})
    summary = Summary.from_dependencies({"values": (shared, shared)}, args={"Name": "summary"})
    return [summary, DataFactor(value, args={"Name": "constant"})]
