/**
 * DAG 可视化组件（React Flow）
 *
 * 因子工作台依赖关系图，使用共享 DAGFlow 组件渲染。
 * 节点样式与 MiningStudio 因子树保持一致。
 */

import { useCallback, useEffect, useMemo } from 'react'
import { message } from 'antd'
import { Node, Edge, MarkerType } from 'reactflow'
import DAGFlow, { DEFAULT_NODE_COLORS } from '../DAGFlow'
import { getFactorDAG, DAGNode } from '../../services/registry'
import { useFactorWorkbenchStore } from '../../stores/factorWorkbench'

function DAGViewer() {
  const {
    selectedQSID,
    dagData,
    loadingDAG,
    setDagData,
    setLoadingDAG,
    setSelectedQSID,
  } = useFactorWorkbenchStore()

  const loadDAG = useCallback(async () => {
    if (!selectedQSID) return
    setLoadingDAG(true)
    try {
      const data = (await getFactorDAG(selectedQSID)) as unknown as import('../../services/registry').DAGData
      setDagData(data)
    } catch {
      message.error('加载 DAG 失败')
      setDagData(null)
    } finally {
      setLoadingDAG(false)
    }
  }, [selectedQSID, setDagData, setLoadingDAG])

  useEffect(() => {
    if (selectedQSID) loadDAG()
  }, [selectedQSID])

  // 转换为 ReactFlow 格式，节点样式与 MiningStudio 因子树一致
  const { flowNodes, flowEdges } = useMemo(() => {
    if (!dagData) return { flowNodes: [], flowEdges: [] }

    const nodes: Node[] = dagData.nodes.map((n: DAGNode) => ({
      id: n.qsid,
      data: {
        nodeType: n.factor_class,
        label: (
          <div
            style={{
              padding: '4px 10px',
              borderRadius: 4,
              background: DEFAULT_NODE_COLORS[n.factor_class] || '#d9d9d9',
              color: n.factor_class === 'DerivativeFactor' ? '#fff' : '#333',
              fontSize: 12,
              fontWeight: 500,
              border: n.qsid === dagData.root_qsid ? '2px solid #fa8c16' : 'none',
              cursor: 'pointer',
            }}
          >
            <div>{n.name}</div>
            {n.operator_type && (
              <div style={{ fontSize: 10, opacity: 0.8 }}>{n.operator_type}</div>
            )}
          </div>
        ),
      },
      position: { x: 0, y: 0 },  // 由 DAGFlow 的 dagre 布局覆盖
    }))

    const edges: Edge[] = dagData.edges.map((e, i) => ({
      id: `${e.source}-${e.target}-${i}`,
      source: e.source,
      target: e.target,
    }))

    return { flowNodes: nodes, flowEdges: edges }
  }, [dagData])

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedQSID(node.id)
  }, [setSelectedQSID])

  return (
    <DAGFlow
      nodes={flowNodes}
      edges={flowEdges}
      onNodeClick={onNodeClick}
      loading={loadingDAG}
      emptyText={selectedQSID ? '无依赖数据' : '选择因子后查看 DAG'}
      nodeColorMap={DEFAULT_NODE_COLORS}
      showToolbar
      onRefresh={loadDAG}
    />
  )
}

export default DAGViewer
