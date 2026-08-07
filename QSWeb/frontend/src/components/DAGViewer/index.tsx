/**
 * DAG 可视化组件（React Flow）
 *
 * 因子工作台依赖关系图，使用共享 DAGFlow 组件渲染。
 * - 默认显示目标因子周围 2 层关联因子，可通过深度滑块调整
 * - 单击节点 → 右侧显示因子详情
 * - 双击节点 → 以该节点为中心重新展开 DAG
 * - 右键节点 → 展开/收起该节点的 1 层邻居关系
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { message, Select } from 'antd'
import { PlusSquareOutlined, MinusSquareOutlined } from '@ant-design/icons'
import { Node, Edge } from 'reactflow'
import DAGFlow, { DEFAULT_NODE_COLORS } from '../DAGFlow'
import { getFactorDAG, getFactorNeighbors, DAGNode, DAGData } from '../../services/registry'
import { useFactorWorkbenchStore } from '../../stores/factorWorkbench'

const DEPTH_OPTIONS = [
  { value: 1, label: '1 层' },
  { value: 2, label: '2 层' },
  { value: 3, label: '3 层' },
  { value: 4, label: '4 层' },
  { value: 5, label: '5 层' },
  { value: 0, label: '全部' },
]

interface ContextMenuState {
  visible: boolean
  x: number
  y: number
  qsid: string
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

  const [dagRoot, setDagRoot] = useState<string | null>(null)
  const [depth, setDepth] = useState<number>(2)
  const [fitVersion, setFitVersion] = useState(0)
  const isInternalClick = useRef(false)

  // 逐节点展开的子图: qsid -> 该节点的 1 层邻居 DAGData
  const [expandedGraphs, setExpandedGraphs] = useState<Map<string, DAGData>>(new Map())

  // 右键菜单
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, qsid: '' })

  const loadDAG = useCallback(async (rootQsid: string, maxDepth?: number) => {
    setLoadingDAG(true)
    try {
      const data = (await getFactorDAG(rootQsid, maxDepth)) as unknown as DAGData
      setDagData(data)
      // 重新加载基础 DAG 时清空逐节点展开
      setExpandedGraphs(new Map())
      // 触发 fitView
      setFitVersion((v) => v + 1)
    } catch {
      message.error('加载 DAG 失败')
      setDagData(null)
    } finally {
      setLoadingDAG(false)
    }
  }, [setDagData, setLoadingDAG])

  // 外部因子选择变化时（如从搜索结果点击），设为新的 DAG 中心并加载
  // DAG 内部单击节点不触发重载（通过 isInternalClick 标记区分）
  useEffect(() => {
    if (selectedQSID) {
      if (isInternalClick.current) {
        isInternalClick.current = false
        return
      }
      setDagRoot(selectedQSID)
      loadDAG(selectedQSID, depth === 0 ? undefined : depth)
    }
  }, [selectedQSID])

  const handleDepthChange = useCallback((newDepth: number) => {
    setDepth(newDepth)
    if (dagRoot) {
      loadDAG(dagRoot, newDepth === 0 ? undefined : newDepth)
    }
  }, [dagRoot, loadDAG])

  // ─── 合并基础 DAG + 所有展开子图 ───────────────────────────

  const mergedDAG = useMemo(() => {
    if (!dagData) return null

    const allNodes = [...dagData.nodes]
    const allEdges = [...dagData.edges]
    const nodeIds = new Set(allNodes.map((n: DAGNode) => n.qsid))
    const edgeKeys = new Set(allEdges.map((e) => `${e.source}->${e.target}`))

    for (const [, subgraph] of expandedGraphs) {
      for (const node of subgraph.nodes) {
        if (!nodeIds.has(node.qsid)) {
          nodeIds.add(node.qsid)
          allNodes.push(node)
        }
      }
      for (const edge of subgraph.edges) {
        const key = `${edge.source}->${edge.target}`
        if (!edgeKeys.has(key)) {
          edgeKeys.add(key)
          allEdges.push(edge)
        }
      }
    }

    return { nodes: allNodes, edges: allEdges, root_qsid: dagData.root_qsid }
  }, [dagData, expandedGraphs])

  // ─── 转换为 ReactFlow 格式 ──────────────────────────────────

  const { flowNodes, flowEdges } = useMemo(() => {
    if (!mergedDAG) return { flowNodes: [], flowEdges: [] }

    const nodes: Node[] = mergedDAG.nodes.map((n: DAGNode) => ({
      id: n.qsid,
      data: {
        nodeType: n.factor_class,
        isRoot: n.qsid === dagData?.root_qsid,
        isSelected: n.qsid === selectedQSID,
        isExpanded: expandedGraphs.has(n.qsid),
        label: (
          <div
            style={{
              padding: '4px 10px',
              borderRadius: 4,
              background: n.qsid === selectedQSID
                ? '#fa8c16'
                : DEFAULT_NODE_COLORS[n.factor_class] || '#d9d9d9',
              color: n.qsid === selectedQSID
                ? '#fff'
                : n.factor_class === 'DerivativeFactor' ? '#fff' : '#333',
              fontSize: 12,
              fontWeight: 500,
              border: n.qsid === dagData?.root_qsid
                ? '2px solid #fa8c16'
                : n.qsid === selectedQSID
                  ? '3px solid #1890ff'
                  : '1px solid transparent',
              boxShadow: n.qsid === selectedQSID
                ? '0 0 12px rgba(24,144,255,0.5)'
                : 'none',
              zIndex: n.qsid === selectedQSID ? 10 : 1,
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {n.name}
              {expandedGraphs.has(n.qsid) && (
                <span style={{ fontSize: 10, color: '#fa8c16' }}>⊕</span>
              )}
            </div>
            {n.operator_type && (
              <div style={{ fontSize: 10, opacity: 0.8 }}>{n.operator_type}</div>
            )}
          </div>
        ),
      },
      position: { x: 0, y: 0 },
    }))

    const edges: Edge[] = mergedDAG.edges.map((e, i) => ({
      id: `${e.source}-${e.target}-${i}`,
      source: e.source,
      target: e.target,
    }))

    return { flowNodes: nodes, flowEdges: edges }
  }, [mergedDAG, selectedQSID, expandedGraphs, dagData])

  // ─── 节点交互 ──────────────────────────────────────────────

  // 单击 → 选中查看详情（不重新展开 DAG）
  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    isInternalClick.current = true
    setSelectedQSID(node.id)
  }, [setSelectedQSID])

  // 双击 → 以该节点为中心重新展开 DAG
  const onNodeDoubleClick = useCallback((_event: React.MouseEvent, node: Node) => {
    isInternalClick.current = true
    setDagRoot(node.id)
    setSelectedQSID(node.id)
    loadDAG(node.id, depth === 0 ? undefined : depth)
  }, [depth, loadDAG, setSelectedQSID])

  // ─── 右键菜单 ──────────────────────────────────────────────

  const onNodeContextMenu = useCallback((event: React.MouseEvent, node: Node) => {
    event.preventDefault()
    setContextMenu({ visible: true, x: event.clientX, y: event.clientY, qsid: node.id })
  }, [])

  const closeContextMenu = useCallback(() => {
    setContextMenu((prev) => ({ ...prev, visible: false }))
  }, [])

  // 展开关系：获取该节点的 1 层邻居并合并到图中
  const handleExpand = useCallback(async () => {
    const qsid = contextMenu.qsid
    closeContextMenu()
    try {
      const neighbors = (await getFactorNeighbors(qsid)) as unknown as DAGData
      setExpandedGraphs((prev) => {
        const next = new Map(prev)
        next.set(qsid, neighbors)
        return next
      })
    } catch {
      message.error('加载邻居关系失败')
    }
  }, [contextMenu.qsid, closeContextMenu])

  // 收起关系：移除该节点展开时加入的邻居
  const handleCollapse = useCallback(() => {
    const qsid = contextMenu.qsid
    closeContextMenu()
    setExpandedGraphs((prev) => {
      const next = new Map(prev)
      next.delete(qsid)
      return next
    })
  }, [contextMenu.qsid, closeContextMenu])

  const isExpanded = expandedGraphs.has(contextMenu.qsid)

  // ─── 工具栏 ────────────────────────────────────────────────

  const toolbarExtra = (
    <span style={{ fontSize: 12, color: '#666', display: 'flex', alignItems: 'center', gap: 4 }}>
      <span>显示:</span>
      <Select
        size="small"
        value={depth}
        onChange={(v) => handleDepthChange(v)}
        options={DEPTH_OPTIONS}
        style={{ width: 80 }}
      />
    </span>
  )

  return (
    <div style={{ height: '100%', position: 'relative' }}>
      <DAGFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        onNodeContextMenu={onNodeContextMenu}
        loading={loadingDAG}
        emptyText={selectedQSID ? '无依赖数据' : '选择因子后查看 DAG'}
        nodeColorMap={DEFAULT_NODE_COLORS}
        fitVersion={fitVersion}
        showToolbar
        onRefresh={() => dagRoot && loadDAG(dagRoot, depth === 0 ? undefined : depth)}
        toolbarExtra={toolbarExtra}
      />

      {/* 右键菜单 */}
      {contextMenu.visible && (
        <>
          {/* 透明遮罩，点击关闭菜单 */}
          <div
            onClick={closeContextMenu}
            onContextMenu={(e) => { e.preventDefault(); closeContextMenu() }}
            style={{ position: 'fixed', inset: 0, zIndex: 999 }}
          />
          {/* 菜单 */}
          <div
            style={{
              position: 'fixed',
              left: contextMenu.x,
              top: contextMenu.y,
              zIndex: 1000,
              background: '#fff',
              borderRadius: 6,
              boxShadow: '0 3px 12px rgba(0,0,0,0.15)',
              padding: 4,
              minWidth: 130,
            }}
          >
            {!isExpanded ? (
              <div
                onClick={handleExpand}
                style={{
                  padding: '6px 12px',
                  cursor: 'pointer',
                  borderRadius: 4,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 13,
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = '#f5f5f5' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
              >
                <PlusSquareOutlined style={{ color: '#52c41a' }} />
                展开关系
              </div>
            ) : (
              <div
                onClick={handleCollapse}
                style={{
                  padding: '6px 12px',
                  cursor: 'pointer',
                  borderRadius: 4,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 13,
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = '#f5f5f5' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
              >
                <MinusSquareOutlined style={{ color: '#ff4d4f' }} />
                收起关系
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default DAGViewer
