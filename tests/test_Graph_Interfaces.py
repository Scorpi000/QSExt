"""公开图参数、有类型占位输入与子图复用的静态/构图验收。"""
from copy import deepcopy
import unittest

from pydantic import Field
from QuantStudio.Core.Input import InputModel
from QuantStudio.Factor.Factor import DataFactor, Factor
from QSExt.Graph.api import (Component, create_default_registry, compile_graph, validate_graph,
    GraphError, extract_subgraph, describe_graph_interface)
from QSExt.Graph.Components import register_component


class WindowArgs(InputModel):
    window: int = Field(default=2, ge=1, le=10)
    label: str = "value"


class StrictArgs(WindowArgs):
    window: int = Field(default=3, ge=2, le=5)


class EmptyInputs(InputModel):
    pass


def reference(block):
    return {"kind": "reference", "block": block}


class GraphInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.registry = create_default_registry()
        self.calls = []
        def build(block, args, inputs):
            self.calls.append(block.id)
            return DataFactor(args["window"], args={"Name": args["label"]})
        for id_, args in (("window", WindowArgs), ("strict", StrictArgs)):
            register_component(self.registry, Component(id=id_, args_model=args,
                input_model=EmptyInputs, output_type=Factor, builder=build))

    def document(self):
        return {"blocks": [{"id": id_, "definition": {"id": definition}, "operation": "build",
            "args": {"window": default}} for id_, definition, default in (("a", "window", 2), ("b", "strict", 3))],
            "outputs": {"a": reference("a"), "b": reference("b")},
            "extensions": {"interface": {"parameters": [{"id": "shared", "name": "length", "value": 4,
                "targets": [{"block": id_, "location": "args", "path": ["window"]} for id_ in ("a", "b")]}]}}}

    def test_shared_parameter_is_authoritative_without_mutating_saved_document(self):
        document = self.document()
        document["blocks"][0]["args"]["window"] = 999
        saved = deepcopy(document)
        self.assertEqual([item for item in validate_graph(document, self.registry) if item.severity == "error"], [])
        self.assertEqual(self.calls, [])
        result = compile_graph(document, self.registry)
        self.assertEqual([result.outputs[name].Args.Data for name in ("a", "b")], [4, 4])
        self.assertEqual(document, saved)

    def test_every_target_constraint_is_enforced(self):
        document = self.document()
        document["extensions"]["interface"]["parameters"][0]["value"] = 8
        with self.assertRaises(GraphError):
            compile_graph(document, self.registry)
        self.assertEqual(self.calls, [])

    def test_invalid_duplicate_and_incompatible_targets_are_diagnosed(self):
        for target, code in (({"block": "a", "path": ["unknown"]}, "invalid_graph_parameter_target"),
                             ({"block": "a", "path": ["label"]}, "incompatible_graph_parameter_targets"),
                             ({"block": "a", "path": ["window"]}, "duplicate_graph_parameter_target")):
            with self.subTest(code=code):
                document = self.document()
                document["extensions"]["interface"]["parameters"][0]["targets"].append(target)
                self.assertIn(code, [item.code for item in validate_graph(document, self.registry)])

    def test_required_factor_input_is_checked_only_in_selected_output_closure(self):
        document = self.document()
        document["blocks"].append({"id": "input", "definition": {"id": "qs.input.factor"}, "operation": "build"})
        document["outputs"]["input"] = reference("input")
        self.assertIn("unbound_graph_input", [item.code for item in validate_graph(document, self.registry)])
        self.assertEqual(compile_graph(document, self.registry, targets=["a"]).outputs["a"].Args.Data, 4)
        with self.assertRaises(GraphError):
            compile_graph(document, self.registry, targets=["input"])
        document["blocks"][-1]["inputs"] = {"value": reference("a")}
        result = compile_graph(document, self.registry, targets=["input"])
        self.assertEqual(result.outputs["input"].Args.Data, 4)
        self.assertEqual(result.outputs["input"].Name, "value")

    def test_optional_factor_input_uses_explicit_default_constant(self):
        document = {"blocks": [{"id": "input", "definition": {"id": "qs.input.factor"}, "operation": "build",
            "args": {"name": "universe", "required": False, "default_value": 1}}], "outputs": {"result": reference("input")}}
        self.assertEqual(compile_graph(document, self.registry).outputs["result"].Args.Data, 1)

    def test_public_values_survive_subgraph_extraction(self):
        recipe, _, _ = extract_subgraph(self.document(), ["a"], self.registry, output="a")
        self.assertEqual(recipe.document.blocks[0].args["window"], 4)
        self.assertNotIn("interface", recipe.document.extensions)

    def test_interface_description_reuses_declared_fields_without_building(self):
        interface, inputs, parameters, candidates, diagnostics = describe_graph_interface(self.document(), self.registry)
        self.assertEqual(interface.parameters[0].value, 4)
        self.assertEqual(len(parameters[0]["fields"]), 2)
        self.assertTrue(any(item.target.path == ["window"] for item in candidates))
        self.assertEqual(self.calls, [])

    def test_subgraph_instances_have_separate_input_name_scopes(self):
        from QSExt.Graph.Subgraphs import SubgraphRecipe, register_subgraph
        recipe = SubgraphRecipe(document={"blocks": [{"id": "input", "definition": {"id": "qs.input.factor"},
            "operation": "build", "args": {"name": "same", "required": False, "default_value": 1}}],
            "outputs": {"result": reference("input")}})
        register_subgraph(self.registry, "optional_input", recipe, title="可选输入")
        document = {"blocks": [{"id": id_, "definition": {"id": "optional_input"}, "operation": "build"} for id_ in ("a", "b")],
            "outputs": {id_: reference(id_) for id_ in ("a", "b")}}
        self.assertEqual([item for item in validate_graph(document, self.registry) if item.severity == "error"], [])
        result = compile_graph(document, self.registry)
        self.assertEqual([result.outputs[id_].Args.Data for id_ in ("a", "b")], [1, 1])


if __name__ == "__main__":
    unittest.main()
