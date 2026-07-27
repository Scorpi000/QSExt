import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Row,
  Col,
  Card,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Select,
  message,
  Popconfirm,
  Tag,
  Spin,
  DatePicker,
  InputNumber,
  Descriptions,
  Divider,
  Switch,
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  SyncOutlined,
  ReloadOutlined,
  EditOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  Connection,
  ConnectionCreate,
  ConnectionUpdate,
  DB_TYPES,
  getConnections,
  createConnection,
  updateConnection,
  deleteConnection,
} from '../../services/connection'
import {
  FactorInfo,
  FactorTable,
  getFactorData,
  FactorData,
  FactorStats,
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
import FactorTree from '../../components/FactorTree/FactorTree'
import DataTable from '../../components/DataTable/DataTable'
import MetadataEditor from '../../components/MetadataEditor/MetadataEditor'

const { RangePicker } = DatePicker

function DataManager() {
  // 连接列表
  const [connections, setConnections] = useState<Connection[]>([])
  const [loadingConnections, setLoadingConnections] = useState(false)

  // 当前选中的连接
  const [activeConnection, setActiveConnection] = useState<Connection | null>(null)

  // 因子树刷新 key（重连后递增以强制重新挂载）
  const [treeRefreshKey, setTreeRefreshKey] = useState(0)

  // 当前选中的表（点击表节点时设置）
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

  // 新建连接对话框
  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [createForm] = Form.useForm()

  // 编辑连接对话框
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [editingConnection, setEditingConnection] = useState<Connection | null>(null)
  const [editForm] = Form.useForm()

  // 加载连接列表
  const loadConnections = useCallback(async () => {
    setLoadingConnections(true)
    try {
      const data = await getConnections()
      setConnections(data as unknown as Connection[])
    } catch {
      // 错误已在 api 拦截器中处理
    } finally {
      setLoadingConnections(false)
    }
  }, [])

  useEffect(() => {
    loadConnections()
  }, [loadConnections])

  // 创建连接
  const handleCreate = async (values: ConnectionCreate) => {
    try {
      await createConnection(values)
      message.success('创建成功')
      setCreateModalVisible(false)
      createForm.resetFields()
      loadConnections()
    } catch {
      // 错误已在 api 拦截器中处理
    }
  }

  // 删除连接
  const handleDelete = async (id: string) => {
    try {
      await deleteConnection(id)
      message.success('删除成功')
      if (activeConnection?.id === id) {
        setActiveConnection(null)
        setSelectedFactor(null)
        setSelectedTable(null)
        setFactorData(null)
      }
      loadConnections()
    } catch {
      // 错误已在 api 拦截器中处理
    }
  }

  // 打开编辑连接对话框
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

  // 编辑连接
  const handleEdit = async (values: ConnectionUpdate) => {
    if (!editingConnection) return
    try {
      await updateConnection(editingConnection.id, values)
      message.success('更新成功')
      setEditModalVisible(false)
      editForm.resetFields()
      setEditingConnection(null)
      loadConnections()
    } catch {
      // 错误已在 api 拦截器中处理
    }
  }

  // 重连因子库
  const handleReconnect = async (id: string) => {
    try {
      await reconnectFactorDB(id)
      message.success('重连成功')
      if (activeConnection?.id === id) {
        setSelectedFactor(null)
        setSelectedTable(null)
        setFactorData(null)
        setTreeRefreshKey((k) => k + 1)
      }
    } catch {
      // 错误已在 api 拦截器中处理
    }
  }

  // 选择表节点
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
    } catch {
      // 错误已在 api 拦截器中处理
    }
  }

  // 选择因子
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
    } catch {
      // 错误已在 api 拦截器中处理
    } finally {
      setLoadingData(false)
    }
  }

  // 刷新数据
  const handleRefreshData = () => {
    if (selectedFactor) {
      handleFactorSelect(selectedFactor)
    }
  }

  // ---------- 表管理回调 ----------

  const handleTableRename = async (oldName: string, newName: string) => {
    if (!activeConnection) return
    await renameTable(activeConnection.id, oldName, newName)
    message.success(`表 "${oldName}" 已重命名为 "${newName}"`)
    setSelectedTable(null)
    setTreeRefreshKey((k) => k + 1)
  }

  const handleTableDelete = async (tableNames: string[]) => {
    if (!activeConnection) return
    await deleteTables(activeConnection.id, tableNames)
    message.success(`已删除 ${tableNames.length} 个表`)
    setSelectedTable(null)
    setSelectedFactor(null)
    setFactorData(null)
    setTreeRefreshKey((k) => k + 1)
  }

  const handleTableMetadataSave = async (metadata: Record<string, any>) => {
    if (!activeConnection || !selectedTable) return
    await updateTableMetadata(activeConnection.id, selectedTable.name, metadata)
    // 刷新元数据显示
    const tMeta = await getTableMetadata(activeConnection.id, selectedTable.name)
    setTableMeta(tMeta as unknown as Record<string, any>)
  }

  // ---------- 因子管理回调 ----------

  const handleFactorRename = async (tableName: string, oldName: string, newName: string) => {
    if (!activeConnection) return
    await renameFactor(activeConnection.id, tableName, oldName, newName)
    message.success(`因子 "${oldName}" 已重命名为 "${newName}"`)
    // 如果当前选中的是被重命名的因子，更新选中状态
    if (selectedFactor?.name === oldName && selectedFactor?.table_name === tableName) {
      setSelectedFactor(null)
      setFactorData(null)
    }
  }

  const handleFactorDelete = async (tableName: string, factorNames: string[]) => {
    if (!activeConnection) return
    await deleteFactors(activeConnection.id, tableName, factorNames)
    message.success(`已删除 ${factorNames.length} 个因子`)
    if (selectedFactor?.table_name === tableName && factorNames.includes(selectedFactor.name)) {
      setSelectedFactor(null)
      setFactorData(null)
    }
  }

  const handleFactorMetadataSave = async (metadata: Record<string, any>) => {
    if (!activeConnection || !selectedFactor) return
    await updateFactorMetadata(
      activeConnection.id,
      selectedFactor.table_name,
      selectedFactor.name,
      metadata
    )
    // 刷新元数据显示
    const fMeta = await getFactorMetadata(
      activeConnection.id,
      selectedFactor.table_name,
      selectedFactor.name
    )
    setFactorMeta(fMeta as unknown as Record<string, any>)
  }

  // 过滤缺失值后的数据
  const displayData = useMemo(() => {
    if (!factorData) return { data: {}, columns: [], index: [] }
    if (!filterNaN) return factorData

    const valueCols = factorData.columns.filter(
      (c) => c !== 'datetime' && c !== 'code'
    )

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

  const getDbTypeColor = (dbType: string) => {
    const colors: Record<string, string> = {
      HDF5DB: 'blue',
      SQLDB: 'cyan',
      ClickHouseDB: 'orange',
      MongoDB: 'lime',
      Neo4jDB: 'purple',
    }
    return colors[dbType] || 'default'
  }

  // 右侧面板标题
  const rightPanelTitle = selectedFactor
    ? `${selectedFactor.table_name} / ${selectedFactor.name}`
    : selectedTable
      ? `${selectedTable.name} / 表信息`
      : '数据预览'

  return (
    <Row gutter={16} style={{ height: 'calc(100vh - 160px)' }}>
      {/* 左侧：连接列表 */}
      <Col span={6}>
        <Card
          title="因子库连接"
          size="small"
          extra={
            <Space size="small">
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={loadConnections}
              />
              <Button
                type="primary"
                size="small"
                icon={<PlusOutlined />}
                onClick={() => setCreateModalVisible(true)}
              >
                新建
              </Button>
            </Space>
          }
          bodyStyle={{ padding: 0, height: 'calc(100% - 56px)', overflow: 'auto' }}
        >
          <Spin spinning={loadingConnections}>
            {connections.length > 0 ? (
              <div>
                {connections.map((conn) => (
                  <div
                    key={conn.id}
                    style={{
                      padding: '12px 16px',
                      borderBottom: '1px solid #f0f0f0',
                      cursor: 'pointer',
                      background:
                        activeConnection?.id === conn.id ? '#e6f7ff' : 'transparent',
                    }}
                    onClick={() => {
                      setActiveConnection(conn)
                      setSelectedFactor(null)
                      setSelectedTable(null)
                      setFactorData(null)
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <Space>
                        <span style={{ fontWeight: 500 }}>{conn.name}</span>
                        <Tag color={getDbTypeColor(conn.db_type)}>{conn.db_type}</Tag>
                      </Space>
                      <Space size="small">
                        <Button
                          type="text"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={(e) => {
                            e.stopPropagation()
                            handleEditOpen(conn)
                          }}
                        />
                        <Button
                          type="text"
                          size="small"
                          icon={<SyncOutlined />}
                          onClick={(e) => {
                            e.stopPropagation()
                            handleReconnect(conn.id)
                          }}
                        />
                        <Popconfirm
                          title="确定删除此连接？"
                          onConfirm={(e) => {
                            e?.stopPropagation()
                            handleDelete(conn.id)
                          }}
                        >
                          <Button
                            type="text"
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={(e) => e.stopPropagation()}
                          />
                        </Popconfirm>
                      </Space>
                    </div>
                    {conn.description && (
                      <div style={{ color: '#999', fontSize: 12, marginTop: 4 }}>
                        {conn.description}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ padding: '40px 16px', textAlign: 'center', color: '#999' }}>
                暂无连接，点击"新建"添加
              </div>
            )}

            {activeConnection && Object.keys(activeConnection.args).length > 0 && (
              <div style={{ padding: '0 16px 12px' }}>
                <Divider style={{ margin: '0 0 8px' }} />
                <Descriptions
                  title="连接参数"
                  column={1}
                  size="small"
                  labelStyle={{ color: '#666', fontSize: 12, padding: '2px 8px 2px 0' }}
                  contentStyle={{ fontSize: 12, padding: '2px 0' }}
                >
                  {Object.entries(activeConnection.args).map(([key, value]) => (
                    <Descriptions.Item key={key} label={key}>
                      {String(value)}
                    </Descriptions.Item>
                  ))}
                </Descriptions>
              </div>
            )}
          </Spin>
        </Card>
      </Col>

      {/* 中间：因子树 */}
      <Col span={6} style={{ height: '100%' }}>
        <Card
          title="因子浏览"
          size="small"
          style={{ height: '100%' }}
          bodyStyle={{ padding: 0, height: 'calc(100% - 46px)', overflow: 'hidden' }}
        >
          {activeConnection ? (
            <FactorTree
              key={`${activeConnection.id}-${treeRefreshKey}`}
              connectionId={activeConnection.id}
              connectionName={activeConnection.name}
              onFactorSelect={handleFactorSelect}
              onTableSelect={handleTableSelect}
              onTableRename={handleTableRename}
              onTableDelete={handleTableDelete}
              onFactorRename={handleFactorRename}
              onFactorDelete={handleFactorDelete}
            />
          ) : (
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100%',
                color: '#999',
              }}
            >
              请先选择一个连接
            </div>
          )}
        </Card>
      </Col>

      {/* 右侧：数据预览 / 表信息 */}
      <Col span={12} style={{ height: '100%' }}>
        <Card
          title={rightPanelTitle}
          size="small"
          style={{ height: '100%' }}
          bodyStyle={{ padding: 0, height: 'calc(100% - 46px)', overflow: 'auto' }}
        >
          {selectedFactor ? (
            <Spin spinning={loadingData}>
              {/* 操作栏 */}
              <div style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0' }}>
                <Space size="small" wrap>
                  <Select
                    mode="tags"
                    size="small"
                    placeholder="筛选 code"
                    value={selectedIds}
                    onChange={setSelectedIds}
                    style={{ minWidth: 150, maxWidth: 250 }}
                    maxTagCount="responsive"
                    allowClear
                  />
                  <RangePicker
                    size="small"
                    value={dateRange}
                    onChange={(dates) =>
                      setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])
                    }
                  />
                  <InputNumber
                    size="small"
                    value={limit}
                    onChange={(v) => setLimit(v || 1000)}
                    min={1}
                    max={10000}
                    style={{ width: 90 }}
                    addonBefore="行数"
                  />
                  <Space size={4}>
                    <Switch
                      size="small"
                      checked={filterNaN}
                      onChange={setFilterNaN}
                    />
                    <span style={{ fontSize: 12 }}>过滤缺失值</span>
                  </Space>
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={handleRefreshData}
                  >
                    刷新
                  </Button>
                </Space>
              </div>
              {/* 因子统计信息 */}
              {factorStats && (
                <div
                  style={{
                    padding: '6px 16px',
                    borderBottom: '1px solid #f0f0f0',
                    background: '#fafafa',
                  }}
                >
                  <Space size="middle" wrap style={{ fontSize: 12 }}>
                    <span>
                      <span style={{ color: '#888' }}>起止ID：</span>
                      <Tag>{factorStats.first_id ?? '-'}</Tag>
                      <span style={{ color: '#ccc' }}>~</span>
                      <Tag>{factorStats.last_id ?? '-'}</Tag>
                      <span style={{ color: '#888' }}>数量：</span>
                      <Tag color="blue">{factorStats.id_count}</Tag>
                    </span>
                    <span>
                      <span style={{ color: '#888' }}>起止时间：</span>
                      <Tag>{factorStats.first_dt ?? '-'}</Tag>
                      <span style={{ color: '#ccc' }}>~</span>
                      <Tag>{factorStats.last_dt ?? '-'}</Tag>
                      <span style={{ color: '#888' }}>数量：</span>
                      <Tag color="green">{factorStats.dt_count}</Tag>
                    </span>
                  </Space>
                </div>
              )}
              {/* 因子元数据 */}
              <div style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0' }}>
                <MetadataEditor
                  title="因子信息"
                  metadata={factorMeta || {}}
                  onSave={handleFactorMetadataSave}
                />
              </div>
              <DataTable
                data={displayData.data}
                columns={displayData.columns}
                index={displayData.index}
                loading={loadingData}
              />
            </Spin>
          ) : selectedTable ? (
            <div style={{ padding: '16px' }}>
              <Descriptions
                title="表基本信息"
                column={2}
                size="small"
                labelStyle={{ color: '#666', fontSize: 12 }}
                contentStyle={{ fontSize: 12 }}
              >
                <Descriptions.Item label="表名">{selectedTable.name}</Descriptions.Item>
                <Descriptions.Item label="因子数量">
                  {selectedTable.factor_count ?? '-'}
                </Descriptions.Item>
                {selectedTable.description && (
                  <Descriptions.Item label="描述">{selectedTable.description}</Descriptions.Item>
                )}
              </Descriptions>
              <Divider style={{ margin: '12px 0' }} />
              <MetadataEditor
                title="因子表信息"
                metadata={tableMeta || {}}
                onSave={handleTableMetadataSave}
              />
            </div>
          ) : (
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100%',
                color: '#999',
              }}
            >
              请从左侧因子树中选择一个表或因子
            </div>
          )}
        </Card>
      </Col>

      {/* 新建连接对话框 */}
      <Modal
        title="新建连接"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false)
          createForm.resetFields()
        }}
        onOk={() => createForm.submit()}
        width={600}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreate}
          initialValues={{
            db_type: 'HDF5DB',
            args: {},
          }}
        >
          <Form.Item
            name="name"
            label="连接名称"
            rules={[{ required: true, message: '请输入连接名称' }]}
          >
            <Input placeholder="例如：本地 HDF5 数据库" />
          </Form.Item>

          <Form.Item
            name="db_type"
            label="数据库类型"
            rules={[{ required: true, message: '请选择数据库类型' }]}
          >
            <Select>
              {DB_TYPES.map((type) => (
                <Select.Option key={type.value} value={type.value}>
                  {type.icon} {type.label}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选描述" />
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) =>
              prevValues.db_type !== currentValues.db_type
            }
          >
            {({ getFieldValue }) => {
              const dbType = getFieldValue('db_type')
              if (dbType === 'HDF5DB') {
                return (
                  <Form.Item
                    name={['args', 'MainDir']}
                    label="MainDir（主目录路径）"
                    rules={[{ required: true, message: '请输入主目录路径' }]}
                  >
                    <Input placeholder="例如：D:/Data/HDF5DB" />
                  </Form.Item>
                )
              }
              if (dbType === 'SQLDB') {
                return (
                  <>
                    <Form.Item
                      name={['args', 'DBType']}
                      label="DBType（数据库类型）"
                      initialValue="MySQL"
                      rules={[{ required: true }]}
                    >
                      <Select>
                        <Select.Option value="MySQL">MySQL</Select.Option>
                        <Select.Option value="PostgreSQL">PostgreSQL</Select.Option>
                        <Select.Option value="SQL Server">SQL Server</Select.Option>
                        <Select.Option value="Oracle">Oracle</Select.Option>
                      </Select>
                    </Form.Item>
                    <Form.Item
                      name={['args', 'IPAddr']}
                      label="IPAddr（主机地址）"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="127.0.0.1" />
                    </Form.Item>
                    <Form.Item name={['args', 'Port']} label="Port（端口）" initialValue={3306}>
                      <InputNumber style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['args', 'User']} label="User（用户名）" initialValue="root">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['args', 'Pwd']} label="Pwd（密码）">
                      <Input.Password />
                    </Form.Item>
                    <Form.Item
                      name={['args', 'DBName']}
                      label="DBName（数据库名）"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="Scorpion" />
                    </Form.Item>
                  </>
                )
              }
              if (dbType === 'ClickHouseDB') {
                return (
                  <>
                    <Form.Item
                      name={['args', 'IPAddr']}
                      label="IPAddr（主机地址）"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="127.0.0.1" />
                    </Form.Item>
                    <Form.Item name={['args', 'Port']} label="Port（端口）" initialValue={9000}>
                      <InputNumber style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['args', 'User']} label="User（用户名）" initialValue="default">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['args', 'Pwd']} label="Pwd（密码）">
                      <Input.Password />
                    </Form.Item>
                    <Form.Item
                      name={['args', 'DBName']}
                      label="DBName（数据库名）"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="default" />
                    </Form.Item>
                  </>
                )
              }
              if (dbType === 'MongoDB') {
                return (
                  <>
                    <Form.Item
                      name={['args', 'IPAddr']}
                      label="IPAddr（主机地址）"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="127.0.0.1" />
                    </Form.Item>
                    <Form.Item name={['args', 'Port']} label="Port（端口）" initialValue={27017}>
                      <InputNumber style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['args', 'User']} label="User（用户名）" initialValue="root">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['args', 'Pwd']} label="Pwd（密码）">
                      <Input.Password />
                    </Form.Item>
                    <Form.Item
                      name={['args', 'DBName']}
                      label="DBName（数据库名）"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="default" />
                    </Form.Item>
                  </>
                )
              }
              if (dbType === 'Neo4jDB') {
                return (
                  <>
                    <Form.Item
                      name={['args', 'IPAddr']}
                      label="IPAddr（主机地址）"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="127.0.0.1" />
                    </Form.Item>
                    <Form.Item name={['args', 'Port']} label="Port（端口）" initialValue={7687}>
                      <InputNumber style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['args', 'User']} label="User（用户名）" initialValue="neo4j">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['args', 'Pwd']} label="Pwd（密码）">
                      <Input.Password />
                    </Form.Item>
                    <Form.Item
                      name={['args', 'DBName']}
                      label="DBName（数据库名）"
                      initialValue="neo4j"
                    >
                      <Input placeholder="neo4j" />
                    </Form.Item>
                  </>
                )
              }
              return null
            }}
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑连接对话框 */}
      <Modal
        title="编辑连接"
        open={editModalVisible}
        onCancel={() => {
          setEditModalVisible(false)
          editForm.resetFields()
          setEditingConnection(null)
        }}
        onOk={() => editForm.submit()}
        width={600}
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleEdit}
        >
          <Form.Item label="数据库类型">
            <Input value={editingConnection?.db_type} disabled />
          </Form.Item>

          <Form.Item
            name="name"
            label="连接名称"
            rules={[{ required: true, message: '请输入连接名称' }]}
          >
            <Input placeholder="例如：本地 HDF5 数据库" />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选描述" />
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) =>
              prevValues.name !== currentValues.name
            }
          >
            {({ getFieldValue }) => {
              const dbType = editingConnection?.db_type
              if (dbType === 'HDF5DB') {
                return (
                  <Form.Item
                    name={['args', 'MainDir']}
                    label="MainDir（主目录路径）"
                    rules={[{ required: true, message: '请输入主目录路径' }]}
                  >
                    <Input placeholder="例如：D:/Data/HDF5DB" />
                  </Form.Item>
                )
              }
              if (dbType === 'SQLDB') {
                return (
                  <>
                    <Form.Item name={['args', 'DBType']} label="DBType（数据库类型）" rules={[{ required: true }]}>
                      <Select>
                        <Select.Option value="MySQL">MySQL</Select.Option>
                        <Select.Option value="PostgreSQL">PostgreSQL</Select.Option>
                        <Select.Option value="SQL Server">SQL Server</Select.Option>
                        <Select.Option value="Oracle">Oracle</Select.Option>
                      </Select>
                    </Form.Item>
                    <Form.Item name={['args', 'IPAddr']} label="IPAddr（主机地址）" rules={[{ required: true }]}>
                      <Input placeholder="127.0.0.1" />
                    </Form.Item>
                    <Form.Item name={['args', 'Port']} label="Port（端口）">
                      <InputNumber style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['args', 'User']} label="User（用户名）">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['args', 'Pwd']} label="Pwd（密码）">
                      <Input.Password />
                    </Form.Item>
                    <Form.Item name={['args', 'DBName']} label="DBName（数据库名）" rules={[{ required: true }]}>
                      <Input placeholder="Scorpion" />
                    </Form.Item>
                  </>
                )
              }
              if (dbType === 'ClickHouseDB') {
                return (
                  <>
                    <Form.Item name={['args', 'IPAddr']} label="IPAddr（主机地址）" rules={[{ required: true }]}>
                      <Input placeholder="127.0.0.1" />
                    </Form.Item>
                    <Form.Item name={['args', 'Port']} label="Port（端口）">
                      <InputNumber style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['args', 'User']} label="User（用户名）">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['args', 'Pwd']} label="Pwd（密码）">
                      <Input.Password />
                    </Form.Item>
                    <Form.Item name={['args', 'DBName']} label="DBName（数据库名）" rules={[{ required: true }]}>
                      <Input placeholder="default" />
                    </Form.Item>
                  </>
                )
              }
              if (dbType === 'MongoDB') {
                return (
                  <>
                    <Form.Item name={['args', 'IPAddr']} label="IPAddr（主机地址）" rules={[{ required: true }]}>
                      <Input placeholder="127.0.0.1" />
                    </Form.Item>
                    <Form.Item name={['args', 'Port']} label="Port（端口）">
                      <InputNumber style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['args', 'User']} label="User（用户名）">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['args', 'Pwd']} label="Pwd（密码）">
                      <Input.Password />
                    </Form.Item>
                    <Form.Item name={['args', 'DBName']} label="DBName（数据库名）" rules={[{ required: true }]}>
                      <Input placeholder="default" />
                    </Form.Item>
                  </>
                )
              }
              if (dbType === 'Neo4jDB') {
                return (
                  <>
                    <Form.Item name={['args', 'IPAddr']} label="IPAddr（主机地址）" rules={[{ required: true }]}>
                      <Input placeholder="127.0.0.1" />
                    </Form.Item>
                    <Form.Item name={['args', 'Port']} label="Port（端口）">
                      <InputNumber style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['args', 'User']} label="User（用户名）">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['args', 'Pwd']} label="Pwd（密码）">
                      <Input.Password />
                    </Form.Item>
                    <Form.Item name={['args', 'DBName']} label="DBName（数据库名）">
                      <Input placeholder="neo4j" />
                    </Form.Item>
                  </>
                )
              }
              return null
            }}
          </Form.Item>
        </Form>
      </Modal>
    </Row>
  )
}

export default DataManager
