"""因子库来源在图准备阶段读取数据时隔离嵌套执行状态。"""
from datetime import datetime, timedelta
import tempfile
import unittest

import pandas as pd

from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Core.QSObject import Panel
from QuantStudio.Factor.Factor import Factor, FactorInitData, FactorLocalContext
from QuantStudio.Factor.HDF5DB import HDF5DB
from QSExt.Graph.api import (
    GraphContext, MappingResourceResolver, RESOURCE_RESOLVER_KEY,
    ResourceCatalog, ResourceDescriptor, compile_graph, create_default_registry,
)


class TestDatabaseSources(unittest.TestCase):
    """通过真实因子表读取复现工作台来源节点的运行路径。"""

    def test_database_and_registered_factor_preserve_outer_graph(self):
        """双来源读取保留外层节点状态、运行标识及事件归属。"""
        dates = [datetime(2026, 1, 1) + timedelta(days=index) for index in range(4)]
        ids = ["A", "B"]
        data = pd.DataFrame([[1., 2.], [3., 4.], [5., 6.], [7., 8.]], index=dates, columns=ids)
        with tempfile.TemporaryDirectory() as directory:
            database = HDF5DB(args={"MainDir": directory}).connect()
            self.addCleanup(database.disconnect)
            database.writeData(Panel({"close": data}), "prices")
            table = database.getTable("prices")
            for kind in ("factor_database", "registered_factor"):
                with self.subTest(kind=kind):
                    descriptor = ResourceDescriptor(id="database", kind=kind)
                    catalog = ResourceCatalog([descriptor])
                    handle = database if kind == "factor_database" else table.getFactor("close") + 1
                    resolver = MappingResourceResolver({"database": handle})
                    blocks = [{"id": name, "definition": {"id": "qs.factor.source"}, "operation": "build",
                        "args": {"table": "prices", "factor_name": "close", "name": name},
                        "inputs": {"resource": {"kind": "resource", "id": "database"}}} for name in ("first", "second")]
                    doc = {"blocks": blocks, "outputs": {name: {"kind": "reference", "block": name} for name in ("first", "second")}}
                    compiled = compile_graph(doc, create_default_registry(), resources=catalog)
                    nodes = compiled.execution_nodes()
                    self.assertTrue(all(isinstance(node, Factor) for node in nodes))
                    events = []
                    with GraphContext(DTRuler=dates, SectionIDs=ids, EventHandler=events.append,
                        Resources={RESOURCE_RESOLVER_KEY: resolver}) as context, Engine(args={"IOConcurrentNum": 1}) as engine:
                        values = engine.run(nodes, context,
                            fwd_data_list=[FactorLocalContext(DTs=dates[1:], IDs=ids) for _ in nodes],
                            init_data_list=[FactorInitData(DTRange=(dates[1], dates[-1])) for _ in nodes])
                        run_id = context.RunID
                        for node in nodes:
                            self.assertIn(node.InstanceID, context.NodeState)
                            self.assertIn("graph_resource", context.NodeState[node.InstanceID])
                    expected = data.loc[dates[1:]] + (1 if kind == "registered_factor" else 0)
                    for value in values:
                        pd.testing.assert_frame_equal(value, expected)
                    self.assertEqual({event["run_id"] for event in events}, {run_id})
                    self.assertEqual({event["instance_id"] for event in events}, {node.InstanceID for node in nodes})


if __name__ == "__main__":
    unittest.main()
