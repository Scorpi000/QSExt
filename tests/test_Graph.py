"""图协议、目标编译、部分绑定和资源作用域的确定性验收测试。"""
import datetime as dt
import json
import subprocess
import sys
import unittest
from unittest.mock import Mock

import pandas as pd
from pydantic import Field, ValidationError

from QuantStudio.Core.Input import DependencyModel, EmptyDependencies, InputModel
from QuantStudio.Core.Node import Context, Node
from QuantStudio.Core.NodeTemplate import NodeTemplate
from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Factor.BasicOperator import Add
from QuantStudio.Factor.Factor import Factor, FactorContext, FactorInitData, FactorLocalContext
from QuantStudio.Factor.FactorOperation import BoundFactorOperator, FactorInputModel, PointOperator

from QSExt.Graph.api import (
    RESOURCE_RESOLVER_KEY, Block, Collection, CollectionItem, DefinitionRef, DefinitionRegistry,
    GraphDocument, GraphError, LiteralValue, MappingResourceResolver, Reference,
    ResourceCatalog, ResourceDescriptor, ResourceReference, TemplateRecipe, TypeDescriptor,
    TypeRegistry, compile_graph, create_default_registry, describe_block, describe_fields,
    export_template, import_template, insert_template, register_application_definitions, validate_graph,
)


class Leaf(Node):
    """无依赖测试节点，返回声明参数。"""

    __QS_DepClass__ = EmptyDependencies

    class __QS_ArgClass__(Node.__QS_ArgClass__):
        Value: int = Field(title="常量值", ge=0)

    def backward_compute(self, path, inputs, context, local_context=None):
        return self._QSArgs.Value


class Sum(Node):
    """命名依赖测试节点，重复边参与每次求和。"""

    class __QS_DepClass__(DependencyModel):
        head: Node
        tail: tuple[Node, ...] = Field(min_length=1, max_length=3)
        mask: Node | None = None

    def backward_compute(self, path, inputs, context, local_context=None):
        return inputs.head + sum(inputs.tail)


class GroupSum(PointOperator):
    """使用集合输入验证部分绑定后追加成员。"""

    class __QS_InputClass__(FactorInputModel):
        x: tuple[Factor, ...] = Field(min_length=2, max_length=3)

    def calculate(self, f, idt, iid, x, args):
        return sum(x)


def block(id_, definition, operation="build", **kwargs):
    return Block(id=id_, definition=DefinitionRef(id=definition), operation=operation, **kwargs)


def collection(*ids):
    return Collection(items=[CollectionItem(id=f"member-{index}", value=Reference(block=id_))
                             for index, id_ in enumerate(ids)])


class TestGraph(unittest.TestCase):
    def setUp(self):
        self.registry = DefinitionRegistry()
        register_application_definitions(self.registry)
        self.registry.register_node("test.leaf", Leaf)
        self.registry.register_node("test.sum", Sum)
        self.registry.register_operator("test.add", Add)
        self.registry.register_operator("test.group", GroupSum)
        self.one = block("one", "test.leaf", args={"Value": 1})
        self.two = block("two", "test.leaf", args={"Value": 2})

    def document(self, *blocks, output="result"):
        return GraphDocument(blocks=list(blocks), outputs={"main": Reference(block=output)})

    def run_factor(self, factor):
        dts, ids = [dt.datetime(2024, 1, 1)], ["A", "B"]
        context = FactorContext(DTRuler=dts, SectionIDs=ids)
        return Engine(args={"IOConcurrentNum": 1}).run([factor], context,
            [FactorLocalContext(DTs=dts, IDs=ids)], [FactorInitData(DTRange=(dts[0], dts[-1]))])[0]

    def test_protocol_roundtrip_and_extensions(self):
        graph = self.document(self.one, output="one")
        graph.extensions = {"qsweb": {"position": {"one": [10, 20]}}}
        value = GraphDocument.model_validate_json(graph.model_dump_json())
        self.assertEqual(value, graph)
        self.assertEqual(GraphDocument.model_json_schema()["title"], "GraphDocument")

    def test_protocol_import_does_not_load_core_or_optional_services(self):
        code = "import sys; from QSExt.Graph.Protocol import GraphDocument; assert 'QuantStudio' not in sys.modules; assert 'neo4j' not in sys.modules; assert 'fastapi' not in sys.modules"
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)

    def test_protocol_rejects_duplicate_ids_and_arbitrary_values(self):
        with self.assertRaises(ValidationError):
            self.document(self.one, self.one, output="one")
        with self.assertRaises(ValidationError):
            Collection(items=[CollectionItem(id="same"), CollectionItem(id="same")])
        with self.assertRaises(ValidationError):
            LiteralValue(value=self.one)
        with self.assertRaises(ValidationError):
            LiteralValue(value=float("nan"))
        with self.assertRaises(ValidationError):
            GraphDocument(schema_version=2)
        with self.assertRaises(ValidationError):
            GraphDocument.model_validate({"edges": []})

    def test_missing_null_and_placeholders_remain_distinct(self):
        missing = block("result", "test.sum", "template", inputs={"head": Reference(block="one")})
        graph = self.document(self.one, missing)
        template = compile_graph(graph, self.registry).outputs["main"]
        self.assertNotIn("mask", template.Dependencies)
        missing.inputs["mask"] = LiteralValue(value=None)
        missing.inputs["tail"] = Collection(items=[CollectionItem(id="unfinished")])
        result = compile_graph(graph, self.registry)
        self.assertIn("mask", result.outputs["main"].Dependencies)
        self.assertEqual(result.outputs["main"].Dependencies["tail"], ())
        self.assertTrue(any(item.member_id == "unfinished" for item in result.diagnostics))

    def test_metadata_is_static_and_default_factories_are_not_called(self):
        calls = []

        class Args(InputModel):
            value: list[int] = Field(default_factory=lambda: calls.append(1) or [1], min_length=1)

        fields = describe_fields(Args)
        self.assertEqual(calls, [])
        self.assertTrue(fields[0].default_factory)
        self.assertFalse(fields[0].default_available)
        self.assertEqual(fields[0].type.items.kind, "integer")
        self.assertEqual(fields[0].min_length, 1)

    def test_registry_metadata_and_exact_versions(self):
        descriptor = self.registry.describe_definition("test.sum")
        self.assertEqual([item.name for item in descriptor.inputs], ["head", "tail", "mask"])
        self.assertEqual(json.loads(descriptor.model_dump_json())["inputs"][1]["min_length"], 1)
        with self.assertRaises(ValueError):
            self.registry.register_node("test.leaf", Leaf)
        with self.assertRaises(KeyError):
            self.registry.get("test.leaf", 2)

    def test_validation_never_builds_nodes(self):
        factory = Mock(side_effect=AssertionError("不应调用构造器"))
        self.registry.register_factory("test.factory", args_model=InputModel, input_model=InputModel,
            output=TypeDescriptor(kind="node"), builder=factory)
        document = self.document(block("result", "test.factory"))
        self.assertEqual(validate_graph(document, self.registry), ())
        self.registry.list_definitions()
        factory.assert_not_called()

    def test_target_closure_ignores_unrelated_invalid_draft(self):
        draft = block("draft", "test.sum", inputs={"head": Reference(block="absent")})
        graph = self.document(self.one, draft, output="one")
        self.assertTrue(any(item.code == "unknown_block" for item in validate_graph(graph, self.registry)))
        result = compile_graph(graph, self.registry)
        self.assertEqual(list(result.objects), ["one"])
        self.assertEqual(Engine().run(result.execution_nodes(), Context()), [1])

    def test_named_node_inputs_order_sharing_and_duplicate_edges(self):
        root = block("result", "test.sum", inputs={"head": Reference(block="two"), "tail": collection("one", "two", "one")})
        result = compile_graph(self.document(self.one, self.two, root), self.registry)
        node = result.outputs["main"]
        self.assertIs(node.Dependencies.tail[1], node.Dependencies.head)
        self.assertIs(node.Dependencies.tail[0], node.Dependencies.tail[2])
        self.assertEqual(Engine().run([node], Context()), [6])
        self.assertEqual(len(node.Deps), 4)
        self.assertEqual(set(result.blocks_for_instance(result.objects["one"].InstanceID)), {"one", "result"})

    def test_recompilation_preserves_semantics_and_recreates_instances(self):
        graph = self.document(self.one, output="one")
        first, second = [compile_graph(graph, self.registry).outputs["main"] for _ in range(2)]
        self.assertEqual(first.QSID, second.QSID)
        self.assertNotEqual(first.InstanceID, second.InstanceID)

    def test_structural_errors_are_machine_readable(self):
        for mutation, code in ((lambda root: setattr(root.definition, "version", 3), "unknown_definition"),
                               (lambda root: setattr(root, "operation", "apply"), "unsupported_operation"),
                               (lambda root: root.inputs.update(head=Reference(block="result")), "cycle"),
                               (lambda root: root.inputs.update(head=Reference(block="one", port="absent")), "unknown_port"),
                               (lambda root: root.inputs.update(undeclared=Reference(block="one")), "unknown_input")):
            with self.subTest(code=code):
                root = block("result", "test.sum", inputs={"head": Reference(block="one"), "tail": collection("one")})
                mutation(root)
                with self.assertRaises(GraphError) as raised:
                    compile_graph(self.document(self.one, root), self.registry)
                self.assertIn(code, [item.code for item in raised.exception.diagnostics])

    def test_complete_target_rejects_missing_input_and_collection_gap(self):
        root = block("result", "test.sum", inputs={"head": Reference(block="one")})
        graph = self.document(self.one, root)
        self.assertTrue(all(item.severity != "error" for item in validate_graph(graph, self.registry)))
        with self.assertRaises(GraphError) as raised:
            compile_graph(graph, self.registry)
        self.assertEqual(raised.exception.diagnostics[0].path, ["inputs", "tail"])
        root.inputs["tail"] = Collection(items=[CollectionItem(id="gap")])
        with self.assertRaises(GraphError) as raised:
            compile_graph(graph, self.registry)
        self.assertTrue(any(item.member_id == "gap" and item.severity == "error" for item in raised.exception.diagnostics))

    def test_type_and_parameter_constraints(self):
        operator = block("operator", "test.add", "bind")
        root = block("result", "test.sum", inputs={"head": Reference(block="operator"), "tail": collection("one")})
        with self.assertRaises(GraphError) as raised:
            compile_graph(self.document(self.one, operator, root), self.registry)
        self.assertTrue(any(item.code == "input_type" for item in raised.exception.diagnostics))
        invalid = self.one.model_copy(deep=True)
        invalid.args = {"Value": -1}
        diagnostics = validate_graph(self.document(invalid, output="one"), self.registry)
        self.assertTrue(any(item.path == ["args", "Value"] for item in diagnostics))

    def test_node_template_continues_binding_through_graph(self):
        template = block("template", "test.sum", "template", inputs={"head": Reference(block="one")})
        root = block("result", "qs.template.build", inputs={"template": Reference(block="template"), "tail": collection("two")})
        graph = self.document(self.one, self.two, template, root)
        result = compile_graph(graph, self.registry)
        self.assertIsInstance(result.objects["template"], NodeTemplate)
        self.assertEqual(Engine().run(result.execution_nodes(), Context()), [3])
        info = describe_block(graph, "result", self.registry)
        self.assertEqual([item.name for item in info.inputs], ["template", "head", "tail", "mask"])
        self.assertTrue(next(item for item in info.inputs if item.name == "head").bound)

    def test_template_partial_parameters_can_be_completed_later(self):
        template = block("template", "test.leaf", "template")
        root = block("result", "qs.template.build", args={"Value": 8}, inputs={"template": Reference(block="template")})
        result = compile_graph(self.document(template, root), self.registry)
        self.assertEqual(Engine().run(result.execution_nodes(), Context()), [8])

    def test_template_captured_parameters_are_visible_and_required_parameters_checked(self):
        template = block("template", "test.leaf", "template", args={"Value": 8})
        root = block("result", "qs.template.build", inputs={"template": Reference(block="template")})
        document = self.document(template, root)
        descriptor = describe_block(document, "result", self.registry)
        self.assertTrue(next(item for item in descriptor.args if item.name == "Value").bound)
        self.assertEqual(Engine().run(compile_graph(document, self.registry).execution_nodes(), Context()), [8])
        del template.args["Value"]
        with self.assertRaises(GraphError) as raised:
            compile_graph(document, self.registry)
        self.assertTrue(any(item.block_id == "result" and item.path == ["args", "Value"] and item.severity == "error"
                            for item in raised.exception.diagnostics))

    def test_protocol_edits_are_revalidated_and_isolated_from_builder(self):
        document = self.document(self.one, output="one")
        document.blocks[0].args["Value"] = 2
        self.assertEqual(Engine().run(compile_graph(document, self.registry).execution_nodes(), Context()), [2])
        document.blocks[0].args["Value"] = object()
        with self.assertRaises(ValidationError):
            compile_graph(document, self.registry)

        def builder(block, args, inputs):
            block.args["new"] = 3
            return Leaf(args={"Value": 1})

        self.registry.register_factory("test.mutator", args_model=InputModel, input_model=InputModel,
            output=TypeDescriptor(kind="node"), builder=builder)
        document = self.document(block("result", "test.mutator"))
        compile_graph(document, self.registry)
        self.assertEqual(document.blocks[0].args, {})

    def test_operator_bind_always_operator_apply_always_factor(self):
        bound = block("bound", "test.add", "bind", inputs={"x0": LiteralValue(value=3)})
        root = block("result", "qs.operator.apply", "apply", inputs={"operator": Reference(block="bound"), "x1": LiteralValue(value=4)})
        graph = self.document(bound, root)
        result = compile_graph(graph, self.registry)
        self.assertIsInstance(result.objects["bound"], BoundFactorOperator)
        self.assertIsInstance(result.outputs["main"], Factor)
        self.assertEqual(self.run_factor(result.outputs["main"]).iloc[0, 0], 7)
        del root.inputs["x1"]
        with self.assertRaises(GraphError):
            compile_graph(graph, self.registry)

    def test_fully_bound_operator_still_is_operator(self):
        bound = block("result", "test.add", "bind", inputs={"x0": LiteralValue(value=3), "x1": LiteralValue(value=4)})
        result = compile_graph(self.document(bound), self.registry)
        self.assertIsInstance(result.outputs["main"], BoundFactorOperator)
        with self.assertRaises(TypeError):
            result.execution_nodes()

    def test_bound_scalar_overwrite_requires_bind(self):
        bound = block("bound", "test.add", "bind", inputs={"x0": LiteralValue(value=3)})
        root = block("result", "qs.operator.apply", "apply", inputs={"operator": Reference(block="bound"),
            "x0": LiteralValue(value=5), "x1": LiteralValue(value=4)})
        graph = self.document(bound, root)
        with self.assertRaises(GraphError) as raised:
            compile_graph(graph, self.registry)
        self.assertIn("bound_input", [item.code for item in raised.exception.diagnostics])
        root.operation = "bind"
        result = compile_graph(graph, self.registry)
        self.assertEqual(self.run_factor(result.outputs["main"]()).iloc[0, 0], 9)

    def test_bound_collection_append_and_total_maximum(self):
        bound = block("bound", "test.group", "bind", inputs={"x": Collection(items=[CollectionItem(id="first", value=LiteralValue(value=3))])})
        root = block("result", "qs.operator.apply", "apply", inputs={"operator": Reference(block="bound"),
            "x": Collection(items=[CollectionItem(id="second", value=LiteralValue(value=4))])})
        graph = self.document(bound, root)
        result = compile_graph(graph, self.registry)
        self.assertEqual(self.run_factor(result.outputs["main"]).iloc[0, 0], 7)
        root.inputs["x"].items += [CollectionItem(id="third", value=LiteralValue(value=2)), CollectionItem(id="fourth", value=LiteralValue(value=2))]
        with self.assertRaises(GraphError) as raised:
            compile_graph(graph, self.registry)
        self.assertIn("collection_max", [item.code for item in raised.exception.diagnostics])

    def test_template_recipe_roundtrip_and_insert_with_ref_remapping(self):
        template = block("result", "test.sum", "template", inputs={"head": Reference(block="one")})
        graph = self.document(self.one, self.two, template)
        recipe = export_template(graph, "main", self.registry, id_="template.sum")
        restored = TemplateRecipe.model_validate_json(recipe.model_dump_json())
        self.assertEqual(restored.digest, recipe.digest)
        self.assertEqual([item.id for item in restored.document.blocks], ["one", "result"])
        self.assertIsInstance(import_template(restored, self.registry), NodeTemplate)
        new_graph, reference = insert_template(GraphDocument(), restored, "copy-", output_name="saved")
        self.assertEqual(reference.block, "copy-result")
        self.assertEqual(new_graph.blocks[-1].inputs["head"].block, "copy-one")
        self.assertIsInstance(compile_graph(new_graph, self.registry).outputs["saved"], NodeTemplate)
        self.assertEqual(recipe.document.blocks[-1].id, "result")

    def test_recipe_rejects_execution_output(self):
        with self.assertRaises(ValueError):
            export_template(self.document(self.one, output="one"), "main", self.registry, id_="bad")

    def test_default_catalog_no_connections_and_constant_factor(self):
        registry = create_default_registry()
        self.assertGreater(len(registry.list_definitions()), 30)
        result = compile_graph(self.document(block("result", "qs.factor.constant", args={"Data": 5})), registry)
        self.assertEqual(self.run_factor(result.outputs["main"]).iloc[0, 0], 5)

    def test_source_compile_is_lazy_and_resource_state_is_per_run(self):
        registry = create_default_registry()
        root = block("result", "qs.factor.source", inputs={"resource": ResourceReference(id="asset://upload")})
        document = self.document(root)
        resource = ResourceDescriptor(id="asset://upload", kind="dataframe", signature="v1")
        result = compile_graph(document, registry, resources=ResourceCatalog([resource]))
        self.assertEqual(result.resources[0].signature, "v1")
        node = result.outputs["main"]
        self.assertIsNone(node.FactorTable)
        dts, ids = [dt.datetime(2024, 1, 1)], ["A"]
        for value in (10, 20):
            data = pd.DataFrame([[value]], index=dts, columns=ids)
            resolver = Mock(wraps=MappingResourceResolver({resource.id: data}))
            context = FactorContext(DTRuler=dts, SectionIDs=ids, Resources={RESOURCE_RESOLVER_KEY: resolver})
            resolver.resolve.assert_not_called()
            output = Engine(args={"IOConcurrentNum": 1}).run(result.execution_nodes(), context,
                [FactorLocalContext(DTs=dts, IDs=ids)], [FactorInitData(DTRange=(dts[0], dts[0]))])[0]
            self.assertEqual(output.iloc[0, 0], value)
            resolver.resolve.assert_called_once()
            self.assertFalse(hasattr(node, "_ResourceHandle"))

    def test_resource_signature_participates_in_semantic_identity(self):
        registry = create_default_registry()
        graph = self.document(block("result", "qs.factor.source", inputs={"resource": ResourceReference(id="db://source")},
            args={"table": "prices", "factor_name": "close"}))
        factors = [compile_graph(graph, registry, resources=ResourceCatalog([
            ResourceDescriptor(id="db://source", signature=version)])).outputs["main"] for version in ("v1", "v2")]
        self.assertNotEqual(factors[0].QSID, factors[1].QSID)

    def test_unknown_resource_is_located_on_source_block(self):
        registry = create_default_registry()
        graph = self.document(block("result", "qs.factor.source", inputs={"resource": ResourceReference(id="absent")}))
        with self.assertRaises(GraphError) as raised:
            compile_graph(graph, registry)
        self.assertEqual(raised.exception.diagnostics[-1].block_id, "result")

    def test_no_arbitrary_code_loading_from_document(self):
        root = block("result", "os.system", args={"command": "echo unexpected"})
        with self.assertRaises(GraphError) as raised:
            compile_graph(self.document(root), self.registry)
        self.assertEqual(raised.exception.diagnostics[0].code, "unknown_definition")

    def test_custom_type_registration_checks_inheritance(self):
        types = TypeRegistry()
        types.register("test.leaf", Leaf)
        self.assertTrue(types.accepts(types.describe(Node), types.describe(Leaf)))
        self.assertFalse(types.accepts(types.describe(Leaf), types.describe(Factor)))


if __name__ == "__main__":
    unittest.main()
