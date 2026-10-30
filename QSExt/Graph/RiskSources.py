"""在准备阶段读取风险库协方差，将连接与可保存的图节点分离。"""
from typing import Literal

from pydantic import Field, JsonValue

from QuantStudio.Core.Input import EmptyDependencies, InputModel
from QuantStudio.Core.QSObject import Panel
from QuantStudio.Risk.RiskTable import RiskTable
from .Components import Component
from .Protocol import ResourceDescriptor
from .Resources import resolve_resource
from .Sources import SourceInputs


class ResourceRiskTable(RiskTable):
    """风险库来源叶子，计算阶段只使用已准备的协方差快照。"""

    __QS_DepClass__ = EmptyDependencies

    class __QS_ArgClass__(RiskTable.__QS_ArgClass__):
        SourceRDB: Literal[None] = Field(default=None, frozen=True, exclude=True, repr=False)
        Resource: ResourceDescriptor = Field(frozen=True, title="资源语义描述")
        Table: str = Field(frozen=True, min_length=1, title="风险表")
        TableArgs: dict[str, JsonValue] = Field(default_factory=dict, frozen=True, title="风险表参数")

    def init_compute(self, path, init_data, context):
        """汇集所有下游请求的日期和证券，在准备阶段统一读取。"""
        state = context.NodeState.setdefault(self.InstanceID, {})
        state.setdefault("risk_dates", set()).update(context.getDateTime(init_data.DTRange))
        state.setdefault("risk_ids", set()).update(init_data.SectionIDs or context.SectionIDs)
        context.PrepareNodeDict[self.InstanceID] = (self.InstanceID, None)
        return []

    def prepare_compute(self, prepare_data, context):
        """按当前运行的授权资源读取数据，不将数据库句柄保存在节点上。"""
        state = context.NodeState[self.InstanceID]
        dates, ids = sorted(state.pop("risk_dates")), sorted(state.pop("risk_ids"))
        database = resolve_resource(context, self.Args.Resource)
        table = database.getTable(self.Args.Table, args=self.Args.TableArgs)
        data = table.readCov(dts=dates, ids=ids)
        state["risk_data"] = Panel({date: data.loc[date].reindex(index=ids, columns=ids).copy(deep=True)
                                    for date in dates}, items=dates, major_axis=ids, minor_axis=ids)

    def backward_compute(self, path, inputs, context, local_context=None):
        """按请求顺序返回协方差，保护共享快照不被下游修改。"""
        data = context.NodeState[self.InstanceID]["risk_data"]
        dates, ids = local_context.DTs, local_context.IDs
        return Panel({date: data.loc[date].reindex(index=ids, columns=ids).copy(deep=True) for date in dates},
                     items=dates, major_axis=ids, minor_axis=ids)


class RiskSourceArgs(InputModel):
    """风险来源在画布上的可保存参数。"""

    name: str = Field(default="风险表", title="名称")
    table: str = Field(min_length=1, title="风险表")
    table_args: dict[str, JsonValue] = Field(default_factory=dict, title="风险表参数")


def build_risk_source(block, args, inputs):
    """只构造语义节点，连接与数据读取推迟到执行准备阶段。"""
    values = RiskSourceArgs(**args)
    resource = inputs["resource"]
    if resource.kind != "risk_database":
        raise ValueError("风险表来源必须引用风险库资源")
    return ResourceRiskTable.from_dependencies({}, args={"Name": values.name, "Resource": resource,
        "Table": values.table, "TableArgs": values.table_args})


RISK_SOURCE_COMPONENT = Component(id="qs.risk.source", title="风险库风险表", category="风险来源",
    args_model=RiskSourceArgs, input_model=SourceInputs, output_type=ResourceRiskTable, builder=build_risk_source)
