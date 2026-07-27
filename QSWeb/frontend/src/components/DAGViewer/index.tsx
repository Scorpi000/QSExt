/**
 * DAG 可视化组件（React Flow）
 */

import { useCallback, useEffect, useMemo } from 'react'
import { Spin, Empty, Button, Space, message } from 'antd'
import { ApartmentOutlined, ReloadOutlined } from '@ant-design/icons'
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { getFactorDAG, DAGNode } from '../../services/registry'
import { useFactorWorkbenchStore } from '../../stores/factorWorkbench'

// 节点类型着色
const NODE_COLORS: Record<string, string> = {
  AtomicFactor: '#91caff',        // 天蓝
  DerivativeFactor: '#4682b4',    // 钢蓝
}

function DAGViewer() {
  const {
    selectedQSID,
    dagData,
    loadingDAG,
    setDagData,
    setLoadingDAG,
    setSelectedQSID,
  } = useFactorWorkbenchStore()

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

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

  // 将 DAG 数据转换为 React Flow 格式
  useEffect(() => {
    if (!dagData) {
      setNodes([])
      setEdges([])
      return
    }

    const flowNodes: Node[] = dagData.nodes.map((n: DAGNode, i: number) => ({
      id: n.qsid,
      data: {
        label: (
          <div
            style={{
              padding: '6px 12px',
              borderRadius: 6,
              background: NODE_COLORS[n.factor_class] || '#d9d9d9',
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
      position: { x: (n.x ?? 0) + 400, y: (n.y ?? 0) + 100 },
      style: { padding: 0, border: 'none', background: 'transparent' },
    }))

    const flowEdges: Edge[] = dagData.edges.map((e, i) => ({
      id: `${e.source}-${e.target}-${i}`,
      source: e.source,
      target: e.target,
      type: 'smoothstep',
      animated: true,
      style: { stroke: '#91caff', strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#91caff', width: 12, height: 12 },
    }))

    setNodes(flowNodes)
    setEdges(flowEdges)
  }, [dagData, setNodes, setEdges])

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedQSID(node.id)
  }, [setSelectedQSID])

  if (!selectedQSID) {
    return (
      <Empty
        description="选择因子后查看 DAG"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ padding: '40px 0' }}
      />
    )
  }

  if (loadingDAG) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <Spin tip="加载 DAG..." />
      </div>
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '4px 12px', borderBottom: '1px solid #f0f0f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space size="small">
          <ApartmentOutlined />
          <span style={{ fontSize: 12, color: '#666' }}>
            {dagData ? `${dagData.nodes.length} 节点, ${dagData.edges.length} 边` : ''}
          </span>
        </Space>
        <Button size="small" icon={<ReloadOutlined />} onClick={loadDAG}>
          刷新
        </Button>
      </div>
      <div style={{ flex: 1 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          fitView
          attributionPosition="bottom-left"
        >
          <Background />
          <Controls />
          <MiniMap
            nodeColor={(n) => {
              const factorClass = dagData?.nodes.find(
                (dn) => dn.qsid === n.id
              )?.factor_class
              return NODE_COLORS[factorClass || ''] || '#d9d9d9'
            }}
          />
        </ReactFlow>
      </div>
    </div>
  )
}

export default DAGViewer
