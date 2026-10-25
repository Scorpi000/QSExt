"""统一定义协议的共享实例、依赖、兼容与失败诊断。"""
import unittest
from datetime import datetime
from pathlib import Path
import tempfile

from QuantStudio.Core.Node import Node
from QSExt.DefModule.DefContent import DefInput, build_graph_def, build_dep
from QSExt.Graph.Import import definition_modules


BASE = '''
from QuantStudio.Core.Node import Node
from pydantic import Field
__GRAPH_META__ = {"MaxLookBack": 900}
calls = 0
def defNode(di):
    global calls
    calls += 1
    return [Node(args={"Name": "signal"})]
'''


class ExportValue(Node):
    def backward_compute(self, path, inputs, context, local_context=None):
        return 1


class GraphDefinitionTests(unittest.TestCase):
    def build(self, files, entry="main.py", args=None):
        with definition_modules(files) as load:
            return build_graph_def([(load(entry), args or {}, {})], DefInput())

    def test_parameters_aliases_shared_instances_and_lookback_before_execution(self):
        files = {"base.py": BASE, "main.py": '''
from QuantStudio.Core.Node import Node
__GRAPH_META__={"MaxLookBack": 10, "NodeDeps": [
    {"Module": ".base", "Output": "signal", "Alias": "a", "ModelArgs": {"window": "$window"}},
    {"Module": ".base", "Output": "signal", "Alias": "b", "ModelArgs": {"window": 20}},
    {"Module": ".base", "Output": "signal", "Alias": "c", "ModelArgs": {"window": 60}}]}
def defNode(di):
    assert di.Nodes['a'] is di.Nodes['b']
    assert di.Nodes['a'] is not di.Nodes['c']
    assert not di.Factors and not di.Strategies
    assert len(di.DTRuler) == 1
    di.ModelArgs['mutated'] = True
    di.DTRuler.clear()
    return [Node(deps=list(di.Nodes.values()), args={"Name": "report"})]
'''}
        with definition_modules(files) as load:
            base, module = load("base.py"), load("main.py")
            di = DefInput()
            def prepare(plan, value):
                self.assertEqual(base.calls, 0)
                self.assertEqual(plan.max_lookback, 900)
                value.DTRuler = [__import__('datetime').datetime(2026, 1, 1)]
            result = build_graph_def([(module, {"window": 20}, {})], di, prepare_input=prepare)
            self.assertEqual(base.calls, 2)
            self.assertEqual(len(result.definitions), 3)
            self.assertEqual(result.max_lookback, 900)
            self.assertEqual(len(di.DTRuler), 1)
            self.assertEqual(di.ModelArgs, {})
            self.assertEqual(result.requested[0].OutputNames, ["report"])

    def test_normalizes_output_names_without_merging_equal_nodes(self):
        files = {"main.py": '''
from QuantStudio.Core.Node import Node
def defNode(di):
    a=Node(args={"Name":"x"})
    return [a, Node(args={"Name":"x"}), Node(args={"Name":"x_2"}), a, Node(args={"Name":""})]
'''}
        with self.assertWarnsRegex(UserWarning, "重复"):
            result = self.build(files).requested[0]
        self.assertEqual(result.OutputNames, ["x", "x_2", "x_2_2", "output_5"])
        self.assertEqual(len(result.OtherNodeList), 4)
        self.assertEqual(result.FactorList, [])
        self.assertIs(result.getNode("x"), result.NodeList[0])
        with self.assertRaisesRegex(TypeError, "不支持普通节点"):
            result.as_legacy()

    def test_legacy_without_target_table_and_both_execute_once(self):
        files = {"base.py": '''
from QuantStudio.Factor.Factor import DataFactor
calls=0
def defFactor(di):
    global calls
    calls+=1
    return DataFactor(2, args={"Name":"x"})
''', "main.py": '''
__FACTOR_META__={"FactorDeps":{"base":["x"]}}
def defNode(di): return [di.Factors['x']]
'''}
        with definition_modules(files) as load:
            result = build_dep([(load("main.py"), {}, {})], DefInput())
            self.assertEqual(load("base.py").calls, 1)
            self.assertEqual(result[1][0][0].FactorNames, ["x"])
            self.assertEqual(result[3][0][0].FactorNames, ["x"])

    def test_overrides_are_distinct_instances(self):
        with definition_modules({"main.py": BASE}) as load:
            module = load("main.py")
            result = build_graph_def([(module, {}, {"Description": "a"}),
                                      (module, {}, {"Description": "b"})], DefInput())
            self.assertEqual(module.calls, 2)
            self.assertIsNot(result.requested[0].NodeList[0], result.requested[1].NodeList[0])

    def test_cycle_invalid_returns_refs_and_aliases(self):
        cases = [
            ({"main.py": '__GRAPH_META__={"NodeDeps":[{"Module":"main","Output":"x"}]}\ndef defNode(di): return []'}, RuntimeError, "循环依赖"),
            ({"main.py": 'def defNode(di): return [42]'}, TypeError, r'return\[0\]'),
            ({"main.py": 'def defNode(di): return None'}, TypeError, 'list\\[Node\\]'),
            ({"main.py": '__GRAPH_META__={"NodeDeps":[{"Module":"base","Output":"signal","ModelArgs":{"x":"$missing"}}]}', "base.py": BASE}, KeyError, "missing"),
            ({"main.py": '__GRAPH_META__={"NodeDeps":[{"Module":"base","Output":"signal","Alias":"same"},{"Module":"base","Output":"signal","Alias":"same"}]}\ndef defNode(di): return []', "base.py": BASE}, ValueError, "别名冲突"),
            ({"main.py": '__GRAPH_META__={"NodeDeps":[{"Module":"base","Output":"missing"}]}\ndef defNode(di): return []', "base.py": BASE}, KeyError, "公开输出"),
        ]
        for files, error, message in cases:
            with self.subTest(files=files), self.assertRaisesRegex(error, message):
                self.build(files)

    def test_metadata_conflict_and_graph_authority(self):
        code = '__FACTOR_META__={"Description":"a"}\n__STRATEGY_META__={"Description":"b"}\ndef defNode(di): return []'
        with self.assertRaisesRegex(ValueError, "消歧"):
            self.build({"main.py": code})
        result = self.build({"main.py": code + '\n__GRAPH_META__={"Description":"graph"}'}).requested[0]
        self.assertEqual(result.Meta.Description, "graph")

    def test_requires_dates_before_calling_definition(self):
        with self.assertRaisesRegex(ValueError, "构图需要日期"):
            self.build({"main.py": '__GRAPH_META__={"RequireDates":True}\ndef defNode(di): raise AssertionError("must not run")'})

    def test_proxy_replaces_dependency_without_double_execution(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from QuantStudio.Factor.Factor import DataFactor
        replacement = DataFactor(7, args={"Name":"x"})
        proxy = SimpleNamespace(TableNames=["table"], getTable=Mock(return_value=SimpleNamespace(
            FactorNames=["x"], getFactor=Mock(return_value=replacement))))
        files = {"base.py": '''
from QuantStudio.Factor.Factor import DataFactor
__FACTOR_META__={"TargetTable":"table"}
calls=0
def defFactor(di):
    global calls
    calls+=1
    return [DataFactor(1,args={"Name":"x"})]
''', "main.py": '__FACTOR_META__={"FactorDeps":{"base":["x"]}}\ndef defNode(di): return [di.Factors["x"]]'}
        with definition_modules(files) as load:
            result = build_dep([(load("main.py"),{}, {})], DefInput(), proxy_db=proxy, proxy_tables="*")
            self.assertIs(result[1][0][0].FactorList[0], replacement)
            self.assertEqual(load("base.py").calls, 1)

    def test_execution_adapter_and_unsupported_context(self):
        from QuantStudio.Core.Node import Context
        from QSExt.Graph.api import ExecutionInputs, execution_inputs
        class Custom(Node):
            @staticmethod
            def __QS_GraphExecutionAdapter__(node, runtime):
                return ExecutionInputs("init", "forward")
        self.assertEqual(execution_inputs([Custom()], {"dates":[datetime(2026,1,1)],"section_ids":[]}),
                         [ExecutionInputs("init", "forward")])
        class SpecialContext(Context): pass
        class Unsupported(Node):
            __QS_GraphContextClass__ = SpecialContext
        with self.assertRaisesRegex(TypeError, "专用全局上下文"):
            execution_inputs([Unsupported()], {"dates":[datetime(2026,1,1)],"section_ids":[]})

    def test_cli_exports_graph_without_factor_storers(self):
        from QSExt.DefModule.scripts.export_graph import main
        from QSExt.Graph.api import GraphDocument
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, components = root / "source", root / "components"
            source.mkdir()
            components.mkdir()
            (source / "main.py").write_text(f'from {__name__} import ExportValue\ndef defNode(di): return [ExportValue(args={{"Name":"graph"}})]', encoding="utf-8")
            (components / "definition.py").write_text(f'from {__name__} import ExportValue\nCOMPONENTS=[ExportValue]', encoding="utf-8")
            output = root / "graph.json"
            main(["--source-dir", str(source), "--entry", "main.py", "--components-dir", str(components), "--output", str(output)])
            self.assertEqual(list(GraphDocument.model_validate_json(output.read_text(encoding="utf-8")).outputs), ["graph"])


if __name__ == "__main__":
    unittest.main()
