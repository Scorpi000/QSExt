import { useState, useCallback, useEffect } from 'react'
import { Tree, Spin, Empty, message, Dropdown, Modal, Input, Checkbox, Space } from 'antd'
import type { DataNode, TreeProps } from 'antd/es/tree'
import type { MenuProps } from 'antd'
import {
  DatabaseOutlined,
  TableOutlined,
  FieldBinaryOutlined,
} from '@ant-design/icons'
import { getTables, getFactors, FactorTable, FactorInfo } from '../../services/factor'

interface FactorTreeProps {
  connectionId: string
  connectionName: string
  /** 只读模式（如 JYDB 不支持写操作） */
  readonly?: boolean
  onFactorSelect?: (factor: FactorInfo) => void
  onTableSelect?: (table: FactorTable) => void
  onTableRename: (oldName: string, newName: string) => Promise<void>
  onTableDelete: (tableNames: string[]) => Promise<void>
  onFactorRename: (tableName: string, oldName: string, newName: string) => Promise<void>
  onFactorDelete: (tableName: string, factorNames: string[]) => Promise<void>
}

interface TreeNodeData extends DataNode {
  type: 'connection' | 'table' | 'factor'
  data?: FactorTable | FactorInfo
}

function FactorTree({
  connectionId,
  connectionName,
  readonly = false,
  onFactorSelect,
  onTableSelect,
  onTableRename,
  onTableDelete,
  onFactorRename,
  onFactorDelete,
}: FactorTreeProps) {
  const [treeData, setTreeData] = useState<TreeNodeData[]>([])
  const [loading, setLoading] = useState(false)
  const [loadedKeys, setLoadedKeys] = useState<string[]>([])

  // 表重命名 Modal
  const [renameTableModal, setRenameTableModal] = useState<{ visible: boolean; oldName: string; value: string }>({
    visible: false,
    oldName: '',
    value: '',
  })
  // 批量删除因子 Modal
  const [deleteFactorsModal, setDeleteFactorsModal] = useState<{
    visible: boolean
    tableName: string
    factors: FactorInfo[]
    selected: string[]
  }>({
    visible: false,
    tableName: '',
    factors: [],
    selected: [],
  })
  // 因子重命名 Modal
  const [renameFactorModal, setRenameFactorModal] = useState<{
    visible: boolean
    tableName: string
    oldName: string
    value: string
  }>({
    visible: false,
    tableName: '',
    oldName: '',
    value: '',
  })

  // 加载因子表列表
  const loadTables = useCallback(async () => {
    if (!connectionId) {
      setTreeData([])
      return
    }
    setLoading(true)
    try {
      const tables = (await getTables(connectionId)) as unknown as FactorTable[]
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
    } catch {
      message.error('加载因子表失败')
    } finally {
      setLoading(false)
    }
  }, [connectionId])

  // 加载因子列表
  const loadFactors = useCallback(
    async (tableName: string): Promise<TreeNodeData[]> => {
      try {
        const factors = (await getFactors(connectionId, tableName)) as unknown as FactorInfo[]
        return factors.map((factor) => ({
          key: `factor-${tableName}-${factor.name}`,
          title: (
            <span className="factor-tree-node">
              <FieldBinaryOutlined className="node-icon" style={{ color: '#1890ff' }} />
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
      } catch {
        message.error('加载因子列表失败')
        return []
      }
    },
    [connectionId]
  )

  // 动态加载子节点
  const handleLoadData: TreeProps['loadData'] = async (node) => {
    const { key, type, data } = node as unknown as TreeNodeData
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
  const handleSelect: TreeProps['onSelect'] = (_, info) => {
    const { type, data } = info.node as unknown as TreeNodeData
    if (type === 'factor' && data && onFactorSelect) {
      onFactorSelect(data as FactorInfo)
    } else if (type === 'table' && data && onTableSelect) {
      onTableSelect(data as FactorTable)
    }
  }

  // 表节点右键菜单
  const getTableMenuItems = (table: FactorTable): MenuProps['items'] => [
    {
      key: 'rename',
      label: '重命名表',
      onClick: () => {
        setRenameTableModal({ visible: true, oldName: table.name, value: table.name })
      },
    },
    { type: 'divider' },
    {
      key: 'delete',
      label: '删除表',
      danger: true,
      onClick: async () => {
        Modal.confirm({
          title: '确定删除此表？',
          content: `表 "${table.name}" 及其所有因子将被删除，此操作不可撤销。`,
          okText: '删除',
          okType: 'danger',
          cancelText: '取消',
          onOk: async () => {
            await onTableDelete([table.name])
            loadTables()
          },
        })
      },
    },
  ]

  // 因子节点右键菜单
  const getFactorMenuItems = (tableName: string, factor: FactorInfo): MenuProps['items'] => [
    {
      key: 'rename',
      label: '重命名因子',
      onClick: () => {
        setRenameFactorModal({
          visible: true,
          tableName,
          oldName: factor.name,
          value: factor.name,
        })
      },
    },
    { type: 'divider' },
    {
      key: 'delete',
      label: '删除因子',
      danger: true,
      onClick: async () => {
        Modal.confirm({
          title: '确定删除此因子？',
          content: `因子 "${factor.name}" 将被删除，此操作不可撤销。`,
          okText: '删除',
          okType: 'danger',
          cancelText: '取消',
          onOk: async () => {
            await onFactorDelete(tableName, [factor.name])
            // 删除操作可能连带删除了整个表，需要判断
            const tables = (await getTables(connectionId)) as unknown as FactorTable[]
            if (tables.find((t) => t.name === tableName)) {
              const factors = await loadFactors(tableName)
              setTreeData((prev) =>
                prev.map((item) =>
                  item.key === `table-${tableName}` ? { ...item, children: factors } : item
                )
              )
            } else {
              loadTables()
            }
          },
        })
      },
    },
    { type: 'divider' },
    {
      key: 'batchDelete',
      label: '批量删除因子',
      onClick: async () => {
        const factors = (await getFactors(connectionId, tableName)) as unknown as FactorInfo[]
        setDeleteFactorsModal({
          visible: true,
          tableName,
          factors,
          selected: [],
        })
      },
    },
  ]

  // titleRender 实现右键菜单（只读模式下不显示右键菜单）
  const titleRender = (node: TreeNodeData) => {
    const { type, data } = node
    if (readonly) {
      return <span>{node.title as React.ReactNode}</span>
    }
    if (type === 'table' && data) {
      return (
        <Dropdown menu={{ items: getTableMenuItems(data as FactorTable) }} trigger={['contextMenu']}>
          <span>{node.title as React.ReactNode}</span>
        </Dropdown>
      )
    }
    if (type === 'factor' && data) {
      const factor = data as FactorInfo
      return (
        <Dropdown menu={{ items: getFactorMenuItems(factor.table_name, factor) }} trigger={['contextMenu']}>
          <span>{node.title as React.ReactNode}</span>
        </Dropdown>
      )
    }
    return <span>{node.title as React.ReactNode}</span>
  }

  // 初始化加载
  useEffect(() => {
    loadTables()
  }, [loadTables])

  // 暴露 refresh 方法给外部
  useEffect(() => {
    ;(FactorTree as any)._lastRefresh = loadTables
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
            titleRender={titleRender}
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

      {/* 表重命名 Modal */}
      <Modal
        title="重命名表"
        open={renameTableModal.visible}
        onCancel={() => setRenameTableModal({ visible: false, oldName: '', value: '' })}
        onOk={async () => {
          const { oldName, value } = renameTableModal
          if (value && value !== oldName) {
            await onTableRename(oldName, value)
            loadTables()
          }
          setRenameTableModal({ visible: false, oldName: '', value: '' })
        }}
        okText="确定"
        cancelText="取消"
      >
        <Input
          value={renameTableModal.value}
          onChange={(e) =>
            setRenameTableModal((prev) => ({ ...prev, value: e.target.value }))
          }
          placeholder="新表名"
        />
      </Modal>

      {/* 因子重命名 Modal */}
      <Modal
        title="重命名因子"
        open={renameFactorModal.visible}
        onCancel={() =>
          setRenameFactorModal({ visible: false, tableName: '', oldName: '', value: '' })
        }
        onOk={async () => {
          const { tableName, oldName, value } = renameFactorModal
          if (value && value !== oldName) {
            await onFactorRename(tableName, oldName, value)
            const factors = await loadFactors(tableName)
            setTreeData((prev) =>
              prev.map((item) =>
                item.key === `table-${tableName}` ? { ...item, children: factors } : item
              )
            )
          }
          setRenameFactorModal({ visible: false, tableName: '', oldName: '', value: '' })
        }}
        okText="确定"
        cancelText="取消"
      >
        <Input
          value={renameFactorModal.value}
          onChange={(e) =>
            setRenameFactorModal((prev) => ({ ...prev, value: e.target.value }))
          }
          placeholder="新因子名"
        />
      </Modal>

      {/* 批量删除因子 Modal */}
      <Modal
        title="批量删除因子"
        open={deleteFactorsModal.visible}
        onCancel={() =>
          setDeleteFactorsModal({ visible: false, tableName: '', factors: [], selected: [] })
        }
        onOk={async () => {
          if (deleteFactorsModal.selected.length > 0) {
            await onFactorDelete(deleteFactorsModal.tableName, deleteFactorsModal.selected)
            const tables = (await getTables(connectionId)) as unknown as FactorTable[]
            if (tables.find((t) => t.name === deleteFactorsModal.tableName)) {
              const factors = await loadFactors(deleteFactorsModal.tableName)
              setTreeData((prev) =>
                prev.map((item) =>
                  item.key === `table-${deleteFactorsModal.tableName}`
                    ? { ...item, children: factors }
                    : item
                )
              )
            } else {
              loadTables()
            }
          }
          setDeleteFactorsModal({ visible: false, tableName: '', factors: [], selected: [] })
        }}
        okText="删除"
        okButtonProps={{ danger: true, disabled: deleteFactorsModal.selected.length === 0 }}
        cancelText="取消"
      >
        <div style={{ maxHeight: 300, overflow: 'auto' }}>
          <Checkbox.Group
            value={deleteFactorsModal.selected}
            onChange={(values) =>
              setDeleteFactorsModal((prev) => ({ ...prev, selected: values as string[] }))
            }
          >
            <Space direction="vertical">
              {deleteFactorsModal.factors.map((f) => (
                <Checkbox key={f.name} value={f.name}>
                  {f.name}
                </Checkbox>
              ))}
            </Space>
          </Checkbox.Group>
        </div>
      </Modal>
    </div>
  )
}

export default FactorTree
