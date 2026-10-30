"""风险来源的延迟连接、准备快照、证券对齐和风险库适配回归。"""
from datetime import datetime
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Risk.HDF5RDB import HDF5RDB, HDF5FRDB
from QuantStudio.Risk.RiskTable import RiskTable
from QSExt.Graph.api import (
    GraphContext, MappingResourceResolver, RESOURCE_RESOLVER_KEY, ResourceCatalog,
    ResourceDescriptor, RISK_SOURCE_COMPONENT, compile_graph, create_default_registry, execution_inputs,
)
from QSExt.Graph.Components import register_component


class TestRiskSources(unittest.TestCase):
    """使用真实临时风险库，不依赖个人配置或外部服务。"""

    def test_covariance_and_factor_databases_prepare_aligned_snapshots(self):
        """两类风险库都通过统一协方差接口提供数据，构图和计算阶段不连接。"""
        dates = [datetime(2026, 1, day) for day in (1, 2)]
        ids = ['B', 'A']
        covariance = pd.DataFrame([[1., .1], [.1, 4.]], index=['A', 'B'], columns=['A', 'B'])
        for db_class in (HDF5RDB, HDF5FRDB):
            with self.subTest(database=db_class.__name__), tempfile.TemporaryDirectory() as directory:
                database = db_class(args={'MainDir': directory}).connect()
                try:
                    for date in dates:
                        if db_class is HDF5RDB:
                            database.writeData('sample', date, covariance)
                        else:
                            database.writeData('sample', date, factor_data=pd.DataFrame([[1.], [.1]], index=['A', 'B'], columns=['F']),
                                factor_cov=pd.DataFrame([[1.]], index=['F'], columns=['F']),
                                specific_risk=pd.Series([0., (4. - .01) ** .5], index=['A', 'B']))
                    resource = ResourceDescriptor(id='risk', kind='risk_database')
                    resolver = MappingResourceResolver({'risk': database})
                    registry = create_default_registry()
                    register_component(registry, RISK_SOURCE_COMPONENT)
                    document = {'blocks': [{'id': 'risk', 'definition': {'id': 'qs.risk.source'}, 'operation': 'build',
                        'args': {'table': 'sample'}, 'inputs': {'resource': {'kind': 'resource', 'id': 'risk'}}}],
                        'outputs': {'result': {'kind': 'reference', 'block': 'risk'}}}
                    with patch.object(resolver, 'resolve', wraps=resolver.resolve) as resolve:
                        compilation = compile_graph(document, registry, resources=ResourceCatalog([resource]))
                        resolve.assert_not_called()
                        nodes = compilation.execution_nodes()
                        requests = execution_inputs(nodes, {'dates': dates, 'section_ids': ids}, section_node_types=(RiskTable,))
                        with GraphContext(DTRuler=dates, SectionIDs=ids, Resources={RESOURCE_RESOLVER_KEY: resolver}) as context, Engine() as engine:
                            values = engine.run(nodes, context, init_data_list=[value.init_data for value in requests],
                                                fwd_data_list=[value.forward_data for value in requests])
                            snapshot = context.NodeState[nodes[0].InstanceID]['risk_data']
                            values[0].loc[dates[0], 'B', 'B'] = 99.
                            self.assertEqual(snapshot.loc[dates[0], 'B', 'B'], 4.)
                        resolve.assert_called_once()
                    # 返回值与缓存分离，日期与行列都遵循请求顺序。
                    pd.testing.assert_frame_equal(values[0].loc[dates[1]], covariance.loc[ids, ids])
                    self.assertIsNone(nodes[0].Args.SourceRDB)
                finally:
                    database.disconnect()

    def test_factor_resource_cannot_be_used_as_risk_source(self):
        """风险来源拒绝其他资源类别，不在构图时访问数据。"""
        from QSExt.Graph.RiskSources import build_risk_source
        with self.assertRaisesRegex(ValueError, '风险库资源'):
            build_risk_source(None, {'table': 'sample'}, {'resource': ResourceDescriptor(id='factor', kind='factor_database')})


if __name__ == '__main__':
    unittest.main()
