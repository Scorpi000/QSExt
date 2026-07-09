import { useState, useCallback, useEffect } from 'react'
import { Tree, Spin, Empty, message } from 'antd'
import type { DataNode, TreeProps } from 'antd/es/tree'
import {
  DatabaseOutlined,
  TableOutlined,
  FieldBinaryOutlined,
} from '@ant-design/icons'
import { getTables, getFactors, FactorTable, FactorInfo } from '../../services/factor'

interface FactorTreeProps {
  connectionId: string
  connectionName: string
  onFactorSelect?: (factor: FactorInfo) => void
}

interface TreeNodeData extends DataNode {
  type: 'connection' | 'table' | 'factor'
  data?: FactorTable | FactorInfo
}

function FactorTree({ connectionId, connectionName, onFactorSelect }: FactorTreeProps) {
  const [treeData, setTreeData] = useState<TreeNodeData[]>([])
  const [loading, setLoading] = useState(false)
  const [loadedKeys, setLoadedKeys] = useState<string[]>([])

  // 加载因子表列表
  const loadTables = useCallback(async () => {
    setLoading(true)
    try {
      const tables = await getTables(connectionId)
      const nodes: TreeNodeData[] = tables.map((table) => ({
        key: `table-${table.name}`,
        title: (
          <span className="factor-tree-node">
            <TableOutlined className="node-icon" style={{ color: '#52c41a' }} />
            <span className="node-label">{table.name}</span>
            {table.factor_count !== undefined && (
              <span className="node-count">({table.factor_count})</span>
            )}
          </span>
        ),
        type: 'table',
        data: table,
        isLeaf: false,
      }))
      setTreeData(nodes)
    } catch (error) {
      message.error('加载因子表失败')
    } finally {
      setLoading(false)
    }
  }, [connectionId])

  // 加载因子列表
  const loadFactors = useCallback(
    async (tableName: string): Promise<TreeNodeData[]> => {
      try {
        const factors = await getFactors(connectionId, tableName)
        return factors.map((factor) => ({
          key: `factor-${tableName}-${factor.name}`,
          title: (
            <span className="factor-tree-node">
              <FieldBinaryOutlined
                className="node-icon"
                style={{ color: '#1890ff' }}
              />
              <span className="node-label">{factor.name}</span>
              {factor.data_type && (
                <span className="node-count">{factor.data_type}</span>
              )}
            </span>
          ),
          type: 'factor',
          data: factor,
          isLeaf: true,
        }))
      } catch (error) {
        message.error('加载因子列表失败')
        return []
      }
    },
    [connectionId]
  )

  // 动态加载子节点
  const handleLoadData: TreeProps['loadData'] = async (node) => {
    const { key, type, data } = node as TreeNodeData

    if (type === 'table' && data) {
      const table = data as FactorTable
      const factors = await loadFactors(table.name)
      setTreeData((prev) =>
        prev.map((item) =>
          item.key === key ? { ...item, children: factors } : item
        )
      )
      setLoadedKeys((prev) => [...prev, key as string])
    }
  }

  // 选择节点
  const handleSelect: TreeProps['onSelect'] = (selectedKeys, info) => {
    const { type, data } = info.node as TreeNodeData
    if (type === 'factor' && data && onFactorSelect) {
      onFactorSelect(data as FactorInfo)
    }
  }

  // 初始化加载
  useEffect(() => {
    loadTables()
  }, [loadTables])

  return (
    <div style={{ height: '100%', overflow: 'auto' }}>
      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid #f0f0f0',
          fontWeight: 500,
        }}
      >
        <DatabaseOutlined style={{ marginRight: 8 }} />
        {connectionName}
      </div>
      <Spin spinning={loading}>
        {treeData.length > 0 ? (
          <Tree
            showIcon
            loadData={handleLoadData}
            onSelect={handleSelect}
            treeData={treeData}
            loadedKeys={loadedKeys}
            style={{ padding: '8px 0' }}
          />
        ) : (
          <Empty
            description="暂无因子表"
            style={{ padding: '40px 0' }}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        )}
      </Spin>
    </div>
  )
}

export default FactorTree
