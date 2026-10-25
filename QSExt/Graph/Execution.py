"""图根节点的执行输入适配，不绑定 Web 任务或资源存储。"""
from dataclasses import dataclass

from QuantStudio.Core.Node import DTInitData, DTLocalContext
from QuantStudio.Factor.Factor import Factor, FactorInitData, FactorLocalContext
from .Context import GraphContext


@dataclass(frozen=True)
class ExecutionInputs:
    init_data: object
    forward_data: object


def execution_inputs(nodes, runtime, *, context_class=GraphContext):
    """特殊节点可用静态 __QS_GraphExecutionAdapter__(node, runtime) 声明输入。"""
    dates, ids = runtime["dates"], runtime["section_ids"]
    if not dates:
        raise ValueError("计算图运行需要非空日期序列")
    result = []
    for node in nodes:
        required = getattr(type(node), "__QS_GraphContextClass__", context_class)
        if not isinstance(required, type) or not issubclass(context_class, required):
            raise TypeError(f"节点 {node.Name} 需要专用全局上下文，当前计算图执行器不支持")
        adapter = getattr(type(node), "__QS_GraphExecutionAdapter__", None)
        if adapter is not None:
            value = adapter(node, runtime)
            if not isinstance(value, ExecutionInputs):
                raise TypeError(f"节点 {node.Name} 的执行适配器必须返回 ExecutionInputs")
        elif isinstance(node, Factor):
            value = ExecutionInputs(FactorInitData(DTRange=(dates[0], dates[-1])), FactorLocalContext(DTs=dates, IDs=ids))
        else:
            value = ExecutionInputs(DTInitData(DTRange=(dates[0], dates[-1])), DTLocalContext(DTs=dates))
        result.append(value)
    return result
