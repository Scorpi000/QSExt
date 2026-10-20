"""仅依赖 Pydantic 的计算图传输协议，不保存活动 Python 对象。"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class ProtocolModel(BaseModel):
    """拒绝未声明字段的协议基类。"""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DefinitionRef(ProtocolModel):
    """稳定定义标识及独立的行为版本。"""

    id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)


class Reference(ProtocolModel):
    """画布对象出口引用。"""

    kind: Literal["reference"] = "reference"
    block: str = Field(min_length=1)
    port: str = Field(default="result", min_length=1)


class LiteralValue(ProtocolModel):
    """显式 JSON 常量，包含与未绑定有区别的 null。"""

    kind: Literal["literal"] = "literal"
    value: JsonValue


class ResourceReference(ProtocolModel):
    """资源逻辑名称，不包含连接句柄和凭据。"""

    kind: Literal["resource"] = "resource"
    id: str = Field(min_length=1)


class CollectionItem(ProtocolModel):
    """有稳定标识的集合成员，空值表示编辑占位。"""

    id: str = Field(min_length=1)
    value: "BindingValue | None" = None


class Collection(ProtocolModel):
    """以数组顺序表达语义次序的集合。"""

    kind: Literal["collection"] = "collection"
    items: list[CollectionItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_members(self):
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("同一集合的成员 ID 必须唯一")
        return self


BindingValue = Annotated[Union[Reference, LiteralValue, ResourceReference, Collection], Field(discriminator="kind")]
CollectionItem.model_rebuild()


class Block(ProtocolModel):
    """显式指定操作的构图对象。"""

    id: str = Field(min_length=1)
    definition: DefinitionRef
    operation: Literal["build", "apply", "bind", "template"]
    args: dict[str, JsonValue] = Field(default_factory=dict)
    result_args: dict[str, JsonValue] = Field(default_factory=dict)
    inputs: dict[str, BindingValue] = Field(default_factory=dict)
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class GraphDocument(ProtocolModel):
    """允许不完整构图对象存在的可持久化文档。"""

    schema_version: Literal[1] = 1
    blocks: list[Block] = Field(default_factory=list)
    outputs: dict[str, Reference] = Field(default_factory=dict)
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique_blocks(self):
        if len({block.id for block in self.blocks}) != len(self.blocks):
            raise ValueError("画布对象 ID 必须唯一")
        return self


class TypeDescriptor(ProtocolModel):
    """可传输类型；对象类别与计算结果数据类型独立。"""

    kind: Literal["unknown", "null", "boolean", "integer", "number", "string", "array", "mapping", "union", "model", "node", "factor", "operator", "template", "resource", "python"] = "unknown"
    type_id: str | None = None
    items: "TypeDescriptor | None" = None
    alternatives: list["TypeDescriptor"] = Field(default_factory=list)
    fields: dict[str, "TypeDescriptor"] = Field(default_factory=dict)
    members: list["FieldDescriptor"] = Field(default_factory=list)
    choices: list[JsonValue] = Field(default_factory=list)
    data_type: str | None = None
    format: str | None = None
    persistable: bool = True


class FieldDescriptor(ProtocolModel):
    """参数或依赖的静态声明。"""

    name: str
    title: str = ""
    description: str = ""
    type: TypeDescriptor = Field(default_factory=TypeDescriptor)
    required: bool = False
    has_default: bool = False
    default: JsonValue = None
    default_available: bool = False
    default_factory: bool = False
    min_length: int | None = None
    max_length: int | None = None
    constraints: dict[str, JsonValue] = Field(default_factory=dict)
    bound: bool = False


TypeDescriptor.model_rebuild()


class DefinitionDescriptor(ProtocolModel):
    """代码注册目录的公开描述。"""

    definition: DefinitionRef
    component_kind: str = ""
    title: str
    category: str = "通用"
    source_path: str = ""
    source_category: str = ""
    directory_categories: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    operations: list[str]
    args: list[FieldDescriptor] = Field(default_factory=list)
    inputs: list[FieldDescriptor] = Field(default_factory=list)
    outputs: dict[str, TypeDescriptor]
    dynamic_inputs: bool = False
    default_args: dict[str, JsonValue] = Field(default_factory=dict)
    default_result_args: dict[str, JsonValue] = Field(default_factory=dict)
    default_extensions: dict[str, JsonValue] = Field(default_factory=dict)


class Diagnostic(ProtocolModel):
    """供 GUI 定位的机器诊断。"""

    code: str
    severity: Literal["error", "warning", "info"] = "error"
    message: str
    block_id: str | None = None
    path: list[str | int] = Field(default_factory=list)
    member_id: str | None = None


class ResourceDescriptor(ProtocolModel):
    """资源语义描述；signature 为快照或版本标识。"""

    id: str = Field(min_length=1)
    kind: str = "factor_database"
    signature: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
