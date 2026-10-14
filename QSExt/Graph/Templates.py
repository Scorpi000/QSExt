"""通过图配方导入、导出和复用节点模板及绑定算子。"""
import hashlib
import json

from pydantic import Field

from .Compiler import GraphError, _analyze, _walk_references, compile_graph
from .Protocol import GraphDocument, ProtocolModel


class TemplateRecipe(ProtocolModel):
    """模板版本与图协议、组件行为版本分别管理。"""

    schema_version: int = Field(default=1, ge=1, le=1)
    id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    document: GraphDocument
    output: str

    @property
    def digest(self):
        """配方内容摘要，不与核心节点 QSID 混用。"""
        value = json.dumps(self.document.model_dump(mode="json"), ensure_ascii=False,
                           sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256((self.output + "\n" + value).encode("utf-8")).hexdigest()


def export_template(document, output, registry, *, id_, version=1):
    """导出指定绑定算子或节点模板的完整构造配方，不序列化对象。

    Args:
        document: 原始画布文档。
        output: 要导出的输出名称。
        registry: 用于核对配方声明的代码目录。
        id_: 共享模板的稳定 ID。
        version: 模板自身版本。
    Returns:
        仅包含该模板及其已捕获依赖闭包的配方。
    """
    document = GraphDocument.model_validate(document)
    _, order, views, diagnostics, _ = _analyze(document, registry, [output], True)
    if any(item.severity == "error" for item in diagnostics):
        raise GraphError(diagnostics)
    reference = document.outputs[output]
    if views[reference.block].output.kind not in ("operator", "template"):
        raise ValueError("只能导出绑定算子或节点模板配方")
    selected = set(order)
    result = document.model_copy(deep=True)
    result.blocks = [block for block in result.blocks if block.id in selected]
    result.outputs = {output: result.outputs[output]}
    return TemplateRecipe(id=id_, version=version, document=result, output=output)


def import_template(recipe, registry, *, resources=None):
    """从可信目录构造新的模板或算子，不恢复任意 Python 代码。"""
    recipe = TemplateRecipe.model_validate(recipe)
    result = compile_graph(recipe.document, registry, targets=[recipe.output], resources=resources)
    value = result.outputs[recipe.output]
    from QuantStudio.Core.NodeTemplate import NodeTemplate
    from QuantStudio.Factor.FactorOperation import FactorOperator
    if not isinstance(value, (NodeTemplate, FactorOperator)):
        raise ValueError("配方输出不是模板或算子")
    return value


def insert_template(document, recipe, prefix, *, output_name=None):
    """将共享配方展开到画布，并重写内部引用而保留成员 ID。

    首版采用明确展开的配方复用，不隐式引入子图执行边界。

    Args:
        document: 目标文档。
        recipe: 可持久化模板配方。
        prefix: 本次插入对象的 ID 前缀。
        output_name: 可选的新文档输出名称。
    Returns:
        新图文档及插入模板的出口引用。
    """
    result = GraphDocument.model_validate(document).model_copy(deep=True)
    recipe = TemplateRecipe.model_validate(recipe).model_copy(deep=True)
    ids = {block.id: f"{prefix}{block.id}" for block in recipe.document.blocks}
    if set(ids.values()) & {block.id for block in result.blocks}:
        raise ValueError("插入模板的对象 ID 与现有画布冲突")
    for block in recipe.document.blocks:
        block.id = ids[block.id]
        for value in block.inputs.values():
            for reference, _, _ in _walk_references(value):
                reference.block = ids[reference.block]
        result.blocks.append(block)
    reference = recipe.document.outputs[recipe.output]
    reference.block = ids[reference.block]
    if output_name is not None:
        if output_name in result.outputs:
            raise ValueError("文档已存在同名输出")
        result.outputs[output_name] = reference.model_copy(deep=True)
    return result, reference
