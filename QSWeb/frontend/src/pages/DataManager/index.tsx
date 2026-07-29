/**
 * DataManager - 数据管理页面
 *
 * 布局编排和状态提升，委托给四个子组件：
 * ConnectionPanel（连接 CRUD）、FactorTreePanel（因子浏览）、DataPreviewPanel（数据预览+元数据）。
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Row, Col, Form, message, Modal, List, Tag, Typography } from 'antd'
import { ExclamationCircleOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import type {
  Connection,
  ConnectionCreate,
  ConnectionUpdate,
  ImpactAnalysis,
} from '../../services/connection'
import {
  getConnections,
  createConnection,
  updateConnection,
  deleteConnectionConfirm,
  getImpact,
} from '../../services/connection'
import type {
  FactorInfo,
  FactorTable,
  FactorData,
  FactorStats,
} from '../../services/factor'
import {
  getFactorData,
  getFactorStats,
  reconnectFactorDB,
  getFactorMetadata,
  getTableMetadata,
  renameTable,
  deleteTables,
  updateTableMetadata,
  renameFactor,
  deleteFactors,
  updateFactorMetadata,
} from '../../services/factor'
import ConnectionPanel from './ConnectionPanel'
import FactorTreePanel from './FactorTreePanel'
import DataPreviewPanel from './DataPreviewPanel'

function DataManager() {
  // 连接列表
  const [connections, setConnections] = useState<Connection[]>([])
  const [loadingConnections, setLoadingConnections] = useState(false)

  // 当前选中的连接
  const [activeConnection, setActiveConnection] = useState<Connection | null>(null)

  // 因子树刷新 key
  const [treeRefreshKey, setTreeRefreshKey] = useState(0)

  // 当前选中的表
  const [selectedTable, setSelectedTable] = useState<FactorTable | null>(null)

  // 当前选中的因子
  const [selectedFactor, setSelectedFactor] = useState<FactorInfo | null>(null)

  // 因子数据
  const [factorData, setFactorData] = useState<FactorData | null>(null)
  const [loadingData, setLoadingData] = useState(false)

  // 元数据
  const [factorMeta, setFactorMeta] = useState<Record<string, any> | null>(null)
  const [tableMeta, setTableMeta] = useState<Record<string, any> | null>(null)

  // 因子统计信息
  const [factorStats, setFactorStats] = useState<FactorStats | null>(null)

  // 数据查询参数
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)
  const [limit, setLimit] = useState(1000)
  const [filterNaN, setFilterNaN] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  // 新建/编辑连接对话框
  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [createForm] = Form.useForm()
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [editingConnection, setEditingConnection] = useState<Connection | null>(null)
  const [editForm] = Form.useForm()

  // 删除影响确认对话框
  const [impactModalVisible, setImpactModalVisible] = useState(false)
  const [impactData, setImpactData] = useState<ImpactAnalysis | null>(null)
  const [deletingQsid, setDeletingQsid] = useState<string | null>(null)
  const [deletingName, setDeletingName] = useState<string>('')
  const [deleting, setDeleting] = useState(false)

  // ── 加载连接列表 ─────────────────────────────────────────
  const loadConnections = useCallback(async () => {
    setLoadingConnections(true)
    try {
      const data = await getConnections()
      setConnections(data as unknown as Connection[])
    } catch { /* handled */ }
    finally { setLoadingConnections(false) }
  }, [])

  useEffect(() => { loadConnections() }, [loadConnections])

  // ── 连接 CRUD ────────────────────────────────────────────
  const handleCreate = async (values: ConnectionCreate) => {
    await createConnection(values)
    message.success('创建成功')
    loadConnections()
  }

  const handleDeleteClick = async (qsid: string, name: string) => {
    try {
      const impact = await getImpact(qsid) as unknown as ImpactAnalysis
      setImpactData(impact)
      setDeletingQsid(qsid)
      setDeletingName(name)
      setImpactModalVisible(true)
    } catch { /* handled */ }
  }

  const handleDeleteConfirm = async () => {
    if (!deletingQsid) return
    setDeleting(true)
    try {
      await deleteConnectionConfirm(deletingQsid)
      message.success('删除成功')
      if (activeConnection?.qsid === deletingQsid) {
        setActiveConnection(null)
        setSelectedFactor(null)
        setSelectedTable(null)
        setFactorData(null)
      }
      loadConnections()
    } catch { /* handled */ }
    finally {
      setDeleting(false)
      setImpactModalVisible(false)
      setImpactData(null)
      setDeletingQsid(null)
    }
  }

  const handleEditOpen = (conn: Connection) => {
    setEditingConnection(conn)
    editForm.setFieldsValue({
      name: conn.name,
      db_type: conn.db_type,
      description: conn.description,
      args: conn.args,
    })
    setEditModalVisible(true)
  }

  const handleEdit = async (_conn: Connection, values: ConnectionUpdate) => {
    if (!editingConnection) return
    await updateConnection(editingConnection.qsid, values)
    message.success('更新成功')
    setEditingConnection(null)
    loadConnections()
  }

  const handleReconnect = async (qsid: string) => {
    await reconnectFactorDB(qsid)
    message.success('重连成功')
    if (activeConnection?.qsid === qsid) {
      setSelectedFactor(null)
      setSelectedTable(null)
      setFactorData(null)
      setTreeRefreshKey((k) => k + 1)
    }
  }

  // ── 选择连接 ─────────────────────────────────────────────
  const handleSelectConnection = (conn: Connection) => {
    setActiveConnection(conn)
    setSelectedFactor(null)
    setSelectedTable(null)
    setFactorData(null)
  }

  // ── 选择表 ───────────────────────────────────────────────
  const handleTableSelect = async (table: FactorTable) => {
    setSelectedTable(table)
    setSelectedFactor(null)
    setFactorData(null)
    setFactorStats(null)
    setFactorMeta(null)
    setTableMeta(null)
    try {
      const tMeta = await getTableMetadata(table.conn_id, table.name)
      setTableMeta(tMeta as unknown as Record<string, any>)
    } catch { /* handled */ }
  }

  // ── 选择因子 ─────────────────────────────────────────────
  const handleFactorSelect = async (factor: FactorInfo) => {
    setSelectedFactor(factor)
    setSelectedTable(null)
    setLoadingData(true)
    setFactorMeta(null)
    setTableMeta(null)
    setFactorStats(null)
    try {
      const params: any = { limit }
      if (dateRange) {
        params.start_date = dateRange[0].format('YYYY-MM-DD')
        params.end_date = dateRange[1].format('YYYY-MM-DD')
      }
      if (selectedIds.length > 0) {
        params.ids = selectedIds.join(',')
      }
      const [data, fMeta, stats] = await Promise.all([
        getFactorData(factor.conn_id, factor.table_name, factor.name, params),
        getFactorMetadata(factor.conn_id, factor.table_name, factor.name),
        getFactorStats(factor.conn_id, factor.table_name, factor.name),
      ])
      setFactorData(data as unknown as FactorData)
      setFactorMeta(fMeta as unknown as Record<string, any>)
      setFactorStats(stats as unknown as FactorStats)
    } catch { /* handled */ }
    finally { setLoadingData(false) }
  }

  const handleRefreshData = () => {
    if (selectedFactor) handleFactorSelect(selectedFactor)
  }

  // ── 表管理回调 ───────────────────────────────────────────
  const handleTableRename = async (oldName: string, newName: string) => {
    if (!activeConnection) return
    await renameTable(activeConnection.qsid, oldName, newName)
    message.success(`表 "${oldName}" 已重命名为 "${newName}"`)
    setSelectedTable(null)
    setTreeRefreshKey((k) => k + 1)
  }

  const handleTableDelete = async (tableNames: string[]) => {
    if (!activeConnection) return
    await deleteTables(activeConnection.qsid, tableNames)
    message.success(`已删除 ${tableNames.length} 个表`)
    setSelectedTable(null)
    setSelectedFactor(null)
    setFactorData(null)
    setTreeRefreshKey((k) => k + 1)
  }

  const handleTableMetadataSave = async (metadata: Record<string, any>) => {
    if (!activeConnection || !selectedTable) return
    await updateTableMetadata(activeConnection.qsid, selectedTable.name, metadata)
    const tMeta = await getTableMetadata(activeConnection.qsid, selectedTable.name)
    setTableMeta(tMeta as unknown as Record<string, any>)
  }

  // ── 因子管理回调 ─────────────────────────────────────────
  const handleFactorRename = async (tableName: string, oldName: string, newName: string) => {
    if (!activeConnection) return
    await renameFactor(activeConnection.qsid, tableName, oldName, newName)
    message.success(`因子 "${oldName}" 已重命名为 "${newName}"`)
    if (selectedFactor?.name === oldName && selectedFactor?.table_name === tableName) {
      setSelectedFactor(null)
      setFactorData(null)
    }
  }

  const handleFactorDelete = async (tableName: string, factorNames: string[]) => {
    if (!activeConnection) return
    await deleteFactors(activeConnection.qsid, tableName, factorNames)
    message.success(`已删除 ${factorNames.length} 个因子`)
    if (selectedFactor?.table_name === tableName && factorNames.includes(selectedFactor.name)) {
      setSelectedFactor(null)
      setFactorData(null)
    }
  }

  const handleFactorMetadataSave = async (metadata: Record<string, any>) => {
    if (!activeConnection || !selectedFactor) return
    await updateFactorMetadata(
      activeConnection.qsid,
      selectedFactor.table_name,
      selectedFactor.name,
      metadata
    )
    const fMeta = await getFactorMetadata(
      activeConnection.qsid,
      selectedFactor.table_name,
      selectedFactor.name
    )
    setFactorMeta(fMeta as unknown as Record<string, any>)
  }

  // ── 过滤缺失值后的数据 ───────────────────────────────────
  const displayData = useMemo(() => {
    if (!factorData) return { data: {}, columns: [], index: [] }
    if (!filterNaN) return factorData

    const valueCols = factorData.columns.filter((c) => c !== 'datetime' && c !== 'code')
    const keepIndices: number[] = []
    for (let i = 0; i < factorData.index.length; i++) {
      const hasValue = valueCols.some((col) => {
        const val = factorData.data[col]?.[i]
        return val !== null && val !== undefined && val !== '' && !Number.isNaN(val)
      })
      if (hasValue) keepIndices.push(i)
    }

    const newData: Record<string, any[]> = {}
    for (const col of factorData.columns) {
      const colData = factorData.data[col] || []
      newData[col] = keepIndices.map((i) => colData[i])
    }
    return {
      data: newData,
      columns: factorData.columns,
      index: keepIndices.map((i) => factorData.index[i]),
    }
  }, [factorData, filterNaN])

  return (
    <>
    <Row gutter={16} style={{ height: 'calc(100vh - 160px)' }}>
      {/* 左侧：连接列表 */}
      <Col span={6}>
        <ConnectionPanel
          connections={connections}
          loading={loadingConnections}
          activeConnection={activeConnection}
          onSelectConnection={handleSelectConnection}
          onRefresh={loadConnections}
          onCreate={handleCreate}
          onEdit={handleEdit}
          onDelete={handleDeleteClick}
          onReconnect={handleReconnect}
          createModalVisible={createModalVisible}
          onOpenCreate={() => setCreateModalVisible(true)}
          onCloseCreate={() => { setCreateModalVisible(false); createForm.resetFields() }}
          createForm={createForm}
          editModalVisible={editModalVisible}
          editingConnection={editingConnection}
          onOpenEdit={handleEditOpen}
          onCloseEdit={() => { setEditModalVisible(false); editForm.resetFields(); setEditingConnection(null) }}
          editForm={editForm}
        />
      </Col>

      {/* 中间：因子树 */}
      <Col span={6} style={{ height: '100%' }}>
        {activeConnection ? (
          <FactorTreePanel
            connectionId={activeConnection.qsid}
            connectionName={activeConnection.name}
            dbType={activeConnection.db_type}
            treeRefreshKey={treeRefreshKey}
            onFactorSelect={handleFactorSelect}
            onTableSelect={handleTableSelect}
            onTableRename={handleTableRename}
            onTableDelete={handleTableDelete}
            onFactorRename={handleFactorRename}
            onFactorDelete={handleFactorDelete}
          />
        ) : (
          <div style={{
            display: 'flex', justifyContent: 'center', alignItems: 'center',
            height: '100%', color: '#999',
          }}>
            请先选择一个连接
          </div>
        )}
      </Col>

      {/* 右侧：数据预览 */}
      <Col span={12} style={{ height: '100%' }}>
        <DataPreviewPanel
          selectedFactor={selectedFactor}
          selectedTable={selectedTable}
          factorData={displayData as FactorData}
          loadingData={loadingData}
          factorStats={factorStats}
          factorMeta={factorMeta}
          tableMeta={tableMeta}
          dateRange={dateRange}
          limit={limit}
          filterNaN={filterNaN}
          selectedIds={selectedIds}
          dbType={activeConnection?.db_type || ''}
          onDateRangeChange={setDateRange}
          onLimitChange={setLimit}
          onFilterNaNChange={setFilterNaN}
          onSelectedIdsChange={setSelectedIds}
          onRefresh={handleRefreshData}
          onFactorMetadataSave={handleFactorMetadataSave}
          onTableMetadataSave={handleTableMetadataSave}
        />
      </Col>
    </Row>

    {/* 删除影响确认对话框 */}
    <Modal
      title={
        <span>
          <ExclamationCircleOutlined style={{ color: '#faad14', marginRight: 8 }} />
          确认删除因子库连接
        </span>
      }
      open={impactModalVisible}
      onOk={handleDeleteConfirm}
      onCancel={() => { setImpactModalVisible(false); setImpactData(null); setDeletingQsid(null) }}
      okText="确认删除"
      okButtonProps={{ danger: true, loading: deleting }}
      cancelText="取消"
      width={560}
    >
      {impactData && (
        <div>
          <Typography.Paragraph>
            即将删除因子库 <Tag color="red">{deletingName}</Tag>，此操作将级联删除以下内容：
          </Typography.Paragraph>

          {/* 因子表 */}
          {impactData.factor_tables.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <Typography.Text strong>
                因子表（{impactData.factor_tables.length} 个）：
              </Typography.Text>
              <div style={{ marginTop: 4 }}>
                {impactData.factor_tables.map((t) => (
                  <Tag key={t.QSID} color="orange" style={{ marginBottom: 4 }}>{t.Name}</Tag>
                ))}
              </div>
            </div>
          )}

          {/* 直接因子 */}
          {impactData.direct_factors.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <Typography.Text strong>
                直接因子（{impactData.direct_factors.length} 个）：
              </Typography.Text>
              <List
                size="small"
                style={{ maxHeight: 120, overflow: 'auto', marginTop: 4 }}
                dataSource={impactData.direct_factors.slice(0, 20)}
                renderItem={(f) => (
                  <List.Item style={{ padding: '2px 0', fontSize: 12 }}>
                    {f.Name}
                    {f.FactorTableName && (
                      <Tag style={{ marginLeft: 6, fontSize: 10 }}>{f.FactorTableName}</Tag>
                    )}
                  </List.Item>
                )}
              />
              {impactData.direct_factors.length > 20 && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  ...及其他 {impactData.direct_factors.length - 20} 个因子
                </Typography.Text>
              )}
            </div>
          )}

          {/* 间接依赖因子 */}
          {impactData.indirect_factors.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <Typography.Text strong>
                间接依赖因子（{impactData.indirect_factors.length} 个）：
              </Typography.Text>
              <List
                size="small"
                style={{ maxHeight: 120, overflow: 'auto', marginTop: 4 }}
                dataSource={impactData.indirect_factors.slice(0, 20)}
                renderItem={(f) => (
                  <List.Item style={{ padding: '2px 0', fontSize: 12 }}>
                    {f.Name}
                  </List.Item>
                )}
              />
              {impactData.indirect_factors.length > 20 && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  ...及其他 {impactData.indirect_factors.length - 20} 个因子
                </Typography.Text>
              )}
            </div>
          )}

          <Typography.Paragraph type="danger" style={{ marginTop: 12, marginBottom: 0 }}>
            共影响 <strong>{impactData.total_affected_factors}</strong> 个因子，此操作不可撤销！
          </Typography.Paragraph>
        </div>
      )}
      {!impactData && (
        <Typography.Text type="secondary">正在查询影响范围...</Typography.Text>
      )}
    </Modal>
    </>
  )
}

export default DataManager
