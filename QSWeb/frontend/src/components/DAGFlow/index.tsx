/**
 * DAGFlow — 共享 DAG / 树形可视化组件
 *
 * 封装 ReactFlow 通用渲染逻辑：dagre 自动布局、Background、Controls、
 * MiniMap、smoothstep 边、空态/加载态、工具栏。
 *
 * 节点样式由调用方通过 ReactFlow Node 的 data.label 自行控制。
 */

import { useEffect, useMemo } from 'react'
import { Spin, Empty, Button, Space } from 'antd'
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
  NodeChange,
  EdgeChange,
} from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from 'dagre'

// ─── 颜色映射（与 MiningStudio 因子树风格一致） ──────────────
export const DEFAULT_NODE_COLORS: Record<string, string> = {
  operator: '#4682b4',
  terminal: '#91caff',
  constant: '#d9d9d9',
  AtomicFactor: '#91caff',
  DerivativeFactor: '#4682b4',
}

// ─── dagre 布局 ──────────────────────────────────────────────

function applyDagreLayout(
  nodes: Node[],
  edges: Edge[],
  options?: { rankdir?: 'TB' | 'LR'; nodesep?: number; ranksep?: number },
): Node[] {
  const { rankdir = 'TB', nodesep = 60, ranksep = 80 } = options || {}

  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir, nodesep, ranksep })

  for (const node of nodes) {
    g.setNode(node.id, { width: 140, height: 40 })
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target)
  }

  dagre.layout(g)

  return nodes.map((node) => {
    const pos = g.node(node.id)
    if (!pos) return node
    return {
      ...node,
      position: {
        x: pos.x - 70,  // center offset (width/2)
        y: pos.y - 20,  // center offset (height/2)
      },
    }
  })
}

// ─── Props ───────────────────────────────────────────────────

export interface DAGFlowProps {
  nodes: Node[]
  edges: Edge[]
  onNodesChange?: (changes: NodeChange[]) => void
  onEdgesChange?: (changes: EdgeChange[]) => void
  onNodeClick?: (event: React.MouseEvent, node: Node) => void
  loading?: boolean
  emptyText?: string
  /** 节点类型 → 颜色，用于 MiniMap 着色 */
  nodeColorMap?: Record<string, string>
  /** 是否显示工具栏 */
  showToolbar?: boolean
  onRefresh?: () => void
}

// ─── 组件 ────────────────────────────────────────────────────

function DAGFlow({
  nodes: rawNodes,
  edges: rawEdges,
  onNodesChange,
  onEdgesChange,
  onNodeClick,
  loading,
  emptyText = '无数据',
  nodeColorMap = DEFAULT_NODE_COLORS,
  showToolbar = false,
  onRefresh,
}: DAGFlowProps) {
  // 自动布局
  const layoutNodes = useMemo(
    () => applyDagreLayout(rawNodes, rawEdges),
    [rawNodes, rawEdges],
  )

  const [nodes, setNodes, handleNodesChange] = useNodesState(layoutNodes)
  const [edges, setEdges, handleEdgesChange] = useEdgesState(rawEdges)

  // 同步外部数据变化（如新数据加载）
  useEffect(() => {
    setNodes(layoutNodes)
    setEdges(rawEdges.map((e) => ({
      ...e,
      type: e.type || 'smoothstep',
      animated: e.animated ?? true,
      style: e.style || { stroke: '#91caff', strokeWidth: 1.5 },
      markerEnd: e.markerEnd || { type: MarkerType.ArrowClosed, color: '#91caff', width: 12, height: 12 },
    })))
  }, [layoutNodes, rawEdges, setNodes, setEdges])

  // 获取节点类型（从 data 中读取，兼容不同的 key 名）
  const getNodeType = (n: Node): string => {
    const data = n.data as Record<string, any> | undefined
    return data?.nodeType || data?.factor_class || data?.type || ''
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <Spin tip="加载中..." />
      </div>
    )
  }

  if (!rawNodes.length) {
    return (
      <Empty
        description={emptyText}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ padding: '40px 0' }}
      />
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {showToolbar && (
        <div style={{
          padding: '4px 12px',
          borderBottom: '1px solid #f0f0f0',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <Space size="small">
            <ApartmentOutlined />
            <span style={{ fontSize: 12, color: '#666' }}>
              {rawNodes.length} 节点, {rawEdges.length} 边
            </span>
          </Space>
          {onRefresh && (
            <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh}>
              刷新
            </Button>
          )}
        </div>
      )}
      <div style={{ flex: 1 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={(changes) => {
            handleNodesChange(changes)
            onNodesChange?.(changes)
          }}
          onEdgesChange={(changes) => {
            handleEdgesChange(changes)
            onEdgesChange?.(changes)
          }}
          onNodeClick={onNodeClick}
          fitView
          attributionPosition="bottom-left"
        >
          <Background />
          <Controls />
          <MiniMap
            nodeColor={(n) => {
              const t = getNodeType(n)
              return nodeColorMap[t] || '#d9d9d9'
            }}
          />
        </ReactFlow>
      </div>
    </div>
  )
}

export default DAGFlow
