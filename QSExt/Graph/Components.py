"""组件列表的声明协议，将类或构图声明转换为内部注册项。"""
from dataclasses import dataclass
import inspect
import sys
from typing import Callable

from QuantStudio.Core.Node import Node
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import FactorOperator

from .Definitions import Definition, EmptyArgs, OperatorInput, TemplateInput


@dataclass(frozen=True)
class Component:
    """列表中的组件声明；普通节点和算子也可以直接使用类。

    Attributes:
        target: 可选的节点或算子类，用于覆盖其目录元信息。
        id: 固定组件标识，缺省根据类或构图函数的模块路径生成。
        title: 中文标题，缺省使用类名或构图函数名。
        category: 分类，缺省继承定义文件的 CATEGORY。
        version: 行为版本，默认为 1。
        args_model: 组合组件的 Pydantic 参数模型。
        input_model: 组合组件的 Pydantic 输入模型。
        output_type: 组合组件返回的节点或算子类型。
        builder: 组合组件的 builder(block, args, inputs) 构图函数。
        operations: 组合组件支持的操作，默认为 build。
        infer_output: 可选的纯输出元信息推断函数。
        kind: 内部构图协议类别，业务组合组件使用默认 factory。
    """

    target: type | None = None
    id: str | None = None
    title: str | None = None
    category: str | None = None
    version: int = 1
    args_model: type | None = None
    input_model: type | None = None
    output_type: type | None = None
    builder: Callable | None = None
    operations: tuple[str, ...] = ("build",)
    infer_output: Callable | None = None
    kind: str = "factory"


def component_id(target):
    """生成不包含服务目录绝对路径或加载批次摘要的标识。"""
    module = target.__module__
    if module.split(".")[0].startswith("qs_components_"):
        namespace = getattr(sys.modules.get(module.split(".")[0]), "__qs_component_namespace__", "components")
        module = namespace + module[module.find("."):] if "." in module else namespace
    return f"{module}.{target.__qualname__}"


def as_component(value):
    """统一列表项，并拒绝构造器尚不符合协议的声明。"""
    item = value if isinstance(value, Component) else Component(target=value)
    if item.id is not None and (not isinstance(item.id, str) or not item.id.strip()):
        raise ValueError("组件 ID 必须为非空字符串")
    if type(item.version) is not int or item.version < 1:
        raise ValueError("组件版本必须为正整数")
    if item.category is not None and (not isinstance(item.category, str) or not item.category.strip()):
        raise ValueError("组件分类必须为非空字符串")
    if item.target is not None:
        if not isinstance(item.target, type) or not issubclass(item.target, (Node, FactorOperator)):
            raise TypeError("COMPONENTS 中只能放 Node/FactorOperator 子类或 Component 声明")
        if item.target in (Node, Factor, FactorOperator) or inspect.isabstract(item.target):
            raise TypeError("组件不能使用抽象类或框架基类")
        if any(value is not None for value in (item.args_model, item.input_model, item.output_type, item.builder)):
            raise ValueError("类组件通过 target 提取声明，不能同时指定组合组件字段")
        if issubclass(item.target, FactorOperator) and any(
            parameter.default is inspect.Parameter.empty and parameter.name != "self"
            and parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            for parameter in inspect.signature(item.target.__init__).parameters.values()
        ):
            raise TypeError("算子构造器存在必填位置参数，请使用 Component 的 builder 显式适配")
    else:
        if not callable(item.builder) or item.args_model is None or item.input_model is None:
            raise TypeError("组合组件必须声明 args_model、input_model 和 builder")
        if not isinstance(item.output_type, type) or not issubclass(item.output_type, (Node, FactorOperator)):
            raise TypeError("组合组件 output_type 必须为 Node 或 FactorOperator 类型")
        if item.kind not in ("factory", "operator_apply", "template_apply"):
            raise ValueError("无效的组件构图类别")
    return item


def register_component(registry, value, category=None):
    """自动登记一个列表项，仅提取声明，不创建计算对象。"""
    item = as_component(value)
    target = item.target or item.builder
    id_ = item.id or component_id(target)
    category = item.category or category or ("因子算子" if item.target and issubclass(item.target, FactorOperator) else "通用")
    title = item.title or target.__name__
    if item.target:
        if issubclass(item.target, FactorOperator):
            return registry.register_operator(id_, item.target, version=item.version, title=title,
                category=category, infer_output=item.infer_output)
        return registry.register_node(id_, item.target, version=item.version, title=title, category=category)
    # 类型先于描述登记，下游报告能够检查具体的分析结果类型。
    registry.types.register(component_id(item.output_type), item.output_type)
    return registry.register(Definition(id_, item.version, title, item.builder.__doc__ or "", item.kind,
        item.args_model, item.input_model, registry.types.describe(item.output_type), item.builder,
        tuple(item.operations), item.infer_output, category))


def _apply_operator(block, args, inputs):
    """应用上游算子，保留动态输入推断协议。"""
    operator = inputs["operator"]
    values = {key: value for key, value in inputs.items() if key != "operator"}
    return operator.bind(**values) if block.operation == "bind" else operator(**values, factor_args=block.result_args)


def _apply_template(block, args, inputs):
    """构建上游节点模板，保留动态参数和输入协议。"""
    template = inputs["template"].with_args(args)
    values = {key: value for key, value in inputs.items() if key != "template"}
    template = template.bind(**values)
    return template if block.operation == "template" else template.build()


APPLICATION_COMPONENTS = [
    Component(id="qs.operator.apply", title="应用已有算子", args_model=EmptyArgs, input_model=OperatorInput,
        output_type=Factor, builder=_apply_operator, operations=("apply", "bind"), kind="operator_apply"),
    Component(id="qs.template.build", title="构造已有模板", args_model=EmptyArgs, input_model=TemplateInput,
        output_type=Node, builder=_apply_template, operations=("build", "template"), kind="template_apply"),
]
