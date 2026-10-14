"""扩展组件的部分绑定、资源服务和注册中心适配验收。"""
import datetime as dt
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
from pydantic import Field

from QuantStudio.Core.Input import InputModel
from QuantStudio.Core.Node import Context
from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Factor.Factor import DataFactor, Factor
from QuantStudio.Factor.FactorOperation import BoundFactorOperator
from QuantStudio.Tools import DataPreprocessingFun
from QSExt.Factor.FactorOperator import FFill, RollingCorr, RankStandardization, ZScoreStandardization, Orthogonalization
from QSExt.MarketRegime.operators import ThresholdClassify, QuantileClassify
from QSExt.ReportGenerator.scenarios.single_factor import SingleFactorReport
from QSExt.Graph.api import (
    RESOURCE_RESOLVER_KEY, Block, DefinitionRef, GraphDocument, Reference,
    ResourceDescriptor, ResourceReference, TypeDescriptor, DefinitionRegistry,
    ResourceCatalog, compile_graph, create_default_registry, export_template,
    validate_graph, DBPoolResourceResolver, RegistryResourceResolver,
)
from QSExt.QSRegistry.GraphStore import GraphCatalogStore


class TestGraphExtensions(unittest.TestCase):
    def setUp(self):
        self.dts = [dt.datetime(2024, 1, 1) + dt.timedelta(days=index) for index in range(5)]
        self.ids = ["A", "B", "C"]
        self.data = pd.DataFrame([[1, 2, 4], [2, 3, 5], [3, 4, 6], [4, 5, 7], [5, 6, 8]], index=self.dts, columns=self.ids)
        self.factor = DataFactor(self.data)

    def test_extended_operator_bind_and_call_contract(self):
        for operator, name in ((FFill(), "f"), (RollingCorr(window=3), "x0"),
                               (RankStandardization(), "f"), (ZScoreStandardization(), "f"),
                               (ThresholdClassify(), "x"), (QuantileClassify(lookback=2), "x")):
            with self.subTest(operator=type(operator).__name__):
                bound = operator.bind(**{name: self.factor})
                self.assertIsInstance(bound, BoundFactorOperator)
                result = bound(self.factor) if isinstance(operator, RollingCorr) else bound()
                self.assertIsInstance(result, Factor)
                data = result.readData(ids=self.ids, dts=self.dts[2:], dt_ruler=self.dts)
                self.assertEqual(data.shape, (3, len(self.ids)))

    def test_named_optional_weight_without_mask_or_category(self):
        weight_data = pd.DataFrame([[1, 2, 3]] * len(self.dts), index=self.dts, columns=self.ids)
        weight = DataFactor(weight_data)
        operator = ZScoreStandardization()
        factor = operator.bind(f=self.factor, dispersion_weight=weight)()
        self.assertIs(factor.Dependencies.dispersion_weight, weight)
        self.assertIsNone(factor.Dependencies.mask)
        self.assertNotIn("dispersion_weight", factor.Args.ModelArgs)
        result = factor.readData(ids=self.ids, dts=self.dts)
        expected = np.vstack([DataPreprocessingFun.standardizeZScore(row, dispersion_weight=weight_data.iloc[index].values)
                              for index, row in enumerate(self.data.values)])
        np.testing.assert_allclose(result.values, expected)

    def test_orthogonalization_collection_binding(self):
        regressor = DataFactor(self.data * 2 + 1)
        result = Orthogonalization().bind(f=self.factor, exog=(regressor,))()
        self.assertEqual(result.Dependencies.exog, (regressor,))
        result.readData(ids=self.ids, dts=self.dts)

    def test_named_kernel_preserves_extra_dependencies(self):
        operator = RankStandardization()
        expected = operator(self.factor).readData(ids=self.ids, dts=self.dts)
        extra = DataFactor(0)
        factor = operator(self.factor, extra_deps=[extra])
        self.assertEqual(factor._ExtraDeps, [extra])
        actual = factor.readData(ids=self.ids, dts=self.dts)
        pd.testing.assert_frame_equal(actual, expected)

    def test_report_template_build_has_no_config_io(self):
        with patch.object(SingleFactorReport, "_load_config", side_effect=AssertionError("构造阶段不能读取配置")):
            template = SingleFactorReport.template(args={"FactorNames": ["alpha"]})
            node = template.build()
            self.assertEqual(node._factor_names, ["alpha"])
            self.assertEqual(node.Dependencies.results, ())
            registry = DefinitionRegistry()
            registry.register_node("report.single", SingleFactorReport)
            document = GraphDocument(blocks=[Block(id="report", definition=DefinitionRef(id="report.single"), operation="build")],
                                     outputs={"main": Reference(block="report")})
            self.assertIsInstance(compile_graph(document, registry).outputs["main"], SingleFactorReport)

    def test_partial_evaluation_operators_have_public_declarations(self):
        from QSExt.LLMFactor.evaluation.operators.incremental_ic import CalcIncrementalIC
        from QSExt.LLMFactor.evaluation.operators.size_stratified import CalcSizeStratifiedAlpha
        from QSExt.LLMFactor.evaluation.operators.sub_period import CalcSubPeriodStats
        for cls in (CalcIncrementalIC, CalcSizeStratifiedAlpha, CalcSubPeriodStats):
            operator = cls(descriptor_ids=self.ids).bind(price=self.factor)
            fields = operator.input_info()
            self.assertTrue(fields["price"]["bound"])
            self.assertEqual(fields["x"]["min_length"], 1)
            inputs = {"x": (self.factor,)}
            if cls is CalcIncrementalIC:
                inputs["base_factors"] = (self.factor,)
            if cls is CalcSizeStratifiedAlpha:
                inputs["market_cap"] = self.factor
            self.assertIsInstance(operator(**inputs), Factor)

    def test_db_pool_adapter_connects_only_at_resolve(self):
        pool = Mock()
        resource = ResourceDescriptor(id="db://prices")
        resolver = DBPoolResourceResolver(pool, {resource.id: "source"})
        pool.connect_one.assert_not_called()
        self.assertIs(resolver.resolve(resource), pool.connect_one.return_value)
        pool.connect_one.assert_called_once_with("source")

    def test_registry_resource_adapter_uses_explicit_mappings(self):
        registry = Mock()
        resolver = RegistryResourceResolver(registry, {"factor://close": "trusted-qsid"})
        resource = ResourceDescriptor(id="factor://close", kind="registered_factor")
        self.assertIs(resolver.resolve(resource), registry.reconstructFactor.return_value)
        registry.reconstructFactor.assert_called_once_with("trusted-qsid")

    def test_catalog_store_roundtrip_without_database(self):
        records = {}
        registry = Mock()

        def execute(query, parameters=None):
            if query.startswith("CREATE"):
                return []
            label = "definition" if "QSGraphDefinition" in query else "template"
            key = (label, parameters["id"], parameters["version"])
            if query.startswith("MERGE"):
                records.setdefault(key, parameters["payload"])
            return [{"payload": records[key]}] if key in records else []

        registry.executeCypher.side_effect = execute
        store = GraphCatalogStore(registry)
        store.initialize_schema()
        catalog = create_default_registry()
        descriptor = catalog.describe_definition("qs.factor.Add")
        store.publish_definition(descriptor)
        self.assertEqual(store.load_definition("qs.factor.Add"), descriptor)
        block = Block(id="operator", definition=DefinitionRef(id="qs.factor.Add"), operation="bind")
        graph = GraphDocument(blocks=[block], outputs={"saved": Reference(block="operator")})
        recipe = export_template(graph, "saved", catalog, id_="template.add")
        store.publish_template(recipe)
        self.assertEqual(store.load_template(recipe.id).digest, recipe.digest)
        changed = recipe.model_copy(deep=True)
        changed.document.blocks[0].args = {"Name": "different"}
        with self.assertRaises(ValueError):
            store.publish_template(changed)
        with self.assertRaises(KeyError):
            store.load_template("absent")

    def test_nested_parameter_validation_does_not_run_default_factories(self):
        calls = []

        class Nested(InputModel):
            values: list[int] = Field(default_factory=lambda: calls.append(1) or [])

        class Args(InputModel):
            config: Nested

        registry = DefinitionRegistry()
        registry.register_factory("test.nested", args_model=Args, input_model=InputModel,
            output=TypeDescriptor(), builder=Mock())
        document = GraphDocument(blocks=[Block(id="nested", definition=DefinitionRef(id="test.nested"),
            operation="build", args={"config": {}})], outputs={"main": Reference(block="nested")})
        self.assertEqual(validate_graph(document, registry), ())
        self.assertEqual(calls, [])

    def test_projection_is_an_execution_node(self):
        registry = create_default_registry()
        registry.register_node("test.projection_source", SingleFactorReport)
        from QSExt.Graph.Nodes import SelectResult
        from QuantStudio.Core.Node import Node

        class Source(Node):
            def backward_compute(self, path, inputs, context, local_context=None):
                return {"nested": [5, 8]}

        source = Source()
        node = SelectResult.template(args={"Path": ["nested", 1]}, deps={"source": source}).build()
        self.assertEqual(Engine().run([node], Context()), [8])

    def test_registered_factor_nested_run_preserves_outer_state(self):
        from QuantStudio.Factor.Factor import FactorContext, FactorInitData, FactorLocalContext
        from QSExt.Graph.api import MappingResourceResolver
        registry = create_default_registry()
        source = Block(id="source", definition=DefinitionRef(id="qs.factor.source"), operation="build",
            inputs={"resource": ResourceReference(id="factor://saved")})
        result = Block(id="result", definition=DefinitionRef(id="qs.factor.Add"), operation="apply",
            inputs={"x0": Reference(block="source"), "x1": {"kind": "literal", "value": 2}})
        document = GraphDocument(blocks=[source, result], outputs={"main": Reference(block="result")})
        resources = ResourceCatalog([ResourceDescriptor(id="factor://saved", kind="registered_factor", signature="v1")])
        compiled = compile_graph(document, registry, resources=resources)
        context = FactorContext(DTRuler=self.dts, SectionIDs=self.ids,
            Resources={RESOURCE_RESOLVER_KEY: MappingResourceResolver({"factor://saved": self.factor})})
        with context:
            output = Engine(args={"IOConcurrentNum": 1}).run(compiled.execution_nodes(), context,
                [FactorLocalContext(DTs=self.dts, IDs=self.ids)],
                [FactorInitData(DTRange=(self.dts[0], self.dts[-1]))])[0]
        pd.testing.assert_frame_equal(output, self.data + 2, check_dtype=False)
        self.assertIn(compiled.objects["source"].InstanceID, context.NodeDict)
        self.assertIn(compiled.objects["result"].InstanceID, context.NodeDict)
        self.assertNotIn(self.factor.InstanceID, context.NodeDict)

    def test_nested_parameter_metadata_preserves_constraints(self):
        descriptor = create_default_registry().describe_definition("qsext.factor.RollingCorr")
        model_args = next(item for item in descriptor.args if item.name == "ModelArgs")
        window = next(item for item in model_args.type.members if item.name == "window")
        self.assertEqual(window.constraints, {"ge": 1})
        self.assertEqual(window.default, 1)
        self.assertTrue(window.default_available)

    def test_resource_database_reads_only_during_execution(self):
        from QuantStudio.Factor.Factor import FactorContext, FactorInitData, FactorLocalContext
        from QSExt.Graph.api import MappingResourceResolver
        registry = create_default_registry()
        block = Block(id="source", definition=DefinitionRef(id="qs.factor.source"), operation="build",
            args={"table": "prices", "factor_name": "close"}, inputs={"resource": ResourceReference(id="db://source")})
        document = GraphDocument(blocks=[block], outputs={"main": Reference(block="source")})
        database = Mock()
        compiled = compile_graph(document, registry, resources=ResourceCatalog([ResourceDescriptor(id="db://source")]))
        database.getTable.assert_not_called()
        context = FactorContext(DTRuler=self.dts, SectionIDs=self.ids,
            Resources={RESOURCE_RESOLVER_KEY: MappingResourceResolver({"db://source": database})})
        # 使用只实现 Panel.iloc[0] 的对象，明确测试因子库接口的结果形式。
        class Panel:
            @property
            def iloc(self):
                return [self.data]
        panel = Panel()
        panel.data = self.data
        database.getTable.return_value.readData.return_value = panel
        output = Engine(args={"IOConcurrentNum": 1}).run(compiled.execution_nodes(), context,
            [FactorLocalContext(DTs=self.dts, IDs=self.ids)], [FactorInitData(DTRange=(self.dts[0], self.dts[-1]))])[0]
        pd.testing.assert_frame_equal(output, self.data)
        database.getTable.assert_called_once_with("prices")
        database.getTable.return_value.readData.assert_called_once_with(factor_names=["close"], ids=self.ids, dts=self.dts)


if __name__ == "__main__":
    unittest.main()
