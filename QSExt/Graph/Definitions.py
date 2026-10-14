"""以稳定 ID 和版本注册可构图组件，目录查询不实例化组件。"""
from dataclasses import dataclass
from typing import Callable

from QuantStudio.Core.Input import InputModel
from QuantStudio.Core.Node import Node
from QuantStudio.Core.NodeTemplate import NodeTemplate
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import FactorOperator

from .Metadata import TypeRegistry, describe_fields
from .Protocol import DefinitionDescriptor, DefinitionRef, TypeDescriptor


class OperatorInput(InputModel):
    """应用已有算子的入口，其他槽位由上游算子推断。"""

    operator: FactorOperator


class TemplateInput(InputModel):
    """应用已有节点模板的入口。"""

    template: NodeTemplate


class EmptyArgs(InputModel):
    """不需要额外参数的构造器。"""


@dataclass(frozen=True)
class Definition:
    """代码定义；builder 只负责构图，禁止连接资源或执行计算。"""

    id: str
    version: int
    title: str
    description: str
    kind: str
    args_model: type
    input_model: type
    output: TypeDescriptor
    builder: Callable
    operations: tuple[str, ...]
    infer_output: Callable | None = None

    def output_type(self, operation, args):
        """在不调用构造器的情况下确定出口类型。"""
        if operation == "bind":
            return TypeDescriptor(kind="operator", type_id="qs.operator")
        if operation == "template":
            return TypeDescriptor(kind="template", type_id="qs.template")
        return self.infer_output(args) if self.infer_output else self.output.model_copy(deep=True)


class DefinitionRegistry:
    """独立于图数据库的内存定义目录。"""

    def __init__(self, types=None):
        self.types = types or TypeRegistry()
        self._definitions = {}

    def register(self, definition):
        """注册指定版本，重复注册视为配置错误。"""
        key = (definition.id, definition.version)
        if key in self._definitions:
            raise ValueError(f"定义已注册: {key}")
        self._definitions[key] = definition
        return definition

    def get(self, reference, version=1):
        """仅查找精确版本，不自动升级文档中的行为版本。"""
        key = (reference.id, reference.version) if isinstance(reference, DefinitionRef) else (reference, version)
        return self._definitions[key]

    def describe_definition(self, reference, version=1):
        """生成可直接通过 JSON 返回给 GUI 的定义描述。"""
        definition = self.get(reference, version)
        return DefinitionDescriptor(definition=DefinitionRef(id=definition.id, version=definition.version),
            title=definition.title, description=definition.description, operations=list(definition.operations),
            args=describe_fields(definition.args_model, self.types), inputs=describe_fields(definition.input_model, self.types),
            outputs={"result": definition.output_type(definition.operations[0], {})},
            dynamic_inputs=definition.kind in ("operator_apply", "template_apply"))

    def list_definitions(self):
        """按注册顺序返回目录，不构造业务对象。"""
        return [self.describe_definition(id_, version) for id_, version in self._definitions]

    def register_node(self, id_, node_class, version=1, title=None):
        """注册提供统一模板构造入口的 Node 子类。"""
        if not issubclass(node_class, Node):
            raise TypeError("节点定义必须是 Node 子类")
        type_id = f"{id_}.result"
        self.types.register(type_id, node_class)

        def builder(block, args, inputs):
            template = node_class.template(args=args, deps=inputs)
            return template if block.operation == "template" else template.build()

        return self.register(Definition(id_, version, title or node_class.__name__, node_class.__doc__ or "", "node",
            node_class.__QS_ArgClass__, node_class.__QS_DepClass__, self.types.describe(node_class), builder, ("build", "template")))

    def register_operator(self, id_, operator_class, version=1, title=None, factory=None, infer_output=None):
        """注册因子算子；参数构造可由可信代码提供工厂适配。"""
        if not issubclass(operator_class, FactorOperator):
            raise TypeError("算子定义必须是 FactorOperator 子类")

        def builder(block, args, inputs):
            operator = factory(args) if factory else operator_class(args=args)
            return operator.bind(**inputs) if block.operation == "bind" else operator(**inputs, factor_args=block.result_args)

        return self.register(Definition(id_, version, title or operator_class.__name__, operator_class.__doc__ or "", "operator",
            operator_class.__QS_ArgClass__, operator_class.__QS_InputClass__,
            TypeDescriptor(kind="factor", type_id="qs.factor"), builder, ("apply", "bind"), infer_output))

    def register_factory(self, id_, *, args_model, input_model, output, builder, version=1, title=None,
                         operations=("build",), infer_output=None):
        """注册脚本或扩展构造器，文档不能指定任意导入路径。

        Args:
            id_: 稳定定义 ID。
            args_model: 参数模型类。
            input_model: 输入模型类。
            output: 传输输出类型描述。
            builder: 接收 block、显式 args、已解析 inputs 的可信构造函数。
            version: 行为版本。
            title: 目录名称。
            operations: 允许的显式操作。
            infer_output: 可选纯元信息推断函数。
        Returns:
            已登记的代码定义。
        """
        return self.register(Definition(id_, version, title or id_, builder.__doc__ or "", "factory",
            args_model, input_model, output, builder, tuple(operations), infer_output))


def register_application_definitions(registry):
    """登记应用已有算子和模板的通用构造器。"""
    def apply_operator(block, args, inputs):
        operator = inputs["operator"]
        values = {key: value for key, value in inputs.items() if key != "operator"}
        return operator.bind(**values) if block.operation == "bind" else operator(**values, factor_args=block.result_args)

    def apply_template(block, args, inputs):
        template = inputs["template"].with_args(args)
        values = {key: value for key, value in inputs.items() if key != "template"}
        template = template.bind(**values)
        return template if block.operation == "template" else template.build()

    registry.register(Definition("qs.operator.apply", 1, "应用已有算子", "输入槽位由算子配方推断", "operator_apply",
        EmptyArgs, OperatorInput, TypeDescriptor(kind="factor", type_id="qs.factor"), apply_operator, ("apply", "bind")))
    registry.register(Definition("qs.template.build", 1, "构造已有模板", "输入槽位和参数由节点模板配方推断", "template_apply",
        EmptyArgs, TemplateInput, TypeDescriptor(kind="node", type_id="qs.node"), apply_template, ("build", "template")))


def create_default_registry():
    """按固定类名规则注册核心算子和来源，不加载数据库扩展。

    Returns:
        内存定义目录，定义 ID 为 ``qs.factor.<类名>``，类名大小写保留。
    """
    from QuantStudio.Factor import BasicOperator, FactorOperator as builtin
    from QuantStudio.Factor.Factor import DataFactor
    from .Sources import register_source_definitions
    from .Nodes import SelectResult
    import inspect
    registry = DefinitionRegistry()
    register_application_definitions(registry)
    registry.register_node("qs.factor.constant", DataFactor)
    registry.register_node("qs.node.select", SelectResult)
    for module in (BasicOperator, builtin):
        for name, cls in vars(module).items():
            # Rename 还需要因子名称等调用参数，使用独立的来源/节点参数编辑即可。
            if isinstance(cls, type) and cls.__module__ == module.__name__ and issubclass(cls, FactorOperator) and name != "Rename":
                if any(parameter.default is inspect.Parameter.empty and parameter.name != "self" and
                       parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                       for parameter in inspect.signature(cls.__init__).parameters.values()):
                    continue
                registry.register_operator(f"qs.factor.{name}", cls)
    register_source_definitions(registry)
    register_extension_definitions(registry)
    return registry


def register_extension_definitions(registry):
    """登记常用扩展算子和无需配置 IO 的回测节点。

    数据库适配、报告配置和可选评测工具仍由应用显式注册。
    """
    from QSExt.Factor import FactorOperator as operators, MLOperator
    from QSExt.BackTest.TSFactor.Correlation import TimeSeriesCorrelation, TimeSeriesCorrelationReport
    for module in (operators, MLOperator):
        for name, cls in vars(module).items():
            if isinstance(cls, type) and cls.__module__ == module.__name__ and issubclass(cls, FactorOperator):
                registry.register_operator(f"qsext.factor.{name}", cls)
    registry.register_node("qsext.backtest.TimeSeriesCorrelation", TimeSeriesCorrelation)
    registry.register_node("qsext.report.TimeSeriesCorrelation", TimeSeriesCorrelationReport)
