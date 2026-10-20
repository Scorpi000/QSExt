"""在执行准备阶段读取外部因子资源的叶子节点。"""
import pandas as pd
from typing import Literal
from pydantic import Field
from pydantic import JsonValue

from QuantStudio.Core.Input import EmptyDependencies, InputModel
from QuantStudio.Core.Identity import ExecutionEffect
from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Factor.Factor import DataFactor, Factor, FactorContext

from .Protocol import ResourceDescriptor, TypeDescriptor
from .Resources import resolve_resource
from .Components import Component, register_component


class ResourceFactor(Factor):
    """因子库、已登记因子或上传表格的延迟读取适配。"""

    __QS_DepClass__ = EmptyDependencies
    __QS_ExecutionEffect__ = ExecutionEffect.READ

    class __QS_ArgClass__(Factor.__QS_ArgClass__):
        Resource: ResourceDescriptor = Field(frozen=True, title="资源语义描述")
        Table: str = Field(default="", frozen=True, title="因子表")
        FactorName: str = Field(default="", frozen=True, title="物理因子名称")
        TableArgs: dict[str, JsonValue] = Field(default_factory=dict, frozen=True, title="因子表参数")
        FactorArgs: dict[str, JsonValue] = Field(default_factory=dict, frozen=True, title="来源因子参数")
        DataType: str = Field(default="double", frozen=True, title="数据类型")

    def getMetaData(self, key=None):
        """只返回已声明元信息，不访问资源。"""
        metadata = {"DataType": self._QSArgs.DataType}
        return metadata if key is None else metadata.get(key)

    def init_compute(self, path, init_data, context):
        """将来源加入准备队列，保持来源为运行图叶子。"""
        state = context.NodeState.setdefault(self.InstanceID, {})
        state.setdefault("source_dates", set()).update(context.getDateTime(init_data.DTRange))
        state.setdefault("source_ids", set()).update(getattr(init_data, "SectionIDs", None) or self.Args.SectionIDs or context.SectionIDs)
        context.PrepareNodeDict[self.InstanceID] = (self.InstanceID, None)
        return []

    def prepare_compute(self, prepare_data, context):
        """解析当前运行的资源句柄，状态仅存放在 Context 中。"""
        state = context.NodeState[self.InstanceID]
        dates, ids = sorted(state.pop("source_dates")), sorted(state.pop("source_ids"))
        if dates:
            calculation_dates = self._QS_getCalcDTs(dates)
            if calculation_dates is not None:
                dates = calculation_dates
        if not dates:
            state["graph_resource"] = pd.DataFrame(index=dates, columns=ids)
            return
        resource = self._QSArgs.Resource
        handle = resolve_resource(context, resource)
        if resource.kind == "factor_database":
            handle = handle.getTable(self._QSArgs.Table, args=self._QSArgs.TableArgs) if self._QSArgs.TableArgs else handle.getTable(self._QSArgs.Table)
        if resource.kind == "factor_database" or isinstance(handle, Factor):
            nested_context = FactorContext(DTRuler=context.DTRuler, SectionIDs=ids,
                Resources=context.Resources, DataVersion=context.DataVersion)
            # readData 会启动一次引擎运行，必须隔离外层图的状态和缓存。
            with nested_context, Engine(args={"IOConcurrentNum": 1}):
                if resource.kind == "factor_database":
                    if self._QSArgs.FactorArgs:
                        factor = handle.getFactor(self._QSArgs.FactorName, args=self._QSArgs.FactorArgs)
                        data = factor.readData(ids=ids, dts=dates, section_ids=ids, dt_ruler=context.DTRuler)
                    else:
                        data = handle.readData(factor_names=[self._QSArgs.FactorName], ids=ids, dts=dates,
                            section_ids=ids, dt_ruler=context.DTRuler).iloc[0]
                else:
                    data = handle.readData(ids=ids, dts=dates, section_ids=ids, dt_ruler=context.DTRuler)
        elif isinstance(handle, pd.DataFrame):
            data = handle.reindex(index=dates, columns=ids)
        else:
            raise TypeError("资源必须解析为因子库、因子或 DataFrame")
        state["graph_resource"] = data

    def backward_compute(self, path, bwd_data_list, context, local_context=None):
        """按运行请求读取数据，不修改画布文档。"""
        return context.NodeState[self.InstanceID]["graph_resource"].reindex(index=local_context.DTs, columns=local_context.IDs)


class SourceArgs(InputModel):
    """因子来源的画布参数。"""

    table: str = ""
    factor_name: str = ""
    name: str = "ResourceFactor"
    data_type: str = "double"
    table_args: dict[str, JsonValue] = Field(default_factory=dict, title="因子表参数")
    factor_args: dict[str, JsonValue] = Field(default_factory=dict, title="因子参数")


class SourceInputs(InputModel):
    """来源构造只接收语义资源描述。"""

    resource: ResourceDescriptor


def build_source(block, args, inputs):
    """构造资源因子，编译阶段只接收资源描述。"""
    values = SourceArgs(**args)
    resource = inputs["resource"]
    if resource.kind == "factor_database" and (not values.table or not values.factor_name):
        raise ValueError("因子库来源必须指定 table 和 factor_name")
    return ResourceFactor.from_dependencies({}, args={**values.factor_args, "Resource": resource,
        "Table": values.table, "FactorName": values.factor_name, "Name": values.name, "DataType": values.data_type,
        "TableArgs": values.table_args, "FactorArgs": values.factor_args})


SOURCE_COMPONENT = Component(id="qs.factor.source", args_model=SourceArgs, input_model=SourceInputs,
    output_type=Factor, builder=build_source, title="资源因子", category="来源",
    infer_output=lambda args: TypeDescriptor(kind="factor", type_id="qs.factor", data_type=args.get("data_type", "double")))


class SpecialConstantArgs(InputModel):
    value: Literal["nan", "inf", "-inf"] = "nan"
    name: str = "NaN"
    data_type: Literal["double", "string", "object"] = "double"
    lookback: int = 0


def build_special_constant(block, args, inputs):
    """JSON 中使用具名值保存 NaN 和无穷大，避免转换为 null。"""
    return DataFactor(float(args["value"]), args={**block.result_args, "Name": args["name"],
        "DataType": args["data_type"], "LookBack": args["lookback"]})


SPECIAL_CONSTANT_COMPONENT = Component(id="qs.factor.special_constant", args_model=SpecialConstantArgs,
    input_model=EmptyDependencies, output_type=Factor, builder=build_special_constant,
    operations=("build", "apply"), title="特殊数值常量", category="因子")


def register_source_definitions(registry):
    """登记不在编译阶段连接资源的来源构造器。"""
    from .Tabular import TABULAR_DATA_COMPONENT
    register_component(registry, SOURCE_COMPONENT)
    register_component(registry, SPECIAL_CONSTANT_COMPONENT)
    register_component(registry, TABULAR_DATA_COMPONENT)
