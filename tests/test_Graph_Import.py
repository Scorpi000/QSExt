"""DefModule 到图文档转换的依赖、数值和失败原子性验收。"""
from datetime import datetime, timedelta
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd

from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Factor.Factor import FactorInitData, FactorLocalContext
from QSExt.DefModule.DefContent import DefInput
from QSExt.Graph.api import (DefinitionDatabase, DefinitionImportError, GraphContext, GraphDocument,
    MappingResourceResolver, RESOURCE_RESOLVER_KEY, ResourceCatalog, ResourceDescriptor,
    compile_graph, create_default_registry, import_definition)


class DefinitionImportTests(unittest.TestCase):
    def setUp(self):
        self.registry = create_default_registry()
        self.resource = ResourceDescriptor(id="prices", kind="dataframe")
        self.di = DefInput(FDB={"DB": DefinitionDatabase("DB", self.resource)})

    def run_document(self, document, data, start_index=0):
        compiled = compile_graph(document, self.registry, resources=ResourceCatalog([self.resource]))
        nodes = compiled.execution_nodes()
        with GraphContext(DTRuler=list(data.index), SectionIDs=list(data.columns),
            Resources={RESOURCE_RESOLVER_KEY: MappingResourceResolver({"prices": data})}) as context, Engine(args={"IOConcurrentNum": 1}) as engine:
            result = engine.run(nodes, context,
                fwd_data_list=[FactorLocalContext(DTs=list(data.index[start_index:]), IDs=list(data.columns)) for _ in nodes],
                init_data_list=[FactorInitData(DTRange=(data.index[start_index], data.index[-1])) for _ in nodes])
        return dict(zip(compiled.outputs, result))

    def test_dependency_alias_parameters_shared_source_and_numeric_roundtrip(self):
        files = {
            "base.py": '''
__FACTOR_META__ = {"TargetTable": "base", "DBDeps": {"DB": "prices"}, "MaxLookBack": 730}
def defFactor(di):
    return [di.FDB["DB"].getTable("daily", args={"LookBack": 0}).getFactor("close")]
''',
            "research.py": '''
from QuantStudio.Factor import FactorOperator as fo
__FACTOR_META__ = {"TargetTable": "research", "MaxLookBack": 10, "FactorDeps": {
    "base": [{"Name": "close", "Alias": "price"}]}}
def defNode(di):
    p = di.Factors["price"]
    avg = fo.RollingMean(window=di.ModelArgs["window"], min_periods=1)(p, factor_args={"Name": "avg"})
    return [avg, (p + avg).new(args={"Name": "total"})]
'''}
        document = import_definition(files, "research.py", self.registry, self.di, model_args={"window": 2})
        json_data = json.loads(json.dumps(document.model_dump(mode="json"), allow_nan=False))
        sources = [block for block in document.blocks if block.definition.id == "qs.factor.source"]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].args["table_args"], {"LookBack": 0})
        self.assertEqual(document.extensions["qsweb"]["definition_import"]["max_lookback"], 730)
        dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(4)]
        data = pd.DataFrame([[1., 5.], [3., 7.], [5., 9.], [7., 11.]], index=dates, columns=["A", "B"])
        result = self.run_document(GraphDocument.model_validate(json_data), data, start_index=1)
        pd.testing.assert_frame_equal(result["avg"], data.rolling(2, min_periods=1).mean().iloc[1:], check_freq=False)
        pd.testing.assert_frame_equal(result["total"], (data + data.rolling(2, min_periods=1).mean()).iloc[1:], check_freq=False)
        mean = next(block for block in document.blocks if block.definition.id == "qs.factor.RollingMean")
        mean.args["ModelArgs"]["window"] = 1
        mean.args["LookBack"] = [0]
        result = self.run_document(document, data)
        pd.testing.assert_frame_equal(result["avg"], data)

    def test_same_names_are_isolated_between_imports_and_cleaned_up(self):
        original = set(sys.modules)
        for value in (2, 7):
            files = {"base.py": f'from QuantStudio.Factor.Factor import DataFactor\ndef defFactor(di): return [DataFactor({value}, args={{"Name": "x"}})]',
                "main.py": '__FACTOR_META__={"TargetTable":"main", "FactorDeps":{"base":["x"]}}\ndef defFactor(di): return [di.Factors["x"]]'}
            document = import_definition(files, "main.py", self.registry, self.di)
            self.assertEqual(document.blocks[0].args["Data"], value)
        self.assertFalse(any(name.startswith("_qs_def_import_") for name in set(sys.modules) - original))

    def test_invalid_files_cycles_and_unregistered_operators_fail(self):
        bad = {'../escape.py': 'pass'}
        with self.assertRaisesRegex(DefinitionImportError, "无效"):
            import_definition(bad, '../escape.py', self.registry, self.di)
        with self.assertRaisesRegex(RuntimeError, "循环依赖"):
            import_definition({'a.py': '__FACTOR_META__={"TargetTable":"a", "FactorDeps":{"a":["x"]}}\ndef defFactor(di): return []'},
                              'a.py', self.registry, self.di)
        code = '''
from QuantStudio.Factor.FactorOperation import FactorOperatorized
@FactorOperatorized(operator_type="Point")
def custom(f, dt, ids, x, args): return x[0]
def defFactor(di): return [custom(di.FDB["DB"].getTable("daily").getFactor("close"))]
'''
        with self.assertRaisesRegex(DefinitionImportError, "自定义算子"):
            import_definition({'custom.py': code}, 'custom.py', self.registry, self.di)

    def test_nan_is_json_portable_and_preserves_missing_values(self):
        code = '''
import numpy as np
from QuantStudio.Factor import FactorOperator as fo
def defFactor(di):
    p=di.FDB["DB"].getTable("daily").getFactor("close")
    return [fo.Where()(p, p>2, np.nan, factor_args={"Name":"filtered"})]
'''
        document = import_definition({'filter.py': code}, 'filter.py', self.registry, self.di)
        json.dumps(document.model_dump(mode="json"), allow_nan=False)
        data = pd.DataFrame([[1., 3.], [4., 2.]], index=pd.date_range("2026-01-01", periods=2), columns=["A", "B"])
        pd.testing.assert_frame_equal(self.run_document(document, data)["filtered"], data.where(data > 2), check_freq=False)

    def test_explicit_table_read_and_dataframe_survive_json_roundtrip(self):
        dates = list(pd.date_range("2026-01-01", periods=4).to_pydatetime())
        data = pd.DataFrame([[1., np.nan], [np.inf, -np.inf], [3., 4.], [5., 6.]],
                            index=dates, columns=["A", "B"])
        read = Mock(return_value=SimpleNamespace(iloc=[data.copy()]))
        describe = Mock(return_value=SimpleNamespace(readData=read))
        self.di = DefInput(FDB={"DB": DefinitionDatabase("DB", self.resource, describe)}, DTs=dates, DTRuler=dates)
        code = '''
from QuantStudio.Factor.Factor import DataFactor
def defNode(di):
    prices=di.FDB["DB"].getTable("daily", args={"LookBack": 0}).readData(
        factor_names=["close"], ids=["A", "B"], dts=di.DTRuler).iloc[0]
    return [DataFactor(prices, args={"Name":"prices", "LookBack":3, "SectionIDs":["A","B"]})]
'''
        document = import_definition({"prices.py": code}, "prices.py", self.registry, self.di)
        describe.assert_called_once_with(self.resource, "daily", {"LookBack": 0})
        read.assert_called_once_with(factor_names=["close"], ids=["A", "B"], dts=dates)
        reopened = GraphDocument.model_validate_json(json.dumps(document.model_dump(mode="json"), allow_nan=False))
        describe.side_effect = AssertionError("reopening must not reconnect")
        pd.testing.assert_frame_equal(self.run_document(reopened, data)["prices"], data, check_freq=False)
        factor = compile_graph(reopened, self.registry).outputs["prices"]
        self.assertEqual(factor.Args.LookBack, 3)
        self.assertEqual(factor.Args.SectionIDs, ["A", "B"])

    def test_series_static_weights_and_datetime_values_keep_their_semantics(self):
        code = '''
import pandas as pd
from QuantStudio.Factor.Factor import DataFactor
def defNode(di):
    return [DataFactor(pd.Series({"A":.2,"B":.8},name="weights"), args={"Name":"weights","CalcDTRuler":di.DTs}),
            DataFactor(pd.Series([2.,3.,4.], index=pd.DatetimeIndex(di.DTs, name="dates")), args={"Name":"daily"})]
'''
        data = pd.DataFrame(0., index=pd.date_range("2026-01-01", periods=3), columns=["A", "B"])
        self.di.DTs = list(data.index.to_pydatetime())
        document = import_definition({"series.py": code}, "series.py", self.registry, self.di)
        reopened = GraphDocument.model_validate_json(json.dumps(document.model_dump(mode="json"), allow_nan=False))
        results = self.run_document(reopened, data)
        np.testing.assert_allclose(results["weights"], np.tile([.2, .8], (3, 1)))
        np.testing.assert_allclose(results["daily"], np.repeat([[2.], [3.], [4.]], 2, axis=1))
        compiled = compile_graph(reopened, self.registry)
        self.assertEqual(compiled.outputs["weights"].Args.Data.name, "weights")
        self.assertEqual(compiled.outputs["daily"].Args.Data.index.name, "dates")

    def test_fixed_example_builds_and_calculates_momentum(self):
        from QSExt.DefModule.examples import stock_cn_factor_example2 as example
        from QuantStudio.Factor.FactorOperation import record_factor_construction
        source = self.di.FDB["DB"].getTable("daily").getFactor("close")
        with record_factor_construction():
            factors = example.defFactor(DefInput(Factors={"close": source}))
        self.assertEqual([node.Name for node in factors], ["momentum_20d", "momentum_20d_zscore"])
        # 直接运行修复后的自定义因子；该实例尚未注册为共享组件，因此图导入明确拒绝。
        data = pd.DataFrame(np.arange(1., 53.).reshape(26, 2), index=pd.date_range("2026-01-01", periods=26), columns=["A", "B"])
        with GraphContext(DTRuler=list(data.index), SectionIDs=list(data.columns),
            Resources={RESOURCE_RESOLVER_KEY: MappingResourceResolver({"prices": data})}) as context, Engine(args={"IOConcurrentNum": 1}) as engine:
            values = engine.run([factors[0]], context,
                fwd_data_list=[FactorLocalContext(DTs=list(data.index[20:]), IDs=list(data.columns))],
                init_data_list=[FactorInitData(DTRange=(data.index[20], data.index[-1]))])
        expected = (data - data.shift(20)) / data.shift(20)
        pd.testing.assert_frame_equal(values[0], expected.iloc[20:], check_freq=False)


if __name__ == '__main__':
    unittest.main()
