/**
 * RiskManager - 风险管理页面
 *
 * 左侧：风险库树（RiskDB → RiskTable）+ 添加/编辑/删除/测试风险库
 * 右侧：内容区（协方差热力图 / 相关系数热力图 / 因子风险分解 / 特异性风险直方图）
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Row, Col, Card, Tree, Select, Tabs, Spin, Empty, message,
  Button, Modal, Form, Input, InputNumber, Popconfirm, Space, Tooltip, Divider, Tag,
} from 'antd'
import {
  SafetyOutlined, TableOutlined, PlusOutlined,
  DeleteOutlined, EditOutlined, LinkOutlined, ReloadOutlined,
} from '@ant-design/icons'
import type { DataNode } from 'antd/es/tree'
import RiskHeatmap from '../../components/RiskHeatmap'
import FactorDecomposition from '../../components/FactorDecomposition'
import SpecificRiskHistogram from '../../components/SpecificRiskHistogram'
import {
  getRiskDatabases, getRiskTables,
  createRiskDatabase, updateRiskDatabase, deleteRiskDatabase, testRiskDatabase,
  getCovariance, getCorrelation, getFactorDecomposition, getTableDates,
  RISK_DB_TYPES,
} from '../../services/risk'
import type {
  RiskDBInfo, RiskTableInfo, MatrixData, FactorDecompositionData,
} from '../../services/risk'

/** 来源标签 */
function SourceTag({ source }: { source?: string }) {
  if (source === 'settings') return <Tag color="green" style={{ fontSize: 10, lineHeight: '16px', marginLeft: 4 }}>settings</Tag>
  if (source === 'neo4j') return <Tag color="default" style={{ fontSize: 10, lineHeight: '16px', marginLeft: 4 }}>neo4j</Tag>
  return null
}

type ViewMode = 'covariance' | 'correlation' | 'factor-decomp' | 'specific-risk'

/** 风险库表单数据 */
interface RiskDBFormValues {
  name: string
  db_type: string
  main_dir: string
  description: string
}

function RiskManager() {
  // ─── 数据状态 ─────────────────────────────────────────────
  const [databases, setDatabases] = useState<RiskDBInfo[]>([])
  const [loadingDBs, setLoadingDBs] = useState(false)
  const [treeData, setTreeData] = useState<DataNode[]>([])
  const [selectedDb, setSelectedDb] = useState<string | null>(null)
  const [selectedTable, setSelectedTable] = useState<string | null>(null)
  const [selectedDt, setSelectedDt] = useState<string | null>(null)
  const [tableDates, setTableDates] = useState<string[]>([])
  const [isFactorRT, setIsFactorRT] = useState(false)

  // ─── 视图状态 ─────────────────────────────────────────────
  const [viewMode, setViewMode] = useState<ViewMode>('covariance')
  const [covData, setCovData] = useState<MatrixData | null>(null)
  const [corrData, setCorrData] = useState<MatrixData | null>(null)
  const [factorDecompData, setFactorDecompData] = useState<FactorDecompositionData | null>(null)
  const [limit, setLimit] = useState(100)
  const [loadingData, setLoadingData] = useState(false)

  // ─── 弹窗状态 ─────────────────────────────────────────────
  const [modalOpen, setModalOpen] = useState(false)
  const [editingDb, setEditingDb] = useState<RiskDBInfo | null>(null)
  const [form] = Form.useForm<RiskDBFormValues>()

  // ─── 加载风险库列表 ───────────────────────────────────────
  const loadDatabases = useCallback(async () => {
    setLoadingDBs(true)
    try {
      const dbs = await getRiskDatabases() as unknown as RiskDBInfo[]
      setDatabases(dbs)
      const nodes: DataNode[] = dbs.map((db) => ({
        key: db.id,
        title: <span>{db.name}<SourceTag source={db.source} /></span>,
        icon: <SafetyOutlined />,
        isLeaf: false,
        children: [],
      }))
      setTreeData(nodes)
    } catch {
      message.error('加载风险库列表失败')
    } finally {
      setLoadingDBs(false)
    }
  }, [])

  useEffect(() => { loadDatabases() }, [loadDatabases])

  // ─── 树节点展开：加载表列表 ───────────────────────────────
  const onLoadData = useCallback(async (node: DataNode) => {
    const { key } = node
    if (String(key).startsWith('table:')) return
    try {
      const tables = await getRiskTables(key as string) as unknown as RiskTableInfo[]
      const children: DataNode[] = tables.map((t) => ({
        key: `table:${key}:${t.name}`,
        title: t.name,
        icon: <TableOutlined />,
        isLeaf: true,
        data: { dbId: key, tableName: t.name, isFactorRT: t.is_factor_rt },
      }))
      setTreeData((prev) =>
        prev.map((n) => (n.key === key ? { ...n, children } : n))
      )
    } catch {
      message.error('加载风险表列表失败')
    }
  }, [])

  // ─── 树节点选中 ───────────────────────────────────────────
  const onSelect = useCallback(async (keys: React.Key[]) => {
    if (keys.length === 0) return
    const key = String(keys[0])

    if (!key.startsWith('table:')) {
      setSelectedDb(key as string)
      setSelectedTable(null)
      setSelectedDt(null)
      setCovData(null); setCorrData(null); setFactorDecompData(null)
      return
    }

    const parts = key.split(':')
    const dbId = parts[1]
    const tableName = parts.slice(2).join(':')

    setSelectedDb(dbId)
    setSelectedTable(tableName)
    setSelectedDt(null)
    setCovData(null); setCorrData(null); setFactorDecompData(null)

    try {
      const dts = await getTableDates(dbId, tableName) as unknown as string[]
      setTableDates(dts)
      if (dts.length > 0) setSelectedDt(dts[dts.length - 1])
    } catch {
      message.error('加载时点列表失败')
    }
  }, [])

  // ─── 加载选中数据 ─────────────────────────────────────────
  const loadData = useCallback(async () => {
    if (!selectedDb || !selectedTable || !selectedDt) return
    setLoadingData(true)
    try {
      if (viewMode === 'covariance') {
        const d = await getCovariance(selectedDb, selectedTable, selectedDt, limit) as unknown as MatrixData
        setCovData(d)
      } else if (viewMode === 'correlation') {
        const d = await getCorrelation(selectedDb, selectedTable, selectedDt, limit) as unknown as MatrixData
        setCorrData(d)
      } else {
        const d = await getFactorDecomposition(selectedDb, selectedTable, selectedDt, limit) as unknown as FactorDecompositionData
        setFactorDecompData(d)
      }
    } catch {
      message.error('加载数据失败')
    } finally {
      setLoadingData(false)
    }
  }, [selectedDb, selectedTable, selectedDt, viewMode, limit])

  useEffect(() => {
    if (selectedDb && selectedTable && selectedDt) loadData()
  }, [selectedDb, selectedTable, selectedDt, viewMode, loadData])

  useEffect(() => {
    if (!selectedDb || !selectedTable) { setIsFactorRT(false); return }
    const node = findTableNode(treeData, selectedDb, selectedTable)
    setIsFactorRT((node as any)?.data?.isFactorRT || false)
  }, [selectedDb, selectedTable, treeData])

  // ─── 风险库 CRUD 操作 ─────────────────────────────────────
  const handleAdd = () => {
    setEditingDb(null)
    form.resetFields()
    form.setFieldsValue({ db_type: 'HDF5RDB' })
    setModalOpen(true)
  }

  const handleEdit = (db: RiskDBInfo) => {
    setEditingDb(db)
    form.setFieldsValue({
      name: db.name,
      db_type: db.db_type,
      main_dir: (db as any).args?.MainDir || '',
      description: db.description || '',
    })
    setModalOpen(true)
  }

  const handleDelete = async (dbId: string) => {
    try {
      await deleteRiskDatabase(dbId)
      message.success('删除成功')
      if (selectedDb === dbId) {
        setSelectedDb(null); setSelectedTable(null); setSelectedDt(null)
      }
      loadDatabases()
    } catch {
      message.error('删除失败')
    }
  }

  const handleTest = async (dbId: string) => {
    try {
      const result = await testRiskDatabase(dbId) as unknown as { success: boolean; message: string }
      if (result.success) message.success(result.message)
      else message.error(result.message)
    } catch {
      message.error('测试连接失败')
    }
  }

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields()
      const args = { MainDir: values.main_dir }
      if (editingDb) {
        await updateRiskDatabase(editingDb.id, {
          name: values.name,
          args,
          description: values.description || '',
        })
        message.success('更新成功')
      } else {
        await createRiskDatabase({
          name: values.name,
          db_type: values.db_type,
          args,
          description: values.description || '',
        })
        message.success('创建成功')
      }
      setModalOpen(false)
      loadDatabases()
    } catch {
      // 表单验证失败
    }
  }

  // ─── 渲染 ─────────────────────────────────────────────────
  const canLoadData = selectedDb && selectedTable && selectedDt

  const viewTabs = [
    { key: 'covariance' as ViewMode, label: '协方差矩阵' },
    { key: 'correlation' as ViewMode, label: '相关系数矩阵' },
    ...(isFactorRT
      ? [
          { key: 'factor-decomp' as ViewMode, label: '因子风险' },
          { key: 'specific-risk' as ViewMode, label: '特异性风险分布' },
        ]
      : []),
  ]

  return (
    <>
      <Row gutter={16} style={{ height: '100%' }}>
        {/* 左侧：风险库树 + 管理工具栏 */}
        <Col span={6}>
          <Card
            size="small"
            title="风险库"
            extra={
              <Tooltip title="添加风险库">
                <Button type="primary" size="small" icon={<PlusOutlined />} onClick={handleAdd}>
                  添加
                </Button>
              </Tooltip>
            }
            style={{ height: '100%', overflow: 'auto' }}
          >
            {loadingDBs ? (
              <Spin />
            ) : treeData.length === 0 ? (
              <Empty
                description="暂无风险库，点击上方「添加」创建"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : (
              <>
                <Tree.DirectoryTree
                  showIcon
                  loadData={onLoadData}
                  onSelect={onSelect}
                  treeData={treeData}
                  selectedKeys={
                    selectedTable
                      ? [`table:${selectedDb}:${selectedTable}`]
                      : selectedDb ? [selectedDb] : []
                  }
                />
                {/* 选中风险库的管理操作 */}
                {selectedDb && !selectedTable && (
                  <div style={{ marginTop: 8 }}>
                    <Divider style={{ margin: '8px 0' }} />
                    {(() => {
                      const selectedDbInfo = databases.find((d) => d.id === selectedDb)
                      const isSettingsSource = selectedDbInfo?.source === 'settings'
                      return (
                    <Space size={4}>
                      <Tooltip title={isSettingsSource ? 'settings 来源不可编辑' : '编辑'}>
                        <Button
                          size="small" icon={<EditOutlined />}
                          disabled={isSettingsSource}
                          onClick={() => {
                            const db = databases.find((d) => d.id === selectedDb)
                            if (db) handleEdit(db)
                          }}
                        />
                      </Tooltip>
                      <Tooltip title="测试连接">
                        <Button
                          size="small" icon={<LinkOutlined />}
                          onClick={() => handleTest(selectedDb)}
                        />
                      </Tooltip>
                      <Tooltip title="刷新">
                        <Button
                          size="small" icon={<ReloadOutlined />}
                          onClick={loadDatabases}
                        />
                      </Tooltip>
                      <Tooltip title={isSettingsSource ? 'settings 来源不可删除' : '删除'}>
                        <Button size="small" danger icon={<DeleteOutlined />}
                          disabled={isSettingsSource}
                          onClick={() => handleDelete(selectedDb)}
                        />
                      </Tooltip>
                    </Space>
                      )
                    })()}
                  </div>
                )}
              </>
            )}
          </Card>
        </Col>

        {/* 右侧：内容区 */}
        <Col span={18}>
          <Card
            size="small"
            title={
              selectedTable
                ? `${selectedTable} - 风险分析`
                : '选择风险表查看分析'
            }
            extra={
              canLoadData ? (
                <Space size={8}>
                  <Select
                    value={selectedDt || undefined}
                    onChange={setSelectedDt}
                    placeholder="选择时点"
                    style={{ width: 220 }}
                    options={tableDates.map((d) => ({ value: d, label: d }))}
                    showSearch
                  />
                  <InputNumber
                    min={1}
                    max={5000}
                    value={limit}
                    onChange={(v) => { if (v) setLimit(v) }}
                    addonBefore="前"
                    addonAfter="只"
                    style={{ width: 130 }}
                  />
                </Space>
              ) : null
            }
            style={{ height: '100%', overflow: 'auto' }}
          >
            {!canLoadData ? (
              <Empty description="请在左侧选择一张风险表" style={{ marginTop: 60 }} />
            ) : (
              <>
                <Tabs
                  activeKey={viewMode}
                  onChange={(key) => setViewMode(key as ViewMode)}
                  items={viewTabs.map((tab) => ({ key: tab.key, label: tab.label }))}
                />
                <div style={{ minHeight: 400 }}>
                  {viewMode === 'covariance' && (
                    <RiskHeatmap
                      data={covData} loading={loadingData}
                      title={`${selectedTable} - 协方差矩阵 (${selectedDt})`}
                      colorscale="RdBu"
                    />
                  )}
                  {viewMode === 'correlation' && (
                    <RiskHeatmap
                      data={corrData} loading={loadingData}
                      title={`${selectedTable} - 相关系数矩阵 (${selectedDt})`}
                      colorscale="RdBu"
                    />
                  )}
                  {viewMode === 'factor-decomp' && (
                    <FactorDecomposition data={factorDecompData} loading={loadingData} />
                  )}
                  {viewMode === 'specific-risk' && (
                    <SpecificRiskHistogram data={factorDecompData} loading={loadingData} />
                  )}
                </div>
              </>
            )}
          </Card>
        </Col>
      </Row>

      {/* 添加/编辑风险库弹窗 */}
      <Modal
        title={editingDb ? '编辑风险库' : '添加风险库'}
        open={modalOpen}
        onOk={handleModalOk}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如：Barra 风险库" />
          </Form.Item>
          <Form.Item name="db_type" label="类型" rules={[{ required: true }]}>
            <Select
              options={RISK_DB_TYPES.map((t) => ({
                value: t.value,
                label: `${t.label} — ${t.desc}`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="main_dir"
            label="数据目录 (MainDir)"
            rules={[{ required: true, message: '请输入 HDF5 文件目录路径' }]}
            tooltip="存放 .hdf5 风险数据文件的路径"
          >
            <Input placeholder="如：D:/Data/RiskData" />
          </Form.Item>
          <Form.Item name="description" label="备注">
            <Input.TextArea rows={2} placeholder="可选备注信息" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

function findTableNode(nodes: DataNode[], dbId: string, tableName: string): DataNode | null {
  for (const node of nodes) {
    if (node.key === dbId && node.children) {
      const targetKey = `table:${dbId}:${tableName}`
      for (const child of node.children) {
        if (child.key === targetKey) return child
      }
    }
  }
  return null
}

export default RiskManager
