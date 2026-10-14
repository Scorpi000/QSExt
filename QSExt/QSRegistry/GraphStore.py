"""复用 QSRegistry 连接持久化定义描述和模板 JSON 配方。"""
from QSExt.Graph.Protocol import DefinitionDescriptor
from QSExt.Graph.Templates import TemplateRecipe


class GraphCatalogStore:
    """可选存储适配；构造器及权限管理由调用方提供。

    Args:
        registry: 提供 executeCypher 的已连接 QSGraphDB。
    """

    def __init__(self, registry):
        self.registry = registry

    def initialize_schema(self):
        """显式建立唯一约束，不在导入或编译时创建 Schema。"""
        for label, name in (("QSGraphDefinition", "qs_graph_definition_version"),
                            ("QSGraphTemplate", "qs_graph_template_version")):
            self.registry.executeCypher(
                f"CREATE CONSTRAINT {name} IF NOT EXISTS FOR (n:{label}) REQUIRE (n.id, n.version) IS UNIQUE")

    def _publish(self, label, id_, version, payload):
        rows = self.registry.executeCypher(
            f"MERGE (n:{label} {{id: $id, version: $version}}) "
            "ON CREATE SET n.payload = $payload RETURN n.payload AS payload",
            {"id": id_, "version": version, "payload": payload})
        if not rows or rows[0]["payload"] != payload:
            raise ValueError("同一 ID 和版本已存在不同内容，请发布新版本")

    def publish_definition(self, descriptor):
        """保存可检索描述，不能替换可信代码定义。"""
        descriptor = DefinitionDescriptor.model_validate(descriptor)
        self._publish("QSGraphDefinition", descriptor.definition.id, descriptor.definition.version,
                      descriptor.model_dump_json())

    def publish_template(self, recipe):
        """按模板版本不可变发布配方，不使用 dill 或 pickle。"""
        recipe = TemplateRecipe.model_validate(recipe)
        self._publish("QSGraphTemplate", recipe.id, recipe.version, recipe.model_dump_json())

    def _load(self, label, id_, version):
        rows = self.registry.executeCypher(
            f"MATCH (n:{label} {{id: $id, version: $version}}) RETURN n.payload AS payload",
            {"id": id_, "version": version})
        if not rows:
            raise KeyError((id_, version))
        return rows[0]["payload"]

    def load_template(self, id_, version=1):
        """读取纯 JSON 配方，实例化仍需调用方提供代码目录。"""
        return TemplateRecipe.model_validate_json(self._load("QSGraphTemplate", id_, version))

    def load_definition(self, id_, version=1):
        """读取精确版本的定义描述，不动态导入代码。"""
        return DefinitionDescriptor.model_validate_json(self._load("QSGraphDefinition", id_, version))
