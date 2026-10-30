"""图根节点的执行输入适配，不绑定 Web 任务或资源存储。"""
from dataclasses import dataclass

from QuantStudio.Core.Node import DTInitData, DTLocalContext
from QuantStudio.Factor.Factor import Factor, FactorInitData, FactorLocalContext
from .Context import GraphContext


@dataclass(frozen=True)
class ExecutionInputs:
    init_data: object
    forward_data: object


def execution_inputs(nodes, runtime, *, context_class=GraphContext, section_node_types=()):
    """生成根输出请求，特殊节点也可用静态适配器声明输入。

    Args:
        nodes: 本次执行的根节点。
        runtime: 已解析的日期、标尺和证券截面。
        context_class: 执行器使用的全局上下文类。
        section_node_types: 除 Factor 外需要日期及证券截面的节点类型元组。

    Returns:
        与根节点顺序一致的初始化及前向请求列表。
    """
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
        elif isinstance(node, section_node_types):
            value = ExecutionInputs(FactorInitData(DTRange=(dates[0], dates[-1]), SectionIDs=ids),
                                    FactorLocalContext(DTs=dates, IDs=ids, SectionIDs=ids))
        else:
            value = ExecutionInputs(DTInitData(DTRange=(dates[0], dates[-1])), DTLocalContext(DTs=dates))
        result.append(value)
    return result
