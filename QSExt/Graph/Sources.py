"""在执行准备阶段读取外部因子资源的叶子节点。"""
import pandas as pd
from pydantic import Field

from QuantStudio.Core.Input import EmptyDependencies, InputModel
from QuantStudio.Core.Identity import ExecutionEffect
from QuantStudio.Factor.Factor import Factor, FactorContext

from .Protocol import ResourceDescriptor, TypeDescriptor
from .Resources import resolve_resource


class ResourceFactor(Factor):
    """因子库、已登记因子或上传表格的延迟读取适配。"""

    __QS_DepClass__ = EmptyDependencies
    __QS_ExecutionEffect__ = ExecutionEffect.READ

    class __QS_ArgClass__(Factor.__QS_ArgClass__):
        Resource: ResourceDescriptor = Field(frozen=True, title="资源语义描述")
        Table: str = Field(default="", frozen=True, title="因子表")
        FactorName: str = Field(default="", frozen=True, title="物理因子名称")
        DataType: str = Field(default="double", frozen=True, title="数据类型")

    def getMetaData(self, key=None):
        """只返回已声明元信息，不访问资源。"""
        metadata = {"DataType": self._QSArgs.DataType}
        return metadata if key is None else metadata.get(key)

    def init_compute(self, path, init_data, context):
        """将来源加入准备队列，保持来源为运行图叶子。"""
        context.PrepareNodeDict[self.InstanceID] = (self.InstanceID, None)
        return []

    def prepare_compute(self, prepare_data, context):
        """解析当前运行的资源句柄，状态仅存放在 Context 中。"""
        resource = self._QSArgs.Resource
        handle = resolve_resource(context, resource)
        if resource.kind == "factor_database":
            handle = handle.getTable(self._QSArgs.Table)
        context.NodeState.setdefault(self.InstanceID, {})["graph_resource"] = handle

    def backward_compute(self, path, bwd_data_list, context, local_context=None):
        """按运行请求读取数据，不修改画布文档。"""
        handle = context.NodeState[self.InstanceID]["graph_resource"]
        resource = self._QSArgs.Resource
        if resource.kind == "factor_database":
            data = handle.readData(factor_names=[self._QSArgs.FactorName], ids=local_context.IDs, dts=local_context.DTs)
            return data.iloc[0]
        if isinstance(handle, Factor):
            # 注册因子的嵌套执行使用独立运行上下文，避免清空外层状态。
            nested_context = FactorContext(DTRuler=context.DTRuler,
                SectionIDs=local_context.SectionIDs or context.SectionIDs,
                Resources=context.Resources, DataVersion=context.DataVersion)
            with nested_context:
                return handle.readData(ids=local_context.IDs, dts=local_context.DTs,
                                       section_ids=local_context.SectionIDs, dt_ruler=context.DTRuler)
        if isinstance(handle, pd.DataFrame):
            return handle.reindex(index=local_context.DTs, columns=local_context.IDs)
        raise TypeError("资源必须解析为因子库、因子或 DataFrame")


class SourceArgs(InputModel):
    """因子来源的画布参数。"""

    table: str = ""
    factor_name: str = ""
    name: str = "ResourceFactor"
    data_type: str = "double"


class SourceInputs(InputModel):
    """来源构造只接收语义资源描述。"""

    resource: ResourceDescriptor


def register_source_definitions(registry):
    """登记不在编译阶段连接资源的来源构造器。"""
    def build(block, args, inputs):
        values = SourceArgs(**args)
        resource = inputs["resource"]
        if resource.kind == "factor_database" and (not values.table or not values.factor_name):
            raise ValueError("因子库来源必须指定 table 和 factor_name")
        return ResourceFactor.from_dependencies({}, args={"Resource": resource,
            "Table": values.table, "FactorName": values.factor_name, "Name": values.name, "DataType": values.data_type})

    registry.register_factory("qs.factor.source", args_model=SourceArgs, input_model=SourceInputs,
        output=TypeDescriptor(kind="factor", type_id="qs.factor"), builder=build, title="资源因子",
        infer_output=lambda args: TypeDescriptor(kind="factor", type_id="qs.factor", data_type=args.get("data_type", "double")))
